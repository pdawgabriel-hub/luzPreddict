# Calidad

## Tests de Python

**608 tests** con pytest (`tests/`), contra una base PostgreSQL de pruebas real, no simulada.

| Qué se prueba | Ejemplos |
|---|---|
| Ingesta | Respuestas reales de REE guardadas como *fixtures*, tramos, reintentos y días de 23 y 25 horas |
| Variables y backtest | Que ninguna variable ni previsión mira el día que predice (alterando los precios futuros) |
| Modelo | Entrenamiento, intervalo ordenado y con cobertura razonable, registro, compatibilidad y respaldo |
| Base de datos | Escrituras idempotentes, fechas sin zona rechazadas y migraciones idénticas a los modelos |
| Pipeline | Varios días de la tarea diaria seguidos, REE caído, modelo corrupto, resumen de ntfy una sola vez |
| Servicios | Mejores horas, simulador, planificador, tarifa y resumen, con casos límite |
| API | Cada endpoint, errores uniformes, caché, límite de peticiones y contrato del OpenAPI |

**Seguridad de los tests.** Los tests vacían su base de datos, así que solo se ejecutan si
`TEST_DATABASE_URL` es distinta de la de trabajo y su nombre termina en `_test`. Si no, se niegan
a arrancar.

## Tests de la web

**214 tests** con Vitest y Testing Library, en jsdom. Prueban las páginas como las usaría una
persona (por rol y nombre accesible, con clics y teclado) sobre los datos de ejemplo, y las
funciones de `lib/` con valores calculados a mano.

El CI exige una **cobertura mínima**: 95 % de sentencias, funciones y líneas, y 85 % de ramas.
Ahora está en el 98 % de sentencias y el 87 % de ramas.

## Revisión estática

| Herramienta | Qué revisa | Dónde |
|---|---|---|
| **ruff** | Errores, estilo, orden de imports y formato de Python | pre-commit y CI |
| **oxlint** | Errores de JavaScript/TypeScript, con los avisos tratados como errores | CI |
| **TypeScript** | Tipos de toda la web, incluidos los generados de la API | CI |
| **pre-commit** | Espacios finales, fin de fichero, YAML, TOML y ficheros grandes | antes de cada commit |

## Lighthouse

El workflow **Lighthouse** audita la web publicada después de cada despliegue a producción:
cuatro páginas en móvil emulado, tres cargas por página (mediana).

| Página | Rendimiento | Accesibilidad | Buenas prácticas | SEO |
|---|---|---|---|---|
| Panel | 91 | 100 | 96 | 91 |
| Histórico | 86 | 100 | 96 | 91 |
| Modelo | 88 | 100 | 96 | 91 |
| Simulador | 83 | 100 | 100 | 91 |

*Medición del 14/10/2026, antes de añadir `robots.txt`, que corrige el aviso de SEO.*

Umbrales (`.github/lighthouserc.json`): la **accesibilidad por debajo de 95 hace fallar** la
ejecución; rendimiento (80), buenas prácticas y SEO (90) solo avisan, porque el rendimiento
varía mucho en las máquinas de GitHub.

!!! note "El 404 de buenas prácticas"
    El Panel pide el precio publicado de mañana antes de recurrir a la previsión. Hasta que
    REE lo publica, la API responde 404 y el navegador lo anota como error, lo que resta unos
    puntos de "buenas prácticas". Es intencionado: es la respuesta correcta de la API pública.

## Comandos

```bash
make lint           # ruff + oxlint + TypeScript
make test           # pytest + Vitest
make web-coverage   # Vitest con cobertura (falla si baja de los mínimos)
```
