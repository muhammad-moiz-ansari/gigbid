"""Live Upwork marketplace through Upwork's official MCP server, behind the same port as the mock.

A write needs an approved, unconsumed GigBid approval: a proposal becomes an Upwork draft that you
confirm on Upwork (Connects are spent only then), and a message is sent. Under Upwork's API & MCP
Terms, search details are cached for at most 24 hours and Upwork outputs never enter memory or evidence.
"""
import asyncio
import json
import re
import time
from datetime import datetime, timezone

from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.handoffs import JobSpec, WriteRequest, WriteResult
from agent.marketplace_port import (
    AdapterReadiness,
    AmbiguousWrite,
    Capabilities,
    NotFound,
    Unavailable,
)
from agent.model import config
from apps.api.db import Approval, User, get_record, put_record, transaction

# The only Upwork tools and actions GigBid calls; profile, permission, offer and confirm tools are never used.
# acknowledge_policy runs only from the user's explicit confirmation in Settings.
ALLOWED = {("list_accounts", None), ("find_jobs", "search"), ("find_jobs", "smart_search"), ("find_jobs", "get"),
           ("get_profile", "connects_balance"), ("get_messages", "list_rooms"), ("get_messages", "list_messages"),
           ("list_freelancer_proposals", "list"), ("list_freelancer_proposals", "invitations"),
           ("manage_proposals", "create"), ("manage_proposals", "acknowledge_policy"), ("send_message", "send")}
CACHE_SECONDS = 24 * 3600  # Upwork API & MCP Terms 8.3
DURATIONS = ("less_than_1_month", "1_to_3_months", "3_to_6_months", "more_than_6_months")
STAGES = {"Accepted": "submitted", "Offered": "interview", "Hired": "hired", "Activated": "hired",
          "Declined": "lost", "Withdrawn": "lost", "Archived": "lost"}


def payload(result):
    if result.isError:
        raise Unavailable("Upwork refused the request: " + " ".join(getattr(b, "text", "") for b in result.content)[:800])
    if result.structuredContent:
        return result.structuredContent
    return json.loads("\n".join(getattr(b, "text", "") for b in result.content) or "{}")


def number(text):
    """The first amount in Upwork's budget text ("$500", "$15.00-$30.00"); 0 when there is none."""
    found = re.search(r"\d[\d,]*(?:\.\d+)?", str(text or ""))
    return float(found.group().replace(",", "")) if found else 0.0


def split_answers(text):
    """GigBid appends screening answers to the outgoing text; Upwork takes them as a separate list."""
    letter, *blocks = text.split("\n\nScreening question: ")
    return letter, [dict(zip(("question", "answer"), block.split("\n", 1))) for block in blocks]


class UpworkAdapter:
    capabilities = Capabilities(search=True, drafts=True, messages=True, reconciliation=True, client_history=True,
                                connects=True, proposals=True, events=True)
    readiness = AdapterReadiness(mode="upwork", implemented=True, contract_verified=True, externally_verified=False,
                                 synthetic=False, detail="Upwork's official MCP server with the signed-in user's OAuth "
                                 "token; reads checked live; a live draft passed Upwork's policy and terms "
                                 "checks and stopped at the account's Connects balance")

    def _call(self, tenant, tool, action=None, params=None):
        """One call to Upwork's MCP server as this user; anything outside ALLOWED is refused."""
        if (tool, action) not in ALLOWED:
            raise PermissionError(f"GigBid does not call upwork__{tool} {action or ''}".strip())
        return asyncio.run(self._session(tenant, tool, action, params or {}))

    async def _session(self, tenant, tool, action, params):
        from apps.api.auth.upwork import access_token
        client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": config()["upwork"]["mcp_url"],
                                                  "headers": {"Authorization": f"Bearer {await access_token(tenant)}"}}})
        try:
            async with client.session("upwork") as session:
                arguments = {"action": action, "org_uid": await self._org(tenant, session), "params": params} if action else {}
                return payload(await session.call_tool(f"upwork__{tool}", arguments))
        except ExceptionGroup as group:
            raise group.exceptions[0] from None

    async def _org(self, tenant, session):
        """The user's freelancer account id, an identifier Upwork lets apps store."""
        with transaction() as db:
            saved = get_record(db, tenant, "upwork_org", "freelancer")
        if saved:
            return saved.value["org_uid"]
        accounts = payload(await session.call_tool("upwork__list_accounts", {}))["accounts"]
        org = next((a["org_uid"] for a in accounts if a.get("role") == "TALENT"), accounts[0]["org_uid"])
        with transaction() as db:
            put_record(db, tenant, "upwork_org", "freelancer", {"org_uid": org})
        return org

    def _cached(self, tenant, job_id):
        with transaction() as db:
            saved = get_record(db, tenant, "upwork_cache", job_id)
            return saved.value if saved and time.time() - saved.value["at"] < CACHE_SECONDS else {}

    def search(self, tenant: str, query: str = "") -> list[JobSpec]:
        # Without a query, Upwork's own recommendations for the profile; GigBid does not rank live jobs.
        found = self._call(tenant, "find_jobs", "search" if query else "smart_search",
                           {"query": query, "limit": 10} if query else {"limit": 10})
        jobs = found.get("jobs") or []
        with transaction() as db:
            for job in jobs:
                put_record(db, tenant, "upwork_cache", str(job["id"]),
                           {"skills": job.get("skills") or [], "client": job.get("client") or {},
                            "duration": job.get("duration") or "", "at": time.time()})
        return [JobSpec(id=str(j["id"]), title=j.get("title", ""), description=j.get("description_snippet", ""),
                        skills=j.get("skills") or [], budget=number(j.get("budget")), connects=0, client_id=str(j["id"]))
                for j in jobs]

    def job(self, tenant: str, job_id: str) -> JobSpec:
        detail = self._call(tenant, "find_jobs", "get", {"id": job_id})
        posting = (detail.get("data") or {}).get("marketplaceJobPosting")
        if not posting:
            raise NotFound("Upwork job not found")
        content, terms = posting.get("content") or {}, posting.get("contractTerms") or {}
        amount = (terms.get("fixedPriceContractTerms") or {}).get("amount") or {}
        questions = [q.get("question", "") for q in posting.get("questions") or [] if isinstance(q, dict)]
        return JobSpec(id=str(job_id), title=content.get("title", ""), description=content.get("description", ""),
                       skills=self._cached(tenant, job_id).get("skills", []), client_id=str(job_id),
                       budget=number(" ".join(str(v) for v in amount.values())),
                       connects=int(detail.get("connects_cost") or 0), screening_questions=[q for q in questions if q])

    def client_history(self, tenant: str, client_id: str):
        record = self._call(tenant, "find_jobs", "get", {"id": client_id}).get("client_record") or {}
        client = self._cached(tenant, client_id).get("client", {})
        return {"id": client_id, "verified": str(client.get("verification_status", "")).upper() == "VERIFIED",
                "spend": float(client.get("total_spent") or 0), "hires": int(record.get("jobs_with_hires") or 0),
                "synthetic": False}

    def balance(self, tenant: str):
        data = self._call(tenant, "get_profile", "connects_balance", {"limit": 25})
        with transaction() as db:
            cap = db.get(User, tenant).profile.get("weekly_connects", 50)
        # Drafts spend nothing in GigBid; Upwork spends Connects when you confirm a draft on Upwork.
        return {"balance": int((data.get("balance") or {}).get("connectsBalance") or 0), "spent": 0, "weekly_spent": 0,
                "weekly_limit": cap, "week": datetime.now(timezone.utc).strftime("%G-W%V")}

    def proposal(self, tenant: str, proposal_id: str):
        raise Unavailable("Open live proposals on Upwork; GigBid reads their status through pipeline events")

    def messages(self, tenant: str, conversation: str):
        data = self._call(tenant, "get_messages", "list_messages", {"room_id": conversation, "limit": 20})
        stories = (data.get("data") or data).get("messages") or []
        return [{"id": str(m.get("story_id") or m.get("id")), "conversation": conversation,
                 "text": m.get("message") or m.get("text") or "", "synthetic": False,
                 "direction": "outbound" if m.get("from_self") else "inbound"} for m in reversed(stories)]

    def events(self, tenant: str, after: int = 0):
        """Proposal status changes and rooms waiting for your reply; ids are stable, so repeats are skipped."""
        now, events = int(time.time()), []
        listed = self._call(tenant, "list_freelancer_proposals", "list", {"limit": 25})
        for edge in ((listed.get("data") or {}).get("vendorProposals") or {}).get("edges") or []:
            node = edge.get("node") or edge
            job_id = str((node.get("job") or node.get("jobPosting") or {}).get("id") or node.get("job_id") or "")
            stage = "viewed" if node.get("viewedByClient") and node.get("status") == "Accepted" else STAGES.get(node.get("status"))
            if job_id and stage:
                events.append({"id": f"{node.get('id')}:{stage}", "sequence": now, "subject": job_id, "kind": "proposal",
                               "proposal_id": str(node.get("id")), "status": stage, "synthetic": False})
        rooms = ((self._call(tenant, "get_messages", "list_rooms", {"limit": 20}).get("data") or {}).get("rooms")) or []
        for room in rooms:
            if room.get("awaiting_reply_from") == "you":
                last = room.get("last_message_id") or room.get("last_message_time") or now
                events.append({"id": f"{room.get('id')}:{last}", "sequence": now, "subject": str(room.get("id")),
                               "kind": "message", "proposal_id": None, "status": "received", "synthetic": False})
        return events

    def write(self, tenant: str, request: WriteRequest) -> WriteResult:
        from apps.api.approvals import lock_decision, validate_approval
        request, action = WriteRequest.model_validate(request), request.action
        if action.kind not in ("proposal", "message"):
            raise ValueError("Upwork live mode supports proposal drafts and messages only")
        job = self.job(tenant, action.destination) if action.kind == "proposal" else None
        preview = {"mode": "upwork", "dry_run": True, "payload": action.model_dump(),
                   "connects_cost": job.connects if job else 0, "status": "preview",
                   "terms": self._terms(tenant, job) if job else {}}
        if request.dry_run:
            return WriteResult(**preview)
        with transaction() as db:
            lock_decision(db, tenant)
            prior = get_record(db, tenant, "idempotency", request.idempotency_key)
            if prior:
                if prior.value.get("result"):
                    return WriteResult.model_validate(prior.value["result"])
                raise AmbiguousWrite(request.idempotency_key)
            approval_id = validate_approval(db, tenant, request, preview, job.model_dump() if job else None).id
            put_record(db, tenant, "idempotency", request.idempotency_key, {"in_flight": True})
        try:
            if action.kind == "proposal":
                self._no_existing(tenant, action.destination)
                letter, answers = split_answers(action.text)
                made = self._call(tenant, "manage_proposals", "create", {"job_reference": action.destination,
                                  "cover_letter": letter, "charged_amount": action.price, "answers": answers,
                                  **preview["terms"]})
                effect, status = made.get("preview_id") or (made.get("preview") or {}).get("preview_id"), "drafted"
                if not effect:
                    # Upwork answers some requests with a next step instead of a draft; nothing was built.
                    raise Unavailable(f"Upwork built no draft: {made.get('next_step') or made.get('status')}")
            else:
                sent = self._call(tenant, "send_message", "send", {"room_id": action.destination, "message": action.text})
                effect, status = sent.get("story_id") or sent.get("id"), "sent"
        except Unavailable:
            # Upwork refused the request, so nothing was created and a later retry is safe.
            with transaction() as db:
                db.delete(get_record(db, tenant, "idempotency", request.idempotency_key))
            raise
        result = WriteResult(mode="upwork", dry_run=False, payload=action.model_dump(), status=status,
                             connects_cost=preview["connects_cost"], effect_id=str(effect or request.idempotency_key),
                             terms=preview["terms"])
        with transaction() as db:
            put_record(db, tenant, "idempotency", request.idempotency_key, {"result": result.model_dump()})
            db.get(Approval, approval_id).consumed = True
        return result

    def _terms(self, tenant, job):
        """Fixed-price draft terms Upwork requires: the posted duration (or the configured one) and payment mode."""
        if job.budget <= 0:
            raise Unavailable("GigBid drafts fixed-price Upwork jobs only; hourly terms are not supported yet")
        rules, posted = config()["upwork"], str(self._cached(tenant, job.id).get("duration", "")).lower().replace(" ", "_")
        return {"estimated_duration": posted if posted in DURATIONS else rules["default_duration"],
                "payment_mode": rules["payment_mode"]}

    def acknowledge_policy(self, tenant):
        """Records Upwork's payment-policy acknowledgement after the user confirms it in Settings."""
        return self._call(tenant, "manage_proposals", "acknowledge_policy")

    def _no_existing(self, tenant, job_id):
        """Upwork requires checking for an invitation or an earlier proposal before preparing a draft."""
        for action in ("invitations", "list"):
            if job_id in json.dumps(self._call(tenant, "list_freelancer_proposals", action, {"limit": 25})):
                raise Unavailable("You already have an Upwork invitation or proposal for this job; continue it on Upwork")

    def reconcile(self, tenant: str, key: str) -> WriteResult | None:
        with transaction() as db:
            prior = get_record(db, tenant, "idempotency", key)
            return WriteResult.model_validate(prior.value["result"]) if prior and prior.value.get("result") else None
