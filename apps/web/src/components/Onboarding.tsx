"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, checked } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Profile = components["schemas"]["Profile"];
type Doc = Record<string, any>;
type Upload = components["schemas"]["Upload"];
export default function Onboarding({ profile: savedProfile, setProfile: saveProfile, portfolio, status, busy, act, notify }: {
  profile: Profile; setProfile: (profile: Profile) => void; portfolio: Doc[]; status: Doc; busy: boolean;
  act: (task: () => Promise<void>) => Promise<void>; notify: (text: string) => void;
}) {
  const [profile, setProfile] = useState(savedProfile);
  const [uploadKey, setUploadKey] = useState(0);
  useEffect(() => setProfile(savedProfile), [savedProfile]);
  const [source, setSource] = useState(""), [text, setText] = useState(""), [skills, setSkills] = useState("");
  const [kind, setKind] = useState<Upload["type"]>("case_study");
  const [project, setProject] = useState(""), [industry, setIndustry] = useState(""), [date, setDate] = useState("");
  const [outcome, setOutcome] = useState<Upload["outcome"]>("unknown");
  const [mode, setMode] = useState("text"), [file, setFile] = useState<File | null>(null);
  const [repository, setRepository] = useState("");
  const [upwork, setUpwork] = useState<{ connected: boolean; tools: string[] }>({ connected: false, tools: [] });
  useEffect(() => {
    void api.GET("/integrations/upwork").then(result => result.data && setUpwork(result.data as typeof upwork));
    const query = new URLSearchParams(window.location.search);
    if (query.get("upwork") === "connected") notify("Upwork connected. Use Check connection to list what it offers.");
    if (query.get("upwork") === "error") notify(`Upwork sign-in did not complete: ${query.get("reason") || "unknown reason"}`);
  }, []);
  const skillList = (value: string) => value.split(",").map(item => item.trim()).filter(Boolean);
  async function upload(event: React.FormEvent) {
    event.preventDefault();
    await act(async () => {
      const metadata = { source: source.trim() || file?.name || "", type: kind,
        skills: skillList(skills), project: project || source || file?.name || "Own portfolio",
        persona: profile.persona || "own", industry: industry || "unspecified",
        date: date || "unspecified", outcome };
      if (mode === "file") {
        if (!file) throw new Error("Choose a portfolio file.");
        const form = new FormData();
        form.append("file", file);
        form.append("metadata", JSON.stringify(metadata));
        checked(await api.POST("/evidence/file", {
          body: form as never, bodySerializer: body => body as unknown as FormData
        }));
      } else {
        checked(await api.POST("/evidence", { body: { ...metadata, text } }));
      }
      setText(""); setFile(null); setUploadKey(key => key + 1);
      notify("Portfolio evidence saved. New and changed passages will be used by retrieval.");
    });
  }
  return <>
    <section className="panel onboarding"><h2>Set up your workspace</h2>
      <ol><li>Save your profile, rates and opportunity filters.</li><li>Add portfolio evidence with its source details.</li>
        <li><Link className="inline-link" href="/inbox">Find an opportunity in your inbox →</Link></li></ol>
      <p>{portfolio.length} portfolio passages available.</p>
    </section>
    <form className="panel" onSubmit={event => { event.preventDefault(); void act(async () => {
      const saved = checked(await api.PUT("/auth/profile", { body: profile }));
      saveProfile(saved); notify("Profile and inbox filters saved.");
    }); }}>
      <p className="eyebrow">ONBOARDING & PREFERENCES</p><h2>Your freelance profile</h2>
      <label>Display name<input required maxLength={100} value={profile.name || ""} onChange={e => setProfile({ ...profile, name: e.target.value })}/></label>
      <label>Persona<select value={profile.persona} onChange={e => setProfile({ ...profile, persona: e.target.value as Profile["persona"] })}>
        <option value="own">My own profile</option><option value="full-stack">Full-stack developer</option>
        <option value="ai-ml">AI / ML engineer</option><option value="data-analyst">Data analyst</option>
      </select></label>
      <label>Marketplace<select value={profile.marketplace_mode || status.marketplace_mode || "mock"}
        onChange={e => setProfile({ ...profile, marketplace_mode: e.target.value as Profile["marketplace_mode"] })}>
        {["mock", "gigsim", "upwork"].map(mode => <option key={mode} value={mode} disabled={mode !== status.marketplace_mode}>
          {mode === "mock" ? "Synthetic mock marketplace" : mode === "gigsim" ? "Official GigSim" : "Upwork"}{mode !== status.marketplace_mode ? " — unavailable" : ""}
        </option>)}
      </select></label><p className="muted">Only the configured backend is selectable. Official integrations are unavailable until verified and authorized.</p>
      <div className="form-grid">
        <label>Minimum fixed bid (USD)<input type="number" required min="1" max="1000000" step="0.01" value={profile.floor_fixed} onChange={e => setProfile({ ...profile, floor_fixed: Number(e.target.value) })}/></label>
        <label>Hourly rate (USD)<input type="number" required min="1" max="10000" step="0.01" value={profile.hourly_rate ?? 50} onChange={e => setProfile({ ...profile, hourly_rate: Number(e.target.value) })}/></label>
      </div>
      <label>Weekly Connects budget<input type="number" required min="0" max="10000" value={profile.weekly_connects} onChange={e => setProfile({ ...profile, weekly_connects: Number(e.target.value) })}/></label>
      <h3>Saved opportunity filters</h3>
      <label>Saved search<input maxLength={200} value={profile.saved_query || ""} onChange={e => setProfile({ ...profile, saved_query: e.target.value })}/></label>
      <label>Required skills (comma separated)<input value={profile.required_skills?.join(", ") || ""} onChange={e => setProfile({ ...profile, required_skills: e.target.value.split(",").map(item => item.trimStart()) })}/></label>
      <div className="form-grid">
        <label>Minimum job budget (USD)<input type="number" min="0" max="1000000" value={profile.min_budget ?? 0} onChange={e => setProfile({ ...profile, min_budget: Number(e.target.value) })}/></label>
        <label>Maximum Connects per job<input type="number" min="0" max="10000" placeholder="No limit" value={profile.max_connects ?? ""} onChange={e => setProfile({ ...profile, max_connects: e.target.value === "" ? null : Number(e.target.value) })}/></label>
      </div>
      <label>Search interval (seconds)<input type="number" min={status.marketplace_mode === "mock" ? 300 : 14400} required value={profile.interval_seconds} onChange={e => setProfile({ ...profile, interval_seconds: Number(e.target.value) })}/></label>
      <label className="checkbox"><input type="checkbox" checked={profile.auto_skip} onChange={e => setProfile({ ...profile, auto_skip: e.target.checked })}/>Archive jobs the agents recommend skipping. Sending always needs your approval.</label>
      <button className="primary" disabled={busy}>Save profile</button>
    </form>
    <form className="panel" onSubmit={upload}><h2>Upload your work</h2>
      <p className="muted">Add your own work or explicitly labelled synthetic examples. Source metadata stays attached to each passage.</p>
      <label>Upload format<select value={mode} onChange={e => setMode(e.target.value)}><option value="text">Paste text</option><option value="file">PDF, Markdown, text or JSON file</option></select></label>
      <label>Source name<input maxLength={200} required={mode === "text"} value={source} onChange={e => setSource(e.target.value)} placeholder="case-study.md"/></label>
      <div className="form-grid">
        <label>Evidence type<select value={kind} onChange={e => setKind(e.target.value as Upload["type"])}>
          <option value="case_study">Case study</option><option value="cv">CV</option><option value="review">Review</option>
          <option value="proposal">Previous proposal</option><option value="repository">Uploaded repository notes</option>
        </select></label>
        <label>Outcome<select value={outcome} onChange={e => setOutcome(e.target.value as Upload["outcome"])}><option value="unknown">Unknown</option><option value="won">Won</option><option value="replied">Replied</option><option value="ignored">Ignored</option></select></label>
      </div>
      <label>Project<input maxLength={200} value={project} onChange={e => setProject(e.target.value)}/></label>
      <label>Evidence skills (comma separated)<input value={skills} onChange={e => setSkills(e.target.value)}/></label>
      <div className="form-grid"><label>Industry<input maxLength={100} value={industry} onChange={e => setIndustry(e.target.value)}/></label>
        <label>Evidence date<input type="date" value={date} onChange={e => setDate(e.target.value)}/></label></div>
      {mode === "text" ? <label>Portfolio text<textarea required rows={6} value={text} onChange={e => setText(e.target.value)}/></label> :
        <label>Portfolio file<input key={uploadKey} required type="file" accept=".pdf,.md,.markdown,.txt,.json" onChange={e => setFile(e.target.files?.[0] || null)}/></label>}
      <button className="secondary" disabled={busy || (mode === "file" ? !file : !source.trim() || !text.trim())}>Save portfolio evidence</button>
      {status.synthetic && <button type="button" className="text-button" disabled={busy} onClick={() => act(async () => {
        checked(await api.POST("/dev/seed")); notify("Labelled synthetic examples loaded.");
      })}>Load synthetic examples</button>}
    </form>
    <form className="panel" onSubmit={event => { event.preventDefault(); void act(async () => {
      const items = checked(await api.POST("/evidence/github", { body: { repository: repository.trim() } }));
      notify(`Imported ${items.length} passages from ${repository.trim()} through GitHub's MCP server.`);
    }); }}><h2>Import a GitHub repository</h2>
      <p className="muted">Reads the README and main source files through GitHub's read-only MCP server.</p>
      <label>Repository<input required maxLength={200} pattern="[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+" value={repository}
        onChange={e => setRepository(e.target.value)} placeholder="owner/repository"/></label>
      <button className="secondary" disabled={busy || !repository.trim()}>Import repository</button>
    </form>
    <section className="panel"><h2>Upwork (live mode)</h2>
      <p className="muted">You sign in on Upwork's own page and GigBid stores the tokens encrypted. Nothing reaches Upwork without your approval here, and proposals still need confirming on Upwork.</p>
      <p role="status">{upwork.connected ? `Connected${upwork.tools.length ? ` · ${upwork.tools.length} tools available` : ""}` : "Not connected"}</p>
      <div className="button-row">
        <button className="secondary" disabled={busy} onClick={() => act(async () => {
          const { authorize_url } = checked(await api.POST("/integrations/upwork/connect")) as { authorize_url: string };
          window.location.assign(authorize_url);
        })}>{upwork.connected ? "Reconnect Upwork" : "Connect Upwork"}</button>
        {upwork.connected && <button className="secondary" disabled={busy} onClick={() => act(async () => {
          const { tools } = checked(await api.POST("/integrations/upwork/check")) as { tools: string[] };
          setUpwork({ connected: true, tools }); notify(`Upwork connection works: ${tools.length} tools available.`);
        })}>Check connection</button>}
        {upwork.connected && <button className="secondary" disabled={busy} onClick={() => act(async () => {
          checked(await api.POST("/integrations/upwork/acknowledge-policy")); notify("Upwork policy acknowledged.");
        })}>I understand Upwork's policies</button>}
        {upwork.connected && <button className="danger" disabled={busy} onClick={() => act(async () => {
          checked(await api.DELETE("/integrations/upwork")); setUpwork({ connected: false, tools: [] }); notify("Upwork disconnected.");
        })}>Disconnect</button>}
      </div>
      {upwork.connected && <p className="muted">Before your first draft Upwork asks you to confirm that you understand its policies: accept payment only through Upwork, which keeps Payment Protection.</p>}
      {upwork.tools.length > 0 && <details><summary>Tools Upwork offers</summary><p className="muted">{upwork.tools.join(", ")}</p></details>}
    </section>
    <section className="panel"><h2>Evidence sources</h2>
      {[...new Set(portfolio.map(item => item.source))].map(source => <div className="list-row" key={source}><span>{source}</span>
        <button className="danger" disabled={busy} aria-label={`Delete source ${source}`} onClick={() => act(async () => {
          checked(await api.DELETE("/evidence/source/{source}", { params: { path: { source } } }));
          notify("Source deleted. Reviews using affected evidence were invalidated.");
        })}>Delete source</button>
      </div>)}
      {!portfolio.length && <p className="empty">No evidence uploaded yet. Start with a case study or CV above.</p>}
    </section>
  </>;
}

