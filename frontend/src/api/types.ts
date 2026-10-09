// Tipos de las respuestas y peticiones de la API, generados de su esquema OpenAPI
// (make api-types). No se escriben a mano: si la API cambia, se regeneran.
import type { components } from './schema'

type Schemas = components['schemas']

export type Health = Schemas['Health']
export type Prices = Schemas['Prices']
export type PriceHour = Schemas['PriceHour']
export type TariffPeriod = Schemas['TariffPeriod']
export type Forecast = Schemas['Forecast']
export type BestHours = Schemas['BestHours']
export type History = Schemas['History']
export type DaySummary = Schemas['DaySummary']
export type Market = Schemas['Market']
export type ModelReport = Schemas['ModelReport']
export type Catalog = Schemas['Catalog']
export type ApplianceOut = Schemas['ApplianceOut']
export type SimulateRequest = Schemas['SimulateRequest']
export type Simulation = Schemas['Simulation']
export type PlanRequest = Schemas['PlanRequest']
export type Plan = Schemas['Plan']
export type BillRequest = Schemas['BillRequest']
export type Bill = Schemas['Bill']
export type Source = Schemas['Source']
export type ErrorResponse = Schemas['ErrorResponse']
export type FieldError = Schemas['FieldError']
