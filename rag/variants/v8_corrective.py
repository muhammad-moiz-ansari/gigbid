from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class RetrievalState(TypedDict, total=False):
    query: str
    attempts: int
    candidates: list
    refused: bool


def retrieve(query, search, limit=2):
    def attempt(state):
        q = state["query"] if state.get("attempts", 0) == 0 else " ".join(state["query"].split()[:8])
        candidates = search(q)
        return {"candidates": candidates, "attempts": state.get("attempts", 0) + 1}

    def route(state):
        if state["candidates"] or state["attempts"] >= limit:
            return "finish"
        return "retrieve"

    builder = StateGraph(RetrievalState)
    builder.add_node("retrieve", attempt)
    builder.add_node("finish", lambda s: {"refused": not bool(s["candidates"])})
    builder.add_edge(START, "retrieve")
    builder.add_conditional_edges("retrieve", route)
    builder.add_edge("finish", END)
    return builder.compile().invoke({"query": query, "attempts": 0})["candidates"]
