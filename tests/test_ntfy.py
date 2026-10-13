import io
import json
import urllib.request

import pytest

from src.notifications import ntfy


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@pytest.fixture
def sent(monkeypatch):
    requests = []

    def urlopen(request, timeout):
        requests.append({"url": request.full_url, "body": json.loads(request.data), "timeout": timeout})
        return FakeResponse(b'{"id": "abc123", "event": "message"}')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return requests


def test_publishes_json_with_accents_to_the_server_root(sent):
    message_id = ntfy.publish("https://ntfy.sh/", "luzpreddict", "Luz el miércoles", "Más barata: 3–5 h")

    assert message_id == "abc123"
    assert sent == [
        {
            "url": "https://ntfy.sh",
            "body": {"topic": "luzpreddict", "title": "Luz el miércoles", "message": "Más barata: 3–5 h"},
            "timeout": ntfy.TIMEOUT_SECONDS,
        }
    ]


def test_click_opens_the_web_when_given(sent):
    ntfy.publish("https://ntfy.sh", "t", "título", "texto", click="https://luzpreddict.vercel.app")

    assert sent[0]["body"]["click"] == "https://luzpreddict.vercel.app"
