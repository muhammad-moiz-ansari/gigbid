"""Client Liaison nodes: read the thread, classify the latest message, draft a reply."""
from agent.handoffs import IntentReport, ProposalDraft
from agent.mcp_client import ToolFailure
from agent.memory.store import recall
from apps.api.safety import risks


class Liaison:
    def __init__(self, tools, model):
        self.tools, self.model = tools, model

    async def intake(self, state):
        messages = await self.tools.call("liaison", "list_messages", {"conversation": state["conversation"]})
        inbound = [m for m in messages if m.get("direction") == "inbound"]
        if not inbound:
            raise ValueError("No client message to answer")
        try:
            job = await self.tools.call("liaison", "get_job", {"job_id": state["conversation"]})
        except ToolFailure as exc:
            if exc.code != "not_found":
                raise
            job = {}
        evidence = await self.tools.call("liaison", "search_evidence", {"requirement": inbound[-1]["text"], "k": 5})
        # Each turn starts clean but keeps the draft version counter, so action keys stay unique.
        return {"messages": messages[-20:], "reply_to": inbound[-1]["id"], "job": job, "slots": [],
                "fit": {"score": 0, "matrix": {}, "evidence": evidence}, "status": "running",
                "draft": {"version": state.get("draft", {}).get("version", 0), "text": ""},
                "verification": {}, "compliance": {}, "preview": {}, "approval_id": None, "outcome": {}, "edit": {}}

    async def classify(self, state):
        text = next(m["text"] for m in state["messages"] if m["id"] == state["reply_to"])
        result, usage = await self.model.complete("intent", {"message": text, "job": state["job"]}, IntentReport)
        result = IntentReport.model_validate(result).model_dump()
        flags = risks(text)
        if set(flags) & {"off_platform", "free_work"}:
            result = {"intent": "scam", "reasons": [f"Rule check: {flag}" for flag in flags]}
        scam = result["intent"] == "scam"
        return {"intent": result["intent"], "status": "blocked" if scam else "running", "usage": [usage],
                "risk": {"score": 0.95 if scam else 0.0, "flags": flags, "reasons": result["reasons"]}}

    async def draft(self, state):
        slots = await self.tools.call("liaison", "free_slots", {}) if state["intent"] == "interview" else []
        result, usage = await self.model.complete("liaison", {
            "messages": state["messages"], "intent": state["intent"], "job": state["job"], "slots": slots,
            "evidence": state["fit"]["evidence"], "memory": await recall(state["tenant"], "style"),
            "minimum_price": state["profile"].get("floor_fixed")}, ProposalDraft)
        draft = {**result, "version": state["draft"]["version"] + 1, "screening_answers": {}}
        return {"draft": ProposalDraft.model_validate(draft).model_dump(), "slots": slots, "usage": [usage]}
