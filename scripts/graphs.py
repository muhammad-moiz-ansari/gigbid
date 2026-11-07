from langgraph.checkpoint.memory import InMemorySaver

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from apps.api.config import ROOT


def main():
    (ROOT / "docs/images").mkdir(parents=True, exist_ok=True)
    for name, builder in (("bid", build_bid_graph), ("conversation", build_conversation_graph)):
        graph = builder(None, None, InMemorySaver())
        (ROOT / f"docs/images/{name}.mmd").write_text(graph.get_graph().draw_mermaid(), encoding="utf-8")


if __name__ == "__main__":
    main()
