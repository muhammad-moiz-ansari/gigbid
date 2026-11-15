# Submission preparation

## Evidence inventory

| Deliverable | Evidence available | Remaining work |
|---|---|---|
| Local app and browser journeys | Nine passing browser journeys and 217 passing Python regression tests | Verify CI on a remote runner after publication is authorized |
| Retrieval and decision studies | Result files and generated tables under `evals/results/` | Re-run on the labelled development set when available |
| Architecture and tool studies | Tool comparison completed on 40 tasks per configuration. Architecture runners exercised with scripted generation | Complete the matched real-model architecture comparison |
| Judge calibration and model comparison | Calibration sheet and model profiles | Collect 30 human labels, then measure agreement and run a matched model comparison |
| Marketplace integration | Historical instructor archive, starter-kit samples and recorded Upwork read checks | Obtain official GigSim and its contract, the grading policy update and full persona material |
| Operations | [30-run smoke report](../evals/results/smoke-20261115-162627.json) with 28 submissions and 29 replies | Verify the final hosted worker and reviewer workflow |
| Research report and technical article | Editable R&D report delivered separately and [article draft](TECHNICAL_WRITEUP.md) | Export the reviewed PDF and publish the article |
| Portfolio MCP | [Install guide](../mcp_servers/portfolio/README.md) and local wheel | Provide a public install link at the submitted revision |
| Demo and reviewer access | Script below, local runbook, and recorded event timelines linked in the README | Add the video and GIF, confirm the production frontend domain, and verify the dedicated reviewer account |

## Classroom submission checklist

- Upload the reviewed R&D PDF with at most ten main pages.
- Add the working public frontend URL and the public GitHub repo at the deployed revision. Put the dedicated, preloaded reviewer login in a private Classroom comment.
- Add the three-minute demo video link and embed a 30-second GIF at the top of the README.
- Add the public Portfolio MCP install link and the published technical write-up link.
- Include both code-derived graphs and the README result tables. Keep at least three trace links in the README. The architecture section of the assignment specifically asks for scam, approval, Critic loop and crash recovery traces, so all four are linked.
- Attach the source ZIP if requested. Keep the app live until grades are released.

Before submitting, open the links in a signed-out browser. Use the reviewer login to verify analysis, approval and live activity. Verify the worker can process reviewer jobs with the development PC off.

The trace files use synthetic workspaces and record only event names, node names,
status, and relative timestamps. Their repository links become public after the
submission revision is pushed. If hosted tracing links are available, add those
alongside the exports.

## Two-line résumé bullet

Built GigBid, an evidence-grounded LangGraph proposal assistant with persistent human approval and mock marketplace reconciliation.<br>
Raised Recall@5 from 0.630 to 0.752 on a 51-job synthetic suite and verified 28 of 30 mock submissions and 29 of 30 mock replies in real-model smoke tests.

## Three-minute demo script

1. **0:00–0:40** Sign in, show portfolio evidence and the instructor inbox, then open a job and explain the distinction between the archive and simulated marketplace actions.
2. **0:40–1:30** Use a disposable seeded mock workspace to analyse the API job. Inspect citations and the dry-run cost, approve once, then show the recorded submission and Connects debit.
3. **1:30–2:10** Analyse the seeded scam and prompt-injection jobs. Show their actual outcomes, including whether the checks blocked a draft or removed unsafe content.
4. **2:10–3:00** Open the synthetic client reply, review the proposed response and interview slots, and approve it. Show completed graph events and their trace IDs.

Record the actual outcomes of the demo. Use the seeded mock workspace for approvals and client replies.

## Extract the README demo GIF

After recording, choose a 30-second segment that shows the inbox, review, and
approval. Replace `00:00:00` with its starting timestamp. Run this from the
repository root with FFmpeg installed.

```powershell
ffmpeg -ss 00:00:00 -i "demo.mp4" -t 30 -filter_complex "[0:v]fps=8,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" "docs/images/demo.gif"
```

Replace the demo placeholder in the README with
`![GigBid demo](docs/images/demo.gif)` and a link to the full video. Verify the
clip shows the workflow clearly and contains no reviewer credentials.

## Proposal experiment protocol

Compare an evidence-first opening with a scope-first opening. Keep the model, retrieval pipeline, quote, approval rules, eligibility criteria and follow-up period fixed. Randomly assign eligible jobs within persona and job category, and record the assignment seed before generating proposals. Give each job one strategy and keep rejected drafts in the recorded denominators.

Use reply within the fixed follow-up period as the primary outcome. Report each arm's sample size, replies, reply rate and the absolute difference with a 95% confidence interval. Predeclare a two-sided Fisher exact test for a small independent sample. Record failed submissions separately and show how they affect the denominators. Assess claim support and reviewer ratings as secondary outcomes.

The current deterministic mock can exercise assignment and recording. A measured strategy effect requires outcomes from the official simulator or another authorized study with independently observed replies.
