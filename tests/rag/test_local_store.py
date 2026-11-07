import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from apps.api.config import ROOT, settings
from apps.api.db import uid
from rag.index.corpus import status
from rag.index.vector_store import open_store
from rag.ingest.loaders import ingest_text
from rag.retriever import retrieve


def test_real_local_qdrant_persists_and_closes_across_threads_and_processes(
    tenant, embeddings, monkeypatch
):
    path = str(ROOT / ".cache" / ("qdrant-phase4-" + uid()))
    monkeypatch.setattr(settings(), "qdrant_mode", "local")
    monkeypatch.setattr(settings(), "qdrant_path", path)
    monkeypatch.setenv("QDRANT_MODE", "local")
    monkeypatch.setenv("QDRANT_PATH", path)
    evidence = ingest_text(tenant, "Python API", {"source": "persistent.md"})[0]
    assert retrieve(tenant, "Python", variant="V0")[0]["id"] == evidence["id"]
    manifest = status(tenant)["dense"][0]

    def read(_):
        with open_store() as store:
            return store.search(
                manifest["collection"],
                tenant,
                manifest["fingerprint"],
                [1, 0, 0],
                [evidence["id"]],
                1,
            )[0].payload["evidence_id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(read, range(4))) == [evidence["id"]] * 4
    code = (
        "from rag.index.vector_store import open_store; "
        "\nwith open_store() as store:\n"
        f" print(store.client.count({manifest['collection']!r}, exact=True).count)\n"
    )
    reopened = subprocess.run(
        [sys.executable, "-c", code],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert reopened.stdout.strip() == "1"
