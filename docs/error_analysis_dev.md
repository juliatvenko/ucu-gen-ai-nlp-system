# Error analysis: TREC end to end, dev split, model mode

Source: `evals/results/trec_llm_dev.json` (all 37 dev topics, 2 trials per label, `gemini-3.5-flash-lite`, run 2026-11-16).
Dev only. Test errors were not read, as `AGENTS.md` requires.

Result: eligible vs excluded P 0.778, R 0.662, F1 0.715 on 74 eligible trials. The run has 39 errors:
25 eligible trials blocked, and 14 excluded trials left open. Each case below was read by hand, so the groups are
a judgement, not a measurement.

## 25 eligible trials blocked

| Group | Count | Cases |
|---|---|---|
| A. Parsing lost the trial's structure | 11 | #3, #4, #9, #15, #23, #31, #33, #34, #35, #37, #39 |
| B. The model follows the trial text; the TREC label is more lenient | 12 | #1, #2, #5, #6, #12, #14, #16, #18, #20, #22, #30, #32 |
| C. The model over-reads the patient text | 2 | #10, #13 |

**A. Parsing lost the structure (11).** The fix belongs in `parsing.py`, not in the prompt.

- *Option lists and sub-groups* (#3, #4, #9, #15, #31, #35, #37, #39). The trial lists alternatives, such as
  "one of these diseases" or criteria for each study group (SPMS or Alzheimer's, migraine with or without aura,
  patients or healthy controls). Each line becomes a separate required criterion, so no patient can meet all of
  them. #3 has 17 disease options, each marked not met.
- *Conditional criteria* (#33). "For women of child-bearing potential, a pregnancy test…" does not apply to a
  menopausal patient, but `not_met` on an inclusion blocks her. There is no "not applicable" status.
- *Wrong polarity or section* (#23, #34). #34 lists exclusions inside the inclusion section ("Participants with a
  history of diabetes … are not eligible"). The model correctly says the patient has no diabetes, which is
  `not_met` on an inclusion, so she is blocked 7 times. #23 has "Patients above 18 years old" in the exclusion list.
  A heading ("Diabetes Mellitus Eligibility Criteria", #4) was also parsed as a criterion.

**B. The trial text excludes the patient, but TREC says eligible (12).** Examples: glioblastoma trial for an
anaplastic astrocytoma (#1, #2), hepatic encephalopathy as an exclusion in a patient with it (#5), "newly
diagnosed" for a patient treated for years (#6, #20), "history of cervical cancer" excluded in a patient with
cervical cancer (#30). These suggest that assessors judged mainly on the main condition. Changing the system for
these would teach it to ignore criteria.

**C. Over-reading (2).** #10: dysphagia for solids read as "unable to take oral medication". #13: "Did not undergo
surgery" marked met because surgery isn't mentioned, which is silence used as evidence.

## 14 excluded trials left open

- *Reasoning contradicts the status* (#19, #27). #19: "She is on stable doses of octreotide LAR", and the reasoning
  says she is treated, but the status is `not_met`. #27: the reasoning says type 1 diabetes is a serious chronic
  disease, but the status is `not_met`. The verbatim check can't catch this, because the quote is real.
- *Silence read as a denial* (#29): "She is otherwise healthy" used as evidence for "not on anticoagulation".
- *The reason for exclusion wasn't found* (the other 11). The deciding criterion stayed `insufficient`, or no
  criterion was decided at all (#8, #28). This is the cautious direction: the patient is shown as needing more data,
  not as eligible.

## What to change, in order

1. Parsing: keep option lists and group-specific criteria together, and flip "are not eligible" lines into
   exclusions (group A, 11 of 25 blocks). Deterministic, so it can be tested without model calls.
2. A "not applicable" outcome for conditional criteria (#33).
3. A consistency check between status and reasoning (#19, #27), or ask the model for the reasoning before the status.

Any of these changes the system that the test split measured. The test run would have to be repeated before the
report's numbers describe the new system.

## After the parsing fix (item 1, same day)

Parsing now marks option groups, subgroup criteria, donor or relative sections, participant groups, and exclusions
written in the inclusion list. Aggregation uses the marks. The case numbers above refer to the error list as it was
before the fix, kept in `evals/results/archive/before-parsing-structure/trec_llm_dev.json`.

- Dev errors: 39 to 34. No new errors appeared.
- Group A fixed: #3 (17 disease options), #4 (three participant groups), #9 (relatives' section and a missed
  exclusion header), #34 (exclusions in the inclusion list), #37 (SPMS and Alzheimer's subgroups). 5 of 11.
- Group A still wrong: #15 and #39 (options at the same level as their parent), #35 (migraine with or without
  aura, alternatives one level up), #23 and #31 (the trial text itself is wrong or mixes two groups in one list),
  #33 (the model answers `not_met` for a criterion it calls not applicable, against the prompt).
- Groups B and C, and the 14 missed exclusions, were not touched.
