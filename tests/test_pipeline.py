import dataclasses
from datetime import timedelta

import pytest

from src import pipeline
from src.db import repository
from src.db.models import ModelRun
from src.ingestion import prices
from src.utils.config import Settings
from tests.fakes import SEEDED_LAST_DAY as LAST_DAY
from tests.fakes import FakeReeClient


def test_backfill_continues_from_the_last_saved_day(seeded):
    client = FakeReeClient(published_until=LAST_DAY + timedelta(days=2))

    result = pipeline.backfill(seeded, client=client, today=LAST_DAY + timedelta(days=1))

    pvpc_calls = [c for c in client.calls if c[0] == prices.PVPC_PATH]
    assert pvpc_calls[0][1:] == (LAST_DAY, LAST_DAY + timedelta(days=2))  # repite el último día y llega a mañana
    assert result.last_price_day == LAST_DAY + timedelta(days=2)
    assert result.prices_changed > 0
    assert repository.last_generation_date(seeded) == LAST_DAY + timedelta(days=1)


def test_train_saves_the_model_in_the_database(seeded, fast_model, monkeypatch):
    pruned = []
    monkeypatch.setattr(repository, "prune_model_binaries", lambda session, keep: pruned.append(keep) or 0)

    version = pipeline.train(seeded, metrics_days=3)

    stored = repository.get_model_artifact(seeded)
    assert stored.version == version
    assert set(stored.metrics["models"]) == {"lightgbm", "precio_ayer", "media_7_dias"}
    assert pruned == [pipeline.KEEP_MODEL_BINARIES]  # y se borran los binarios antiguos


def test_daily_saves_a_forecast_for_the_first_unpublished_day(seeded, sessions, fast_model):
    pipeline.train(seeded, metrics_days=3)
    client = FakeReeClient(published_until=LAST_DAY + timedelta(days=1))

    result = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)

    assert result.status == "completo"  # mañana ya está publicado
    assert result.forecast.day == LAST_DAY + timedelta(days=2)
    assert result.forecast.model == "lightgbm"
    run = repository.latest_forecast(seeded, result.forecast.day)
    assert run.id == result.run_id
    assert run.model_version == result.forecast.model_version
    assert len(run.hours) == 24
    assert all(h.lower <= h.prediction <= h.upper for h in run.hours)
    assert [h.lower for h in run.hours] == pytest.approx(result.forecast.lower.tolist())


def test_daily_is_pending_when_tomorrow_is_not_published_yet(seeded, sessions):
    client = FakeReeClient(published_until=LAST_DAY)  # REE aún no ha publicado mañana

    result = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)

    assert result.status == "pendiente"
    assert result.forecast.day == LAST_DAY + timedelta(days=1)  # se prevé mañana igualmente
    assert result.forecast.model == "precio_ayer"  # no hay modelo guardado: respaldo
    run = repository.latest_forecast(seeded, result.forecast.day)
    assert all(h.lower is None and h.upper is None for h in run.hours)  # el respaldo no tiene intervalo


def test_predict_command_needs_prices():
    with pytest.raises(ValueError, match="make backfill"):
        pipeline.forecast_next_day(_EmptyRepositorySession())


class _EmptyRepositorySession:
    """Sesión mínima para una base de datos sin precios."""

    def scalar(self, *args, **kwargs):
        return None


def test_repeating_daily_does_not_duplicate_the_forecast(seeded, sessions):
    client = FakeReeClient(published_until=LAST_DAY)

    first = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)
    second = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)

    assert second.run_id == first.run_id
    assert seeded.query(ModelRun).count() == 1


def test_a_changed_forecast_is_saved_as_a_new_run(seeded, sessions, fast_model):
    client = FakeReeClient(published_until=LAST_DAY)
    first = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)  # respaldo, sin modelo

    pipeline.train(seeded, metrics_days=3)
    second = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)  # ya con LightGBM

    assert second.run_id != first.run_id
    assert repository.latest_forecast(seeded, second.forecast.day).model == "lightgbm"


def test_a_forecast_whose_interval_changes_is_saved_as_a_new_run(seeded):
    forecast = pipeline.forecast_next_day(seeded)  # respaldo: sin intervalo
    first = pipeline.save_forecast(seeded, forecast)
    assert pipeline.save_forecast(seeded, forecast) == first

    with_interval = dataclasses.replace(
        forecast,
        generated_at=forecast.generated_at + timedelta(hours=2),
        lower=forecast.prices - 10,
        upper=forecast.prices + 10,
    )
    second = pipeline.save_forecast(seeded, with_interval)

    assert second != first
    assert pipeline.save_forecast(seeded, with_interval) == second
    assert repository.latest_forecast(seeded, forecast.day).hours[0].upper == pytest.approx(
        forecast.prices.iloc[0] + 10
    )


# --- Informe para GitHub Actions ---


def test_github_summary_describes_the_daily_task(seeded, sessions):
    client = FakeReeClient(published_until=LAST_DAY)
    result = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)  # sin modelo: respaldo

    summary = pipeline.github_summary(result)

    assert summary.startswith("### Tarea diaria · pendiente")
    assert f"| Previsión | {result.forecast.day:%d/%m/%Y} (24 h) · ejecución {result.run_id} |" in summary
    assert "| Modelo | precio_ayer |" in summary
    assert "| Hora más barata | " in summary and " €/MWh |" in summary
    assert "> Respaldo activado: LookupError" in summary
    # Sin líneas vacías dentro de la tabla: la partirían en dos
    table = summary.split("\n\n")[1]
    assert all(line.startswith("|") for line in table.strip().splitlines())


def test_daily_command_reports_to_github_only_inside_actions(seeded, sessions, monkeypatch, tmp_path, capsys):
    client = FakeReeClient(published_until=LAST_DAY + timedelta(days=1))
    result = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)
    monkeypatch.setattr(pipeline, "daily", lambda: result)
    monkeypatch.setattr(pipeline, "configure_logging", lambda: None)

    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    pipeline.main(["daily"])  # en local no escribe nada fuera de la consola
    assert "Estado: completo" in capsys.readouterr().out

    summary, output = tmp_path / "summary.md", tmp_path / "output"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    pipeline.main(["daily"])

    assert summary.read_text(encoding="utf-8").startswith("### Tarea diaria · completo")
    assert output.read_text(encoding="utf-8") == f"status=completo\nforecast_day={result.forecast.day.isoformat()}\n"


METRICS = {
    "period": {"start": "2026-07-16", "end": "2026-10-13", "days": 90},
    "models": {
        "precio_ayer": {"mae": 33.81, "rmse": 50.1, "bias": -0.5},
        "lightgbm": {"mae": 22.94, "rmse": 31.2, "bias": -3.1},
        "media_7_dias": {"mae": 32.9, "rmse": 45.0, "bias": -2.0},
    },
    "interval": {"level": 0.8, "coverage": 0.702, "width": 69.33, "n": 2160},
}


def test_training_summary_ranks_the_models_and_shows_the_interval():
    summary = pipeline.training_summary("20261013-173857", METRICS)

    assert summary.startswith("### Modelo 20261013-173857")
    assert "Backtest de los últimos 90 días (2026-07-16 – 2026-10-13)" in summary
    models = [line.split(" | ")[0].removeprefix("| ") for line in summary.splitlines() if "€/MWh |" in line]
    assert models == ["lightgbm", "media_7_dias", "precio_ayer"]  # de menor a mayor error
    assert "| lightgbm | 22,9 €/MWh | 31,2 €/MWh | -3,1 €/MWh |" in summary
    assert "Intervalo del 80%: el precio real cayó dentro el 70,2% de las horas." in summary


def test_warns_in_actions_when_the_model_does_not_beat_the_baselines(monkeypatch, tmp_path, capsys):
    worse = {**METRICS, "models": {**METRICS["models"], "lightgbm": {"mae": 40.0, "rmse": 55.0, "bias": 1.0}}}
    assert pipeline.beats_baselines(METRICS) and not pipeline.beats_baselines(worse)

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    pipeline.report_training_to_github("v", worse)
    assert capsys.readouterr().out == ""  # en local, nada

    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    pipeline.report_training_to_github("v", worse)
    assert capsys.readouterr().out.startswith("::warning::El modelo v no mejora")
    assert summary.read_text(encoding="utf-8").startswith("### Modelo v")

    pipeline.report_training_to_github("v", METRICS)
    assert capsys.readouterr().out == ""  # si mejora, sin aviso


# --- Resumen diario por ntfy ---


def test_the_digest_is_sent_once_when_tomorrows_prices_arrive(seeded, sessions):
    client = FakeReeClient(published_until=LAST_DAY + timedelta(days=1))

    first = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)
    digest = pipeline.daily_digest(seeded, first)

    assert first.tomorrow_just_published
    assert digest.day == LAST_DAY + timedelta(days=1)
    assert digest.source == "published"
    assert digest.body.endswith("Precios publicados por REE.")

    retry = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)  # el reintento de las 21:30
    assert not retry.tomorrow_just_published
    assert pipeline.daily_digest(seeded, retry, last_attempt=True) is None


def test_without_ree_prices_the_forecast_is_sent_only_on_the_last_attempt(seeded, sessions):
    client = FakeReeClient(published_until=LAST_DAY)
    result = pipeline.daily(client=client, today=LAST_DAY, session_factory=sessions)

    assert pipeline.daily_digest(seeded, result) is None  # aún puede publicar: se espera al reintento

    digest = pipeline.daily_digest(seeded, result, last_attempt=True)
    assert digest.source == "forecast"
    assert digest.day == LAST_DAY + timedelta(days=1)
    assert 'Previsión de luzPreddict (respaldo "precio de ayer")' in digest.body


@pytest.fixture
def ntfy_settings(monkeypatch):
    settings = Settings(_env_file=None, ntfy_topic="luzpreddict", site_url="https://luzpreddict.vercel.app")
    monkeypatch.setattr(pipeline, "get_settings", lambda: settings)
    return settings


def test_notify_publishes_to_the_public_topic(seeded, sessions, ntfy_settings, monkeypatch):
    published = []
    monkeypatch.setattr(pipeline.ntfy, "publish", lambda *args, **kwargs: published.append((args, kwargs)) or "id1")
    result = pipeline.daily(
        client=FakeReeClient(published_until=LAST_DAY + timedelta(days=1)), today=LAST_DAY, session_factory=sessions
    )

    outcome = pipeline.notify(result, last_attempt=False, session_factory=sessions)

    assert outcome == f"Resumen del {LAST_DAY + timedelta(days=1):%d/%m/%Y} enviado a ntfy (precios de REE)"
    (server, topic, title, body), kwargs = published[0]
    assert (server, topic) == ("https://ntfy.sh", "luzpreddict")
    assert title.startswith("Luz el ")
    assert kwargs == {"click": "https://luzpreddict.vercel.app"}


def test_a_ntfy_failure_does_not_fail_the_task(seeded, sessions, ntfy_settings, monkeypatch, capsys, caplog):
    def down(*args, **kwargs):
        raise TimeoutError("ntfy no responde")

    monkeypatch.setattr(pipeline.ntfy, "publish", down)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    result = pipeline.daily(
        client=FakeReeClient(published_until=LAST_DAY + timedelta(days=1)), today=LAST_DAY, session_factory=sessions
    )

    outcome = pipeline.notify(result, last_attempt=False, session_factory=sessions)

    assert outcome == "No se pudo enviar el resumen (TimeoutError)"
    assert "::warning::No se pudo enviar el resumen a ntfy (TimeoutError: ntfy no responde)" in capsys.readouterr().out
    assert "ntfy no responde" in caplog.text


def test_without_a_topic_nothing_is_sent(seeded, sessions, monkeypatch):
    monkeypatch.setattr(pipeline, "get_settings", lambda: Settings(_env_file=None))
    result = pipeline.daily(
        client=FakeReeClient(published_until=LAST_DAY + timedelta(days=1)), today=LAST_DAY, session_factory=sessions
    )

    assert pipeline.notify(result, last_attempt=False, session_factory=sessions) == (
        "No se pudo enviar el resumen (ValueError)"
    )


def test_the_daily_command_only_notifies_with_the_option(seeded, sessions, monkeypatch, capsys):
    result = pipeline.daily(client=FakeReeClient(published_until=LAST_DAY), today=LAST_DAY, session_factory=sessions)
    calls = []
    monkeypatch.setattr(pipeline, "daily", lambda: result)
    monkeypatch.setattr(pipeline, "configure_logging", lambda: None)
    monkeypatch.setattr(pipeline, "notify", lambda result, last_attempt: calls.append(last_attempt) or "Enviado")

    pipeline.main(["daily"])  # make pipeline: nunca envía
    pipeline.main(["daily", "--notify"])
    pipeline.main(["daily", "--notify", "--last-attempt"])

    assert calls == [False, True]
    assert capsys.readouterr().out.count("Enviado") == 2
