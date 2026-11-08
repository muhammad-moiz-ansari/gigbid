"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import BidWorkspace from "./BidWorkspace";
import Onboarding from "./Onboarding";
import RunTimeline from "./RunTimeline";
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

export default function Dashboard() {
  const router = useRouter(), path = usePathname();
  const [section = "inbox", id] = path.split("/").filter(Boolean);
  const [session, setSession] = useState<Session | null>(null), [loading, setLoading] = useState(true);
  const [email, setEmail] = useState(""), [password, setPassword] = useState(""), [register, setRegister] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState<Doc[]>([]), [runs, setRuns] = useState<Run[]>([]), [status, setStatus] = useState<Doc>({});
  const [portfolio, setPortfolio] = useState<Doc[]>([]), [messages, setMessages] = useState<Doc[]>([]);
  const [pipeline, setPipeline] = useState<Doc[]>([]), [analytics, setAnalytics] = useState<Doc>({}), [memory, setMemory] = useState<Doc[]>([]);
  const [query, setQuery] = useState(""), [decisionFilter, setDecisionFilter] = useState("all");
  const [refreshing, setRefreshing] = useState(false), [loaded, setLoaded] = useState(false);
  const inflight = useRef<Promise<void> | null>(null);
  const workspaceEpoch = useRef(0);
  const [profile, setProfile] = useState<Profile>({ name: "Freelancer", persona: "own", floor_fixed: 50, weekly_connects: 50, auto_skip: true, saved_query: "", interval_seconds: 14400, hourly_rate: 50, min_budget: 0, required_skills: [] });
  const [conversation, setConversation] = useState("mock-api"), [incoming, setIncoming] = useState("");

  const clearWorkspace = useCallback(() => {
    workspaceEpoch.current += 1;
    inflight.current = null;
    setJobs([]); setRuns([]); setPortfolio([]); setMessages([]); setPipeline([]);
    setAnalytics({}); setMemory([]); setStatus({}); setLoaded(false);
    setRegister(false);
    setQuery(""); setDecisionFilter("all"); setError(""); setNotice(""); setRefreshing(false);
  }, []);
  const refresh = useCallback((): Promise<void> => {
    if (inflight.current) return inflight.current;
    const epoch = workspaceEpoch.current;
    setRefreshing(true);
    inflight.current = (async () => {
      const [s, r, e] = await Promise.all([api.GET("/status"), api.GET("/runs"), api.GET("/evidence")]);
      if (epoch !== workspaceEpoch.current) return;
      const current = checked(s);
      setStatus(current); setRuns(checked(r)); setPortfolio(checked(e));
      if (current.marketplace_available) {
        const data = checked(await api.GET("/jobs"));
        if (epoch !== workspaceEpoch.current) return;
        setJobs(data);
      }
      const optional = await Promise.allSettled([
        api.GET("/messages"), api.GET("/pipeline"), api.GET("/analytics"), api.GET("/memory")
      ]);
      if (epoch !== workspaceEpoch.current) return;
      const setters = [setMessages, setPipeline, setAnalytics, setMemory];
      optional.forEach((result, index) => {
        if (result.status === "fulfilled" && result.value.response.ok) setters[index](result.value.data as never);
      });
      setLoaded(true);
    })().catch(error => {
      if (epoch !== workspaceEpoch.current) return;
      if (error?.status === 401) { clearWorkspace(); setSession(null); setCsrf(""); }
      throw error;
    }).finally(() => {
      if (epoch === workspaceEpoch.current) { setRefreshing(false); inflight.current = null; }
    });
    return inflight.current;
  }, [clearWorkspace]);
  useEffect(() => { api.GET("/auth/me").then(result => {
    if (result.data) { setSession(result.data); setCsrf(result.data.csrf); setProfile(result.data.profile as Profile); }
  }).catch(() => setError("Unable to connect. Check the API and try signing in.")).finally(() => setLoading(false)); }, []);
  useEffect(() => { if (!session) return; refresh().catch(e => setError(e.message));
    const timer = setInterval(() => refresh().catch(e => setError(e.message)), 3500); return () => clearInterval(timer);
  }, [session, refresh]);
  const run = runs.find(r => r.id === id) || runs.find(r => r.subject === id);
  const selectedJob = jobs.find(j => j.id === id || j.id === run?.subject);
  async function act(task: () => Promise<void>) { setError(""); setNotice(""); setBusy(true); try { const epoch = workspaceEpoch.current; await task(); if (epoch === workspaceEpoch.current) await refresh(); } catch (e) { setError(e instanceof Error ? e.message : "Operation failed"); } finally { setBusy(false); } }
  async function auth(e: React.FormEvent) { e.preventDefault(); setBusy(true); setError(""); try {
    const result = register ? await api.POST("/auth/register", { body: { email, password } }) : await api.POST("/auth/login", { body: { email, password } });
    const user = checked(result); clearWorkspace(); setSession(user); setCsrf(user.csrf); setProfile(user.profile as Profile); setPassword(""); router.push(register ? "/settings" : "/inbox");
  } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }
  async function analyse(jobId: string) { await act(async () => { const result = checked(await api.POST("/jobs/{job_id}/analyse", { params: { path: { job_id: jobId } } })); router.push(`/jobs/${jobId}`); setNotice(`Run queued: ${result.id}`); }); }

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
  const waiting = runs.filter(r => r.status === "awaiting_approval" && r.approval_status === "pending").length;
  const shown = jobs.filter(j => {
    const terms = (query + " " + (profile.saved_query || "")).toLowerCase().split(/\s+/).filter(Boolean);
    const searchable = (j.title + " " + j.description + " " + j.skills.join(" ")).toLowerCase();
    return terms.every(term => searchable.includes(term)) && j.budget >= (profile.min_budget || 0) &&
      (profile.max_connects == null || j.connects <= profile.max_connects) &&
      (profile.required_skills || []).map(skill => skill.trim().toLowerCase()).filter(Boolean).every(skill =>
        j.skills.some((value: string) => value.toLowerCase() === skill)) &&
      (decisionFilter === "all" || (decisionFilter === "awaiting_approval" ? j.status === decisionFilter :
        decisionFilter === "unanalysed" ? !j.analysis.decision : j.analysis.decision?.action === decisionFilter));
  }).sort((a, b) => (b.analysis.fit?.score ?? -1) - (a.analysis.fit?.score ?? -1));
  return <div className="shell"><a className="skip-link" href="#main-content">Skip to main content</a><aside className="sidebar"><Link href="/inbox" className="brand">g<span>↗</span> gigbid<span className="brand-dot">●</span></Link>
    <div className="workspace"><span className="avatar">{profile.name?.[0]?.toUpperCase() || "F"}</span><div><strong>{profile.name || "Freelancer"}</strong><small>Personal workspace</small></div><span>⌄</span></div>
    <p className="nav-label">WORKSPACE</p><nav aria-label="Main navigation">{navigation.map(([key, icon, label]) => <Link aria-current={(section === key || key === "inbox" && ["jobs", "studio"].includes(section)) ? "page" : undefined} key={key} href={`/${key}`} className={(section === key || key === "inbox" && ["jobs", "studio"].includes(section)) ? "active" : ""}><span>{icon}</span>{label}{key === "inbox" && waiting > 0 && <b>{waiting}</b>}</Link>)}</nav>
    <div className="sidebar-note"><span className="status-dot"/> Human in the loop<p>Every proposal and message waits for your approval.</p></div>
    <div className="sidebar-bottom"><small>{session.email}</small><button className="text-button" onClick={() => act(async () => { checked(await api.POST("/auth/logout")); clearWorkspace(); setSession(null); setCsrf(""); })}>Sign out ↗</button></div>
  </aside><main className="main" id="main-content" tabIndex={-1}><header className="topbar"><span>Workspace <span className="muted"> / {section === "inbox" ? "Job inbox" : section}</span></span><div><Badge tone="amber">{status.synthetic ? "SYNTHETIC / MOCK" : status.marketplace_mode || "Loading"}</Badge><button className="text-button" disabled={refreshing} onClick={() => refresh().catch(e => setError(e.message))}>{refreshing ? "Refreshing…" : "Refresh workspace"}</button><span className="top-avatar">{profile.name?.[0] || "F"}</span></div></header>
    <div className="content"><div className="page-heading"><div><p className="eyebrow">{section === "inbox" ? "LESS SCROLLING. BETTER FIT." : "YOUR FREELANCE COPILOT"}</p><h1>{titles[section] || titles.inbox}</h1><p className="muted">{section === "inbox" ? "Discover work that fits your skills. Send only what you believe in." : "Portfolio evidence, clear decisions, and your approval at every step."}</p></div>
      {section === "inbox" && <button className="primary" disabled={busy} onClick={() => act(async () => { checked(await api.POST("/dev/seed")); setNotice("Original synthetic examples loaded."); })}>＋ Load synthetic examples</button>}</div>
    {error && <div role="alert" className="alert error">{error}<button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}
    {notice && <div role="status" className="alert success">{notice}</div>}
    {status.marketplace_available === false && <div role="alert" className="alert warning"><strong>Marketplace unavailable.</strong> {status.error} Queued work is retained. Retry failed runs after recovery.</div>}
    <div className="mode-note"><span>◈</span>{status.synthetic ? "Synthetic marketplace · Jobs, clients and sample portfolios are authored development examples." : "Configured marketplace · Check integration readiness before proceeding."} Uploaded portfolio evidence retains its own provenance. Policy remains provisional.</div>
    {!loaded && <p role="status" className="panel">{error ? "Workspace data is unavailable. Use Refresh workspace to retry." : "Loading workspace data…"}</p>}

    {section === "inbox" && <><div className="metrics"><Metric label="OPPORTUNITIES" value={jobs.length} note="In your current feed"/><Metric label="READY FOR REVIEW" value={waiting} note="Your decision comes next"/><Metric label="CONNECTS AVAILABLE" value={analytics.connects?.balance ?? "—"} note={`${analytics.connects?.spent || 0} spent · recorded mock activity`}/><Metric label="IN YOUR PIPELINE" value={pipeline.length} note="Tracked from marketplace events"/></div>
      <div className="inbox-layout"><section><div className="section-heading"><h2>Opportunity feed <span className="count">{shown.length}</span></h2><input aria-label="Filter opportunities" placeholder="⌕  Search skills or titles" value={query} onChange={e => setQuery(e.target.value)}/></div>
      <div className="feed-tabs"><span className="selected">All opportunities</span><span>{waiting} awaiting review</span><small>Ranked by analysed fit ↓ · saved filters applied</small></div>
      <div className="filter-row"><label htmlFor="decision-filter">Decision filter</label><select id="decision-filter" value={decisionFilter} onChange={e => setDecisionFilter(e.target.value)}>
        <option value="all">All decisions</option><option value="awaiting_approval">Awaiting review</option><option value="bid">Bid</option><option value="watch">Watch</option><option value="skip">Skip</option><option value="unanalysed">Not analysed</option>
      </select><Link className="inline-link" href="/settings">Edit saved budget and skill filters</Link></div>
      {!shown.length && loaded && <div className="panel empty"><h3>{jobs.length ? "No opportunities match your filters." : "Your opportunity feed is empty."}</h3>
        <p>{jobs.length ? "Adjust the search or saved filters in Settings to see more opportunities." : "Load labelled synthetic examples to explore the workflow, and add your own portfolio in Settings."}</p></div>}
      {shown.map(job => <article key={job.id} className="job-card"><div className="job-top"><span className="job-icon">{job.skills[0]?.slice(0, 2)}</span><div><small>{job.client_id} <span className="muted">· synthetic client</span></small><h3><Link href={`/jobs/${job.id}`}>{job.title}</Link></h3></div><Badge tone={job.status === "skip" ? "red" : job.analysis.fit ? "green" : "neutral"}>{job.analysis.fit ? `${Math.round(job.analysis.fit.score * 100)}% fit` : "Not analysed"}</Badge></div>
        <p className="job-description">{job.description}</p><div className="skills">{job.skills.map((s: string) => <span key={s}>{s}</span>)}</div>
        <div className="job-footer"><span><strong>{money(job.budget)}</strong> <small>fixed budget</small></span><span>◈ {job.connects} Connects</span><Badge tone={job.analysis.risk?.flags?.length ? "amber" : "neutral"}>{job.analysis.risk?.flags?.join(", ") || job.status.replaceAll("_", " ")}</Badge>
          <span>Bid {money(job.analysis.price?.amount)}</span><span>Action: {job.analysis.decision?.action || "Pending"}</span><button className="secondary" disabled={busy} onClick={() => job.run_id ? router.push(`/studio/${job.run_id}`) : analyse(job.id)}>{job.run_id ? "View analysis" : "Analyse fit"} ↗</button></div></article>)}</section>
      <aside className="right-rail"><div className="panel review-card"><div className="rail-symbol">✳</div><p className="eyebrow">YOUR JUDGMENT MATTERS</p><h2>Good proposals start with proof.</h2><p>GigBid connects each experience claim to your portfolio. You choose what leaves this workspace.</p><Link href="/settings" className="inline-link">Build your evidence library ↗</Link></div><div className="panel"><h3>Your workflow</h3><ol className="workflow-list"><li><b>1</b><span>Find your fit<small>Analyse requirements and risks</small></span></li><li><b>2</b><span>Ground your proposal<small>Show the work behind each claim</small></span></li><li><b>3</b><span>Review and approve<small>Your voice. Your final decision.</small></span></li></ol></div></aside></div></>}

    {loaded && ["jobs", "studio"].includes(section) && <BidWorkspace run={run} job={selectedJob} busy={busy} act={act} analyse={analyse} onUpdate={refresh}/>}
    {section === "pipeline" && <div className="kanban">{["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"].map(stage => <section key={stage}><h3>{stage} <span className="count">{pipeline.filter(p => p.status === stage).length}</span></h3>{pipeline.filter(p => p.status === stage).map(p => <Link className="panel pipeline-card" key={p.subject} href={`/jobs/${p.subject}`}><strong>{jobs.find(j => j.id === p.subject)?.title || p.subject}</strong><small>Recorded marketplace event · {p.synthetic ? "mock" : "live"}</small></Link>)}<p className="muted small">{pipeline.some(p => p.status === stage) ? "" : "No opportunities yet"}</p></section>)}</div>}
    {section === "messages" && <div className="studio-layout"><section className="panel"><h2>Client conversations</h2>{messages.length ? messages.map(m => <article key={m.id} className="message"><Badge tone={m.direction === "inbound" ? "green" : "neutral"}>{m.direction}</Badge><small>{m.conversation} · synthetic</small><p>{m.text}</p>{m.direction === "inbound" && <button className="secondary" onClick={() => act(async () => { const r = checked(await api.POST("/messages/{conversation}/draft", { params: { path: { conversation: m.conversation } } })); router.push(`/studio/${r.id}`); })}>Draft a reply for review ↗</button>}</article>) : <p className="empty">Client replies appear here. Every outgoing reply needs approval.</p>}</section><section className="panel"><Badge tone="amber">Mock controls</Badge><h2>Explore a client reply</h2><p className="muted">Create an explicitly synthetic inbound message. This does not contact anyone.</p><label>Conversation<input value={conversation} onChange={e => setConversation(e.target.value)}/></label><label>Client message<textarea rows={4} value={incoming} onChange={e => setIncoming(e.target.value)} placeholder="Could we schedule an interview?"/></label><button className="secondary" disabled={busy || !incoming.trim()} onClick={() => act(async () => { checked(await api.POST("/dev/client-message", { body: { conversation, text: incoming } })); setIncoming(""); })}>Add synthetic reply</button></section></div>}
    {section === "analytics" && <><div className="metrics"><Metric label="PROPOSALS SUBMITTED" value={analytics.submitted ?? 0} note="Recorded marketplace events"/><Metric label="REPLY RATE" value={analytics.reply_rate == null ? "—" : `${Math.round(analytics.reply_rate * 100)}%`} note="Mock only · not GigSim results"/><Metric label="HIRED" value={analytics.hired ?? 0} note="Recorded outcomes only"/><Metric label="CONNECTS SPENT" value={analytics.connects?.spent ?? 0} note="No estimated charges"/></div><section className="panel"><h2>Measured node usage</h2><p className="muted">API USD is unassigned for local compute. Official comparisons and human ratings are pending.</p><div className="table-wrap"><table><thead><tr><th>Node</th><th>Model</th><th>Tokens</th><th>Latency</th><th>API USD</th></tr></thead><tbody>{analytics.usage?.map((u: Doc, i: number) => <tr key={i}><td>{u.node}</td><td>{u.model}{u.test_double && " (TEST DOUBLE)"}</td><td>{u.tokens}</td><td>{u.latency_seconds?.toFixed(2)}s</td><td>{u.api_usd ?? "Local / unassigned"}</td></tr>)}</tbody></table></div>{!analytics.usage?.length && <p className="empty">Run an analysis to collect usage.</p>}</section></>}
    {section === "settings" && <div className="studio-layout"><div><Onboarding profile={profile} setProfile={setProfile} portfolio={portfolio} status={status} busy={busy} act={act} notify={setNotice}/></div>
      <aside><section className="panel"><h2>Connected marketplace</h2><Badge tone="amber">{status.marketplace_mode} mode</Badge><p>Switch mode in server configuration. Official GigSim requires its contract. Upwork OAuth is unavailable pending verified integration and account authorization.</p><label>Simulate marketplace condition<select aria-label="Simulate marketplace condition" disabled={!status.synthetic || busy} defaultValue="none" onChange={e => act(async () => { checked(await api.PUT("/dev/fault", { body: { mode: e.target.value as "none" | "outage" | "rate_limit" | "timeout" | "ambiguous_write" } })); })}><option value="none">Available</option><option value="outage">Service outage</option><option value="rate_limit">Rate limited</option><option value="timeout">Timeout</option><option value="ambiguous_write">Ambiguous write response</option></select></label></section>
      <section className="panel"><h2>What GigBid remembers</h2><p className="muted">Only explicitly promoted observations. Delete an entry to exclude it from future runs.</p>{memory.length ? memory.map(m => <div className="memory" key={m.id}><Badge>{m.kind}</Badge><p>{m.rule || m.interpretation} {m.word}</p><small>{m.promotion_rule}</small><details><summary>Supporting observations</summary><pre>{JSON.stringify(m.supporting_runs || m.supporting_events, null, 2)}</pre></details><button className="danger" onClick={() => act(async () => { checked(await api.DELETE("/memory/{memory_id}", { params: { path: { memory_id: m.id } } })); })}>Forget this</button></div>) : <p className="empty">Nothing promoted yet. Style memory requires the same change in five distinct approved edits.</p>}</section></aside></div>}
    {!["inbox", "jobs", "studio", "settings", "runs", "pipeline", "messages", "analytics"].includes(section) && <section className="panel"><h2>Page not found</h2><Link href="/inbox">Return to inbox</Link></section>}
    <footer>GigBid <span>Evidence first. Human always.</span><small>Local development · No live marketplace connection</small></footer></div></main></div>;
}

function Metric({ label, value, note }: { label: string; value: string | number; note: string }) {
  return <div className="metric"><p>{label}</p><strong>{value}</strong><small>{note}</small></div>;
}
