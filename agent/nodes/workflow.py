import asyncio
import time
from difflib import unified_diff

from langgraph.types import interrupt

from agent import budgets
from agent.errors import BudgetExceeded
from agent.handoffs import (
    Action,
    AnalystHandoff,
    BidDecision,
    ComplianceVerdict,
    Critique,
    FitHandoff,
    FitReport,
    JobSpec,
    PriceQuote,
    ProposalDraft,
    RiskHandoff,
    RiskReport,
    WriteRequest,
    WriteResult,
)
from agent.model import config, usage_sink
from apps.api.approvals import approval_context, stage_approval, validate_resume
from apps.api.db import Approval, put_record, transaction
from apps.api.safety import risks
from rag.verify import verify


def tracked(name, function):
    async def wrapped(state):
        limits = config()["budgets"]
        totals = budgets.reserve(state["tenant"], state["run_id"], name)
        start = time.monotonic()
        observed, result, failure = [], {}, None
        token = usage_sink.set(observed)
        try:
            timeout = min(config().get("generation", {}).get("node_timeout_seconds", 150),
                          limits["active_seconds"] - totals["active_seconds"])
            result = await asyncio.wait_for(function(state), timeout=max(.01, timeout))
        except Exception as exc:
            failure = exc
        finally:
            usage_sink.reset(token)
            elapsed = time.monotonic() - start
            totals = budgets.observe(state["tenant"], state["run_id"], elapsed,
                                     observed or result.get("usage", []), node=name)
        # An already completed effect remains a fact even when its duration exceeds a budget.
        if budgets.exceeded(totals) and name != "execute":
            raise BudgetExceeded(f"{name}: execution budget exhausted ({', '.join(budgets.exceeded(totals))})") from failure
        if failure:
            raise failure
        return {**result, "steps": 1, "active_seconds": elapsed}
    return wrapped


class Nodes:
    def __init__(self, tools, model):
        self.tools, self.model = tools, model

    async def intake(self, state):
        job = await self.tools.call("intake", "get_job", {"job_id": state["job"]["id"]})
        return {"job": JobSpec.model_validate(job).model_dump(), "status": "running"}

    async def analyst(self, state):
        result, usage = await self.model.complete("analyst", state["job"], JobSpec)
        # Immutable marketplace fields cannot be invented by the model.
        result = {**result, **{k: state["job"][k] for k in
                              ("id", "title", "description", "skills", "budget", "connects", "client_id", "screening_questions")}}
        return {"analyses": [AnalystHandoff(result=result).model_dump()],
                "usage": [usage]}

    async def risk(self, state):
        client = await self.tools.call("risk", "get_client_history", {"client_id": state["job"]["client_id"]})
        result, usage = await self.model.complete("risk", {"job": state["job"], "client": client}, RiskReport)
        result = RiskReport.model_validate(result).model_dump()
        deterministic = risks(state["job"]["description"])
        result["flags"] = sorted(set(result["flags"] + deterministic))
        if set(deterministic) & {"off_platform", "free_work"}:
            result["score"] = max(result["score"], 0.95)
        # Injection is treated as untrusted content; it cannot authorize actions.
        return {"analyses": [RiskHandoff(result=result).model_dump()], "usage": [usage]}

    async def matcher(self, state):
        matrix, evidence = {}, {}
        for skill in state["job"]["skills"]:
            matches = await self.tools.call("matcher", "search_evidence", {"requirement": skill, "k": 5})
            # Dense retrieval can return unrelated neighbours; require metadata overlap
            # before calling an explicit skill supported.
            supported = [e for e in matches if skill.casefold() in {s.casefold() for s in e["skills"]}]
            matrix[skill] = [e["id"] for e in supported]
            evidence.update({e["id"]: e for e in supported})
        fit = {"score": sum(bool(v) for v in matrix.values()) / max(len(matrix), 1),
               "matrix": matrix, "evidence": list(evidence.values())}
        return {"analyses": [FitHandoff(result=fit).model_dump()]}

    async def reconcile(self, state):
        analyses = {item["role"]: item["result"] for item in state["analyses"]}
        analyses = {"analyst": JobSpec.model_validate(analyses["analyst"]).model_dump(),
                    "risk": RiskReport.model_validate(analyses["risk"]).model_dump(),
                    "matcher": FitReport.model_validate(analyses["matcher"]).model_dump()}
        fit, risk = analyses["matcher"], analyses["risk"]
        thresholds = config()["thresholds"]
        if risk["score"] >= thresholds["max_risk"]:
            action, reason = "skip", "Risk exceeds configured threshold"
        elif not fit["evidence"] or fit["score"] < thresholds["min_fit"]:
            action, reason = "skip", "Insufficient portfolio evidence"
        elif state["job"]["budget"] < state["profile"].get("floor_fixed", 50):
            action, reason = "watch", "Budget is below profile floor"
        else:
            action, reason = "bid", "Evidence supports requirements within risk and budget thresholds"
        return {"job_spec": analyses["analyst"], "risk": risk, "fit": fit,
                "decision": BidDecision(action=action, reason=reason).model_dump(),
                "status": "running" if action == "bid" else action}

    async def pricing(self, state):
        balance = await self.tools.call("pricing", "get_connects_balance", {})
        if balance["balance"] < state["job"]["connects"]:
            raise BudgetExceeded("Insufficient Connects balance")
        result, usage = await self.model.complete("pricing", {"job": state["job"], "profile": state["profile"],
                                                              "balance": balance}, PriceQuote)
        result = PriceQuote.model_validate(result).model_dump()
        result["amount"] = max(state["profile"].get("floor_fixed", 50),
                               min(result["amount"], state["job"]["budget"]))
        result["connects"] = state["job"]["connects"]
        return {"price": PriceQuote.model_validate(result).model_dump(), "usage": [usage]}

    async def writer(self, state):
        result, usage = await self.model.complete("writer", {
            "job": state["job_spec"], "evidence": state["fit"]["evidence"], "price": state["price"],
            "critique": state.get("critique"), "memory": state.get("memory", []),
            "version": state.get("draft", {}).get("version", 0) + 1,
        }, ProposalDraft)
        result["version"] = state.get("draft", {}).get("version", 0) + 1
        return {"draft": ProposalDraft.model_validate(result).model_dump(), "usage": [usage]}

    async def verifier(self, state):
        evidence = []
        for item in state["fit"]["evidence"]:
            try:
                current = await self.tools.call("verifier", "get_case_study", {"id": item["id"]})
                evidence.append(current)
            except Exception as exc:
                # A deleted passage is a grounding failure; an unavailable server is
                # surfaced as recoverable by the worker, never counted as support.
                if "not found" not in str(exc).lower():
                    raise
        draft = ProposalDraft.model_validate(state["draft"]).model_dump()
        checked = verify(draft["text"], evidence)
        answers = {}
        for question, answer in draft.get("screening_answers", {}).items():
            if question not in state["job"].get("screening_questions", []):
                checked["unsupported_before"] += 1
                checked["claims"].append({"text": question, "label": "unsupported", "evidence_id": None,
                                          "reason": "Question is not present in the marketplace job"})
                continue
            result = verify(answer, evidence)
            checked["unsupported_before"] += result["unsupported_before"]
            checked["unsupported_after"] += result["unsupported_after"]
            checked["claims"].extend(result["claims"])
            answers[question] = result["text"]
        draft["text"] = checked["text"]
        draft["screening_answers"] = answers
        draft["evidence_ids"] = sorted({c["evidence_id"] for c in checked["claims"]
                                         if c["label"] == "supported" and c["evidence_id"]})
        return {"draft": draft, "verification": checked,
                "fit": {**state["fit"], "evidence": evidence}}

    async def critic(self, state):
        result, usage = await self.model.complete("critic", {"job": state["job"], "draft": state["draft"],
                                                            "verification": state["verification"]}, Critique)
        result = Critique.model_validate(result).model_dump()
        if not state["draft"]["text"].strip():
            result = {"passed": False, "comments": ["No grounded proposal content remains"]}
        return {"critique": Critique.model_validate(result).model_dump(), "revision": state.get("revision", 0) + (not result["passed"]),
                "usage": [usage]}

    async def compliance(self, state):
        reasons = []
        text = state["draft"]["text"] + "\n" + "\n".join(
            f"{q}\n{a}" for q, a in state["draft"].get("screening_answers", {}).items())
        reasons.extend(risks(text))
        policy = config()["policy"]
        reasons.extend(f"Banned phrase: {p}" for p in policy["banned_phrases"] if p in text.lower())
        if len(text.split()) > policy["max_proposal_words"]:
            reasons.append("Proposal exceeds configured word limit")
        if not text.strip() or not state.get("critique", {"passed": True})["passed"]:
            reasons.append("Draft did not pass critique")
        # Deterministic policy cannot be overruled by a model verdict.
        result, usage = await self.model.complete("compliance", {"draft": state["draft"], "policy": policy}, ComplianceVerdict)
        result = ComplianceVerdict.model_validate(result).model_dump()
        reasons += result["reasons"] if not result["passed"] else []
        return {"compliance": {"passed": not reasons, "reasons": reasons},
                "status": "running" if not reasons else "blocked", "usage": [usage]}

    def action(self, state):
        draft = state["draft"]
        text = draft["text"]
        for question, answer in draft.get("screening_answers", {}).items():
            text += f"\n\nScreening question: {question}\n{answer}"
        return Action(kind="message" if state.get("conversation") else "proposal",
            destination=state.get("conversation") or state["job"]["id"], text=text,
            price=state.get("price", {}).get("amount", 0), version=draft["version"],
            evidence_hashes={e["id"]: e["content_hash"] for e in state["fit"]["evidence"]
                             if e["id"] in draft["evidence_ids"]})

    def request(self, state):
        action = self.action(state)
        return WriteRequest(action=action, run_id=state["run_id"], approval_id=state.get("approval_id"),
                            idempotency_key=f"{state['run_id']}:{action.kind}:v{action.version}")

    async def preview(self, state):
        request = self.request(state)
        tool = "send_message" if state.get("conversation") else "submit_proposal"
        result = await self.tools.call("executor", tool, {"request": request.model_dump()})
        result.pop("effect_id", None)
        with transaction() as db:
            approval = stage_approval(db, state["tenant"], state["run_id"], result, approval_context(state))
            approval_id = approval.id
        return {"preview": result, "approval_id": approval_id, "status": "awaiting_approval"}

    async def approval(self, state):
        response = interrupt({"approval_id": state["approval_id"], "preview": state["preview"],
                              "draft": state["draft"], "risk": state.get("risk"),
                              "evidence": state["fit"]["evidence"], "price": state.get("price")})
        validate_resume(state, response)
        if response["decision"] == "edit":
            edit = {"before": state["draft"]["text"], "after": response["text"],
                    "diff": "".join(unified_diff(state["draft"]["text"].splitlines(keepends=True),
                        response["text"].splitlines(keepends=True), fromfile="before", tofile="after"))}
            with transaction() as db:
                put_record(db, state["tenant"], "draft_edit", state["approval_id"], edit)
            return {"draft": {**state["draft"], "text": response["text"],
                               "version": state["draft"]["version"] + 1},
                    "edit": edit, "status": "rechecking"}
        if response["decision"] == "regenerate":
            return {"edit": {"paragraph": response.get("paragraph", 0)}, "status": "regenerating"}
        return {"status": "approved" if response["decision"] == "approve" else "rejected"}

    async def regenerate(self, state):
        result, usage = await self.model.complete("writer", {
            "job": state.get("job_spec", {}), "evidence": state["fit"]["evidence"],
            "price": state.get("price", {}), "version": state["draft"]["version"] + 1,
            "regenerate_paragraph": state["edit"]["paragraph"], "previous_draft": state["draft"]}, ProposalDraft)
        paragraphs = state["draft"]["text"].split("\n\n")
        index = min(state["edit"]["paragraph"], len(paragraphs) - 1)
        paragraphs[index] = result["text"].split("\n\n")[0]
        return {"draft": {**state["draft"], "text": "\n\n".join(paragraphs),
                          "version": state["draft"]["version"] + 1}, "usage": [usage]}

    async def execute(self, state):
        request = self.request(state).model_copy(update={"dry_run": False})
        result = await self.tools.call("executor", "reconcile_write", {"idempotency_key": request.idempotency_key})
        if result:
            result = WriteResult.model_validate(result).model_dump()
            if (result["payload"] != request.action.model_dump() or result["dry_run"]
                or result["mode"] != state["preview"]["mode"]
                or result["connects_cost"] != state["preview"]["connects_cost"]):
                raise PermissionError("Reconciled effect does not match the approved action")
            return {"outcome": result, "status": result["status"]}
        # Recovery reads may confirm an existing effect even after a budget expires.
        # A new write always reserves a budgeted graph step.
        return await tracked("execute", self._execute)(state)

    async def _execute(self, state):
        request = self.request(state).model_copy(update={"dry_run": False})
        tool = "send_message" if state.get("conversation") else "submit_proposal"
        try:
            result = await self.tools.call("executor", tool, {"request": request.model_dump()})
        except Exception as exc:
            result = await self.tools.call("executor", "reconcile_write", {"idempotency_key": request.idempotency_key})
            if not result:
                if isinstance(exc, PermissionError) or getattr(exc, "code", None) == "permission_denied":
                    with transaction() as db:
                        approval = db.get(Approval, state["approval_id"])
                        if approval and approval.tenant == state["tenant"] and not approval.consumed:
                            approval.decision = "invalidated"
                raise RuntimeError("Write not confirmed; reconcile or renew approval before retry")
        result = WriteResult.model_validate(result).model_dump()
        if (result["payload"] != request.action.model_dump() or result["dry_run"]
            or result["mode"] != state["preview"]["mode"]
            or result["connects_cost"] != state["preview"]["connects_cost"]):
            raise PermissionError("Marketplace effect does not match the approved action")
        return {"outcome": result, "status": result["status"]}
