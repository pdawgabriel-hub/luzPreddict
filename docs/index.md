# luzPreddict · Guía técnica

**luzPreddict** prevé el precio de la luz del mercado regulado español (PVPC) para el día
siguiente, hora a hora, y lo publica en una web y en una API pública. Esta guía explica
cómo está construido: de dónde salen los datos, cómo se entrena y se evalúa el modelo,
cómo se automatiza todo cada día y cómo se despliega sin coste.

<div class="grid" markdown>

[Abrir la web](https://luzpreddict.vercel.app){ .md-button .md-button--primary }
[Documentación de la API](https://luzpreddict.vercel.app/docs){ .md-button }
[Código en GitHub](https://github.com/pdawgabriel-hub/luzPreddict){ .md-button }

</div>

![Panel de luzPreddict: precio de ahora, media de hoy, hora más barata y previsión de mañana](img/capturas/panel.png)

## El proyecto en cifras

| | |
|---|---|
| Datos | PVPC horario y mix de generación de Red Eléctrica (REE) desde junio de 2021: unas 47.000 horas |
| Modelo | LightGBM con 17 variables, entrenado con los dos últimos años y reentrenado cada semana |
| Error | Un 30 % menos que la mejor referencia simple ("precio de ayer" o "media de 7 días") |
| Rango probable | Intervalo en el que cae el precio real 8 de cada 10 horas en el periodo de prueba |
| Automatización | Seis workflows de GitHub Actions: tarea diaria, reentrenamiento, carga, migraciones, CI y Lighthouse |
| Calidad | 608 tests de Python y 214 de la web, con cobertura mínima obligatoria en el CI |
| Coste | 0 € al mes: GitHub Actions, Neon, Vercel, Upstash y ntfy en sus planes gratuitos |

## Cómo leer esta guía

Los capítulos siguen el recorrido de los datos, de la fuente al usuario:

1. **[Arquitectura](arquitectura.md):** las piezas, cómo se comunican y por qué se eligieron.
2. **[Datos](datos.md):** la API de REE, la ingesta, la limpieza y la base de datos.
3. **[Modelo](modelo.md):** variables, referencias, LightGBM, backtest e intervalos de predicción.
4. **[Automatización](automatizacion.md):** los workflows de GitHub Actions y los avisos internos por ntfy.
5. **[API](api.md):** endpoints, errores, caché y límite de peticiones.
6. **[Web](web.md):** las páginas, el cliente de la API, los datos de ejemplo y las gráficas.
7. **[Calidad](calidad.md):** tests, cobertura, pre-commit y Lighthouse.
8. **[Despliegue y operación](despliegue.md):** Vercel, Neon, Upstash y qué hacer si algo falla.
9. **[Desarrollo local](desarrollo-local.md):** cómo ponerlo en marcha en tu máquina, con o sin Docker.
10. **[Decisiones y mejoras](decisiones.md):** lo que se descartó, por qué, y lo que queda por hacer.

!!! info "Convenciones"
    Los precios se guardan y se sirven en **€/MWh** (1 €/MWh = 0,001 €/kWh); la web los
    muestra en €/kWh. Las horas se guardan en **UTC** y se sirven en **hora de Madrid**. Las
    rutas de ficheros son relativas a la raíz del repositorio.
