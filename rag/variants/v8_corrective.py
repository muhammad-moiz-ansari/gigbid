from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from rag.index.corpus import tokens

# Words that tie almost any passage to a job post, so they cannot ground evidence on their own.
COMMON = {"a", "an", "and", "are", "as", "at", "be", "by", "can", "for", "from", "have", "i", "in", "is", "it",
          "looking", "need", "of", "on", "or", "our", "the", "this", "to", "we", "will", "with", "you", "your"}


class RetrievalState(TypedDict, total=False):
    query: str
    attempts: int
    candidates: list
    refused: bool


def grounded(query, item):
    """Graded relevant when the passage shares a content word with the query; dense neighbours alone are not trusted."""
    return bool((set(tokens(query)) - COMMON) & set(tokens(item["text"] + " " + " ".join(item["skills"]))))


def retrieve(query, search, limit=2):
    def attempt(state):
        q = state["query"] if state.get("attempts", 0) == 0 else " ".join(state["query"].split()[:8])
        candidates = [pair for pair in search(q) if grounded(q, pair[0])]
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
