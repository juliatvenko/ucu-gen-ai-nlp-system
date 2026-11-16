---
name: run-evals
description: Run TrialMatch component evals and compare them with the previous results. Use after any change to a pipeline component, prompt, lexicon, or gold data.
---

1. Save the current scores: `cp -r evals/results /tmp/evals_before`.
2. Run the eval for the changed component, on dev while iterating:
   `.venv/bin/python -m evals.run_all --mode offline --split dev --only <component>`
   Components: profile, retrieval, parsing, checker, aggregate, safety, trec.
3. LLM mode spends money or free-tier quota. Ask the user first and use `--limit` for a small run:
   `.venv/bin/python -m evals.run_all --mode llm --split dev --only checker --limit 3`
4. Show before and after for each metric. Do not summarise with one number.
5. For a drop, read individual errors in the result JSON and name the cause.
6. Run `--split test` only when the change is finished. Do not tune on what it shows.
7. Rebuild report tables with `.venv/bin/python -m evals.build_report`.
