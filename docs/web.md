# Web

React 19 con TypeScript y Vite (`frontend/`). Es una aplicación de página única servida como
ficheros estáticos desde la CDN de Vercel. Llama a la API en el mismo dominio, así que no
necesita CORS.

## Las páginas

| Página | Ruta | Para qué sirve |
|---|---|---|
| **Panel** | `/` | Precio de ahora, media y hora más barata de hoy, previsión de mañana, las próximas horas y las mejores horas para consumir. Compara hoy con mañana y muestra el rango probable de la previsión. |
| **Histórico** | `/historico` | Evolución de 7, 14 o 30 días, precio medio por hora del día, laborables frente a fines de semana y mapa de calor hora × día. |
| **Mercado** | `/mercado` | Mix de generación y relación entre renovables y precio: cuanta más eólica y solar, menos ciclo combinado y precios más bajos. |
| **Simulador** | `/simulador` | Cuánto cuesta poner un aparato a una hora y cuánto se ahorra moviéndolo a la mejor. |
| **Planificador** | `/planificador` | Reparte varios aparatos en las horas baratas sin superar la potencia contratada. |
| **Factura** | `/factura` | Si con tu consumo te compensa el PVPC o un precio fijo, con los precios reales de los últimos 30 días. |
| **Alertas** | `/alertas` | Umbral personal guardado en el navegador: qué horas de mañana lo cumplen y cuántas veces habría saltado en los últimos 30 días. No envía nada a ningún servidor. |
| **Modelo** | `/modelo` | Cuánto acierta la previsión frente al precio real y frente a las referencias, por hora y por día. |
| **API** | `/desarrolladores` | Documentación de la API pública con peticiones reales y comandos `curl` para copiar. |

<div class="grid" markdown>

![Simulador](img/capturas/simulador.png)
![Planificador](img/capturas/planificador.png)

</div>

## Organización del código

```text
frontend/src/
├── api/          # cliente HTTP, tipos generados del OpenAPI y carga de un día (publicado o previsto)
├── mocks/        # datos de ejemplo deterministas (VITE_USE_MOCKS=1)
├── hooks/        # useApi, useNow, useWidth, usePageTitle
├── lib/          # cálculos y formatos sin React: fechas, precios, escalas, histórico, modelo…
├── components/   # cabecera, tarjetas, controles, estados de carga y error
│   └── charts/   # barras por hora, líneas con banda y mapa de calor, en SVG propio
├── pages/        # una por ruta
└── styles/       # tokens de diseño (colores, tipografía, espacios) y estilos globales
```

**`useApi`** carga datos con cancelación: si cambia la fecha antes de que llegue la respuesta,
la petición anterior se aborta y su respuesta se descarta. Expone `loading`, `error` y `success`
y un `reload` para el botón de reintentar.

**`loadDay`** (`api/days.ts`) resuelve "los precios de un día": si REE ya publicó el día entero,
usa el precio publicado; si no, la previsión con su rango; y si tampoco hay previsión, lo dice.

**Los cálculos van en `lib/`**, como funciones puras con sus tests: tercios de barato, medio y
caro, correlación entre renovables y precio, cobertura del rango probable, formatos en
castellano ("0,088 €/kWh", "12 %", "1 día" o "3 días")… Las páginas solo componen.

## Gráficas accesibles

Las gráficas están hechas a mano en SVG (`components/charts/`), sin librerías:

- Cada una tiene un resumen para lectores de pantalla (`role="img"` y `aria-label`) y una
  **tabla de datos accesible** con los mismos valores.
- Las barras por hora se pueden recorrer con el **teclado** (flechas, Inicio y Fin) y con el
  ratón.
- Los colores no son la única pista: hay leyendas, valores y patrones (línea discontinua para la
  previsión).

## Datos de ejemplo

`VITE_USE_MOCKS=1` (`make web-mocks`) hace que el cliente responda con datos de ejemplo
deterministas en lugar de llamar a la API, para trabajar en la web sin backend.
`VITE_MOCK_SCENARIO` simula casos difíciles de reproducir con la API real:

| Escenario | Qué simula |
|---|---|
| `stale` | Datos desactualizados: aparece el aviso de que faltan precios |
| `error` | Errores de la API: aparecen los estados de error con reintento |
| `slow` | Respuestas lentas: aparecen los estados de carga |

Los datos de ejemplo no llegan al build de producción: el CI lo comprueba buscando uno de sus
textos en los ficheros generados.

## Estilos

CSS Modules con **tokens** en `styles/tokens.css` (colores, tipografía, espacios y radios). Una
paleta azul para el precio publicado y otra ámbar para la previsión, para que nunca se confundan.
Tipografía Space Grotesk para títulos, IBM Plex Sans para el texto e IBM Plex Mono para las
cifras, servidas con fontsource desde el propio dominio. Diseño pensado para móvil: en pantallas
estrechas el menú se pliega y las tarjetas se apilan.

![Panel en el móvil](img/capturas/movil-panel.png){ width="320" }
