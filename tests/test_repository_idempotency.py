"""Idempotencia de los upserts: guardar lo mismo dos veces deja la base igual que una vez."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from src.db import repository as repo
from src.db.models import DailyError, GenerationDay, PriceHour

MADRID = ZoneInfo("Europe/Madrid")
START = datetime(2026, 1, 1, tzinfo=UTC)
LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)


def _hours(n, price=100.0, start=START):
    return [(start + timedelta(hours=i), price + i) for i in range(n)]


# --- Lotes ---


def test_more_rows_than_one_batch(db_session):
    rows = _hours(2 * repo.BATCH_SIZE + 1)

    assert repo.upsert_prices(db_session, rows) == len(rows)
    assert repo.upsert_prices(db_session, rows) == 0
    assert len(repo.get_prices(db_session)) == len(rows)


def test_changes_spread_across_batches_are_all_counted(db_session):
    rows = _hours(2 * repo.BATCH_SIZE + 1)
    repo.upsert_prices(db_session, rows)
    changed_positions = [0, repo.BATCH_SIZE, 2 * repo.BATCH_SIZE]  # una fila en cada lote
    modified = [(ts, -1.0) if i in changed_positions else (ts, price) for i, (ts, price) in enumerate(rows)]

    assert repo.upsert_prices(db_session, modified) == 3
    stored = dict(repo.get_prices(db_session))
    assert [stored[rows[i][0]] for i in changed_positions] == [-1.0, -1.0, -1.0]


def test_generators_are_accepted_as_input(db_session):
    assert repo.upsert_prices(db_session, (row for row in _hours(10))) == 10


# --- updated_at ---


def _age_all_prices(db_session):
    db_session.execute(update(PriceHour).values(updated_at=LONG_AGO))


def test_unchanged_rows_keep_their_updated_at(db_session):
    repo.upsert_prices(db_session, _hours(24))
    _age_all_prices(db_session)

    repo.upsert_prices(db_session, _hours(24))
    db_session.expire_all()

    assert set(db_session.scalars(select(PriceHour.updated_at))) == {LONG_AGO}


def test_only_changed_rows_get_a_new_updated_at(db_session):
    repo.upsert_prices(db_session, _hours(24))
    _age_all_prices(db_session)

    repo.upsert_prices(db_session, [(START, 999.0)] + _hours(24)[1:])
    db_session.expire_all()

    by_hour = {row.datetime: row.updated_at for row in db_session.scalars(select(PriceHour))}
    assert by_hour[START] > LONG_AGO
    assert {ts for ts, updated in by_hour.items() if updated == LONG_AGO} == {ts for ts, _ in _hours(24)[1:]}


def test_generation_and_daily_errors_also_touch_only_changed_rows(db_session):
    repo.upsert_generation(db_session, [(date(2026, 1, 1), "Eólica", 1.0), (date(2026, 1, 1), "Solar", 2.0)])
    repo.upsert_daily_errors(db_session, [(date(2026, 1, 1), "lightgbm", 10.0, 12.0, 0.5, 24)])
    db_session.execute(update(GenerationDay).values(updated_at=LONG_AGO))
    db_session.execute(update(DailyError).values(computed_at=LONG_AGO))

    repo.upsert_generation(db_session, [(date(2026, 1, 1), "Eólica", 5.0), (date(2026, 1, 1), "Solar", 2.0)])
    repo.upsert_daily_errors(db_session, [(date(2026, 1, 1), "lightgbm", 10.0, 12.0, 0.5, 24)])
    db_session.expire_all()

    generation = {row.technology: row.updated_at for row in db_session.scalars(select(GenerationDay))}
    assert generation["Eólica"] > LONG_AGO
    assert generation["Solar"] == LONG_AGO
    assert db_session.scalars(select(DailyError.computed_at)).one() == LONG_AGO


# --- Claves ---


def test_the_same_instant_in_another_timezone_is_the_same_row(db_session):
    repo.upsert_prices(db_session, _hours(24))
    in_madrid = [(ts.astimezone(MADRID), price) for ts, price in _hours(24)]

    assert repo.upsert_prices(db_session, in_madrid) == 0


def test_duplicated_keys_in_the_same_input_keep_the_last_value(db_session):
    """REE puede repetir una hora entre tramos; gana el último valor, como en la ingesta."""
    rows = _hours(3) + [(START + timedelta(hours=1), 555.0)]

    assert repo.upsert_prices(db_session, rows) == 3
    assert dict(repo.get_prices(db_session))[START + timedelta(hours=1)] == 555.0


def test_duplicated_generation_keys_in_the_same_input_keep_the_last_value(db_session):
    rows = [(date(2026, 1, 1), "Eólica", 1.0), (date(2026, 1, 1), "Eólica", 7.0)]

    assert repo.upsert_generation(db_session, rows) == 1
    assert repo.get_generation(db_session) == [(date(2026, 1, 1), "Eólica", 7.0)]


@pytest.mark.parametrize("save", [repo.upsert_prices, repo.upsert_generation, repo.upsert_daily_errors])
def test_empty_input_changes_nothing(db_session, save):
    assert save(db_session, []) == 0


# --- Rangos de lectura ---


def test_price_range_includes_start_and_excludes_end(db_session):
    repo.upsert_prices(db_session, _hours(10))

    rows = repo.get_prices(db_session, start=START + timedelta(hours=2), end=START + timedelta(hours=5))

    assert [ts for ts, _ in rows] == [START + timedelta(hours=h) for h in (2, 3, 4)]


def test_generation_and_error_ranges_include_both_days(db_session):
    days = [date(2026, 1, d) for d in range(1, 6)]
    repo.upsert_generation(db_session, [(d, "Eólica", 1.0) for d in days])
    repo.upsert_daily_errors(db_session, [(d, "lightgbm", 1.0, 1.0, 0.0, 24) for d in days])

    assert [d for d, _, _ in repo.get_generation(db_session, start=days[1], end=days[3])] == days[1:4]
    assert [e.day for e in repo.get_daily_errors(db_session, start=days[1], end=days[3])] == days[1:4]
