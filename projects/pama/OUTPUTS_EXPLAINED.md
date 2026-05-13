# Outputs Explained

This file explains what each generated output means.

## current_plan.md
Session planning file with objective, subproblems, dependencies, and measurable outputs.

## best_output.md
Current best revised output across rounds based on judge score.
Read this first for the quickest summary.

## final_session_report.md
Session-level report generated in `--session` mode.
Includes direction, criticism, risks, ideas, and next actions.

## research_state.json
Lightweight structured snapshot of:
- strongest hypothesis
- biggest blocker
- next experiment
- open question

## score_history.json
Per-round scoring timeline.
Useful for debugging progress, regressions, and stop conditions.

## runs/YYYY.../round_xx/
Round-level raw artifacts:
- `01_draft.md`
- `02_review.md`
- `03_revised.md`
- `04_judge.md`

Use these files to inspect exactly how each round evolved.
