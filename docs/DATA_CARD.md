# Portfolio data card - Phase 4

## Scope and provenance

The corpus currently consists of original labelled synthetic development examples
and files explicitly uploaded by the account owner. Instructor personas, official
policy/evaluation materials and GitHub MCP data have not been imported. Synthetic
reviews and proposal outcomes are authored fixture labels, not actual endorsements,
human panel ratings, client responses or GigSim results.

`dev_support/fixtures/portfolio.json` contains four original demonstration cases
spanning full-stack, AI/ML and data-analysis work. Additional original fixtures are
`case_study.md`, `reviews.json` and `past_proposals.json`. The seed command loads
these through the same ingestion functions as uploads. Every fixture passage has
`synthetic=true`. Tests construct text-only synthetic PDF CVs in memory; they are not
assignment evidence or screenshots of real CVs.

## Accepted formats

| Format | Behavior | Inspectable provenance |
|---|---|---|
| PDF CV | pypdf selectable text, extracted separately per page | Original logical filename, page and character range |
| Markdown case study | UTF-8 text and optional safe YAML frontmatter | Body's starting line and character range |
| Plain text / manually uploaded Python or TypeScript | UTF-8 text; code classified as repository text | Filename and character range; user-upload provenance |
| JSON review/proposal | Object or array of objects with `text` plus typed metadata fields | Entry number, character range, type and actual supplied outcome label |

Example JSON upload (all examples here are synthetic):

```json
[
  {
    "text": "Proposed approach: I would reconcile source totals first.",
    "type": "proposal",
    "persona": "data-analyst",
    "project": "Original demonstration",
    "skills": ["SQL", "dbt"],
    "date": "2026-05-03",
    "industry": "retail",
    "outcome": "replied",
    "synthetic": true
  }
]
```

JSON entries cannot override the uploaded source identity or supply a tenant ID.
Malformed JSON is rejected instead of becoming raw JSON portfolio prose. Metadata
supports persona, type, project, skills, date, industry, outcome and synthetic flag.
Unknown dates/outcomes remain explicitly unspecified/unknown. Skills are normalized
and deduplicated without inventing experience. Upload metadata can provide skills
for PDFs; no unverified model extraction of credentials is performed.

Encrypted PDFs, unsupported file types, empty/unreadable text, invalid metadata and
oversized inputs fail before replacing the previous source. Scanned PDFs require
OCR before upload; OCR is not implemented. Selectable PDF extraction is not a claim
of layout-perfect reading, table reconstruction or image understanding.

GitHub repositories are imported through GitHub's official MCP server (Settings, or
`POST /evidence/github`): the root README and up to 12 source files in configured languages,
taking source folders (`src`, `app`, `lib`, ...) and larger files first, and skipping vendored
folders, generated `.d.ts` files and files over 50 KB (`github` in `agent/config.yaml`). Each file
becomes `repository` evidence with the repository as its project and `github:owner/repo/path`
as its source; re-importing replaces changed files. Manually uploaded repository text stays
labelled as an upload. No website scraping, browser sessions or account access occurs.

## Hashes, chunking and aliases

The loader preserves a raw SHA-256 and a normalized document hash. Source records
contain loader/chunker versions, metadata and evidence IDs. Extracted document
sections are retained privately for explicit re-chunking; uploaded PDF binaries are
not retained by this implementation.

Fixed character chunks use the configured size and overlap in `agent/config.yaml`.
Character ranges refer to normalized extracted text, with Windows line endings
normalized to LF; raw byte hashes still identify the original upload.
The chunker version includes both values. Evidence IDs bind tenant, content hash,
metadata, section/offset/location, loader and chunker version. Unchanged passages can
retain their IDs and cached vectors on replacement. A metadata/location change that
affects provenance gets a new identity. Each passage includes exact inspectable text
and a content hash.

Identical documents under another filename share evidence rather than create duplicate
hits when their content/metadata/location agree. Both source records retain their
evidence references. Deleting one alias retains evidence owned by another alias and
updates the canonical visible source when necessary. Deleting the final owner removes
the passage. This preserves provenance rather than treating unrelated projects or
different outcomes as interchangeable duplicates.

## Indexes and baseline

SQL evidence is authoritative. Every corpus has a content fingerprint and monotonically
changing revision; no-op uploads leave the revision unchanged. BM25 token records and
the index manifest are updated transactionally with ingestion. Missing token caches
can be repaired without inventing a new corpus revision. BM25 builds scores only over
tenant-owned evidence and supports explicit metadata filters.

V0 is the current default: embed the supplied query without expansion and search
fixed chunks using cosine similarity in Qdrant. It is a baseline, not a measured
winning retrieval strategy. Pre-existing advanced variant code is preserved for
later phases; it has not been selected by an official evaluation in Phase 4.

Production embeddings use the configured open Ollama model. The adapter resolves its
actual installed digest via `/api/tags`, disables silent input truncation, validates
vector counts/dimensions/finiteness, and refuses to fabricate vectors if the model is
unavailable. Embedding cache keys include evidence/content and the provider/model
revision. Index manifests include the embedding identity, dimensions, cosine metric,
corpus fingerprint/revision, chunk versions and pinned index-library versions.

Qdrant filters always include tenant and corpus fingerprint; metadata selection is
also applied to the permitted evidence IDs. Results are rehydrated from current SQL
evidence and checked against a final current fingerprint. Stale points from an older
generation or another tenant cannot authorize a claim or reappear as current evidence.

## Replacement, deletion and recovery

Source replacement is transactional: old passages lose their references, unchanged
passages can be retained, the new source is installed, lexical records are rebuilt
incrementally and affected unconsumed approvals are invalidated. Invalid replacement
input leaves the previous source searchable. Deletes also remove retained extracted
text and obsolete SQL vector caches. Approvals that cite other untouched evidence
remain intact.

Dense indexing is lazy on the next dense query or explicit local rebuild, so uploads
do not pretend an unavailable model/index has succeeded. Existing document vectors
are reused; new/changed passages are embedded in bounded batches. Concurrent corpus
changes abort stale publication/results rather than restoring deleted SQL evidence.

Vector cleanup is attempted after mutation. If the vector service is unavailable,
the tenant-scoped cleanup record remains pending. Canonical SQL deletion and generation
filters immediately hide the old evidence; physical removal is not falsely reported
as complete. Retry with the cleanup command after recovery. Qdrant payloads contain
IDs/hashes/filter metadata, while inspectable passage text remains in tenant-scoped SQL.

## Verification limits

Tests use real local Qdrant engines, including persistent storage accessed from threads
and a reopened process. Dense tests inject explicitly labelled fixed vectors and mark
index manifests `test_double=true`; they verify index correctness, not semantic quality.
Real `nomic-embed-text` embeddings have since run locally in the 2026-11-08 smoke checks.
No official retrieval metrics, model rankings, reply/hire rates or human
quality scores are reported.

See `docs/checks/phase4.json` for actual test/build outcomes, source/fixture hashes,
and the remaining service/material blockers.

## Evaluation dev set (Phase 8)

`evals/datasets/synthetic/` holds a labelled synthetic dev set for running the evaluation harness until the
official dev set arrives. It is suitable for harness validation only; no official conclusion rests on it.
Its SHA-256 fingerprint (`python -m evals.dataset`) is stored in every results file; the version used for the
first Phase 8 runs is `15356448130890922a0f9bbfa5a8890351a863b11671202fb8daa305226c45d5`.

| Persona | Evidence items | Jobs | Floor (USD) |
|---|---|---|---|
| ai-ml | 16 | 17 | 300 |
| full-stack | 16 | 17 | 200 |
| data-analyst | 16 | 17 | 150 |

- Evidence (48): 3 CVs, 14 case studies, 13 repository READMEs with code excerpts, 6 client reviews and 12 past
  proposals (6 won, 3 replied, 3 ignored). Each persona has three projects described three ways in different
  words, and 25 items show a skill the text never names (listed under `implied`, which is not ingested). Each
  persona has a won and an ignored proposal on the same topic.
- Jobs (51): per persona 3 multi-requirement, 3 exact-tool, 2 implied-skill, 2 vague, 2 out-of-scope, 1 low-budget,
  2 scam and 2 prompt-injection jobs. 33 should get a bid and 6 are scams. 9 legitimate jobs come from new unverified
  clients, so verification alone does not reveal a scam, and one scam and one injection job per persona avoid the
  keyword rules in `apps/api/safety.py`.
- Gold labels per job: bid or skip, scam or not, relevance of each evidence item (2 directly shows a core
  requirement, 1 related; 1 to 10 items, 3.8 on average, for 42 jobs), a fair fixed-price band for bid jobs and a
  one-sentence reason. Injection jobs carry a unique canary string that must never reach a draft.
- Authorship: written on 2026-11-09 with AI assistance (three Claude subagents, one per persona) to a fixed written
  specification, then validated by `evals/dataset.py`. All people, clients and projects are fictional. The labels
  come from the same authors as the system, not from independent annotators, so they can share its blind spots.
- Limits: 17 jobs per persona against about 200 in the official set; two jobs have more than five gold items, which
  caps their Recall@5 below 1.

`evals/datasets/tool_tasks.yaml` holds the 40 labelled tool-call tasks for R&D A and the rewritten tool
descriptions. Human judge labels and panel ratings go in `evals/labels/`; none are invented.
# Instructor dataset bundle

The local import uses `data/instructor/archive/Final_Upwork_Dataset.csv`.
The supplied introduction attributes the archive to Ahmed Mayalou
([Kaggle profile](https://www.kaggle.com/ahmedmyalo/)) and describes it as
historical Upwork postings collected in February and March 2023. Its sample
mix is uneven across search categories. The companion feature guide documents
the columns and notes missing fixed-price budgets for some 3D jobs.
No redistribution license was supplied with the local files. Keep raw files
and exports of job text local until permissions are confirmed.

```powershell
python -m dev_support.instructor_jobs --limit 100
python -m dev_support.instructor_jobs --limit 100 --tenant YOUR_TENANT_ID
```

The first command validates without writing. The second seeds an existing
mock-mode account. Use a dedicated account if you want an inbox containing
only historical imports. The importer reads the first eligible unique rows in
file order, trims text, deduplicates by a hash of the source URL, keeps skill
tags, and uses the dollar budget and the archive's revised Connects field.
It skips hourly jobs, incomplete rows and rows with invalid costs. Results are
neither representative samples nor current market estimates.

The job text and posted fields are historical observations. Job URLs are not
stored by the importer, but descriptions may still contain personal details
or links. Use local models for this data unless external processing is
permitted. Per-job client records and any subsequent simulator conversations,
portfolio evidence from demo fixtures, and outcomes are synthetic. An
unverified mock client with zero recorded activity means that no linked
client record was imported. It is not a finding about the original client.

Other inputs in this bundle remain unused:

| File | Reason |
| --- | --- |
| 2024 jobs CSV | Has dates and pricing fields but no descriptions or skills for matching. |
| Contracts CSV | Has historical payment and hours fields but no verified join to these postings or persona evidence. |
| Freelancer gig success CSV | Profile-level metrics do not label bid decisions, evidence relevance, or proposal quality. Provenance and license are unverified. |
| Preprocessed BERT workbook | Unlabelled. Its provenance and relationship to the archive are unverified. |
| Archive XLSX | CSV selected for streaming import; workbook not used as an independent source. |

The historical import does not supply GigSim, official outcomes, the policy
update, or the assignment's labelled development split. Keep existing
synthetic evaluation results labelled as such.
