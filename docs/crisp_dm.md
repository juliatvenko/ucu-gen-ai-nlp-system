# CRISP-DM log

Agents update this file as they work (see `AGENTS.md`). Newest entries go last in each phase.

## 1. Business understanding

**Problem.** To find a suitable trial, someone reads the criteria of dozens of studies by hand and compares each one with the patient. That is slow and expensive.

**Users.** Primary: clinician or trial coordinator, who save the most time. Secondary: patient or relative, for orientation only.

**Modes.** Matcher (one patient, ranked trials). Cohort (one trial, a set of patients). Same engine.

**Success looks like:** finds on-topic trials, catches patients who fail a criterion, shows its reason for every decision, and says "insufficient data" instead of guessing.

**Costly errors, in order.** A guess presented as fact. Telling an excluded patient they qualify. Hiding a trial the patient could join.

**Ethics.** Assistive, not diagnostic. It quotes its basis, and final decisions belong to clinicians and study staff. Synthetic and public data only.

**Out of scope.** Trial location and travel, deployment, real patient data.

## 2. Data understanding

**2026-11-04, Chia** (figshare, CC BY 4.0). Files came in `_inc` / `_exc` pairs, BRAT format: 2000 text files, 12,631 lines. Most common entity types: Condition 12,039, Qualifier 4,157, Value 4,002, Drug 3,801, Procedure 3,595, Temporal 3,580, Measurement 3,305. 1,920 spans are discontinuous, and are scored by their outer span.

**2026-11-04, TREC Clinical Trials 2021.** 75 patient topics, 35,832 judgements: 24,243 not relevant, 6,019 excluded, 5,570 eligible, so about 155 relevant per topic. Added after the original plan because it gives human judgements on real patient descriptions, and the brief says to check existing datasets before generating synthetic ones.

**2026-11-04, ClinicalTrials.gov API v2.** Open, no key. Structured age and sex fields, free-text eligibility. Sample query returned over 12,000 trials for a common condition. Text contains escapes such as `\>=`.

**2026-11-05, PMC-Patients.** Published case reports from PubMed Central, CC BY-NC-SA 4.0. The first 5 MB of the 837 MB file holds 1,620 complete records. It has no trial labels. Note: MediPhi-Instruct lists it as training data, so scores on it would be biased for that model.

**Rejected.** n2c2 2018: needs a DUA and manual approval, too much overhead for this assignment.

## 3. Data preparation

**2026-11-04.** `scripts/download_data.py` fetches raw data. `scripts/chia.py` splits Chia by trial (800 / 100 / 100, seed 13), so one trial's wording can't cross splits. The gazetteer is built from train only and keeps a phrase if it is annotated at least half the times it appears.

**2026-11-04, went back from Evaluation.** Condition F1 was implausibly low. Cause: Python's newline conversion shifted about 20% of Chia offsets (1,522 of 7,663 sampled spans misaligned, 0 with raw reads). This had corrupted the gazetteer too. Fixed with `read_raw`, regression test added, and the gazetteer grew from 440 to 1,862 phrases.

**2026-11-04, synthetic gold.** `data/vignettes.json`: 16 patients, 128 labelled pairs, split by patient into dev and test. Written by the coding agent. They still need review by a person with domain knowledge.

## 4. Modeling

**2026-11-04.** Built deterministic pieces first (parsing, numeric checks, aggregation), then added the model where judgement is needed. Offline rules are the baseline.

**2026-11-04, went back from Deployment.** Tracing live trials exposed errors the gold set didn't:

| Found | Fix |
|---|---|
| `Age ≥ 21 and ≤ 65` checked only the first bound | All bounds must hold |
| A 40-criteria cap dropped later criteria, which are often exclusions | Removed the cap, and model calls are batched |
| mmol/L thresholds compared with mg/dL values | Abstain on foreign units |
| `Years of T2DM ≤ 10` marked met on a mention alone | A mention can't settle a number |
| `Other types of diabetes besides T2DM` blocked a T2DM patient | Abstain on other, except, and similar words |
| `Untreated brain metastases` matched "treated brain metastases" | Abstain on qualifiers |

**2026-11-04, went back from Evaluation.** Rebuilding the gazetteer caused a safety regression: "no known allergies" became a diagnosis, so an input proceeded that should have asked for one. The fallback now checks negation and skips non-diagnoses such as "healthy". Follow-up questions also stopped re-asking about stated facts.

## 5. Evaluation

Results are in `evals/results/`, summarised in `docs/report.pdf`.

**2026-11-04, metric correction.** TREC recall@100 against the live registry came out near zero. Part of that is the measure itself: thousands of hits for a query, against a pool of about 155 from a 2021 snapshot. Added query recall and precision over the judged pool, which has no depth cutoff. Both are reported.

**2026-11-04, split discipline.** Rule changes used dev errors and live-trial traces. Test aggregates were seen during the fixes above, but test errors were not read. The last rule fix lowered dev macro-F1, and was kept because it removes wrong blocks on real trials that the small gold set doesn't contain.

**2026-11-04, LLM mode started.** Model: `nvidia/nemotron-3.5-super-vl:free`, chosen after trying each JSON-capable free model once: three were unavailable, and one misspelled a drug. Real calls exposed a JSON failure the fake server couldn't: a missing quote, repeated by the retry. Fixed with JSON mode, a repair prompt that shows the bad reply, and abstention on invalid output.

**2026-11-04, dev checker scored 64 of 64.** Treated as a warning, not a success: the vignettes are short and clear, and were written by a model. TREC is the real test. Stopped by the 50-requests-a-day free limit before TREC ran.

**2026-11-04, model changed.** Moved to Google AI Studio's free `gemini-3.5-flash-lite` for its higher daily limit and first-party reliability. Nemotron dev results are kept in `evals/results/archive/nemotron-dev/`.

**2026-11-04, went back to Modeling.** Gemini decided on 44% of dev criteria where the record is silent, quoting real but irrelevant text ("Female, age 47" for "Known hepatitis B"). The verbatim guard can't catch this, because it proves a quote exists, not that it is relevant. Tightening the prompt lowered this to 19%. Also fixed a safety bug: the model read "this headache" as a diagnosis, so advice questions proceeded.

**2026-11-04, prompts frozen** after TREC on 8 dev topics. Remaining wrong blocks there include disease-specific items applied to the wrong disease, and cases where the human label looks more lenient than the trial text. These are reported as limitations and not tuned further.

**2026-11-04, test split complete** with frozen prompts, on all 38 test topics at 2 trials per label. Test errors were not read. Both systems reach the same F1 on TREC with opposite errors, so F1 alone is not a useful summary here. The baseline was rescored on the same pool, because nDCG depends on pool size.

**2026-11-16, full dev error analysis.** The TREC eval didn't save its failures, so it now does. Ran all 37 dev topics with the model (before: 8). Dev F1 0.715 on 74 eligible trials, close to test (0.705). Read all 39 errors by hand ([error_analysis_dev.md](error_analysis_dev.md)). Of 25 wrong blocks, 11 come from parsing losing the trial's structure (option lists, group-specific criteria, exclusions written inside the inclusion section), 12 follow the trial text where the TREC label is more lenient, and 2 over-read the patient. Two missed exclusions have reasoning that contradicts the status. Nothing was changed: prompts and parsing stay frozen, so the test results still describe the system. Parsing structure is the first next step.

**2026-11-16, went back to Modeling: trial structure in parsing.** Yuliia chose to fix the 11 parsing errors (group A) and nothing else. Parsing now marks option groups, subgroup criteria, donor or relative sections, participant groups, and exclusions written in the inclusion list, and aggregation applies them in code. Criterion text and ids were kept, so the model's prompts changed for only 11 of 443 trials and cached answers covered the rest. Every new mark was read across all 443 pool trials before running anything, which caught false positives ("healthy women of reproductive age", "COPD patients Gold B or C", headings that are criteria). Dev F1 0.715 to 0.761, test 0.705 to 0.722, excluded trials caught unchanged. Rules lost one caught exclusion on test. This reopens the test split once: test was rerun after the change, and its errors were not read. Before-results are in `evals/results/archive/before-parsing-structure/`.

## 6. Deployment

**2026-11-04.** Local Streamlit app. Checked in a browser against live ClinicalTrials.gov in offline mode, and by headless tests. Hosted deployment is optional in the brief and was not attempted.

**2026-11-04.** Checked in a browser on Gemini. This exposed a bug: `load_dotenv` kept old values in a running process, so an edited `.env` produced a mix of old and new settings. `.env` now always wins.

**2026-11-05, interface rebuilt** in FastAPI and React, with live progress and quotes highlighted in the patient text. The Streamlit app and its tests were then removed. The pipeline only gained progress-reporting generators, and `match_patient` now runs on them. Checker offline test score was unchanged after the rewrite. Prompts are untouched, and the model results were not rerun.

**2026-11-06, published examples added.** Five PMC-Patients cases were added to the app as demo examples (breast cancer, HIV, Crohn's disease, coronary artery disease, atrial fibrillation). They were chosen by rule: a lexicon condition, ages 18–85, 500–1,800 characters, no urgent wording, and recruiting trials found. Text is unchanged and credited. They are not in any eval.

**2026-11-06, trial picker for cohort mode.** Seven suggested trials that fit example patients (`data/suggested_trials.json`), live search by condition or ID, and a preview with the trial's description and its parsed criteria before screening. Descriptions use a separate request, so the evals' cache keys and results are unchanged: the TREC eval made no new registry requests afterwards.

**2026-11-06, retrieval bug found through a published case.** The model listed "cutaneous lesions on the right leg" before Crohn's disease, and the old fallback shortened that phrase until it matched, so the app searched for "the right leg". Retrieval now tries every diagnosis first, then shorter forms, and never searches for a body location or a generic word alone. The retrieval eval was rerun from cached profiles, and the report tables were rebuilt.

**2026-11-05, fallback added, at the author's request.** A provider overload (HTTP 503) stopped a search with an error. The interface now falls back to the rules and labels those results "Rules only". It is off by default in the pipeline, so evals still fail loudly, and a test enforces this. Eval scores are unaffected.

**2026-11-05, instability seen in the browser.** Adding "not pregnant or breastfeeding" correctly settled the pregnancy criteria, but also changed 23 of 71 statuses on trial NCT05369065. The first run had marked silent criteria as `not_met`, and the second correctly marked them `insufficient`. Listed as a limitation, because prompts are frozen.

**2026-11-06, cohort search added, measured before it was built in.** Cohort mode could only screen patients picked by hand. A new rules-only search ranks patients for a trial, and an eval was written first: TREC in reverse, ranking all 75 TREC patients for each of 300 dev and 300 test trials. Seven query settings were compared on dev. Test was run once and its errors were not read. The search then went into the app over the 1,620 PMC case reports, with a matching sentence shown for each, because the first shortlists contained passing mentions such as a negative rheumatoid factor test. Settings weren't changed after seeing PMC results, since PMC has no labels to check a change against.

**2026-11-09, synthetic vignettes removed from the app, at the author's request.** The demo examples are now only the five published case reports, plus cohort search over all 1,620. The vignettes stay in `data/vignettes.json` as eval data, so no score changes.
