import httpx
import pytest

from agent.marketplace_port import Unavailable
from rag.index.dense import OllamaEmbeddings


def test_real_adapter_http_contract_without_claiming_real_inference(monkeypatch):
    requests = []

    def handler(request):
        import json

        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "nomic-embed-text:latest", "digest": "test-contract-digest"}
                    ]
                },
            )
        body = json.loads(request.content)
        assert body["truncate"] is False and body["model"] == "nomic-embed-text"
        return httpx.Response(200, json={"embeddings": [[1, 0, 0] for _ in body["input"]]})

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)
    )
    backend = OllamaEmbeddings("nomic-embed-text")
    assert backend.identity()["revision"] == "test-contract-digest"
    assert backend.embed(["one", "two"]) == [[1, 0, 0], [1, 0, 0]]
    assert [r.url.path for r in requests] == ["/api/tags", "/api/embed"]


def test_missing_or_failed_open_model_never_silently_falls_back(monkeypatch):
    original = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"models": []}))
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs))
    with pytest.raises(Unavailable, match="not installed"):
        OllamaEmbeddings("missing").identity()
