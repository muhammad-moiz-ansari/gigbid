# Hypotheses, recorded before any evaluation run

Written on 2026-11-09, before the first run of each study. Every results file stores this file's SHA-256,
so a later edit shows up as a changed hash.

## R&D B: retrieval

- On jobs that ask for several things or name an exact tool (`multi_requirement`, `exact_tool`), requirement
  decomposition with hybrid retrieval and cross-encoder reranking (V1+V2+V3) raises evidence Recall@5 by at
  least 10 points over V0.
- On `implied_skill` jobs BM25 adds nothing, so V1+V3 scores at least as well as V1+V2+V3.
- Outcome-aware ranking (V4) moves Recall@5 by less than 2 points.
- Better retrieval does not change bid or skip decisions on `implied_skill` jobs, because the Fit Matcher only
  counts evidence whose skill tags name the requirement.

## R&D C: architecture

- Our graph writes fewer unsupported claims per proposal than one ReAct agent holding all tools, and lets no
  compliance violation through, where the ReAct agent lets at least one through.
- The ReAct agent matches our bid or skip accuracy on clear-cut jobs (`out_of_scope`, `scam`).
- The prebuilt supervisor uses the most tokens per job, because every hand-off resends the conversation.

## R&D A: tool granularity

- A few coarse tools (one per server, with an action argument) cut tool-selection errors but raise argument
  errors. The fine-grained set with rewritten descriptions gets the best combined accuracy, for at most 20%
  more tokens per task than the coarse set.

## Models

- gpt-oss-120b as writer and critic gives fewer unsupported claims and a higher judge score than gpt-oss-20b in
  every role, at about twice the cost per proposal; qwen3.8-27b as writer lands between the two.
