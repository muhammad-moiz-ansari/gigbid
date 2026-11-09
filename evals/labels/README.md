# Human labels

Only people fill in these files. A missing label keeps its study pending; no label is ever generated.

## Judge calibration (`judge_calibration.csv`)

`make eval STUDY=judge ARGS=--sheet` writes 30 proposals without their source or the judge's verdict. For each
row, read the job post and the proposal (with its screening answers), then write one word in the `label` column:

- `good`: you would shortlist this freelancer
- `acceptable`: usable after light edits
- `poor`: you would ignore it

Judge the proposal as the client would: does it address this job's requirements, back its claims with specific
past work, propose a concrete approach, read clearly without a generic opening, and answer every screening
question? Bracketed IDs such as `[a1b2c3]` are citations of the freelancer's portfolio. `notes` is optional.
Do not open `judge_calibration_key.json` before you finish; it says where each proposal came from.

`make eval STUDY=judge` then reports Cohen's kappa between your labels and the judge's.

## Pairwise panel (`panel_pairs.csv`)

`make eval STUDY=judge ARGS=--panel` writes up to 20 pairs of anonymised proposals for the same job from two
different runs, with sides shuffled. Each classmate takes one rater column and writes `A`, `B` or `tie` for the
proposal they would rather receive as the client. Do not open `panel_pairs_key.json`. The judge study then
reports each run's win rate; until ratings exist the panel stays pending.
