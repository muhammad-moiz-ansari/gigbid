from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.model import config
from agent.nodes.workflow import Nodes, tracked
from agent.state import BidState


def build_bid_graph(tools, model, checkpointer):
    nodes = Nodes(tools, model)
    builder = StateGraph(BidState)
    for name in ("intake", "analyst", "risk", "matcher", "reconcile", "pricing", "writer",
                 "verifier", "critic", "compliance", "preview", "regenerate"):
        builder.add_node(name, tracked(name, getattr(nodes, name)))
    # interrupt node intentionally has no asyncio.wait_for wrapper; cancellation must
    # never catch GraphInterrupt or turn approval into a normal return value.
    builder.add_node("approval", nodes.approval)
    builder.add_node("execute", nodes.execute)
    builder.add_edge(START, "intake")
    builder.add_conditional_edges("intake", lambda s: [Send(name, s) for name in ("analyst", "risk", "matcher")],
                                  ["analyst", "risk", "matcher"])
    builder.add_edge(["analyst", "risk", "matcher"], "reconcile")
    builder.add_conditional_edges("reconcile", lambda s: "pricing" if s["decision"]["action"] == "bid" else END,
                                  ["pricing", END])
    builder.add_edge("pricing", "writer")
    builder.add_edge("writer", "verifier")
    builder.add_edge("regenerate", "verifier")
    builder.add_edge("verifier", "critic")
    builder.add_conditional_edges("critic", lambda s: "writer" if not s["critique"]["passed"] and
                                  s["revision"] <= min(2, config()["thresholds"]["critic_revisions"]) else "compliance",
                                  ["writer", "compliance"])
    builder.add_conditional_edges("compliance", lambda s: "preview" if s["compliance"]["passed"] else END,
                                  ["preview", END])
    builder.add_edge("preview", "approval")
    builder.add_conditional_edges("approval", lambda s: "execute" if s["status"] == "approved" else
                                  "regenerate" if s["status"] == "regenerating" else
                                  "verifier" if s["status"] == "rechecking" else END,
                                  ["execute", "regenerate", "verifier", END])
    builder.add_edge("execute", END)
    return builder.compile(checkpointer=checkpointer)
