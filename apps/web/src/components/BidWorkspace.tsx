"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { api, checked } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import RunTimeline from "./RunTimeline";

type Run = components["schemas"]["RunView"];
type Doc = Record<string, any>;
type Action = (task: () => Promise<void>) => Promise<void>;

export function EvidenceHover({ evidence }: { evidence: Doc }) {
  return <details className="evidence" id={`evidence-${evidence.id}`}>
    <summary>{evidence.project || evidence.source} · {evidence.location}</summary>
    <blockquote>{evidence.text}</blockquote>
    <small>{evidence.source} · {evidence.date} · {evidence.skills?.join(", ")}</small>
    <span className={`badge ${evidence.synthetic ? "amber" : "green"}`}>{evidence.synthetic ? "Synthetic example" : "Uploaded evidence"}</span>
    <code>{evidence.id}</code>
  </details>;
}

function Citation({ evidence }: { evidence: Doc }) {
  const tooltipId = useId();
  const [dismissed, setDismissed] = useState(false);
  return <span className="citation" onMouseEnter={() => setDismissed(false)} onFocus={() => setDismissed(false)}
    onKeyDown={event => { if (event.key === "Escape") setDismissed(true); }}>
    <a href={`#evidence-${evidence.id}`} aria-describedby={dismissed ? undefined : tooltipId}
      onClick={() => document.getElementById(`evidence-${evidence.id}`)?.setAttribute("open", "")}>Evidence: {evidence.project || evidence.source}</a>
    <span className="citation-tooltip" style={dismissed ? {display: "none"} : undefined} role="tooltip" id={tooltipId}>
      <strong>{evidence.source} · {evidence.location}</strong><span>{evidence.text}</span>
    </span>
  </span>;
}

export default function BidWorkspace({ run, job, busy, act, analyse, onUpdate }: {
  run?: Run; job?: Doc; busy: boolean; act: Action; analyse: (id: string) => Promise<void>;
  onUpdate: () => Promise<void>;
}) {
  const state = (run?.state || {}) as Doc;
  const [draft, setDraft] = useState(""), [reason, setReason] = useState("");
  const [paragraph, setParagraph] = useState(0);
  const [tab, setTab] = useState<"preview" | "edit">("preview");
  useEffect(() => {
    setDraft(state.draft?.text || "");
    setReason("");
    setParagraph(0);
  }, [run?.id, state.draft?.version]);
  if (!run) return <section className="panel">
    <h2>{job?.title || "Opportunity not found"}</h2>
    <p>{job?.description || "Choose an opportunity from your inbox, or retry when the marketplace returns."}</p>
    {job && <button className="primary" disabled={busy} onClick={() => analyse(job.id)}>Analyse this opportunity →</button>}
    <Link className="inline-link" href="/inbox"> Back to inbox</Link>
  </section>;
  const evidence: Doc[] = state.fit?.evidence || [];
  const dirty = draft !== (state.draft?.text || "");
  const waiting = run.status === "awaiting_approval" && run.approval_status === "pending";
  const parts = run.draft_paragraphs || [];
  async function decide(decision: "approve" | "reject" | "edit" | "regenerate") {
    if (!state.approval_id) return;
    await act(async () => {
      checked(await api.POST("/approvals/{approval_id}/decision", {
        params: { path: { approval_id: state.approval_id } },
        body: { decision, paragraph, reason, text: decision === "edit" ? draft : undefined }
      }));
    });
  }
  return <>
    <div className="detail-heading"><h2>{job?.title || state.job?.title || run.subject}</h2>
      <span className={`badge ${waiting ? "amber" : "green"}`} role="status">{run.status.replaceAll("_", " ")}</span>
      <Link href={`/runs/${run.id}`}>Open run activity ↗</Link>
    </div>
    <div className="studio-layout"><div>
      <section className="panel">
        <div className="panel-title"><h2>Proposal studio</h2><span className="badge">v{state.draft?.version || "—"}</span></div>
        {!state.draft ? <p className="empty">{["skip", "watch", "blocked"].includes(run.status) ?
          state.decision?.reason || "No proposal was produced for this opportunity." :
          "The run is queued or processing. Its actual activity appears below."}</p> : <>
          <div className="button-row" role="group" aria-label="Proposal view">
            <button className="secondary" aria-pressed={tab === "preview"} onClick={() => setTab("preview")}>Grounded preview</button>
            <button className="secondary" aria-pressed={tab === "edit"} onClick={() => setTab("edit")}>Edit cover letter</button>
          </div>
          {tab === "edit" ? <><label htmlFor="draft">Your cover letter</label>
            <textarea id="draft" className="draft-editor" value={draft} maxLength={10000} readOnly={!waiting} onChange={e => setDraft(e.target.value)} rows={12}/>
            <small className="muted">{draft.split(/\s+/).filter(Boolean).length} words. Save edits to recheck before approving.</small>
          </> : <div className="proposal-preview">{parts.map((text, index) => <article key={index}>
            <p>{text}</p>
            <div className="citation-row">{evidence.filter(item => text.includes(`[${item.id}]`)).map(item => <Citation key={item.id} evidence={item}/>)}</div>
          </article>)}</div>}
          {dirty && <p role="status" className="feedback">You have unsaved edits. Approval and paragraph regeneration are disabled until these edits are saved and rechecked.</p>}
          {Object.entries(state.draft.screening_answers || {}).map(([q, a]) => <details key={q}><summary>{q}</summary><p>{String(a)}</p></details>)}
          <div className="feedback"><strong>Claim verification</strong>
            <p>{state.verification?.unsupported_before ?? "—"} unsupported passages removed · {state.verification?.unsupported_after ?? "—"} remaining by the conservative grammar check.</p>
            <details><summary>Inspect claim feedback</summary>{state.verification?.claims?.map((claim: Doc, index: number) =>
              <p key={index}><span className="badge">{claim.label}</span> {claim.reason}</p>)}</details>
          </div>
          {state.critique && <div className="feedback"><strong>Critic · {state.critique.passed ? "Passed" : "Needs work"}</strong>
            <p>{state.critique.comments.join(" · ") || "No revision requested."}</p></div>}
          {state.compliance && <div className={`feedback ${state.compliance.passed ? "" : "error"}`}>
            <strong>Compliance · {state.compliance.passed ? "Passed provisional rules" : "Blocked"}</strong>
            <p>{state.compliance.reasons.join(" · ") || "No configured policy violations found."}</p></div>}
          {run.status === "awaiting_approval" && !waiting && <div className="feedback error" role="alert">
            <strong>This review is no longer active.</strong><p>Recheck current evidence and create a fresh review before approving.</p>
            <button className="secondary" disabled={busy} onClick={() => act(async () => {
              checked(await api.POST("/runs/{run_id}/renew", { params: { path: { run_id: run.id } } }));
            })}>Recheck and renew approval</button>
          </div>}
          {waiting && <div className="approval-panel">
            <h3>Review the exact action</h3>
            <dl className="action-summary"><div><dt>Bid</dt><dd>{currency(state.preview?.payload?.price)}</dd></div>
              <div><dt>Connects cost</dt><dd>{state.preview?.connects_cost ?? "—"}</dd></div>
              <div><dt>Destination</dt><dd>{state.preview?.payload?.destination}</dd></div>
              <div><dt>Draft version</dt><dd>{state.preview?.payload?.version}</dd></div></dl>
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
            <button className="danger" disabled={busy || !reason.trim()} onClick={() => decide("reject")}>Reject proposal</button>
          </div>}
          {["submitted", "sent"].includes(run.status) && <p className="feedback" role="status">Approved action completed. Effect: {state.outcome?.effect_id || "Recorded by marketplace"}.</p>}
        </>}
        {state.error && <p role="alert" className="error">{state.error}</p>}
        {["recoverable", "needs_attention"].includes(run.status) && <div className="button-row">
          <button className="secondary" disabled={busy} onClick={() => act(async () => {
            checked(await api.POST("/runs/{run_id}/retry", { params: { path: { run_id: run.id } } }));
          })}>Retry run</button>
          {state.draft && run.status === "recoverable" && <button className="secondary" disabled={busy} onClick={() => act(async () => {
            checked(await api.POST("/runs/{run_id}/renew", { params: { path: { run_id: run.id } } }));
          })}>Recheck and renew approval</button>}
        </div>}
      </section>
      <Analysis state={state} job={job}/>
      <RunTimeline run={run} onUpdate={onUpdate}/>
    </div><aside><section className="panel"><h2>Requirement → evidence</h2>
      <p className="muted">Hover over a citation or focus it with the keyboard to inspect its passage.</p>
      {Object.entries(state.fit?.matrix || {}).map(([requirement, ids]) => <div className="matrix" key={requirement}>
        <h3>{requirement}</h3>{(ids as string[]).length ? (ids as string[]).map(id => {
          const item = evidence.find(e => e.id === id);
          return item ? <Citation key={id} evidence={item}/> : <span key={id}>Evidence unavailable</span>;
        }) : <p>No supporting portfolio evidence.</p>}
      </div>)}
      {!Object.keys(state.fit?.matrix || {}).length && <p className="empty">The evidence matrix will appear after matching completes.</p>}
    </section><section className="panel"><h2>Portfolio passages</h2>
      {evidence.map(item => <EvidenceHover key={item.id} evidence={item}/>)}
      {!evidence.length && <p className="empty">No evidence matched this opportunity.</p>}
    </section></aside></div>
  </>;
}

export const currency = (value?: number) => value == null ? "—" :
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);

function Analysis({ state, job }: { state: Doc; job?: Doc }) {
  const spec = state.job_spec || state.job || job || {};
  return <section className="panel"><h2>Structured job analysis</h2>
    <p>{spec.description || "Waiting for job intake."}</p>
    <dl className="action-summary">
      <div><dt>Decision</dt><dd>{state.decision?.action || "Pending"}</dd></div>
      <div><dt>Fit</dt><dd>{state.fit ? `${Math.round(state.fit.score * 100)}%` : "Pending"}</dd></div>
      <div><dt>Risk</dt><dd>{state.risk ? `${Math.round(state.risk.score * 100)}%` : "Pending"}</dd></div>
      <div><dt>Suggested bid</dt><dd>{currency(state.price?.amount)}</dd></div>
    </dl>
    <p>{state.decision?.reason}</p><h3>Deliverables</h3><ul>{spec.deliverables?.map((text: string) => <li key={text}>{text}</li>)}</ul>
    <p><strong>Timeline:</strong> {spec.timeline || "Unspecified"}</p>
    <h3>Needs to clarify</h3><ul>{spec.hidden_needs?.map((text: string) => <li key={text}>{text}</li>)}</ul>
    {!spec.hidden_needs?.length && <p className="muted">No additional needs identified.</p>}
    <h3>Risk reasoning</h3><p>{state.risk?.reasons?.join(" · ") || "Risk assessment pending."}</p>
    <div className="skills">{state.risk?.flags?.map((flag: string) => <span key={flag}>{flag}</span>)}</div>
    <h3>Pricing reasoning</h3><p>{state.price?.rationale || "Pricing has not completed."}</p>
    <p className="muted">{spec.connects ?? "—"} Connects to apply · {currency(spec.budget)} job budget</p>
  </section>;
}

