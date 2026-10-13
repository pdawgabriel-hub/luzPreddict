import io
import json
import logging
import urllib.request

import pytest

from src.api import rate_limit
from src.api.rate_limit import RateLimiter, UpstashCounter, build_rate_limiter
from src.utils.config import Settings
from tests.api_helpers import TODAY, make_client, save_prices

T0 = 1_759_999_980.0  # múltiplo de 60: inicio de una ventana


class FakeCounter:
    """Contadores en memoria, como Redis con INCR."""

    def __init__(self):
        self.counts = {}
        self.ttls = {}

    def hit(self, key, ttl_seconds):
        self.counts[key] = self.counts.get(key, 0) + 1
        self.ttls[key] = ttl_seconds
        return self.counts[key]


class BrokenCounter:
    def hit(self, key, ttl_seconds):
        raise TimeoutError("Upstash no responde")


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now


def limiter(limit=3, clock=None, counter=None):
    return RateLimiter(counter or FakeCounter(), limit, secret="secreto", clock=clock or Clock())


# --- Limitador ---


def test_counts_per_client_and_window():
    clock = Clock(T0 + 15)
    rl = limiter(limit=2, clock=clock)

    first, second, third = (rl.check("1.2.3.4") for _ in range(3))

    assert (first.count, first.remaining, first.allowed) == (1, 1, True)
    assert (second.remaining, second.allowed) == (0, True)
    assert (third.remaining, third.allowed) == (0, False)
    assert third.reset_seconds == 45
    assert rl.check("5.6.7.8").count == 1  # cada IP tiene su contador

    clock.now = T0 + 60  # minuto siguiente: contador nuevo
    assert rl.check("1.2.3.4").count == 1


def test_keys_do_not_contain_the_ip_and_expire():
    counter = FakeCounter()
    rl = limiter(counter=counter)

    rl.check("1.2.3.4")

    [key] = counter.counts
    assert "1.2.3.4" not in key
    assert key.startswith("rate:") and key.endswith(f":{int(T0)}")
    assert counter.ttls[key] == 60
    # Con otro secreto, la misma IP da otra clave: el hash no se puede comparar entre despliegues
    assert RateLimiter(counter, 3, secret="otro").key("1.2.3.4", 0) != rl.key("1.2.3.4", 0)


def test_headers_and_retry_after_only_when_blocked():
    rl = limiter(limit=1, clock=Clock(T0 + 59.5))

    allowed, blocked = rl.check("ip"), rl.check("ip")

    assert allowed.headers() == {"X-RateLimit-Limit": "1", "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1"}
    assert blocked.headers()["Retry-After"] == "1"  # nunca 0, aunque quede medio segundo


def test_disabled_without_upstash_configuration():
    assert build_rate_limiter(Settings(_env_file=None)) is None
    configured = Settings(_env_file=None, upstash_redis_rest_url="https://x.upstash.io", upstash_redis_rest_token="t")
    assert build_rate_limiter(configured).limit == 60


# --- Upstash ---


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_upstash_counter_sends_incr_and_expire_in_one_request(monkeypatch):
    sent = {}

    def urlopen(request, timeout):
        sent.update(url=request.full_url, body=json.loads(request.data), auth=request.get_header("Authorization"))
        sent["timeout"] = timeout
        return FakeResponse(json.dumps([{"result": 7}, {"result": 1}]).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    assert UpstashCounter("https://x.upstash.io/", "secreto").hit("rate:abc:0", 60) == 7
    assert sent == {
        "url": "https://x.upstash.io/pipeline",
        "body": [["INCR", "rate:abc:0"], ["EXPIRE", "rate:abc:0", 60]],
        "auth": "Bearer secreto",
        "timeout": 1.0,
    }


def test_upstash_errors_are_raised(monkeypatch):
    error = json.dumps([{"error": "WRONGPASS"}, {"result": 1}]).encode()
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: FakeResponse(error))

    with pytest.raises(RuntimeError, match="WRONGPASS"):
        UpstashCounter("https://x.upstash.io", "t").hit("k", 60)


# --- En la API ---


@pytest.fixture
def limited_client(db_session):
    client = make_client(db_session)
    client.app.state.rate_limiter = limiter(limit=2)
    save_prices(db_session, TODAY)
    return client


def test_limited_routes_report_the_remaining_requests(limited_client):
    response = limited_client.get("/v1/prices")

    assert response.status_code == 200
    assert response.headers["x-ratelimit-limit"] == "2"
    assert response.headers["x-ratelimit-remaining"] == "1"
    assert response.headers["x-ratelimit-reset"] == "60"
    assert "retry-after" not in response.headers


def test_over_the_limit_is_a_429_with_the_common_error_format(limited_client):
    for _ in range(2):
        limited_client.get("/v1/prices")

    response = limited_client.get("/v1/prices")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.headers["x-ratelimit-remaining"] == "0"
    assert response.headers["cache-control"] == "no-store"
    error = response.json()["error"]
    assert error["code"] == "too_many_requests"
    assert error["message"] == "Has superado el límite de 2 peticiones por minuto: vuelve a intentarlo en 60 s"
    assert error["request_id"] == response.headers["x-request-id"]


def test_the_limit_is_shared_by_v1_and_the_web_routes(limited_client):
    limited_client.get("/v1/prices")
    limited_client.get("/api/tools/catalog")

    assert limited_client.get("/api/model").status_code == 429  # sin modelo sería un 404: el límite va antes


def test_health_and_docs_are_not_limited(limited_client):
    for _ in range(3):
        limited_client.get("/v1/prices")

    for path in ("/health", "/docs", "/openapi.json", "/"):
        response = limited_client.get(path)
        assert response.status_code == 200, path
        assert "x-ratelimit-limit" not in response.headers


def test_each_client_ip_has_its_own_limit(limited_client):
    for _ in range(3):
        limited_client.get("/v1/prices", headers={"X-Real-IP": "1.1.1.1"})

    assert limited_client.get("/v1/prices", headers={"X-Real-IP": "1.1.1.1"}).status_code == 429
    assert limited_client.get("/v1/prices", headers={"X-Real-IP": "2.2.2.2"}).status_code == 200


def test_if_upstash_fails_requests_go_through(limited_client, caplog):
    limited_client.app.state.rate_limiter = limiter(counter=BrokenCounter())

    with caplog.at_level(logging.WARNING, logger=rate_limit.__name__):
        response = limited_client.get("/v1/prices")

    assert response.status_code == 200
    assert "x-ratelimit-limit" not in response.headers
    assert "Upstash no responde" in caplog.text


def test_browsers_can_read_the_limit_headers(limited_client):
    response = limited_client.get("/v1/prices", headers={"Origin": "http://localhost:5173"})

    exposed = response.headers["access-control-expose-headers"]
    assert {"X-RateLimit-Remaining", "Retry-After"} <= set(exposed.split(", "))


def test_the_429_is_documented(limited_client):
    schema = limited_client.get("/openapi.json").json()

    assert "429" in schema["paths"]["/v1/prices"]["get"]["responses"]
    assert "429" in schema["paths"]["/api/model"]["get"]["responses"]
    assert "429" not in schema["paths"]["/health"]["get"]["responses"]
