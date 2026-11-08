"use client";

import { useEffect, useRef, useState } from "react";
import { api, checked } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Run = components["schemas"]["RunView"];
type Event = components["schemas"]["RunEvent"];

export default function RunTimeline({ run, onUpdate }: { run: Run; onUpdate?: () => Promise<void> }) {
  const [events, setEvents] = useState<Event[]>([]);
  const [connection, setConnection] = useState("Loading saved events");
  const [attempt, setAttempt] = useState(0);
  const refresh = useRef(onUpdate);
  refresh.current = onUpdate;
  useEffect(() => {
    let disposed = false, source: EventSource | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const abort = new AbortController();
    setEvents([]);
    setConnection("Loading saved events");
    const merge = (items: Event[]) => setEvents(old => {
      const byId = new Map(old.map(item => [item.id, item]));
      items.forEach(item => byId.set(item.id, item));
      return [...byId.values()].sort((a, b) => a.id - b.id).slice(-1000);
    });
    async function connect() {
      try {
        let cursor = 0, more = true;
        while (more && !disposed) {
          const page = checked(await api.GET("/runs/{run_id}/history", {
            params: { path: { run_id: run.id }, query: { after: cursor, limit: 100 } },
            signal: abort.signal
          }));
          if (disposed) return;
          merge(page.events);
          cursor = page.next_cursor;
          more = page.has_more;
        }
        if (disposed) return;
        source = new EventSource(`/api/runs/${encodeURIComponent(run.id)}/events?after=${cursor}`);
        source.onopen = () => !disposed && setConnection("Live");
        source.onerror = () => !disposed && setConnection("Reconnecting — saved events will replay");
        source.addEventListener("session-expired", () => {
          source?.close();
          setConnection("Session expired — sign in again");
        });
        source.onmessage = message => {
          if (disposed) return;
          try {
            const item = JSON.parse(message.data) as Event;
            if (!Number.isSafeInteger(item.id) || typeof item.name !== "string") throw new Error();
            merge([item]);
            clearTimeout(timer);
            timer = setTimeout(() => refresh.current?.().catch(() => {
              if (!disposed) setConnection("Live — workspace refresh unavailable");
            }), 200);
          } catch {
            source?.close();
            setConnection("Event stream unavailable — retry connection");
          }
        };
      } catch (error) {
        if (!disposed) setConnection(error instanceof Error ? error.message : "Event history unavailable");
      }
    }
    void connect();
    return () => { disposed = true; abort.abort(); source?.close(); clearTimeout(timer); };
  }, [run.id, attempt]);
  const activity = events.filter(event => !event.name.startsWith("budget:"));
  return <section className="panel" aria-label="Run activity">
    <div className="panel-title"><h2>Live run activity</h2><span className="badge">{connection}</span></div>
    <p className="muted" role="status">{activity.length} saved events · actual graph work, including previous attempts.</p>
    <button type="button" className="text-button" onClick={() => setAttempt(n => n + 1)}>Reconnect and reload history</button>
    <ol className="timeline">{activity.map(event => <li key={event.id} data-event-id={event.id}>
      <span className="dot"/><div><strong>{String(event.payload.node || event.name).replace("node:", "").replaceAll(":", " · ").replaceAll("_", " ")}</strong>
      <small>{new Date(event.created * 1000).toLocaleTimeString()} · {String(event.payload.phase || event.payload.status || event.name.split(":")[0])}</small>
      {typeof event.payload.message === "string" && <p>{event.payload.message}</p>}
      {Array.isArray(event.payload.usage) && <small>{event.payload.usage.reduce((sum: number, u: {tokens?: number}) => sum + (u.tokens || 0), 0)} reported tokens</small>}
    </div></li>)}</ol>
    {!activity.length && <p className="empty">{run.status === "queued" ? "Queued. Waiting for a worker." : "No saved activity is available yet."}</p>}
    {events.length >= 1000 && <p className="muted">Showing the most recent 1,000 saved events.</p>}
    <details><summary>Usage and execution budgets</summary>
      {events.filter(event => event.name.startsWith("budget:")).map(event => <div key={event.id} className="list-row">
        <span>{event.name.replace("budget:", "")}</span><span>{(event.payload.totals as {tokens?: number})?.tokens ?? "—"} total tokens · {(event.payload.totals as {steps?: number})?.steps ?? "—"} steps</span>
      </div>)}
    </details>
    <small className="muted">Trace ID <code>{run.trace_id}</code>. A public trace link is unavailable in this workspace.</small>
  </section>;
}

