# Plan: using PMC-Patients

**Status:** A is done (2026-11-06). Cohort search over all 1,620 cases is also done (2026-11-06), scored on TREC in reverse because PMC has no trial labels. B to E have not started, and all of them are optional.

## The data

- **What it is:** [PMC-Patients](https://huggingface.co/datasets/zhengyun21/PMC-Patients), patient summaries from published case reports in PubMed Central.
- **License:** CC BY-NC-SA 4.0 (per the Hugging Face tag). Credit the source, no commercial use, and share adapted material under the same license. Don't commit the dataset.
- **Local copy:** the first 5 MB of `PMC-Patients-V2.json` is in `data/raw/pmc/first5mb.json`, ignored by git. It holds 1,620 complete records.
- **Fields:** `patient_id`, `patient_uid`, `PMID`, `file_path`, `title`, `patient`, `age`, `gender`, `pub_date`.
- **Fetched by `scripts/download_data.py`** (the same first 5 MB). `scripts/pmc_examples.py` then rebuilds `data/pmc_examples.json`.

## Options

All of these add to the project. Prompts stay frozen, and current results don't change.

| | Use | What you get | Model calls | Your time |
|---|---|---|---|---|
| **A** | **Demo examples:** add about 5 published cases to the app | A demo on real-world text, not only the synthetic vignettes | About 6 per case | None |
| **B** | **Profile eval on real text:** compare extracted age and sex with the dataset's `age` and `gender` fields | The first profile score on real text that wasn't labelled by the coding agent | About 100 for a model sample; rules are free on all 1,620 | None |
| **C** | **Stability test:** run each case twice, adding an unrelated sentence the second time, and count changed statuses | A number for the instability seen in the browser, which no eval measures yet | About 90 for 30 cases on one trial each | Reading the result |
| **D** | **Your own gold set:** label about 50 patient–criterion pairs on real cases | Independent labels, which fixes the biggest weakness in the evaluation | About 15–30 | 2–3 hours |
| **E** | **Leave it unused** and focus on submitting | Time for the video and reflection | 0 | None |

## How each one affects the grade

- **A** helps the demo and working prototype, and is an honest answer to "are these patients real?". It adds no numbers.
- **B** is the best value for the evaluation points. The `age` and `gender` fields are ready-made reference labels. They only cover those two fields, and we haven't checked how the dataset's authors produced them, so the report would need to say so.
- **C** turns a limitation into a measured result, and it's a good metric-choice point for the video. Expect the number to look unflattering.
- **D** is the strongest evidence and uses your medical NLP background. It's also the only option where the judgement is entirely yours.

## Suggested paths

- **Little time:** A + B. No labelling, and it fits in one day's quota.
- **Strongest evaluation:** B + C + D, then A for the demo. A few hundred calls, plus 2–3 hours for D.
- **Short before 15 Nov:** E. The report is already defensible without this.

Recommended: **A + B**. Required work still comes first: the video, your reflection, the gold-label review, and `git init`.

## How B would run

| Run | Cases | Calls |
|---|---|---|
| Rules | All 1,620 | 0 |
| `gemini-3.5-flash-lite` (the app's model) | About 100, random sample | About 100 |

- **Scoring is plain code, with no LLM.** The model is only the system being tested.
- **Test the app's own model.** A different model's score would describe a system you don't use.
- **Check first** how the dataset's `age` and `gender` were produced. If they came from regex rules, a high rule score partly means two similar rule systems agree. Report it as "agreement with the dataset's fields", not "accuracy".

## Models to avoid on this data

- **MediPhi-Instruct** (`microsoft/MediPhi-Instruct`): its training data includes PMC-Patients, so scores on these cases may reflect text it has seen. It could still be compared on dev vignettes or TREC.
