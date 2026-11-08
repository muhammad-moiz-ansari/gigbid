"use client";

import { useEffect, useState } from "react";
import { api, checked } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { currency } from "@/lib/format";

type Run = components["schemas"]["RunView"];
type Doc = Record<string, any>;
type Action = (task: () => Promise<void>) => Promise<void>;

export default function ApprovalPanel({ run, draft, dirty, busy, act }: {
  run: Run; draft: string; dirty: boolean; busy: boolean; act: Action;
}) {
  const state = run.state as Doc, reply = run.kind === "conversation";
  const [paragraph, setParagraph] = useState(0), [reason, setReason] = useState("");
  useEffect(() => { setParagraph(0); setReason(""); }, [run.id, state.draft?.version]);
  const parts = run.draft_paragraphs || [];
  const waiting = run.status === "awaiting_approval" && run.approval_status === "pending";
  async function decide(decision: "approve" | "reject" | "edit" | "regenerate") {
    await act(async () => {
      checked(await api.POST("/approvals/{approval_id}/decision", {
        params: { path: { approval_id: state.approval_id } },
        body: { decision, paragraph, reason, text: decision === "edit" ? draft : undefined }
      }));
    });
  }
  if (run.status === "awaiting_approval" && !waiting) return <div className="feedback error" role="alert">
    <strong>This review is no longer active.</strong><p>Recheck current evidence and create a fresh review before approving.</p>
    <button className="secondary" disabled={busy} onClick={() => act(async () => {
      checked(await api.POST("/runs/{run_id}/renew", { params: { path: { run_id: run.id } } }));
    })}>Recheck and renew approval</button>
  </div>;
  if (!waiting) return null;
  return <div className="approval-panel">
    <h3>Review the exact action</h3>
    <dl className="action-summary">{reply ? <>
      <div><dt>Send reply to</dt><dd>{state.preview?.payload?.destination}</dd></div>
      <div><dt>Client intent</dt><dd>{state.intent}</dd></div>
    </> : <>
      <div><dt>Bid</dt><dd>{currency(state.preview?.payload?.price)}</dd></div>
      <div><dt>Connects cost</dt><dd>{state.preview?.connects_cost ?? "—"}</dd></div>
      <div><dt>Destination</dt><dd>{state.preview?.payload?.destination}</dd></div>
    </>}<div><dt>Draft version</dt><dd>{state.preview?.payload?.version}</dd></div></dl>
    <p className="muted">Nothing is sent or spent until you approve this exact action.</p>
    <details><summary>Inspect dry-run payload</summary><pre>{JSON.stringify(state.preview, null, 2)}</pre></details>
    <div className="button-row"><button className="primary" disabled={busy || dirty} onClick={() => decide("approve")}>Approve exact action →</button>
      <button className="secondary" disabled={busy || !dirty || !draft.trim()} onClick={() => decide("edit")}>Save edit & recheck</button></div>
    <label htmlFor="paragraph">Paragraph to regenerate</label>
    <select id="paragraph" value={paragraph} onChange={e => setParagraph(Number(e.target.value))}>
      {parts.map((text, index) => <option key={index} value={index}>Paragraph {index + 1}: {text.slice(0, 65)}</option>)}
    </select>
    <button className="secondary" disabled={busy || dirty || !parts.length} onClick={() => decide("regenerate")}>Regenerate selected paragraph</button>
    <p className="muted">Regeneration runs evidence, Critic and Compliance checks again and requires a new approval.</p>
    <label htmlFor="rejection-reason">Rejection reason</label><input id="rejection-reason" value={reason} maxLength={1000} onChange={e => setReason(e.target.value)}/>
    <button className="danger" disabled={busy || !reason.trim()} onClick={() => decide("reject")}>{reply ? "Reject reply" : "Reject proposal"}</button>
  </div>;
}
