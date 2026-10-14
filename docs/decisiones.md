# Decisiones y mejoras

## Lo que se descartó, y por qué

**Previsiones de demanda, eólica y solar como variables del modelo.** Mejorarían la previsión,
porque el precio depende mucho de cuánta renovable habrá mañana, pero la API pública de REE no
sirve para esto:

- No tiene previsiones de eólica ni de solar.
- La de demanda no cubre el día siguiente entero a la hora de la tarea diaria.
- Su histórico parece la última revisión, no la que había la víspera. Entrenar con ella haría
  trampa en el backtest.

La fuente correcta es ESIOS, la otra API de REE, que necesita un token.

**Canarias, Baleares, Ceuta y Melilla.** La API pública solo publica el PVPC peninsular; el de
cada sistema está en ESIOS. Además, los periodos de la tarifa de Ceuta y Melilla tienen otros
horarios. Las páginas de precios de la web indican que son los del sistema peninsular
("PVPC · Península").

**Cuentas de usuario y correos.** Las alertas personales se guardan en el navegador y el resumen
va por ntfy. Sin cuentas no hay datos personales que proteger ni contraseñas que gestionar.

**Un servidor propio.** El cálculo dura minutos al día, así que GitHub Actions es suficiente y
gratuito. La API, como función serverless con caché en la CDN, no necesita estar encendida.

**`api/index.py` como función de Vercel.** Era el plan inicial, pero Vercel detecta FastAPI y su
preset tiene prioridad sobre las funciones de `/api`. Se usan sus *Services*, la forma que
recomienda ahora para juntar una web y un backend de Python en el mismo proyecto.

## Limitaciones conocidas

- **El tema público de ntfy** lo puede usar cualquiera que conozca su nombre, también para
  publicar: reservar un tema es de pago. Es el precio de no tener cuentas.
- **La cobertura del intervalo** baja en épocas de precios muy volátiles: los cuantiles aprenden
  del pasado reciente. Se mide y se publica en la página Modelo.
- **La página Modelo necesita días con previsión guardada** para comparar con el precio real. Se
  llena sola cada día desde el despliegue.
- **Las cabeceras `X-RateLimit-*` de una respuesta servida desde la CDN** son las de la primera
  petición, no las de quien la recibe. El límite real no se ve afectado.

## Mejoras posibles

| Mejora | Qué haría falta |
|---|---|
| Variables de previsión de demanda, eólica y solar | Token de ESIOS y validar en el backtest que mejora |
| PVPC de Canarias, Baleares, Ceuta y Melilla | Token de ESIOS, región en las tablas y la API, y selector en la web |
| Intervalos que se adapten a la volatilidad reciente | Calibración conformal sobre las últimas semanas |
| Menos desplazamiento al cargar el Simulador | Reservar el espacio de los resultados mientras llegan |
| Avisos por umbral sin abrir la web | Un tema de ntfy por umbral, generado en el navegador |
