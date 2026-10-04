from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from src.ingestion.ree_client import (
    RETRY_STATUS,
    ReeApiError,
    ReeClient,
    ReePoint,
    build_session,
    date_chunks,
    parse_series,
)


def _response(payload, status=200):
    response = MagicMock()
    response.ok = status < 400
    response.status_code = status
    response.json.return_value = payload
    response.text = str(payload)
    return response


def _item(series_type, points):
    return {"type": series_type, "attributes": {"values": [{"value": v, "datetime": dt} for dt, v in points]}}


def _payload(series_type, points):
    return {"included": [_item(series_type, points)]}


def _client(*responses, max_days=28):
    session = MagicMock()
    session.get.side_effect = list(responses)
    return ReeClient(session=session, base_url="https://ree.test/es/datos/", timeout=5, max_days=max_days), session


# --- Tramos de fechas ---


def test_date_chunks_cover_the_range_without_gaps_or_overlaps():
    chunks = list(date_chunks(date(2026, 1, 1), date(2026, 3, 15), max_days=28))
    assert chunks[0] == (date(2026, 1, 1), date(2026, 1, 28))
    assert chunks[-1][1] == date(2026, 3, 15)
    for (_, prev_end), (next_start, _) in zip(chunks, chunks[1:], strict=False):
        assert (next_start - prev_end).days == 1
    assert all((end - start).days < 28 for start, end in chunks)


def test_date_chunks_single_day():
    assert list(date_chunks(date(2026, 1, 1), date(2026, 1, 1), max_days=28)) == [(date(2026, 1, 1), date(2026, 1, 1))]


def test_date_chunks_reject_inverted_range():
    with pytest.raises(ValueError, match="posterior"):
        list(date_chunks(date(2026, 2, 1), date(2026, 1, 1), max_days=28))


# --- Reintentos ---


def test_session_retries_rate_limits_and_server_errors_only():
    retry = build_session().get_adapter("https://apidatos.ree.es").max_retries
    assert retry.total == 5
    assert set(retry.status_forcelist) == set(RETRY_STATUS)
    assert 400 not in retry.status_forcelist
    assert retry.backoff_factor > 0


# --- Interpretación de respuestas ---


def test_parse_series_converts_to_utc_and_keeps_every_type():
    payload = _payload("PVPC", [("2026-07-01T00:00:00.000+02:00", 100.5)])
    payload["included"].append(_item("Precio mercado spot", [("2026-07-01T00:00:00.000+02:00", 1)]))
    series = parse_series(payload)
    assert set(series) == {"PVPC", "Precio mercado spot"}
    assert series["PVPC"] == [ReePoint(datetime(2026, 6, 30, 22, tzinfo=UTC), 100.5)]


def test_parse_series_flattens_grouped_content():
    payload = {
        "included": [
            {
                "type": "Renovable",
                "attributes": {
                    "content": [
                        _item("Eólica", [("2026-07-01T00:00:00+02:00", 5)]),
                        _item("Solar", [("2026-07-01T00:00:00+02:00", 7)]),
                    ]
                },
            }
        ]
    }
    values = {name: [p.value for p in pts] for name, pts in parse_series(payload).items()}
    assert values == {"Eólica": [5.0], "Solar": [7.0]}


def test_parse_series_empty_payload():
    assert parse_series({}) == {}


# --- Cliente ---


def test_fetch_requests_each_chunk_with_the_right_parameters():
    client, session = _client(_response(_payload("PVPC", [])), _response(_payload("PVPC", [])))

    client.fetch("mercados/precios-mercados-tiempo-real", date(2026, 1, 1), date(2026, 2, 10), params={"geo_id": 8741})

    assert session.get.call_count == 2
    first = session.get.call_args_list[0]
    assert first.args[0] == "https://ree.test/es/datos/mercados/precios-mercados-tiempo-real"
    assert first.kwargs["params"] == {
        "start_date": "2026-01-01T00:00",
        "end_date": "2026-01-28T23:59",
        "time_trunc": "hour",
        "geo_id": 8741,
    }
    assert first.kwargs["timeout"] == 5
    assert session.get.call_args_list[1].kwargs["params"]["start_date"] == "2026-01-29T00:00"


def test_fetch_merges_chunks_sorted_and_without_duplicates():
    late = ("2026-01-29T01:00:00.000+01:00", 20.0)
    early = ("2026-01-28T23:00:00.000+01:00", 10.0)
    repeated = ("2026-01-29T00:00:00.000+01:00", 15.0)
    client, _ = _client(
        _response(_payload("PVPC", [repeated, early])),
        _response(_payload("PVPC", [late, (repeated[0], 16.0)])),
    )

    points = client.fetch("x", date(2026, 1, 1), date(2026, 2, 10))["PVPC"]

    assert [p.value for p in points] == [10.0, 16.0, 20.0]  # el último tramo prevalece
    assert [p.datetime.hour for p in points] == [22, 23, 0]  # en UTC


def test_fetch_raises_with_ree_error_detail():
    error = {"errors": [{"status": "400", "detail": "Los datos solicitados no están disponibles"}]}
    client, _ = _client(_response(error, status=400))

    with pytest.raises(ReeApiError, match="400: Los datos solicitados no están disponibles"):
        client.fetch("x", date(2026, 1, 1), date(2026, 1, 2))


def test_fetch_raises_when_error_body_is_not_json():
    response = _response(None, status=502)
    response.json.side_effect = ValueError("no es JSON")
    response.text = "Bad Gateway"
    client, _ = _client(response)

    with pytest.raises(ReeApiError, match="502: Bad Gateway"):
        client.fetch("x", date(2026, 1, 1), date(2026, 1, 2))
