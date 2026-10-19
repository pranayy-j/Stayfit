import asyncio
import functools
from collections.abc import Callable, Iterator

import httpx2
import pytest

from app.services import eating_classifier
from app.services.eating_classifier import ClassificationError


def jev_reply(noul: float) -> httpx2.Response:
    body = {"model": "jev-test", "answers": {"is_eating_update": {"type": "noul", "noul": noul}}}
    return httpx2.Response(200, json=body)


@pytest.fixture
def fake_jev(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., list[httpx2.Request]]]:
    """Point the real classifier at a scripted fake JEV; returns the requests it received."""
    requests: list[httpx2.Request] = []

    def install(*replies: httpx2.Response) -> list[httpx2.Request]:
        queue = list(replies)

        def handler(request: httpx2.Request) -> httpx2.Response:
            requests.append(request)
            return queue.pop(0)

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        monkeypatch.setattr(
            eating_classifier,
            "TypeSafeClassifier",
            functools.partial(eating_classifier.TypeSafeClassifier, async_client=client),
        )
        monkeypatch.setattr(eating_classifier.settings, "typesafe_api_key", "test-key")
        return requests

    yield install
    asyncio.run(eating_classifier.close_client())


def test_sends_criteria_and_transcript(fake_jev) -> None:
    requests = fake_jev(jev_reply(0.98))
    assert asyncio.run(eating_classifier.is_eating_update("I ate two eggs")) is True
    payload = requests[0].read().decode()
    assert "I ate two eggs" in payload
    assert "An eating update says the user ate" in payload


def test_threshold_is_exclusive(fake_jev) -> None:
    fake_jev(jev_reply(0.75))
    assert asyncio.run(eating_classifier.is_eating_update("egg")) is False


def test_retries_transient_errors(fake_jev) -> None:
    requests = fake_jev(httpx2.Response(503), httpx2.Response(429), jev_reply(0.9))
    assert asyncio.run(eating_classifier.is_eating_update("milk")) is True
    assert len(requests) == 3


def test_does_not_retry_auth_errors(fake_jev) -> None:
    requests = fake_jev(httpx2.Response(401, json={"detail": "bad key"}))
    with pytest.raises(ClassificationError):
        asyncio.run(eating_classifier.is_eating_update("milk"))
    assert len(requests) == 1


def test_missing_api_key_is_classification_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eating_classifier.settings, "typesafe_api_key", None)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    asyncio.run(eating_classifier.close_client())
    with pytest.raises(ClassificationError):
        asyncio.run(eating_classifier.is_eating_update("milk"))
