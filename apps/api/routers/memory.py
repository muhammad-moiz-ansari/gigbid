from fastapi import APIRouter, Depends

from agent.memory.store import delete_memory, list_memory
from apps.api.auth.service import current_user
from apps.api.db import User

router = APIRouter(tags=["memory"])


@router.get("/memory")
def memory(user: User = Depends(current_user)) -> list[dict]:
    return list_memory(user.id)


@router.delete("/memory/{memory_id}")
def forget(memory_id: str, user: User = Depends(current_user)) -> dict:
    delete_memory(user.id, memory_id)
    return {"deleted": memory_id}
