# Submission preparation

## Evidence inventory

| Deliverable | Evidence available | Remaining work |
|---|---|---|
| Local app and browser journeys | Nine passing browser journeys and 217 passing Python regression tests | Verify CI on a remote runner after publication is authorized |
| Retrieval and decision studies | Result files and generated tables under `evals/results/` | Re-run on the labelled development set when available |
| Architecture and tool studies | Existing runners and labelled tool tasks | Run with a configured model and report completed cases, failures, latency and token usage |
| Judge calibration and model comparison | Calibration sheet and model profiles | Collect 30 human labels, then measure agreement and run a matched model comparison |
| Marketplace integration | Historical instructor archive, starter-kit samples and recorded Upwork read checks | Obtain official GigSim and its contract, the grading policy update and full persona material |
| Operations | Compose configuration and prior stack verification | Run the 30-job smoke study and compare failures, latency and cost against declared thresholds |
| Research report and technical article | Evaluation guide, reproducible results and phase log | Complete the report and article after the missing studies |
| Demo and reviewer access | Script below and local runbook | Record the demo, prepare private reviewer credentials and record actual deployment and trace links when available |

## Three-minute demo script

1. **0:00–0:40** Sign in, show portfolio evidence and the instructor inbox, then open a job and explain the distinction between the archive and simulated marketplace actions.
2. **0:40–1:30** Use a disposable seeded mock workspace to analyse the API job. Inspect citations and the dry-run cost, approve once, then show the recorded submission and Connects debit.
3. **1:30–2:10** Analyse the seeded scam and prompt-injection jobs. Show their actual outcomes, including whether the checks blocked a draft or removed unsafe content.
4. **2:10–3:00** Open the synthetic client reply, review the proposed response and interview slots, and approve it. Show completed graph events and their trace IDs.

Record the actual outcomes of the demo. Use the seeded mock workspace for approvals and client replies.

## Proposal experiment protocol

Compare an evidence-first opening with a scope-first opening. Keep the model, retrieval pipeline, quote, approval rules, eligibility criteria and follow-up period fixed. Randomly assign eligible jobs within persona and job category, and record the assignment seed before generating proposals. Give each job one strategy and keep rejected drafts in the recorded denominators.

Use reply within the fixed follow-up period as the primary outcome. Report each arm's sample size, replies, reply rate and the absolute difference with a 95% confidence interval. Predeclare a two-sided Fisher exact test for a small independent sample. Record failed submissions separately and show how they affect the denominators. Assess claim support and reviewer ratings as secondary outcomes.

The current deterministic mock can exercise assignment and recording. A measured strategy effect requires outcomes from the official simulator or another authorized study with independently observed replies.
