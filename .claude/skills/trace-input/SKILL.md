---
name: trace-input
description: Walk one patient description through every TrialMatch component and show each input and output. Use for the report walkthrough, the demo video, or debugging a wrong verdict.
---

1. Pick the input. Use a synthetic vignette from `data/vignettes.json` unless the user gives text. Never use real patient data.
2. Run `.venv/bin/python -m scripts.trace_input --vignette <id>` (add `--nct <id>` to fix the trial).
3. Show, in order: safety decision, profile, retrieval query and top candidates, parsed criteria, each check with evidence, verdict, follow-up questions.
4. Mark each step as model call, external tool call, or plain code.
5. For a wrong verdict, name the first component whose output was wrong. Later errors may just be downstream.
