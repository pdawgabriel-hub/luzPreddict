"""Peticiones y respuestas de /api/tools (uso interno de la web).

Las horas de las peticiones son horas de reloj en Madrid (0-23; 24 es la
medianoche siguiente). Los costes van en € y los precios en €/kWh, que es como
los lee alguien en su factura.
"""

import datetime as dt
from typing import Annotated, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from src.api.schemas.common import Source, pvpc_source
from src.services.simulator import APPLIANCES
from src.services.tariffs import PROFILES
from src.utils.calendar import TariffPeriod

HourOfDay = Annotated[int, Field(ge=0, le=23)]
EndHour = Annotated[int, Field(ge=1, le=24)]

MAX_TASKS = 20


# --- Aparatos ---


class CustomAppliance(BaseModel):
    """Un aparato que no está en el catálogo."""

    name: str = Field(min_length=1, max_length=60)
    power_kw: float = Field(gt=0, le=15, description="Potencia media durante el uso, en kW")
    hours: int = Field(ge=1, le=24, description="Duración de un uso, en horas")


def _check_appliance(value: str | CustomAppliance | None) -> str | CustomAppliance | None:
    if isinstance(value, str) and value not in APPLIANCES:
        raise ValueError(f"Aparato desconocido: {value}. Opciones: {', '.join(APPLIANCES)}")
    return value


class ApplianceOut(BaseModel):
    id: str
    name: str
    power_kw: float
    hours: int
    kwh: float = Field(description="Consumo de un uso")


class HourRange(BaseModel):
    """Franja en la que se puede usar el aparato."""

    from_hour: HourOfDay = Field(default=0, description="Primera hora en la que puede empezar")
    to_hour: EndHour = Field(default=24, description="Hora a la que debe haber terminado")

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.to_hour <= self.from_hour:
            raise ValueError("to_hour debe ser posterior a from_hour")
        return self


class PriceWindow(BaseModel):
    start: dt.datetime
    end: dt.datetime
    avg_price: float = Field(description="Precio medio de la ventana, en €/kWh")


# --- Catálogo ---


class ProfileOut(BaseModel):
    id: str
    name: str
    description: str


class Catalog(BaseModel):
    appliances: list[ApplianceOut]
    profiles: list[ProfileOut] = Field(description="Perfiles de consumo horario para la factura")
    contracted_powers_kw: list[float] = Field(description="Potencias contratadas habituales")
    base_load_kw: float = Field(description="Consumo base que el planificador suma a todas las horas")


# --- Simulador ---


class SimulateRequest(HourRange):
    date: dt.date | None = Field(default=None, description="Día (por defecto, el último publicado)")
    appliance: str | CustomAppliance | None = Field(
        default=None, description="Id del catálogo o aparato propio; sin él, se comparan todos los del catálogo"
    )
    start_hour: HourOfDay = Field(default=20, description="Hora a la que se usaría sin planificar")
    uses_per_week: float = Field(default=1, ge=0, le=21)

    _check = field_validator("appliance")(_check_appliance)


class SimulationOut(BaseModel):
    appliance: ApplianceOut
    start: dt.datetime = Field(description="Inicio a la hora habitual (adelantado si no cabe en el día)")
    end: dt.datetime
    cost: float = Field(description="€ a la hora habitual")
    best: PriceWindow | None = Field(description="Mejor ventana dentro de la franja")
    best_cost: float | None = Field(description="€ en la mejor ventana")
    saving_per_use: float | None
    yearly_saving: float | None = Field(description="€ al año con `uses_per_week` usos por semana")


class Simulation(BaseModel):
    date: dt.date
    uses_per_week: float
    simulations: list[SimulationOut]
    total_yearly_saving: float = Field(description="Suma del ahorro anual de todos los aparatos simulados")
    source: Source = pvpc_source()


# --- Planificador ---


class TaskIn(HourRange):
    id: str = Field(min_length=1, max_length=40, description="Identificador único de la tarea")
    appliance: str | CustomAppliance
    habitual_hour: HourOfDay = Field(description="Hora a la que se haría sin planificar")
    fixed: bool = Field(default=False, description="Si no se puede mover de su hora habitual")

    _check = field_validator("appliance")(_check_appliance)


class PlanRequest(BaseModel):
    date: dt.date | None = Field(default=None, description="Día (por defecto, el último publicado)")
    power_kw: float = Field(default=4.6, gt=0, le=15, description="Potencia contratada, en kW")
    tasks: list[TaskIn] = Field(min_length=1, max_length=MAX_TASKS)


class PlannedTaskOut(BaseModel):
    id: str
    appliance: ApplianceOut
    fixed: bool
    placed: bool = Field(description="False si no cabe en ningún sitio sin superar la potencia")
    start: dt.datetime | None
    end: dt.datetime | None
    cost: float | None
    habitual_start: dt.datetime
    habitual_cost: float
    saving: float | None


class LoadHour(BaseModel):
    datetime: dt.datetime
    price: float = Field(description="€/kWh")
    kw: float = Field(description="Potencia con el plan")
    habitual_kw: float = Field(description="Potencia a las horas habituales")


class Plan(BaseModel):
    date: dt.date
    power_kw: float
    base_load_kw: float
    tasks: list[PlannedTaskOut]
    plan_cost: float = Field(description="€ de las tareas colocadas")
    habitual_cost: float = Field(description="€ de todas las tareas a su hora habitual")
    saving: float = Field(description="€ ahorrados en las tareas colocadas")
    unplaced: list[str] = Field(description="Tareas que no caben")
    habitual_overloads: list[dt.datetime] = Field(description="Horas en que el horario habitual supera la potencia")
    hours: list[LoadHour]
    source: Source = pvpc_source()


# --- Factura ---


class BillRequest(BaseModel):
    start: dt.date | None = Field(default=None, description="Primer día (por defecto, hace 30 días)")
    end: dt.date | None = Field(default=None, description="Último día, incluido")
    total_kwh: float = Field(gt=0, le=100_000, description="Consumo del periodo, en kWh")
    profile: str = Field(default="tipico", description="Perfil de consumo horario")
    fixed_price: float | None = Field(default=None, gt=0, le=2, description="Precio fijo a comparar, en €/kWh")
    shift_fraction: float = Field(default=0, ge=0, le=1, description="Parte del consumo que se movería a horas baratas")

    @field_validator("profile")
    @classmethod
    def _check_profile(cls, value: str) -> str:
        if value not in PROFILES:
            raise ValueError(f"Perfil desconocido: {value}. Opciones: {', '.join(PROFILES)}")
        return value


class PeriodOut(BaseModel):
    period: TariffPeriod
    kwh: float
    cost: float
    avg_price: float | None = Field(description="€/kWh medio pagado en el tramo")


class DayCostOut(BaseModel):
    date: dt.date
    kwh: float
    pvpc_cost: float
    fixed_cost: float | None


class Bill(BaseModel):
    start: dt.date
    end: dt.date
    profile: str
    total_kwh: float
    shift_fraction: float
    pvpc_cost: float = Field(description="€ con PVPC")
    pvpc_shifted_cost: float = Field(description="€ con PVPC moviendo `shift_fraction` del consumo")
    fixed_cost: float | None = Field(description="€ con el precio fijo")
    effective_price: float = Field(description="€/kWh medio pagado con PVPC")
    break_even_price: float = Field(description="Precio fijo (€/kWh) por debajo del cual compensa el fijo")
    fixed_saving: float | None = Field(description="€ ahorrados con PVPC frente al fijo (negativo si gana el fijo)")
    days_fixed_was_cheaper: int | None
    periods: list[PeriodOut]
    days: list[DayCostOut]
    missing_days: list[dt.date] = Field(description="Días sin precios: el consumo se reparte entre el resto")
    note: str = "Solo el término de energía: sin término de potencia, alquiler del contador ni impuestos."
    source: Source = pvpc_source()
