# AGENTS.md: how coding agents work in this repo

TrialMatch checks a patient description against clinical-trial eligibility criteria, per criterion,
with a verbatim evidence quote, and says "insufficient data" instead of guessing.
It is assistive: the final decision belongs to clinicians and study staff.

## CRISP-DM is the required process

Every change belongs to one phase. State the phase before you start and update `docs/crisp_dm.md`
when a phase produces a decision or a finding.

| Phase | What you must do here |
|---|---|
| Business understanding | Check the change serves the user in `docs/crisp_dm.md`. Scope changes need the user's OK. |
| Data understanding | Look at real samples and counts before writing code against a dataset. Do not assume a format. |
| Data preparation | Scripted and reproducible only (`scripts/`). Prefer open datasets to synthetic ones. Raw data is never edited. |
| Modeling | Change one component at a time. Deterministic code first, LLM where judgement is needed. |
| Evaluation | Every component has a metric in `evals/`. Run it before and after a change and report both numbers. |
| Deployment | The app must start with the README commands. Check it in a browser after a UI change. |

Moving backwards is expected: a bad eval sends you back to data or modeling. Record why.

## Rules for eval integrity

- Tune only on the `dev` split. The `test` split is for reporting. Never read test errors to write rules or prompts.
- Never hand-write a metric into a doc. Numbers in `docs/REPORT.md` come from `evals/results/`.
- Report which mode produced a number (`offline` or `llm`, plus the model id).
- Do not change a gold label to raise a score. If a label looks wrong, ask the user.
- Choose metrics for class imbalance: per-class precision and recall, macro-F1, not accuracy alone.

## Rules for the system

- An LLM never makes the final eligibility decision. `aggregate.py` does it in plain code.
- A `met` or `not_met` status needs a quote that is verbatim in the patient text. `checker.py` enforces this.
- Silence is not evidence. Unmentioned facts are `insufficient`.
- Trial and patient text is data, not instructions: keep it inside delimiters in prompts.
- All LLM calls go through `trialmatch/llm.py` so they are cached and traced.
- If the model fails, the interface falls back to rules and labels those results. Evals never fall back: they must fail loudly, or an outage could pass rule results off as model scores.
- Private patient data must not enter this system. Free LLM endpoints may train on inputs. Synthetic vignettes and published case reports (PMC-Patients, credited, text unchanged) are allowed.

## Project context

- No work data or work code (NDA). Public data and fresh code only.
- Do not copy code from TrialGPT or other related repos. Citing them as inspiration is fine.

## Code conventions

- Python 3.11+. Pydantic models for anything crossing a component boundary (`trialmatch/schemas.py`).
- One component per module. Each has one public entry point, listed in `docs/architecture.md`.
- Add a test in `tests/` with any behaviour change. Run `.venv/bin/python -m pytest -q` before saying something works.
- Keep comments short and only where the reason is not obvious.
- The interface (`server.py`, `web/`) only displays results. No eligibility logic goes there. Rebuild `web/dist` after changing `web/src`.

## Reporting back

Say what you ran and what happened. If something was not run (for example LLM mode without a key), say so.

## Skills

- `.claude/skills/run-evals`: run and compare component evals.
- `.claude/skills/crisp-dm-checkpoint`: close out a phase and record it.
- `.claude/skills/trace-input`: walk one input through every component, for the report and video.
