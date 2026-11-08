"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, checked } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import RunTimeline from "./RunTimeline";

type Run = components["schemas"]["RunView"];
type Doc = Record<string, any>;
type Action = (task: () => Promise<void>) => Promise<void>;

export default function RunViewer({ runs, id, busy, act, onUpdate }: {
  runs: Run[]; id?: string; busy: boolean; act: Action; onUpdate: () => Promise<void>;
}) {
  const run = runs.find(item => item.id === id);
  if (!run) return <section className="panel"><h2>Agent runs</h2>
    {runs.map(item => <div className="list-row" key={item.id}>
      <span>{item.kind === "conversation" ? "Reply" : "Bid"} · {item.subject}<small>{item.id}</small></span>
      <span className="badge">{item.status.replaceAll("_", " ")}</span>
      <Link className="inline-link" href={`/runs/${item.id}`}>Open activity ↗</Link>
    </div>)}
    {!runs.length && <p className="empty">Runs appear here once you analyse a job or a client replies.</p>}
  </section>;
  return <div className="studio-layout"><div>
    <div className="detail-heading"><h2>{run.kind === "conversation" ? "Reply" : "Bid"} · {run.subject}</h2>
      <span className="badge">{run.status.replaceAll("_", " ")}</span>
      <Link href={`/studio/${run.id}`}>Open studio ↗</Link></div>
    <RunTimeline run={run} onUpdate={onUpdate}/>
  </div><aside><Checkpoints run={run} busy={busy} act={act}/></aside></div>;
}

function Checkpoints({ run, busy, act }: { run: Run; busy: boolean; act: Action }) {
  const [items, setItems] = useState<Doc[]>([]);
  useEffect(() => {
    api.GET("/runs/{run_id}/checkpoints", { params: { path: { run_id: run.id } } })
      .then(result => setItems(result.data || [])).catch(() => setItems([]));
  }, [run.id, run.status]);
  const active = ["queued", "running"].includes(run.status);
  return <section className="panel"><h2>Replay from a checkpoint</h2>
    <p className="muted">Re-runs the graph from a saved step as a new branch. Anything already sent is reconciled, never sent twice.</p>
    {items.filter(item => item.next.length).slice(0, 15).map(item => <div className="list-row" key={item.checkpoint_id}>
      <span>Step {item.step}<small>{new Date(item.created).toLocaleString()}</small></span>
      <button className="secondary" disabled={busy || active} onClick={() => act(async () => {
        checked(await api.POST("/runs/{run_id}/replay", { params: { path: { run_id: run.id } }, body: { checkpoint_id: item.checkpoint_id } }));
      })}>Replay {item.next.join(", ")}</button>
    </div>)}
    {!items.length && <p className="empty">Saved checkpoints appear after the run starts.</p>}
  </section>;
}
