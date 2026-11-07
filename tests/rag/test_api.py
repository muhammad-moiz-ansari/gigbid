import json


def test_uploaded_json_and_index_status_are_inspectable_and_repeatable(client, account):
    data = json.dumps(
        [
            {
                "text": "Rust API review",
                "type": "review",
                "skills": ["Rust"],
                "project": "Example",
                "synthetic": True,
            }
        ]
    ).encode()
    first = client.post("/evidence/file", files={"file": ("review.json", data, "application/json")})
    assert first.status_code == 200, first.text
    assert first.json()[0]["type"] == "review" and first.json()[0]["synthetic"]
    second = client.post(
        "/evidence/file", files={"file": ("review.json", data, "application/json")}
    )
    assert second.json() == first.json()
    status = client.get("/evidence/index").json()
    assert status["bm25"]["status"] == "ready"
    assert any(s["source"] == "review.json" for s in status["sources"])
    assert client.delete("/evidence/source/review.json").status_code == 200
    assert all(item["id"] != first.json()[0]["id"] for item in client.get("/evidence").json())


def test_file_metadata_and_invalid_replacement_preserve_original(client, account):
    good = client.post(
        "/evidence/file",
        files={"file": ("work.txt", b"Python work", "text/plain")},
        data={"metadata": json.dumps({"type": "cv", "skills": ["Python"], "persona": "own"})},
    )
    assert good.status_code == 200 and good.json()[0]["type"] == "cv"
    bad = client.post("/evidence/file", files={"file": ("work.txt", b"\xff", "text/plain")})
    assert bad.status_code == 422
    assert any(e["id"] == good.json()[0]["id"] for e in client.get("/evidence").json())
