# Current user instruction

2026-11-07: The user changed the earlier permission to continue through phases.
Do not begin or continue another phase until the user explicitly names it. After
each requested phase, report and stop again.

2026-11-08: The user authorized continuation of Phase 6 only. Implement and verify
the core web workflow and real event streaming, then stop. Phase 7 and later work remain
unauthorized. Running compatibility tests does not authorize new phase features.

2026-11-08: The user authorized Phase 7 with Claude Code, including the writer/verifier
redesign as step 0. Match the existing code style, keep comments to one-liners, avoid
over-complication and keep the code modular and readable. Stop at four commit checkpoints
(after step 0, steps 1-2, steps 3-5 and steps 6-8) with a suggested message; the user commits.

2026-11-08 (later): the user asked to run the rest of Phase 7 (steps 0c and 1-8) in one
pass and to commit once the whole phase is complete, instead of at intermediate checkpoints.

Commit-message preference: a short conventional title followed by a detailed bullet
body. Suggest the message only; never execute a commit without explicit permission.

Preserve the later-phase code already written before this instruction. Its presence
does not mean those phases are finished, accepted, or authorized for further work.
No commits, pushes, PRs, branches or publishing are authorized. Suggest messages only.
