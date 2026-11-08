from langgraph.graph import END, START, StateGraph

from agent.nodes.liaison import Liaison
from agent.nodes.workflow import Nodes, tracked
from agent.state import BidState


def build_conversation_graph(tools, model, checkpointer, store=None):
    shared, liaison = Nodes(tools, model), Liaison(tools, model)
    builder = StateGraph(BidState)
    for name in ("intake", "classify", "draft"):
        builder.add_node(name, tracked(name, getattr(liaison, name)))
    for name in ("verifier", "compliance", "preview", "regenerate"):
        builder.add_node(name, tracked(name, getattr(shared, name)))
    builder.add_node("approval", shared.approval)
    builder.add_node("execute", shared.execute)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "classify")
    builder.add_conditional_edges("classify", lambda s: END if s["status"] == "blocked" else "draft", ["draft", END])
    builder.add_edge("draft", "verifier")
    builder.add_edge("regenerate", "verifier")
    builder.add_edge("verifier", "compliance")
    builder.add_conditional_edges("compliance", lambda s: "preview" if s["compliance"]["passed"] else END, ["preview", END])
    builder.add_edge("preview", "approval")
    builder.add_conditional_edges("approval", lambda s: "execute" if s["status"] == "approved" else
                                  "regenerate" if s["status"] == "regenerating" else
                                  "verifier" if s["status"] == "rechecking" else END,
                                  ["execute", "regenerate", "verifier", END])
    builder.add_edge("execute", END)
    return builder.compile(checkpointer=checkpointer, store=store)
