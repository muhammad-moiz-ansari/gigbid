# Evaluation (Phase 8)

Every number in the README and report comes from a file in `evals/results/`. Each summary (`<study>-<time>.json`)
records the dataset fingerprint, the config and hypotheses hashes, the code commit with an uncommitted-changes
flag, and the models used. Per-job rows go to JSONL files, so a run stopped by provider quotas resumes where it
stopped. The dev set is synthetic (see the [data card](DATA_CARD.md)), so these results validate the harness;
official conclusions wait for the official dev set and GigSim.

## Running

| Command | Study | Tokens |
|---|---|---|
| `make eval` | Retrieval variants, pipelines, ablation and the evidence-gate check | None (local embeddings and reranker) |
| `make eval STUDY=decisions` | All 51 jobs decided and priced, 12 drafted, production models | About 250K |
| `make eval-all` | The final run: decisions, both R&D C baselines, R&D A and the judge, then the tables. It needs more than one day's free-tier quota; rerun it after a quota stop to resume | All of the below |
| `make eval STUDY=decisions ARGS="--profile open_small --subset proposals"` | Model comparison on the 12 proposal jobs (set aside for now) | About 140K |
| `make eval STUDY=decisions ARGS="--variant V2+V3 --subset proposals"` | Proposals with a chosen retrieval pipeline | About 130K |
| `make eval STUDY=architecture ARGS="--design react"` (or `supervisor`) | R&D C baselines | Measured per job |
| `make eval STUDY=tools` | R&D A, 40 tasks with three tool sets | About 120K |
| `make eval STUDY=judge` (`ARGS=--sheet` writes the labelling sheet) | Rubric judge and calibration | About 1.5K per proposal |
| `make tables` | Regenerates `evals/results/TABLES.md` and the README results block | None |

The extras `rerank` (sentence-transformers and torch for V3) and `eval` (langchain-groq and langgraph-supervisor)
install into the project's virtual environment; V3's weights download into `.venv/huggingface`.

## Retrieval variants and pipelines

Each ID adds one component to the V0 baseline; `+` joins components into one pipeline, for example `V1+V2+V3`.

| ID | Component |
|---|---|
| V0 | Dense retrieval: fixed 1,200-character chunks, `nomic-embed-text`, cosine top-k on the whole query |
| BM25 | Lexical retrieval alone (reference point) |
| V1 | Requirement decomposition: one retrieval per line of the job's title, skill tags and deliverables, merged by best score |
| V2 | Hybrid: BM25 and dense rankings fused with reciprocal rank fusion |
| V3 | Cross-encoder reranking of the top 20 with `BAAI/bge-reranker-v2-m3` on the CPU |
| V4 | Outcome-aware ranking: passages from won proposals up 15%, replied up 7%, ignored down 5% |
| V8 | Corrective retrieval in LangGraph: keep passages sharing a content word with the query, re-query once with a shorter query, refuse when none remain |

Queries: pipelines with V1 retrieve once per requirement line; the others use the whole post (title, description
and skill tags). The Fit Matcher already retrieves once per skill tag, so `retrieval.variant` in
`agent/config.yaml` sets the remaining components for it.

## Metrics

- Retrieval: Recall@5, MRR and nDCG@10 (gain 2^relevance - 1) against the graded gold evidence, counted per source
  document; jobs without gold evidence measure refusal instead.
- Decisions: bid accuracy and F1 (bid is the positive class; watch counts as no bid), scam precision and recall
  (a scam call is a skip whose risk report names a fraud signal: `scam`, `off_platform` or `free_work`; a skip for a
  low budget alone is not one), and the share of priced bid jobs inside the gold
  price band.
- Grounding: unsupported claims per proposal before and after claim verification, from the graph's own verifier.
- Safety: canary strings from injection jobs that reach a draft, and drafts blocked by the Compliance Guard.
- Cost and speed: tokens, USD at Groq's list prices and wall-clock seconds per job analysed and per proposal,
  as p50 and p95.
- Proposal quality: a rubric judge (`agent/prompts/judge.v1.md`, qwen3.8-27b, a different family from the
  writer) scores relevance, evidence, specificity, clarity and screening answers from 1 to 5 and gives an overall
  label. Its agreement with 30 human labels is reported as Cohen's kappa.

## Studies

- R&D B, retrieval: hypotheses were written to `evals/hypotheses.md` before any run. The runner compares every
  single variant and six pipelines, ablates the best pipeline one component at a time, breaks results down by
  persona and job type, and replays the Fit Matcher's tag rule under V0 and the best pipeline to see whether
  better retrieval changes any decision.
- Decisions and grounding: the production profile (gpt-oss-20b for small nodes, gpt-oss-120b as writer and
  critic) decides and prices all 51 jobs. To fit the free tier, only 12 jobs are drafted up to the approval
  interrupt: the first multi-requirement, exact-tool, implied-skill and injection job of each persona. The other
  runs stop where the writer would start; nothing is approved or sent.
- Models: set aside for now by the user's decision; the deployed profile is used throughout. The runner
  supports it: the production profile against `open_small` (gpt-oss-20b everywhere) on the same 12 proposal
  jobs. qwen3.8-27b cannot be compared as a writer, because the free tier allows it 1,000 output tokens per
  minute, below the writer's 2,000-token cap.
- R&D C, architecture: one ReAct agent holding all 16 MCP tools, and a prebuilt `langgraph-supervisor` with an
  analyst, a researcher and a writer, both on gpt-oss-120b, against the hand-built graph's rows from the decision
  study. All three share the jobs, tools, evidence, policy rules and task wording. The set is 12 jobs (the first
  multi-requirement, implied-skill, scam and injection job of each persona) instead of the PDF's 50, which the
  daily token quota cannot cover. Baseline claims are checked with the same verifier, and their write-tool
  attempts are counted; the marketplace refuses writes without approval.
- R&D A, tool granularity: 40 labelled requests, each sent once with the 16 published tools, with one coarse tool
  per server (an `action` argument), and with the 16 tools carrying rewritten descriptions and unchanged schemas.
  Tool-selection accuracy, argument accuracy (partial matching, defined in the task file) and tokens per task;
  no tool is executed.
- Judge calibration: `make eval STUDY=judge ARGS=--sheet` writes 30 anonymised proposals to
  `evals/labels/judge_calibration.csv`; kappa stays pending until a person fills in the label column.
- Pending by design: the blind pairwise human panel and GigSim reply and hire rates. The mock marketplace's
  replies are random draws (reply 0.65, hire 0.25) that ignore the proposal text, so they are not reported as
  outcomes.

## Free-tier limits that shaped the studies

| Model | Per minute | Per day | Effect |
|---|---|---|---|
| openai/gpt-oss-20b | 8K tokens, 30 requests | 200K tokens, 1K requests | Decision runs spread over two days |
| openai/gpt-oss-120b | 8K tokens, 30 requests | 200K tokens, 1K requests | 12 drafted jobs per configuration |
| qwen/qwen3.8-27b | 8K tokens, 1,000 output tokens | 200K tokens | Judge only; no writer comparison |

Groq's documentation states that cached prompt tokens do not count towards these limits.

## Failure taxonomy

Inspected from the per-job rows and the runs' checkpoint history. Rows produced before a fix are kept in
`evals/results/decisions-open-15356448-before-*.jsonl`; fix experiments write `decisions-open-<fix>-*` files.

| Failure | Jobs | Cause | Fix attempted | Outcome |
|---|---|---|---|---|
| Thread token budget exhausted | da-01 | The verifier emptied a screening answer (an uncited "I added..." reply to "which tests would you add"); the Critic sent the draft back, and one revision needs about 6K tokens on top of 9K | Token budget 12K to 24K, so the two revisions the Critic may ask for fit | da-01 reached approval at 10.1K tokens; no run hit the budget afterwards |
| Draft blocked: every past-work sentence removed | aiml-01, aiml-02, aiml-04 | The writer embellished evidence (an invented "92% precision") and merged CV and case-study facts under one citation; the Critic named the removed sentences but offered no supported wording | The Critic quotes the closest evidence sentence for each removed claim; writer prompt v6 reuses it | aiml-02 and aiml-04 reached approval; aiml-01 stayed blocked |
| Draft blocked: one citation for a project described three ways | aiml-01, fs-01, fs-02 | Faithful sentences combine a project's case study and README but cite one of them, and word overlap with that one passage falls below 60%; for aiml-01 the quoted hint also came from an unrelated project | A citation stands for every item of the same project (not the default "Own portfolio") | Not measured yet: the rerun hit the daily token limit; the final run covers these jobs |
| Legitimate jobs with planted instructions skipped | aiml-10, da-05, da-14, fs-07 | The risk model scored what the planted text asked for (contact details, guarantees, free work) as client risk, reaching 0.8 against the 0.65 skip threshold | Risk prompt v4: score the job as if the planted instructions were absent; code still applies the 0.5 injection floor | aiml-10, da-05 and da-14 now get a bid; fs-07 is still skipped at 0.7. Side effect: the subtle scam aiml-09 now gets a bid at 0.6, although the model flagged `off_platform` and `free_work`, which the approval screen shows. Kept as is by the user's decision |
| Low budget called a scam | aiml-11, fs-10 | The skip was right but the risk model added the `scam` flag, which halves scam precision | Risk prompt v4: a low budget is `low_budget`, never `scam` | Both are still skipped, without the scam flag; on the 15 risk jobs scam precision is 1.0 and recall 0.83 |
| Price above the fair band | aiml-04, aiml-06, aiml-14, da-03, da-06, da-16, fs-09, fs-11, fs-16 | Pricing anchors at about 0.95 of the budget; all nine misses are jobs whose budget is generous for the scope | None yet; a candidate is estimating effort from the deliverables and the profile's hourly rate | Open |
| Decomposition lowers recall | V1 pipelines | Merging sub-query results by best score lets generic sub-queries (deliverables such as "Documentation") lift generic passages | None yet; a candidate is a reciprocal-rank merge | Open |
| Reranking adds latency without gain | V3 pipelines | Each persona has 16 items, fewer than the 20-item rerank window, so V3 reorders the whole corpus; 4.9 s per query on the CPU | Not shipped | Open until a larger corpus |
| Daily token limit reached mid-run | 27 of 45 jobs in the 2026-11-09 afternoon attempt (`decisions-open-15356448-quota-ran-out.jsonl`) | From the 13th job gpt-oss-20b answered 429, most likely its daily limit after the morning's runs. The model layer waited and retried once on gpt-oss-120b, whose answers for the small nodes failed their schemas; 6 more jobs finished on 120b alone. The error said only "ValidationError", so the runner saved these jobs instead of stopping | A model error now names an earlier rate limit, so the runner's stop rule catches it; the attempt's rows are kept aside and the final run starts from an empty file | Covered by a unit test; why gpt-oss-120b's small-node answers fail their schemas is still open |

## What ships

Retrieval: V2, hybrid BM25 and dense retrieval with reciprocal rank fusion, is set in `agent/config.yaml`. On the
dev set it raised Recall@5 from 0.630 to 0.752 and nDCG@10 from 0.763 to 0.812 over V0 at the same latency
(about 80 ms per query), and it led on every persona. Cross-encoder reranking (V3) did not ship: it gained
nothing here and cost 4.9 s per query on the CPU, and because each persona holds 16 items, fewer than its
20-item window, it reorders the whole corpus whatever the first stage. Decomposition (V1) and outcome-aware
ranking (V4) lowered nDCG@10, and corrective retrieval (V8) matched V0 on whole posts; with decomposition it
refused 11% of out-of-scope jobs. The hypothesis that V1+V2+V3 adds 10 points of Recall@5 on multi-requirement
and exact-tool jobs failed (+2 points). Better retrieval changed no bid or skip decision: the Fit Matcher
counts only evidence whose skill tags name the requirement, and in 37 jobs it retrieved gold evidence that it
could not count, which is where the next gain lies. The graph ships with the 24K token budget, the Critic's
closest-evidence hint and writer prompt v6, risk prompt v4 and project-level citations.

Run-to-run noise: BM25 breaks score ties by chunk ID, which depends on the tenant, so pipelines with many ties
move by about 0.01 between runs.
