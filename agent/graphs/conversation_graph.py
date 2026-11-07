from langgraph.graph import END, START, StateGraph

from agent.handoffs import ProposalDraft
from agent.nodes.workflow import Nodes, tracked
from agent.state import BidState
from apps.api.safety import risks


def build_conversation_graph(tools, model, checkpointer):
    shared = Nodes(tools, model)

    async def intake(state):
        messages = await tools.call("liaison", "list_messages", {"conversation": state["conversation"]})
        incoming = [m for m in messages if m.get("direction") == "inbound"]
        if not incoming:
            raise ValueError("No client message to answer")
        text = incoming[-1]["text"]
        flags = risks(text)
        intent = "scam" if set(flags) & {"off_platform", "free_work"} else "interview" if any(
            w in text.lower() for w in ("interview", "schedule", "available")) else "negotiation" if any(
            w in text.lower() for w in ("price", "budget", "rate")) else "question"
        evidence = await tools.call("liaison", "search_evidence", {"requirement": text, "k": 5})
        return {"messages": incoming, "intent": intent, "fit": {"score": 0, "matrix": {}, "evidence": evidence},
                "risk": {"score": 1 if intent == "scam" else 0.2, "flags": flags, "reasons": flags},
                "status": "blocked" if intent == "scam" else "running"}

    async def draft(state):
        slots = await tools.call("liaison", "free_slots", {}) if state["intent"] == "interview" else []
        result, usage = await model.complete("liaison", {"messages": state["messages"],
            "intent": state["intent"], "evidence": state["fit"]["evidence"], "slots": slots,
            "memory": state.get("memory", [])}, ProposalDraft)
        return {"draft": result, "usage": [usage], "critique": {"passed": True, "comments": []}}

    builder = StateGraph(BidState)
    builder.add_node("intake", tracked("liaison_intake", intake))
    builder.add_node("draft", tracked("liaison_draft", draft))
    for name in ("verifier", "compliance", "preview", "execute", "regenerate"):
        builder.add_node(name, tracked(name, getattr(shared, name)))
    builder.add_node("approval", shared.approval)
    builder.add_edge(START, "intake")
    builder.add_conditional_edges("intake", lambda s: END if s["status"] == "blocked" else "draft")
    builder.add_edge("draft", "verifier")
    builder.add_edge("regenerate", "verifier")
    builder.add_edge("verifier", "compliance")
    builder.add_conditional_edges("compliance", lambda s: "preview" if s["compliance"]["passed"] else END)
    builder.add_edge("preview", "approval")
    builder.add_conditional_edges("approval", lambda s: "execute" if s["status"] == "approved" else
                                  "regenerate" if s["status"] == "regenerating" else
                                  "verifier" if s["status"] == "rechecking" else END)
    builder.add_edge("execute", END)
    return builder.compile(checkpointer=checkpointer)
