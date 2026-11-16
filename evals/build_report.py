"""Write metric tables into docs/REPORT.md from evals/results, so no number is typed by hand."""
import json
import re

from .common import RESULTS, ROOT

REPORT = ROOT / "docs" / "REPORT.md"
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def load(component: str, mode: str, split: str) -> dict | None:
    path = RESULTS / f"{component}_{mode}_{split}.json"
    return json.loads(path.read_text()) if path.exists() else None


def rows(mode: str, split: str, trec_name: str = "trec") -> list[tuple[str, str, str]]:
    out = []

    def add(component, metric, value):
        out.append((component, metric, "n/a" if value is None else str(value)))

    if r := load("profile", mode, split):
        m = r["metrics"]
        for field in ("diagnoses", "medications", "absent", "labs_name_and_value"):
            add("1 Profile", f"{field} P / R / F1", f"{m[field]['precision']} / {m[field]['recall']} / {m[field]['f1']} (n={m[field]['support']})")
        add("1 Profile", "age / sex accuracy", f"{m['age_accuracy']} / {m['sex_accuracy']}")
        add("1 Profile", "main diagnosis first", m["main_diagnosis_first_accuracy"])
    if r := load("retrieval", mode, split):
        m = r["metrics"]
        add("2 Retrieval", "TREC query recall over judged pool", m["trec_query_recall_over_judged_pool"])
        add("2 Retrieval", "TREC query precision over judged pool", m["trec_query_precision_over_judged_pool"])
        add("2 Retrieval", "TREC recall@100 of the live registry", m["trec_recall_at_100_of_live_registry"])
        add("2 Retrieval", "topics with no query", f"{m['trec_topics_without_query']} of {m['trec_topics']}")
        add("2 Retrieval", "pool nDCG@10: rerank vs random", f"{m['pool_ndcg_at_10_rerank']} vs {m['pool_ndcg_at_10_random']}")
        add("2 Retrieval", "vignette on-topic P@10", m["vignette_on_topic_precision_at_10"])
        add("2 Retrieval", "hard-filter violations", m["hard_filter_violations"])
    if r := load("patient_search", mode, split):
        m = r["metrics"]
        sysm, cond, rnd = m["system"], m["conditions_only"], m["random"]
        n = f" ({m['trials']} trials, {m['patients_ranked_per_trial']} patients each)"
        add("2b Cohort search", "trials with an eligible patient in top 10: system / conditions only / random" + n,
            f"{sysm['trials_with_eligible_in_top_10']} {sysm['trials_with_eligible_in_top_10_95ci']} / {cond['trials_with_eligible_in_top_10']} / {rnd['trials_with_eligible_in_top_10']}")
        add("2b Cohort search", "eligible recall@10: system / conditions only / random",
            f"{sysm['eligible_recall_at_10']} / {cond['eligible_recall_at_10']} / {rnd['eligible_recall_at_10']}")
        add("2b Cohort search", "nDCG@10: system / conditions only / random", f"{sysm['ndcg_at_10']} / {cond['ndcg_at_10']} / {rnd['ndcg_at_10']}")
        add("2b Cohort search", "eligible patients flagged by the age/sex filter", f"{sysm['eligible_patients_ruled_out_by_filter']} of {sysm['eligible_patients']}")
    if r := load("parsing", mode, split):
        m = r["metrics"]
        add("3 Parsing", "segmentation F1, hand-written cases", m["segmentation_gold_cases"]["f1"])
        rt = m["segmentation_chia_roundtrip"]
        add("3 Parsing", "segmentation F1, Chia: star / dash / plain", f"{rt['star']['f1']} / {rt['dash']['f1']} / {rt['plain']['f1']}")
        e = m["entities"]
        add("3 Parsing", "entity micro-F1 vs Chia: strict / relaxed", f"{e['strict']['micro']['f1']} / {e['relaxed']['micro']['f1']} ({e['lines_scored']} lines)")
        for t in ("Condition", "Drug", "Procedure", "Measurement", "Value", "Temporal", "Negation", "Person"):
            add("3 Parsing", f"{t} F1: strict / relaxed", f"{e['strict'][t]['f1']} / {e['relaxed'][t]['f1']}")
        s = m["screening_only_vs_chia"]
        add("3 Parsing", "screening-only P / R / F1", f"{s['precision']} / {s['recall']} / {s['f1']} (n={s['support']})")
    if r := load("checker", mode, split):
        m = r["metrics"]
        for label in ("met", "not_met", "insufficient"):
            c = m["per_class"][label]
            add("4 Checker", f"{label} P / R / F1", f"{c['precision']} / {c['recall']} / {c['f1']} (n={c['support']})")
        add("4 Checker", "macro-F1", m["macro_f1"])
        add("4 Checker", "accuracy (95% CI)", f"{m['accuracy']} {m['accuracy_95ci']}")
        add("4 Checker", "quotes verbatim in patient text", m["evidence_verbatim_rate"])
        add("4 Checker", "quote matches gold, when status correct", m["evidence_matches_gold_when_correct"])
        add("4 Checker", "flip rate (met read as not met, or reverse)", m["flip_rate_on_definitive"])
        add("4 Checker", "invented decision on insufficient", m["invented_decision_rate_on_insufficient"])
        add("6 Follow-up", "criteria settled correctly after an answer", f"{m['followup_resolution_rate']} (n={m['followups']})")
        add("6 Follow-up", "targeted question rate", m["specific_question_rate"])
    if r := load("aggregate", mode, split):
        m = r["metrics"]
        add("5 Aggregation", "truth table", f"{m['truth_table_correct']} of {m['truth_table_total']}")
    if r := load("checker", mode, split):
        m = r["metrics"]
        add("5 Aggregation", "verdict agrees with verdict from gold statuses", m["verdict_agreement_with_gold_statuses"])
        add("5 Aggregation", "missed blocks (patient should be blocked)", f"{m['missed_blocks_rate']} (n={m['gold_blocked_patients']})")
    if r := load("safety", mode, split):
        m = r["metrics"]
        add("6 Safety", "macro-F1 (authored cases, not held out)", m["per_class"]["macro_f1"])
        add("6 Safety", "unsafe proceed rate", m["unsafe_proceed_rate"])
        add("6 Safety", "urgent recall", m["urgent_recall"])
    if r := load(trec_name, mode, split):
        m = r["metrics"]
        e = m["eligible_vs_excluded"]
        add("End to end (TREC)", "eligible vs excluded P / R / F1", f"{e['precision']} / {e['recall']} / {e['f1']} (n={e['support']})")
        add("End to end (TREC)", "precision if nothing is ever blocked", m["precision_if_always_open"])
        add("End to end (TREC)", "excluded trials caught (95% CI)", f"{m['excluded_trials_caught']} {m['excluded_trials_caught_95ci']}")
        add("End to end (TREC)", "nDCG@10: system vs random", f"{m['ndcg_at_10_system']} vs {m['ndcg_at_10_random']}")
        add("End to end (TREC)", "verdicts on eligible trials", json.dumps(m["verdicts_by_gold_label"].get("eligible", {})))
        add("End to end (TREC)", "verdicts on excluded trials", json.dumps(m["verdicts_by_gold_label"].get("excluded", {})))
    return out


def table(mode: str) -> str:
    dev, test = rows(mode, "dev"), rows(mode, "test")
    if not dev and not test:
        return f"No `{mode}` results yet.\n"
    test_by_key = {(c, k): v for c, k, v in test}
    dev_by_key = {(c, k): v for c, k, v in dev}
    keys = list(dict.fromkeys([(c, k) for c, k, _ in test] + [(c, k) for c, k, _ in dev]))
    lines = ["| Component | Metric | Test | Dev |", "|---|---|---|---|"]
    lines += [f"| {c} | {k} | {test_by_key.get((c, k), '')} | {dev_by_key.get((c, k), '')} |" for c, k in keys]
    sample = load("checker", mode, "test") or load("checker", mode, "dev") or {}
    note = f"Mode `{mode}`, model `{sample.get('model')}`, run {sample.get('date')}, limit {sample.get('limit')}.\n\n"
    return note + "\n".join(lines) + "\n"


def comparison() -> str:
    """Test split, side by side. TREC rows use the same smaller pool for both, so they compare fairly."""
    offline, llm = rows("offline", "test", "trec_samepool"), rows("llm", "test")
    if not llm:
        return "No LLM test results yet.\n"
    off = {(c, k): v for c, k, v in offline}
    lines = ["| Component | Metric | Offline rules | Model |", "|---|---|---|---|"]
    lines += [f"| {c} | {k} | {off.get((c, k), '')} | {v} |" for c, k, v in llm]
    sample = load("checker", "llm", "test") or {}
    return f"Model `{sample.get('model')}`, run {sample.get('date')}.\n\n" + "\n".join(lines) + "\n"


def main() -> None:
    body = (
        f"{START}\n\n### Test split: offline rules vs model\n\n{comparison()}\n"
        f"### Offline baseline, all samples\n\n{table('offline')}\n### Model, test and dev\n\n{table('llm')}\n{END}"
    )
    text = REPORT.read_text()
    REPORT.write_text(re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: body, text, flags=re.S))
    print("updated", REPORT)


if __name__ == "__main__":
    main()
