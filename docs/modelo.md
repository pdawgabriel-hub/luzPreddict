# Modelo

## El problema

Cada tarde hay que prever el PVPC de las 24 horas (23 o 25 en los cambios de hora) del
primer día que REE aún no ha publicado. En ese momento **solo se conocen los precios hasta el
día anterior**: cualquier variable que mire el día que se predice haría trampa.

## Las referencias que hay que batir

Un modelo solo tiene sentido si mejora algo simple. Hay dos referencias
(`src/models/baselines.py`):

| Referencia | Previsión de cada hora |
|---|---|
| **Precio de ayer** | El precio de esa misma hora el día anterior |
| **Media 7 días** | La media de esa hora en los siete días anteriores |

Si a una hora le falta el dato principal (la 2:00 del día siguiente al cambio a horario de
verano no tiene "precio de ayer"), se usa el siguiente de la lista, para que siempre haya
previsión. "Precio de ayer" es además el **respaldo** de producción: si el modelo no se puede
usar, se publica esta referencia y se indica el motivo.

## Variables

`src/processing/features.py` construye 17 variables. Todas las de precio usan **solo días
anteriores** al predicho.

| Grupo | Variables |
|---|---|
| Calendario | `hour`, `dayofweek`, `month`, `dayofyear`, `is_weekend`, `is_holiday` (festivos nacionales), `tariff_period` (valle, llano o punta de la 2.0TD) |
| Precio de días anteriores | `price_lag_1d`, `price_lag_2d`, `price_lag_3d`, `price_lag_7d` (la misma hora hace 1, 2, 3 y 7 días) |
| Resumen de días anteriores | `same_hour_mean_7d`, `prev_day_mean`, `prev_day_min`, `prev_day_max`, `prev_day_last`, `prev_7d_mean` |

!!! warning "Sin fugas del futuro"
    `tests/test_features_leakage.py` y `tests/test_backtest.py` lo comprueban de forma
    directa: cambian los precios **desde** el día D (por ejemplo, multiplicándolos por 3) y
    verifican que ninguna variable ni previsión **hasta** D cambia.

## LightGBM

`src/models/lightgbm_model.py`. Se eligió LightGBM porque capta interacciones no lineales
(la forma del día cambia con la estación y con los fines de semana), entrena en segundos con
decenas de miles de filas y no necesita escalar variables.

| Parámetro | Valor | Por qué |
|---|---|---|
| Objetivo | `l1` (error absoluto) | Es la métrica que se mide, y es menos sensible a picos extremos |
| Ventana | últimos 730 días | Dos años: suficiente historia sin arrastrar regímenes de precios muy distintos |
| Árboles | 500, tasa de aprendizaje 0,03 | Elegidos en el periodo de validación |
| `num_leaves` / `min_child_samples` | 31 / 50 | Árboles moderados, hojas con datos suficientes |
| `subsample` / `colsample_bytree` | 0,8 / 0,8 | Algo de aleatoriedad para generalizar mejor |

## Cómo se evalúa: backtest *walk-forward*

`src/models/evaluate.py` simula la producción día a día: para cada día D, el modelo solo ve
los precios anteriores a D, y las horas de D se le pasan con el precio vacío. Se reentrena al
principio y cada 30 días. Las métricas se miden en €/MWh:

- **MAE:** error absoluto medio, la métrica principal.
- **RMSE:** castiga más los errores grandes.
- **Sesgo:** error medio con signo (negativo: la previsión se queda corta).

No se usa el error porcentual (MAPE): con precios cercanos a cero o negativos, que se dan en
las horas solares, se dispara y deja de tener sentido.

Para no elegir la configuración mirando el resultado final, hay **dos periodos**:

| Periodo | Uso | LightGBM | Precio de ayer | Media 7 días |
|---|---|---|---|---|
| **Validación** (2024) | Elegir parámetros y percentiles | 15,6 | 26,5 | — |
| **Prueba** (desde 2025) | Medir la configuración elegida | ≈ 16 | ≈ 28,5 | ≈ 28,9 |
| **Producción** (últimos 90 días al entrenar el 13/10/2026) | Métricas guardadas con el modelo | 22,9 | 33,8 | 32,9 |

Error absoluto medio en €/MWh. En producción LightGBM se equivoca un **30 % menos** que la
mejor referencia. El error es mayor en los últimos meses porque los precios han sido más
volátiles, y afecta a todos los modelos por igual.

![Página Modelo: error medio, comparación con las referencias y previsión frente a precio real](img/capturas/modelo.png)

## Intervalos de predicción

Además de la previsión, el modelo da un **rango probable** para cada hora. Son dos modelos
LightGBM más, con objetivo de **regresión por cuantiles**, que estiman los percentiles bajo
y alto del precio. Los tres se entrenan con los mismos datos y parámetros; si en alguna hora
se cruzan, se ordenan para que siempre se cumpla `lower ≤ previsión ≤ upper`.

**Calibración.** Con los percentiles 10 y 90, en teoría un intervalo del 80 %, el precio
real solo caía dentro el 68 % de las horas de validación: los cuantiles se quedan cortos
cuando los precios cambian de régimen. Se eligieron los percentiles **5 y 95** en el periodo
de validación, igual que el resto de parámetros:

| Percentiles | Cobertura en validación (2024) | Anchura media |
|---|---|---|
| 10 y 90 | 68 % | 39 €/MWh |
| **5 y 95** | **80 %** | 53 €/MWh |
| 3 y 97 | 87 % | 66 €/MWh |

En el periodo de prueba, que no se usó para elegir, los percentiles 5 y 95 dieron una
cobertura del **79,5 %** con 55 €/MWh de anchura media. Por eso la web anuncia "8 de cada 10
horas". La cobertura real de cada modelo se mide al entrenarlo y se publica en la página
Modelo, aunque salga peor que la anunciada (fue del 70 % en los 90 días previos al
13/10/2026, un periodo muy volátil).

## Registro de modelos

`src/models/registry.py` serializa el modelo con joblib junto con sus metadatos: versión,
fechas, variables, parámetros, métricas del backtest, versiones de las librerías y
`FORMAT_VERSION`.

- Al cargarlo se comprueba que el formato y las **variables** coinciden con las del código
  actual. Si no, se lanza un error claro ("vuelve a entrenar") y la previsión usa el
  respaldo.
- Se guarda en la tabla `model_artifact`; la previsión usa siempre el más reciente.
- Cada modelo ocupa unos 1,6 MB. Al entrenar, se borra el **binario** de los modelos
  anteriores salvo los cuatro últimos. Los metadatos se conservan, porque la API los usa para
  las previsiones antiguas.

## Previsión y respaldo

`predict_day()` (`src/models/predict.py`) siempre devuelve una previsión. Si el modelo no
existe, es incompatible, falla o devuelve valores vacíos o infinitos, o horas distintas a las
del día, publica "precio de ayer" sin intervalo y guarda el motivo en `fallback_reason`. La
web y la API lo muestran, y el error diario lo registra con el nombre del modelo que de verdad
se usó.

## Comandos

```bash
make backtest   # compara LightGBM con las referencias desde 2025 (unos minutos)
make train      # entrena con el histórico de la base de datos y lo guarda en ella
make predict    # muestra la previsión del siguiente día sin guardarla
```

Los notebooks de `notebooks/` recogen el análisis exploratorio de los precios y del mix, y
la comparación de modelos que llevó a esta configuración.
