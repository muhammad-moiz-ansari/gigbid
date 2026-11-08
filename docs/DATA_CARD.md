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

GitHub repository ingestion through a verified third-party MCP server remains
unavailable. `rag/ingest/github.py` fails explicitly. Manually uploaded repository
text is labelled as an upload, never represented as GitHub-verified code or a fetched
repository snapshot. No website scraping, browser sessions or account access occurs.

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
