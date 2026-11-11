from fastapi import APIRouter, Depends, HTTPException

from apps.api.auth.service import current_user
from apps.api.db import User, transaction
from apps.api.routers.workflow import owned_run
from apps.api.schemas.api import ReplayInput, RunView
from worker.replay import checkpoints, queue_replay

router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}/checkpoints")
async def run_checkpoints(run_id: str, user: User = Depends(current_user)) -> list[dict]:
    with transaction() as db:
        run = owned_run(db, user.id, run_id)
    return await checkpoints(run)


@router.post("/runs/{run_id}/replay", response_model=RunView)
async def replay(run_id: str, data: ReplayInput, user: User = Depends(current_user)):
    with transaction() as db:
        run = owned_run(db, user.id, run_id)
    if data.checkpoint_id not in {item["checkpoint_id"] for item in await checkpoints(run)}:
        raise HTTPException(404, "Checkpoint not found for this run")
    return queue_replay(user.id, run_id, data.checkpoint_id)
