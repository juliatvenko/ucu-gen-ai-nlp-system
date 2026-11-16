---
name: crisp-dm-checkpoint
description: Close out a CRISP-DM phase and record the decision. Use when finishing a chunk of work or when an eval result sends the work back to an earlier phase.
---

1. Name the phase you are closing and the phase that comes next.
2. Add a dated entry under that phase in `docs/crisp_dm.md`: what was decided, the evidence, and what was rejected.
3. Evidence must be something you ran or read, such as a dataset count or a file in `evals/results/`.
4. If you are going back a phase, write what triggered it.
5. Check the exit condition:
   - Data understanding: real samples inspected and counts recorded.
   - Modeling: tests pass and the component has an eval.
   - Evaluation: dev and test results exist and low scores have a stated cause.
   - Deployment: the README commands were run from a clean start.
6. Report any exit condition that is not met. Do not mark the phase closed.
