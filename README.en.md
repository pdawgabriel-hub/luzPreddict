<a id="top"></a>
# luzPreddict

[Español](./README.md) | **English**

### Hour-by-hour forecast of Spain's regulated electricity price (PVPC) for the next day, with tools to decide when to use power

[![CI](https://github.com/pdawgabriel-hub/luzPreddict/actions/workflows/ci.yml/badge.svg)](https://github.com/pdawgabriel-hub/luzPreddict/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![LightGBM](https://img.shields.io/badge/LightGBM-model-9ACD32)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-336791?logo=postgresql&logoColor=white)
![Vercel](https://img.shields.io/badge/Vercel-deployed-000000?logo=vercel&logoColor=white)
![License](https://img.shields.io/badge/License-Portfolio%20%2F%20Restricted%20use-red)
![Status](https://img.shields.io/badge/Status-In%20production-brightgreen)

**[Open the website](https://luzpreddict.vercel.app)** · **[API documentation](https://luzpreddict.vercel.app/docs)** · **[Technical guide (Spanish)](https://pdawgabriel-hub.github.io/luzPreddict/)** · **[Daily summary on ntfy](https://ntfy.sh/luzpreddict)**

![luzPreddict dashboard](docs/img/capturas/panel.png)

---

## Table of contents

- [Overview](#overview)
- [The problem it solves](#problem)
- [Architecture](#architecture)
- [The website](#the-website)
- [Screenshots](#screenshots)
- [Available links](#links)
- [The model and its results](#model)
- [Quality and tests](#quality)
- [Getting started](#getting-started)
- [Technical documentation](#technical-documentation)
- [Limitations and possible improvements](#limitations)
- [Data source](#data)
- [License](#license)
- [Author](#author)

---

<a id="overview"></a>
## Overview

**luzPreddict** forecasts the **PVPC** (Spain's regulated electricity price) for the next day,
hour by hour, with a machine learning model, and publishes it on a **website** and a **public
API**, along with tools to decide when to use electricity.

Every evening, when Red Eléctrica (REE, the Spanish grid operator) publishes the prices, an
automated job downloads the data, updates the forecast, measures how accurate the previous one
was and sends a summary to your phone. The website and the API only read those results, so they
respond instantly and the whole system **costs €0 per month**.

In short:

- **Real data** from REE since June 2021: hourly PVPC and the generation mix.
- **LightGBM model** whose error is **30% lower** than the best simple baseline, with a
  **likely range** for each hour and a daily evaluation against the actual price.
- **Website with nine sections:** dashboard, history, market, simulator, planner, bill, alerts,
  model evaluation and API documentation.
- **Public API** with no key, documented with OpenAPI, for home automation and scripts.
- **Full automation** with GitHub Actions: daily job, weekly retraining, migrations, CI,
  Lighthouse audits and Dependabot.

The project is a **technical portfolio piece** that covers the full life cycle of a data product:
ingestion, model, database, API, web, automation, deployment and documentation.

[Back to top](#top)

---

<a id="problem"></a>
## The problem it solves

The PVPC changes **every hour**, and the difference within a single day is large. On 14 October
2026, the cheapest hour cost **€0.052/kWh** and the most expensive one **€0.417/kWh**: eight times
as much. Running the washing machine at 20:00 cost **€0.39**; at 14:00, **€0.05**.

REE publishes the next day's prices around 20:15 (Madrid time). Until then, nobody knows what each
hour will cost tomorrow, and afterwards only one day is known. **luzPreddict brings that
information forward**: in the morning it already has a forecast for tomorrow, and in the evening,
one for the day after.

### Who it is for

| User | What they gain |
|---|---|
| **Households on the PVPC tariff** | Knowing when to run the washing machine, dishwasher or oven, and how much they save per year by moving them. The Simulator works it out: about €71 a year with the washing machine alone, at four loads a week. |
| **Electric cars and self-consumption** | Scheduling charging in the cheapest hours without exceeding the contracted power (Planner). |
| **Home automation and developers** | A keyless API so that Home Assistant or a script can switch appliances on at the best hours. |
| **Anyone unsure about their tariff** | Checking with their own data whether the PVPC or a fixed price suits them better (Bill). |
| **The power grid** | Cheap hours usually coincide with more wind and solar (Market page): shifting consumption towards them makes better use of renewables. |

### Possible business models

The project runs as a free service, but the same foundation supports several models:

- **Pay-per-volume API** for home automation integrators, energy managers and third-party apps.
  The free tier keeps its limit of 60 requests per minute.
- **White label or widget** for electricity retailers and tariff comparison sites, which can offer
  the forecast and the simulator to their customers.
- **Advanced alerts**, such as personal thresholds or a "charge your car now" alert, for users who
  want more than the daily summary.
- **A service for small businesses** with shiftable consumption (laundries, bakeries, cold rooms,
  electric fleets) that plan their production around the forecast price.

[Back to top](#top)

---

<a id="architecture"></a>
## Architecture

![luzPreddict architecture (labels in Spanish)](docs/img/arquitectura.svg)

The system separates **the heavy part** (computing) from **what is served** (website and API):

1. **REE**, the source. Red Eléctrica's public API provides the hourly PVPC and the generation
   mix, with no key.
2. **GitHub Actions**, the computing. Every evening the **daily job** downloads the new data,
   forecasts the next day with the stored model and measures the error of previous forecasts. It
   runs again two hours later in case REE is late. Every Sunday the model is **retrained**. Database
   migrations are applied automatically when they reach `main`.
3. **Neon (PostgreSQL)**, the data. It stores prices, generation, forecasts with their interval,
   daily errors and the trained model itself. **Upstash (Redis)** counts requests for the API rate
   limit.
4. **Vercel**, the service. It serves the **website** (React) and the **API** (FastAPI) from the
   same domain and from its CDN, which caches every response until the next update: most visits
   reach neither the API nor the database.
5. **ntfy**, the notifications. When tomorrow's prices arrive, it sends the summary to a public
   topic, and if a workflow fails, it alerts through a private topic.

**Why this design:** the API does not load pandas or the model (it only reads rows), which makes it
fast and free on Vercel; the computing takes a few minutes a day, which GitHub Actions provides at
no cost; and everything runs in **Frankfurt**, so every query stays in Europe. Details and
decisions are in the [technical guide](https://pdawgabriel-hub.github.io/luzPreddict/arquitectura/)
(in Spanish).

[Back to top](#top)

---

<a id="the-website"></a>
## The website

| Section | What it is for |
|---|---|
| **Panel** (dashboard) | Current price, today's average and cheapest hour, tomorrow's forecast with its likely range, the next hours and the best hours to use power |
| **Histórico** (history) | Trends over 7, 14 or 30 days, average price by hour, weekdays versus weekends and a heat map |
| **Mercado** (market) | Generation mix and how each technology affects the price |
| **Simulador** (simulator) | What it costs to run an appliance at a given hour and how much you save by moving it |
| **Planificador** (planner) | Spreads several appliances over the cheap hours without exceeding the contracted power |
| **Factura** (bill) | Whether the PVPC or a fixed price suits you, with your consumption and 30 days of real prices |
| **Alertas** (alerts) | Personal threshold stored in the browser and subscription to the daily summary |
| **Modelo** (model) | How accurate the forecast is: error by hour and by day, and against the baselines |
| **API** | Public API documentation with live requests and `curl` commands |

The website is in Spanish and needs no user guide: each section explains what it shows. It is
accessible (charts with data tables for screen readers, keyboard navigation) and works on mobile.

[Back to top](#top)

---

<a id="screenshots"></a>
## Screenshots

| History | Market |
|---|---|
| ![History](docs/img/capturas/historico.png) | ![Market](docs/img/capturas/mercado.png) |

| Simulator | Planner |
|---|---|
| ![Simulator](docs/img/capturas/simulador.png) | ![Planner](docs/img/capturas/planificador.png) |

| Bill | Alerts |
|---|---|
| ![Bill](docs/img/capturas/factura.png) | ![Alerts](docs/img/capturas/alertas.png) |

| Model | API |
|---|---|
| ![Model](docs/img/capturas/modelo.png) | ![API](docs/img/capturas/api.png) |

| Dashboard on mobile | Simulator on mobile |
|---|---|
| <img src="docs/img/capturas/movil-panel.png" alt="Dashboard on mobile" width="300"> | <img src="docs/img/capturas/movil-simulador.png" alt="Simulator on mobile" width="300"> |

*Screenshots of the live website, 14 October 2026.*

[Back to top](#top)

---

<a id="links"></a>
## Available links

### Website

| Link | What you see |
|---|---|
| [luzpreddict.vercel.app](https://luzpreddict.vercel.app) | Dashboard: current price, today's prices and tomorrow's forecast |
| [/historico](https://luzpreddict.vercel.app/historico) | Price history |
| [/mercado](https://luzpreddict.vercel.app/mercado) | Generation mix and its relationship with the price |
| [/simulador](https://luzpreddict.vercel.app/simulador) | Cost and savings simulator per appliance |
| [/planificador](https://luzpreddict.vercel.app/planificador) | Day planner |
| [/factura](https://luzpreddict.vercel.app/factura) | PVPC versus a fixed price |
| [/alertas](https://luzpreddict.vercel.app/alertas) | Alerts and subscription to the daily summary |
| [/modelo](https://luzpreddict.vercel.app/modelo) | Model evaluation |
| [/desarrolladores](https://luzpreddict.vercel.app/desarrolladores) | API documentation inside the website |

### Public API (JSON, no key)

| Link | What it is for |
|---|---|
| [/docs](https://luzpreddict.vercel.app/docs) | Interactive documentation (Swagger): try each endpoint from the browser |
| [/openapi.json](https://luzpreddict.vercel.app/openapi.json) | OpenAPI schema, to generate clients |
| [/health](https://luzpreddict.vercel.app/health) | Service status: latest price, latest forecast and model in use |
| [/v1/prices](https://luzpreddict.vercel.app/v1/prices) | Today's PVPC (or a day or range with `date`, `start` and `end`) |
| [/v1/forecast](https://luzpreddict.vercel.app/v1/forecast) | Latest forecast, with the likely range of each hour |
| [/v1/best-hours?hours=3](https://luzpreddict.vercel.app/v1/best-hours?hours=3) | Today's cheapest 3 consecutive hours |
| [/v1/history](https://luzpreddict.vercel.app/v1/history) | Summary of the last 30 days |
| [/v1/market](https://luzpreddict.vercel.app/v1/market) | Generation mix over the last 30 days |

### Project

| Link | What it is for |
|---|---|
| [Technical guide](https://pdawgabriel-hub.github.io/luzPreddict/) | How everything is built, chapter by chapter (in Spanish) |
| [Daily summary on ntfy](https://ntfy.sh/luzpreddict) | Tomorrow's prices on your phone, no account needed (ntfy app, topic `luzpreddict`) |
| [GitHub Actions](https://github.com/pdawgabriel-hub/luzPreddict/actions) | Runs of the daily job, retraining, CI and Lighthouse |

[Back to top](#top)

---

<a id="model"></a>
## The model and its results

A **LightGBM** model with 17 features: calendar (hour, day of the week, public holidays, 2.0TD
tariff period) and prices from previous days (the same hour 1, 2, 3 and 7 days earlier, plus
recent averages, minimums and maximums). It never uses the day it predicts: the tests check this by
altering future prices.

It is evaluated as in production (*walk-forward*): each day is predicted using only earlier days.
The parameters were chosen on 2024 data and then measured on a different period:

| Mean absolute error (€/MWh) | LightGBM | Yesterday's price | 7-day average |
|---|---|---|---|
| Validation (2024) | **15.6** | 26.5 | — |
| Test (from 2025) | **≈ 16** | ≈ 28.5 | ≈ 28.9 |
| Last 90 days, when trained on 13/10/2026 | **22.9** | 33.8 | 32.9 |

Besides the forecast, the model gives a **likely range** for each hour, using two quantile
regression models: over the test period, the actual price fell inside it in **79.5%** of the hours.
If the model cannot be used, the website publishes "yesterday's price" and says so. The details are
in the [technical guide](https://pdawgabriel-hub.github.io/luzPreddict/modelo/) (in Spanish).

[Back to top](#top)

---

<a id="quality"></a>
## Quality and tests

- **608 Python tests** (pytest) against a real PostgreSQL test database: ingestion with real REE
  responses, 23- and 25-hour days, future leakage in the model, idempotent writes, migrations,
  several consecutive days of the daily job and every API endpoint.
- **218 web tests** (Vitest and Testing Library) with mandatory minimum coverage: 98% of statements
  and 87% of branches.
- **CI on every push:** ruff, oxlint, TypeScript, tests, build and up-to-date API types.
- **Lighthouse after every deployment:** accessibility **100** on the audited pages and performance
  between 83 and 91 on mobile.
- Weekly **Dependabot** and **pre-commit** before every commit.

[Back to top](#top)

---

<a id="getting-started"></a>
## Getting started

### With Docker

No need to install Python or Node: just Docker with Compose.

```bash
make docker-up     # database, API and website
make docker-seed   # first time only: REE history, training and tomorrow's forecast
make docker-down   # stops everything (data is kept)
```

The website runs at http://localhost:8080, with the API on the same paths as in production.

### For development

Requirements: Python 3.12, Node 22 and PostgreSQL 16.

```bash
python3 -m venv venv
make install          # dependencies and pre-commit hooks
cp .env.example .env  # DATABASE_URL and TEST_DATABASE_URL
make migrate backfill train pipeline
make dev              # API on :8000 and website on :5173
```

`make help` lists every command. The website also runs without a backend, using sample data:
`make web-mocks`.

[Back to top](#top)

---

<a id="technical-documentation"></a>
## Technical documentation

The **[technical guide](https://pdawgabriel-hub.github.io/luzPreddict/)** (in Spanish) explains the
project in detail, chapter by chapter:

- **Architecture:** the components, a day's cycle and why each service was chosen.
- **Data:** the REE API, ingestion, daylight saving changes, cleaning and the database.
- **Model:** features, baselines, LightGBM, backtesting and calibrated prediction intervals.
- **Automation:** the GitHub Actions workflows, notifications and secrets.
- **API:** endpoints, uniform errors, CDN caching and rate limiting.
- **Web:** code organisation, accessible charts and sample data.
- **Quality, deployment and operations:** tests, Lighthouse, Vercel, Neon and what to do if
  something breaks.
- **Local development and decisions:** how to run it and what was ruled out, and why.

Its source lives in [`docs/`](docs/) and is published automatically on every change.

[Back to top](#top)

---

<a id="limitations"></a>
## Limitations and possible improvements

- **Mainland system only.** REE's public API only publishes the mainland PVPC. The Canary Islands,
  the Balearic Islands, Ceuta and Melilla would need ESIOS, REE's other API, which requires a
  token.
- **No demand, wind or solar forecasts as features**, for the same reason: the public API does not
  provide them for the next day. This is the improvement with the most potential for the model.
- **The public ntfy topic** can be used by anyone who knows its name: reserving a topic is a paid
  feature.
- **The forecast is indicative** and does not guarantee the final price. In very volatile periods,
  the likely range is right less than 8 times out of 10; the Model page shows the actual figure.

[Back to top](#top)

---

<a id="data"></a>
## Data source

PVPC prices and the generation mix come from the
[public API of Red Eléctrica (REE)](https://www.ree.es/es/apidatos) and are subject to its own
terms of use.

[Back to top](#top)

---

<a id="license"></a>
## License

This project is published as a **personal portfolio piece** under a restricted-use license. In
detail:

- You may **view, clone and run** the code for **learning, technical assessment or portfolio
  review** purposes (for example, as part of a hiring process or to study the project's
  architecture).
- You may **modify the code for personal, non-commercial use**, always crediting the original
  author.
- **Commercial use is not allowed**, in whole or in part (including deploying it as a product or
  service, reselling it or integrating it into third-party commercial solutions), without the
  author's express permission.
- **The only holder of the right to exploit the project commercially is the original author**,
  [Gabriel](https://github.com/pdawgabriel-hub).

The full legal text is in [`LICENSE.en.md`](./LICENSE.en.md) (Spanish version:
[`LICENSE.md`](./LICENSE.md)).

[Back to top](#top)

---

<a id="author"></a>
## Author

Developed by **Gabriel Iborra Vicente** as a portfolio project, to demonstrate the full
development of a data product: from ingestion and the machine learning model to a public API, an
accessible website, automation and cost-free cloud deployment.

[Back to top](#top)
