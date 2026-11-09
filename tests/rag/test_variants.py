import pytest

from rag.ingest.loaders import ingest_text
from rag.retriever import retrieve
from rag.variants import v8_corrective


def test_components_join_into_one_pipeline(tenant):
    ingest_text(tenant, "Tableau sales dashboard for a retailer", {"source": "tableau.md", "skills": ["Tableau"]})
    for outcome in ("ignored", "won"):
        ingest_text(tenant, f"Proposal for a Celery queue migration ({outcome})",
                    {"source": f"{outcome}.json", "type": "proposal", "skills": ["Celery"], "outcome": outcome})
    hits = retrieve(tenant, "Celery\nTableau", k=5, variant="BM25+V1+V4")
    order = [h["source"] for h in hits]
    assert set(order) == {"tableau.md", "ignored.json", "won.json"} and hits[0]["retrieval_variant"] == "BM25+V1+V4"
    assert order.index("won.json") < order.index("ignored.json")
    with pytest.raises(ValueError, match="Unknown retrieval variant"):
        retrieve(tenant, "Celery", variant="V1+V7")


def test_corrective_retrieval_grades_requeries_and_refuses():
    item, queries = {"text": "Tableau sales dashboard", "skills": ["Tableau"]}, []

    def search(query):
        queries.append(query)
        return [(item, 0.9)]
    assert v8_corrective.retrieve("Kubernetes cluster for our team", search) == []
    assert len(queries) == 2
    assert v8_corrective.retrieve("Tableau", search) == [(item, 0.9)]
