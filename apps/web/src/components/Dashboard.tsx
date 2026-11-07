"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, checked, setCsrf } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Session = components["schemas"]["SessionView"];
type Run = components["schemas"]["RunView"];
type Profile = components["schemas"]["Profile"];
// Domain documents are currently represented as JSON objects by the backend.
// Endpoint names, parameters and requests remain generated OpenAPI types.
type Doc = Record<string, any>;
const navigation = [["inbox", "▦", "Job inbox"], ["pipeline", "▥", "Pipeline"], ["messages", "◷", "Messages"],
  ["runs", "⌁", "Agent runs"], ["analytics", "↗", "Analytics"], ["settings", "⚙", "Settings"]];
const money = (n: number | undefined) => n == null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function EvidenceHover({ evidence }: { evidence: Doc }) {
  return <details className="evidence"><summary>{evidence.project || evidence.source} <span>↗</span></summary>
    <blockquote>{evidence.text}</blockquote><small>{evidence.source} · {evidence.location} · {evidence.date}</small>
    <div><Badge tone={evidence.synthetic ? "amber" : "green"}>{evidence.synthetic ? "Synthetic example" : "Uploaded evidence"}</Badge>
      <code>{evidence.id}</code></div></details>;
}

function RunTimeline({ run }: { run: Run }) {
  const [events, setEvents] = useState<Doc[]>([]);
  useEffect(() => {
    setEvents([]);
    const source = new EventSource(`/api/runs/${run.id}/events`);
    source.onmessage = event => { const item = JSON.parse(event.data); setEvents(old => old.some(e => e.id === item.id) ? old : [...old, item]); };
    return () => source.close();
  }, [run.id]);
  return <section className="panel"><div className="panel-title"><h2>Live run activity</h2><Badge tone="green">Persisted events</Badge></div>
    <p className="muted">Actual worker and graph events. Reconnects replay saved events.</p>
    <ol className="timeline">{events.map(e => <li key={e.id}><span className="dot"/><div><strong>{e.name.replace("node:", "").replaceAll("_", " ")}</strong>
      <small>{new Date(e.created * 1000).toLocaleTimeString()} {e.payload.status ? `· ${e.payload.status}` : ""}</small>
      {e.payload.message && <p>{e.payload.message}</p>}</div></li>)}</ol>
    {!events.length && <p className="empty">Queued. Start the worker to process this run.</p>}
    <small className="muted">Trace ID <code>{run.trace_id}</code> · Public trace pending configured Langfuse</small></section>;
}

export default function Dashboard() {
  const router = useRouter(), path = usePathname();
  const [section = "inbox", id] = path.split("/").filter(Boolean);
  const [session, setSession] = useState<Session | null>(null), [loading, setLoading] = useState(true);
  const [email, setEmail] = useState(""), [password, setPassword] = useState(""), [register, setRegister] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState<Doc[]>([]), [runs, setRuns] = useState<Run[]>([]), [status, setStatus] = useState<Doc>({});
  const [portfolio, setPortfolio] = useState<Doc[]>([]), [messages, setMessages] = useState<Doc[]>([]);
  const [pipeline, setPipeline] = useState<Doc[]>([]), [analytics, setAnalytics] = useState<Doc>({}), [memory, setMemory] = useState<Doc[]>([]);
  const [query, setQuery] = useState(""), [draft, setDraft] = useState(""), [reason, setReason] = useState("");
  const [profile, setProfile] = useState<Profile>({ name: "Freelancer", persona: "own", floor_fixed: 50, weekly_connects: 50, auto_skip: true, saved_query: "", interval_seconds: 14400 });
  const [source, setSource] = useState(""), [uploadText, setUploadText] = useState(""), [skills, setSkills] = useState("");
  const [conversation, setConversation] = useState("mock-api"), [incoming, setIncoming] = useState("");

  const refresh = useCallback(async () => {
    const s = checked(await api.GET("/status")); setStatus(s);
    setRuns(checked(await api.GET("/runs")));
    if (s.marketplace_available) setJobs(checked(await api.GET("/jobs")));
    setPortfolio(checked(await api.GET("/evidence")));
    setMessages(checked(await api.GET("/messages")));
    setPipeline(checked(await api.GET("/pipeline")));
    setAnalytics(checked(await api.GET("/analytics")));
    setMemory(checked(await api.GET("/memory")));
  }, []);
  useEffect(() => { api.GET("/auth/me").then(result => {
    if (result.data) { setSession(result.data); setCsrf(result.data.csrf); setProfile(result.data.profile as Profile); }
  }).finally(() => setLoading(false)); }, []);
  useEffect(() => { if (!session) return; refresh().catch(e => setError(e.message));
    const timer = setInterval(() => refresh().catch(e => setError(e.message)), 3500); return () => clearInterval(timer);
  }, [session, refresh]);
  const run = runs.find(r => r.id === id) || runs.find(r => r.subject === id);
  const state = (run?.state || {}) as Doc;
  const selectedJob = jobs.find(j => j.id === id || j.id === run?.subject);
  useEffect(() => { setDraft(state.draft?.text || ""); setReason(""); }, [run?.id, state.draft?.version, state.draft?.text]);
  async function act(task: () => Promise<void>) { setError(""); setNotice(""); setBusy(true); try { await task(); await refresh(); } catch (e) { setError(e instanceof Error ? e.message : "Operation failed"); } finally { setBusy(false); } }
  async function auth(e: React.FormEvent) { e.preventDefault(); setBusy(true); setError(""); try {
    const result = register ? await api.POST("/auth/register", { body: { email, password } }) : await api.POST("/auth/login", { body: { email, password } });
    const user = checked(result); setSession(user); setCsrf(user.csrf); setProfile(user.profile as Profile); setPassword(""); router.push(register ? "/settings" : "/inbox");
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }
  async function analyse(jobId: string) { await act(async () => { const result = checked(await api.POST("/jobs/{job_id}/analyse", { params: { path: { job_id: jobId } } })); router.push(`/jobs/${jobId}`); setNotice(`Run queued: ${result.id}`); }); }
  async function decision(choice: "approve" | "reject" | "edit") { if (!run || !state.approval_id) return;
    await act(async () => { checked(await api.POST("/approvals/{approval_id}/decision", { params: { path: { approval_id: state.approval_id } }, body: { decision: choice, paragraph: 0, text: choice === "edit" ? draft : undefined, reason } })); setNotice(choice === "approve" ? "Approval recorded. The worker will execute this exact action." : choice === "edit" ? "Edit saved. Grounding, Critic and Compliance checks will run again." : "Proposal rejected."); }); }

  if (loading) return <main className="auth"><p>Opening your workspace…</p></main>;
  if (!session) return <main className="auth"><div className="auth-story"><Link className="brand" href="/">g<span>↗</span> gigbid</Link><Badge tone="green">Your work, well represented</Badge>
    <h1>Find the right work.<br/><em>Make your case.</em></h1><p>A calmer way to find opportunities, show your evidence, and write proposals worth sending.</p>
    <div className="auth-principles"><span>01 &nbsp; Real portfolio evidence</span><span>02 &nbsp; A second pair of eyes</span><span>03 &nbsp; You approve every send</span></div>
    <small>Local development · Synthetic marketplace · Official integrations pending</small></div>
    <form className="auth-form" onSubmit={auth}><p className="eyebrow">YOUR FREELANCE WORKSPACE</p><h2>{register ? "Create your account" : "Welcome back"}</h2><p className="muted">Keep your next opportunity in focus.</p>
      <label>Email<input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label>Password<input type="password" minLength={12} maxLength={128} autoComplete={register ? "new-password" : "current-password"} required value={password} onChange={e => setPassword(e.target.value)} /></label>
      <small className="muted">At least 12 characters.</small>{error && <p role="alert" className="error">{error}</p>}
      <button className="primary" disabled={busy}>{busy ? "Please wait…" : register ? "Create account →" : "Sign in →"}</button>
      <button type="button" className="text-button" onClick={() => setRegister(!register)}>{register ? "Already have an account? Sign in" : "New here? Create an account"}</button></form></main>;

  const titles: Record<string, string> = { inbox: "Your next opportunity.", jobs: "A closer look.", studio: "Make a strong first impression.", pipeline: "Keep good work moving.", messages: "Keep the conversation going.", runs: "See the thinking behind it.", analytics: "Learn from what happens.", settings: "Make this workspace yours." };
  const waiting = runs.filter(r => r.status === "awaiting_approval").length;
  const shown = jobs.filter(j => `${j.title} ${j.skills.join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="shell"><aside className="sidebar"><Link href="/inbox" className="brand">g<span>↗</span> gigbid<span className="brand-dot">●</span></Link>
    <div className="workspace"><span className="avatar">{profile.name?.[0]?.toUpperCase() || "F"}</span><div><strong>{profile.name || "Freelancer"}</strong><small>Personal workspace</small></div><span>⌄</span></div>
    <p className="nav-label">WORKSPACE</p><nav aria-label="Main navigation">{navigation.map(([key, icon, label]) => <Link key={key} href={`/${key}`} className={(section === key || key === "inbox" && ["jobs", "studio"].includes(section)) ? "active" : ""}><span>{icon}</span>{label}{key === "inbox" && waiting > 0 && <b>{waiting}</b>}</Link>)}</nav>
    <div className="sidebar-note"><span className="status-dot"/> Human in the loop<p>Every proposal and message waits for your approval.</p></div>
    <div className="sidebar-bottom"><small>{session.email}</small><button className="text-button" onClick={() => act(async () => { checked(await api.POST("/auth/logout")); setSession(null); setCsrf(""); })}>Sign out ↗</button></div>
  </aside><main className="main"><header className="topbar"><span>Workspace <span className="muted"> / {section === "inbox" ? "Job inbox" : section}</span></span><div><Badge tone="amber">{status.synthetic ? "SYNTHETIC / MOCK" : status.marketplace_mode || "Loading"}</Badge><span className="top-avatar">{profile.name?.[0] || "F"}</span></div></header>
    <div className="content"><div className="page-heading"><div><p className="eyebrow">{section === "inbox" ? "LESS SCROLLING. BETTER FIT." : "YOUR FREELANCE COPILOT"}</p><h1>{titles[section] || titles.inbox}</h1><p className="muted">{section === "inbox" ? "Discover work that fits your skills. Send only what you believe in." : "Portfolio evidence, clear decisions, and your approval at every step."}</p></div>
      {section === "inbox" && <button className="primary" disabled={busy} onClick={() => act(async () => { checked(await api.POST("/dev/seed")); setNotice("Original synthetic examples loaded."); })}>＋ Load synthetic examples</button>}</div>
    {error && <div role="alert" className="alert error">{error}<button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}
    {notice && <div role="status" className="alert success">{notice}</div>}
    {status.marketplace_available === false && <div role="alert" className="alert warning"><strong>Marketplace unavailable.</strong> {status.error} Queued work is retained. Retry failed runs after recovery.</div>}
    <div className="mode-note"><span>◈</span> Development workspace · Jobs, clients and sample portfolios are synthetic. Provisional policy. Official GigSim and live integrations pending.</div>

    {section === "inbox" && <><div className="metrics"><Metric label="OPPORTUNITIES" value={jobs.length} note="In your current feed"/><Metric label="READY FOR REVIEW" value={waiting} note="Your decision comes next"/><Metric label="CONNECTS AVAILABLE" value={analytics.connects?.balance ?? "—"} note={`${analytics.connects?.spent || 0} spent · recorded mock activity`}/><Metric label="IN YOUR PIPELINE" value={pipeline.length} note="Tracked from marketplace events"/></div>
      <div className="inbox-layout"><section><div className="section-heading"><h2>Opportunity feed <span className="count">{shown.length}</span></h2><input aria-label="Filter opportunities" placeholder="⌕  Search skills or titles" value={query} onChange={e => setQuery(e.target.value)}/></div>
      <div className="feed-tabs"><span className="selected">All opportunities</span><span>{waiting} awaiting review</span><small>Ranked by analysed fit ↓</small></div>
      {!shown.length && <div className="panel empty"><h3>A little context goes a long way.</h3><p>Upload your work in Settings, or load the labelled synthetic examples to explore the workflow.</p></div>}
      {shown.map(job => <article key={job.id} className="job-card"><div className="job-top"><span className="job-icon">{job.skills[0]?.slice(0, 2)}</span><div><small>{job.client_id} <span className="muted">· synthetic client</span></small><h3><Link href={`/jobs/${job.id}`}>{job.title}</Link></h3></div><Badge tone={job.status === "skip" ? "red" : job.analysis.fit ? "green" : "neutral"}>{job.analysis.fit ? `${Math.round(job.analysis.fit.score * 100)}% fit` : "Not analysed"}</Badge></div>
        <p className="job-description">{job.description}</p><div className="skills">{job.skills.map((s: string) => <span key={s}>{s}</span>)}</div>
        <div className="job-footer"><span><strong>{money(job.budget)}</strong> <small>fixed budget</small></span><span>◈ {job.connects} Connects</span><Badge tone={job.analysis.risk?.flags?.length ? "amber" : "neutral"}>{job.analysis.risk?.flags?.join(", ") || job.status.replaceAll("_", " ")}</Badge>
          <button className="secondary" disabled={busy} onClick={() => job.run_id ? router.push(`/studio/${job.run_id}`) : analyse(job.id)}>{job.run_id ? "View analysis" : "Analyse fit"} ↗</button></div></article>)}</section>
      <aside className="right-rail"><div className="panel review-card"><div className="rail-symbol">✳</div><p className="eyebrow">YOUR JUDGMENT MATTERS</p><h2>Good proposals start with proof.</h2><p>GigBid connects each experience claim to your portfolio. You choose what leaves this workspace.</p><Link href="/settings" className="inline-link">Build your evidence library ↗</Link></div><div className="panel"><h3>Your workflow</h3><ol className="workflow-list"><li><b>1</b><span>Find your fit<small>Analyse requirements and risks</small></span></li><li><b>2</b><span>Ground your proposal<small>Show the work behind each claim</small></span></li><li><b>3</b><span>Review and approve<small>Your voice. Your final decision.</small></span></li></ol></div></aside></div></>}

    {["jobs", "studio"].includes(section) && <>{!run ? <section className="panel"><h2>{selectedJob?.title || "Select an opportunity"}</h2><p>{selectedJob?.description}</p>{selectedJob && <button className="primary" disabled={busy} onClick={() => analyse(selectedJob.id)}>Analyse this opportunity →</button>}</section> : <><div className="detail-heading"><h2>{selectedJob?.title || run.subject}</h2><Badge tone={run.status === "awaiting_approval" ? "amber" : "green"}>{run.status.replaceAll("_", " ")}</Badge><Link href={`/runs/${run.id}`}>Open run activity ↗</Link></div>
      <div className="studio-layout"><div><section className="panel"><div className="panel-title"><h2>Proposal studio</h2><Badge>v{state.draft?.version || "—"}</Badge></div>
        {!state.draft ? <p className="empty">This run is {run.status.replaceAll("_", " ")}. Start the worker and configured Ollama models to generate a proposal.</p> : <><label htmlFor="draft">Your cover letter</label><textarea id="draft" className="draft-editor" value={draft} onChange={e => setDraft(e.target.value)} rows={12}/><small className="muted">{draft.split(/\s+/).filter(Boolean).length} words · Edits need verification and a fresh approval.</small>
        {Object.entries(state.draft.screening_answers || {}).map(([q, a]) => <details key={q}><summary>{q}</summary><p>{String(a)}</p></details>)}
        <div className="feedback"><strong>Claim verification</strong><p>{state.verification?.unsupported_before ?? "—"} unsupported passages removed before review. Method: conservative exact quotations.</p></div>
        {state.critique && <div className="feedback"><strong>Critic · {state.critique.passed ? "Passed" : "Needs work"}</strong><p>{state.critique.comments.join(" · ") || "No revision requested."}</p></div>}
        {state.compliance && <div className={`feedback ${state.compliance.passed ? "" : "error"}`}><strong>Compliance · {state.compliance.passed ? "Passed provisional rules" : "Blocked"}</strong><p>{state.compliance.reasons.join(" · ")}</p></div>}
        {run.status === "awaiting_approval" && <div className="approval-panel"><h3>Review the exact action</h3><p>{money(state.preview?.payload?.price)} bid · {state.preview?.connects_cost} Connects · Destination <code>{state.preview?.payload?.destination}</code></p><details><summary>Inspect dry-run payload</summary><pre>{JSON.stringify(state.preview, null, 2)}</pre></details>
          <div className="button-row"><button className="primary" disabled={busy || draft !== state.draft.text} onClick={() => decision("approve")}>Approve exact action →</button><button className="secondary" disabled={busy || draft === state.draft.text} onClick={() => decision("edit")}>Save edit & recheck</button></div>
          <label>Rejection reason<input value={reason} onChange={e => setReason(e.target.value)} placeholder="Tell your future self why"/></label><button className="danger" disabled={busy || !reason.trim()} onClick={() => decision("reject")}>Reject proposal</button></div>}</>}
        {state.error && <p role="alert" className="error">{state.error}</p>}{["recoverable", "needs_attention"].includes(run.status) && <button className="secondary" disabled={busy} onClick={() => act(async () => { checked(await api.POST("/runs/{run_id}/retry", { params: { path: { run_id: run.id } } })); })}>Retry run</button>}</section>
        <section className="panel"><h2>Analysis & pricing</h2><p>{state.decision?.reason || "Analysis pending"}</p><p>{state.price?.rationale}</p><div className="skills">{state.risk?.flags?.map((f: string) => <Badge key={f} tone="amber">{f}</Badge>)}</div><p>{state.job_spec?.deliverables?.join(" · ")}</p></section></div>
        <aside><section className="panel"><p className="eyebrow">THE WORK BEHIND THE WORDS</p><h2>Evidence library</h2><p className="muted">Inspect each passage and its provenance before approving.</p>{state.fit?.evidence?.map((e: Doc) => <EvidenceHover key={e.id} evidence={e}/>)}
          {state.fit?.matrix && <div className="matrix">{Object.entries(state.fit.matrix).map(([skill, ids]) => <p key={skill}><strong>{skill}</strong><Badge tone={(ids as string[]).length ? "green" : "amber"}>{(ids as string[]).length} sources</Badge></p>)}</div>}</section><RunTimeline run={run}/></aside></div></>}</>}

    {section === "runs" && (id && run ? <RunTimeline run={run}/> : <section className="panel"><h2>Recorded runs</h2>{runs.length ? runs.map(r => <Link className="list-row" key={r.id} href={`/runs/${r.id}`}><span>{r.subject}<small>{r.kind} · {r.id}</small></span><Badge>{r.status.replaceAll("_", " ")}</Badge><span>↗</span></Link>) : <p className="empty">No runs yet. Analyse a job from your inbox.</p>}</section>)}
    {section === "pipeline" && <div className="kanban">{["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"].map(stage => <section key={stage}><h3>{stage} <span className="count">{pipeline.filter(p => p.status === stage).length}</span></h3>{pipeline.filter(p => p.status === stage).map(p => <Link className="panel pipeline-card" key={p.subject} href={`/jobs/${p.subject}`}><strong>{jobs.find(j => j.id === p.subject)?.title || p.subject}</strong><small>Recorded marketplace event · {p.synthetic ? "mock" : "live"}</small></Link>)}<p className="muted small">{pipeline.some(p => p.status === stage) ? "" : "No opportunities yet"}</p></section>)}</div>}
    {section === "messages" && <div className="studio-layout"><section className="panel"><h2>Client conversations</h2>{messages.length ? messages.map(m => <article key={m.id} className="message"><Badge tone={m.direction === "inbound" ? "green" : "neutral"}>{m.direction}</Badge><small>{m.conversation} · synthetic</small><p>{m.text}</p>{m.direction === "inbound" && <button className="secondary" onClick={() => act(async () => { const r = checked(await api.POST("/messages/{conversation}/draft", { params: { path: { conversation: m.conversation } } })); router.push(`/studio/${r.id}`); })}>Draft a reply for review ↗</button>}</article>) : <p className="empty">Client replies appear here. Every outgoing reply needs approval.</p>}</section><section className="panel"><Badge tone="amber">Mock controls</Badge><h2>Explore a client reply</h2><p className="muted">Create an explicitly synthetic inbound message. This does not contact anyone.</p><label>Conversation<input value={conversation} onChange={e => setConversation(e.target.value)}/></label><label>Client message<textarea rows={4} value={incoming} onChange={e => setIncoming(e.target.value)} placeholder="Could we schedule an interview?"/></label><button className="secondary" disabled={busy || !incoming.trim()} onClick={() => act(async () => { checked(await api.POST("/dev/client-message", { body: { conversation, text: incoming } })); setIncoming(""); })}>Add synthetic reply</button></section></div>}
    {section === "analytics" && <><div className="metrics"><Metric label="PROPOSALS SUBMITTED" value={analytics.submitted ?? 0} note="Recorded marketplace events"/><Metric label="REPLY RATE" value={analytics.reply_rate == null ? "—" : `${Math.round(analytics.reply_rate * 100)}%`} note="Mock only · not GigSim results"/><Metric label="HIRED" value={analytics.hired ?? 0} note="Recorded outcomes only"/><Metric label="CONNECTS SPENT" value={analytics.connects?.spent ?? 0} note="No estimated charges"/></div><section className="panel"><h2>Measured node usage</h2><p className="muted">API USD is unassigned for local compute. Official comparisons and human ratings are pending.</p><div className="table-wrap"><table><thead><tr><th>Node</th><th>Model</th><th>Tokens</th><th>Latency</th><th>API USD</th></tr></thead><tbody>{analytics.usage?.map((u: Doc, i: number) => <tr key={i}><td>{u.node}</td><td>{u.model}{u.test_double && " (TEST DOUBLE)"}</td><td>{u.tokens}</td><td>{u.latency_seconds?.toFixed(2)}s</td><td>{u.api_usd ?? "Local / unassigned"}</td></tr>)}</tbody></table></div>{!analytics.usage?.length && <p className="empty">Run an analysis to collect usage.</p>}</section></>}
    {section === "settings" && <div className="studio-layout"><div><form className="panel" onSubmit={e => { e.preventDefault(); act(async () => { const p = checked(await api.PUT("/auth/profile", { body: profile })); setProfile(p); setNotice("Profile saved."); }); }}><p className="eyebrow">ONBOARDING & PREFERENCES</p><h2>Your freelance profile</h2><label>Display name<input value={profile.name || ""} onChange={e => setProfile({ ...profile, name: e.target.value })} required/></label><label>Persona<select value={profile.persona} onChange={e => setProfile({ ...profile, persona: e.target.value as Profile["persona"] })}><option value="own">My own profile</option><option value="full-stack">Full-stack developer</option><option value="ai-ml">AI / ML engineer</option><option value="data-analyst">Data analyst</option></select></label><div className="form-grid"><label>Minimum fixed bid (USD)<input type="number" min="1" value={profile.floor_fixed} onChange={e => setProfile({ ...profile, floor_fixed: +e.target.value })}/></label><label>Weekly Connects budget<input type="number" min="0" value={profile.weekly_connects} onChange={e => setProfile({ ...profile, weekly_connects: +e.target.value })}/></label></div><label>Saved search<input value={profile.saved_query || ""} onChange={e => setProfile({ ...profile, saved_query: e.target.value })}/></label><label>Search interval (seconds)<input type="number" min="300" value={profile.interval_seconds} onChange={e => setProfile({ ...profile, interval_seconds: +e.target.value })}/></label><label className="checkbox"><input type="checkbox" checked={profile.auto_skip} onChange={e => setProfile({ ...profile, auto_skip: e.target.checked })}/> Allow low-fit auto-skip (sending always needs approval)</label><button className="primary" disabled={busy}>Save profile</button></form>
      <section className="panel"><h2>Upload your work</h2><p className="muted">Case studies, reviews and outcome-labelled proposals become inspectable evidence.</p><label>Source name<input value={source} onChange={e => setSource(e.target.value)} placeholder="case-study.md"/></label><label>Skills (comma separated)<input value={skills} onChange={e => setSkills(e.target.value)} placeholder="Python, FastAPI, Postgres"/></label><label>Portfolio text<textarea rows={5} value={uploadText} onChange={e => setUploadText(e.target.value)}/></label><button className="secondary" disabled={busy || !source.trim() || !uploadText.trim()} onClick={() => act(async () => { checked(await api.POST("/evidence", { body: { source, text: uploadText, type: "case_study", project: source, persona: profile.persona || "own", industry: "unspecified", date: new Date().toISOString().slice(0,10), outcome: "unknown", skills: skills.split(",").map(s => s.trim()).filter(Boolean) } })); setUploadText(""); setNotice("Evidence indexed. Retrieval will use the current source version."); })}>Index portfolio text</button>
      <label>Or upload a PDF / Markdown file<input type="file" accept=".pdf,.md,.txt,.json" onChange={e => { const file = e.target.files?.[0]; if (file) act(async () => { const form = new FormData(); form.append("file", file); checked(await api.POST("/evidence/file", { body: form as never, bodySerializer: body => body as unknown as FormData })); setNotice("Portfolio file indexed."); }); }}/></label>
      <button className="text-button" disabled={busy} onClick={() => act(async () => { checked(await api.POST("/dev/seed")); setNotice("Labelled synthetic examples loaded."); })}>Load synthetic examples</button></section>
      <section className="panel"><h2>Evidence sources</h2>{[...new Set(portfolio.map(e => e.source))].map(s => <div className="list-row" key={s}><span>{s}</span><button className="danger" onClick={() => act(async () => { checked(await api.DELETE("/evidence/source/{source}", { params: { path: { source: s } } })); setNotice("Source deleted; pending approvals invalidated."); })}>Delete source</button></div>)}</section></div>
      <aside><section className="panel"><h2>Connected marketplace</h2><Badge tone="amber">{status.marketplace_mode} mode</Badge><p>Switch mode in server configuration. Official GigSim requires its contract. Upwork OAuth is unavailable pending verified integration and account authorization.</p><label>Simulate marketplace condition<select aria-label="Simulate marketplace condition" defaultValue="none" onChange={e => act(async () => { checked(await api.PUT("/dev/fault", { body: { mode: e.target.value as "none" | "outage" | "rate_limit" | "timeout" | "ambiguous_write" } })); })}><option value="none">Available</option><option value="outage">Service outage</option><option value="rate_limit">Rate limited</option><option value="timeout">Timeout</option><option value="ambiguous_write">Ambiguous write response</option></select></label></section>
      <section className="panel"><h2>What GigBid remembers</h2><p className="muted">Only explicitly promoted observations. Delete an entry to exclude it from future runs.</p>{memory.length ? memory.map(m => <div className="memory" key={m.id}><Badge>{m.kind}</Badge><p>{m.rule || m.interpretation} {m.word}</p><small>{m.promotion_rule}</small><details><summary>Supporting observations</summary><pre>{JSON.stringify(m.supporting_runs || m.supporting_events, null, 2)}</pre></details><button className="danger" onClick={() => act(async () => { checked(await api.DELETE("/memory/{memory_id}", { params: { path: { memory_id: m.id } } })); })}>Forget this</button></div>) : <p className="empty">Nothing promoted yet. Style memory requires the same change in five distinct approved edits.</p>}</section></aside></div>}
    <footer>GigBid <span>Evidence first. Human always.</span><small>Local development · No live marketplace connection</small></footer></div></main></div>;
}

function Metric({ label, value, note }: { label: string; value: string | number; note: string }) {
  return <div className="metric"><p>{label}</p><strong>{value}</strong><small>{note}</small></div>;
}
