"""Operator replay: re-run a durable thread from one of its saved checkpoints as a new branch."""
from agent.checkpoints import checkpointer, thread_config
from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from apps.api.db import Run, transaction
from apps.api.routers.workflow import dispatch, view


async def checkpoints(run):
    """Saved checkpoints of a run, newest first, with the node each one would run next."""
    async with checkpointer() as saver:
        graph = (build_bid_graph if run.kind == "bid" else build_conversation_graph)(None, None, saver)
        return [{"checkpoint_id": snap.config["configurable"]["checkpoint_id"], "step": snap.metadata.get("step"),
                 "next": list(snap.next), "created": snap.created_at}
                async for snap in graph.aget_state_history(thread_config(run.tenant, run.id))]


def queue_replay(tenant, run_id, checkpoint_id):
    with transaction() as db:
        run = db.get(Run, run_id)
        if not run or run.tenant != tenant:
            raise PermissionError("Run is not owned by this tenant")
        if run.status in ("queued", "running"):
            raise ValueError("Wait for the current run to finish before replaying it")
        run.resume, run.status, run.lease_until = {"decision": "replay", "checkpoint_id": checkpoint_id}, "queued", 0
        result = view(run)
    dispatch(run_id)
    return result


async def cli(run_id, node=None):
    with transaction() as db:
        run = db.get(Run, run_id)
    if not run:
        raise SystemExit("Run not found")
    history = await checkpoints(run)
    if not node:
        for item in history:
            print(item["checkpoint_id"], f"step {item['step']}", ", ".join(item["next"]) or "(end)")
        return
    target = next((item for item in history if node in item["next"]), None)
    if not target:
        raise SystemExit(f"No saved checkpoint runs {node} next")
    queue_replay(run.tenant, run.id, target["checkpoint_id"])
    print(f"Queued a replay of {run_id} from {node}; the worker will run it.")
