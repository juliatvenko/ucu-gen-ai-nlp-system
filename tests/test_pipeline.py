import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from trialmatch.aggregate import aggregate, effect, rank
from trialmatch.checker import check_hybrid, check_llm, check_rule, quote_is_verbatim
from trialmatch.followup import generate_questions
from trialmatch.llm import LLMClient, LLMError, parse_json
from trialmatch.parsing import parse_criteria
from trialmatch.profile import extract_rule
from trialmatch.retrieval import _parse_age, hard_filter, rerank
from trialmatch.safety import assess
from trialmatch.schemas import Criterion, CriterionCheck, PatientProfile, Trial

ROOT = Path(__file__).resolve().parent.parent


def crit(text, kind="inclusion", cid="c1", **kw):
    return Criterion(id=cid, kind=kind, text=text, **kw)


class FakeClient:
    """Stands in for the model: returns canned checks and counts calls."""
    label = "fake:model"

    def __init__(self, checks):
        self.checks = checks
        self.calls = 0

    def complete_json(self, component, system, user, schema):
        self.calls += 1
        return schema.model_validate({"checks": self.checks})


# ---- gold data integrity ----

def test_gold_evidence_is_verbatim_in_patient_text():
    for v in json.loads((ROOT / "data" / "vignettes.json").read_text()):
        for c in v["criteria"]:
            if c["status"] != "insufficient":
                assert c["evidence"].lower() in v["text"].lower(), (v["id"], c["text"])
            else:
                assert "evidence" not in c, (v["id"], c["text"])


def test_gold_splits_are_balanced():
    data = json.loads((ROOT / "data" / "vignettes.json").read_text())
    assert sum(v["split"] == "dev" for v in data) == sum(v["split"] == "test" for v in data)


# ---- aggregation ----

@pytest.mark.parametrize("kind,status,want", [
    ("inclusion", "met", "passes"), ("inclusion", "not_met", "blocks"), ("inclusion", "insufficient", "unknown"),
    ("exclusion", "met", "blocks"), ("exclusion", "not_met", "passes"), ("exclusion", "insufficient", "unknown"),
])
def test_effect_polarity(kind, status, want):
    assert effect(kind, status) == want


def verdict_of(*pairs):
    criteria = [crit("x", k, str(i)) for i, (k, _) in enumerate(pairs)]
    checks = [CriterionCheck(criterion_id=str(i), status=s) for i, (_, s) in enumerate(pairs)]
    return aggregate(Trial(nct_id="N"), criteria, checks)


def test_one_blocker_beats_everything():
    assert verdict_of(("inclusion", "met"), ("exclusion", "met")).verdict == "not_eligible"


def test_all_passing_is_likely_eligible():
    assert verdict_of(("inclusion", "met"), ("exclusion", "not_met")).verdict == "likely_eligible"


def test_mostly_unknown_is_insufficient_not_a_guess():
    assert verdict_of(("inclusion", "insufficient"), ("exclusion", "insufficient"), ("inclusion", "met")).verdict == "insufficient_data"


def test_screening_only_is_not_missing_data():
    criteria = [crit("Signed informed consent", cid="a", screening_only=True), crit("Adult", cid="b")]
    checks = [CriterionCheck(criterion_id="a", status="insufficient"), CriterionCheck(criterion_id="b", status="met")]
    assert aggregate(Trial(nct_id="N"), criteria, checks).verdict == "likely_eligible"


def test_rank_puts_ineligible_last():
    a, b = verdict_of(("exclusion", "met")), verdict_of(("inclusion", "met"))
    assert rank([a, b])[0].verdict == "likely_eligible"


# ---- evidence guard ----

def test_quote_guard_normalises_whitespace_but_not_words():
    assert quote_is_verbatim("HbA1c  8.4%", "Recent hba1c 8.4% today")
    assert not quote_is_verbatim("HbA1c 9.4%", "Recent HbA1c 8.4% today")
    assert not quote_is_verbatim("", "anything")


def test_llm_decision_without_real_quote_becomes_insufficient():
    client = FakeClient([{"id": "c1", "status": "met", "evidence": "made up text", "reasoning": "r"}])
    check = check_llm([crit("Has asthma")], "Patient has diabetes.", client)[0]
    assert check.status == "insufficient" and check.source == "guard"


def test_llm_decision_with_real_quote_is_kept():
    client = FakeClient([{"id": "c1", "status": "met", "evidence": "has diabetes", "reasoning": "r"}])
    assert check_llm([crit("Has diabetes")], "Patient has diabetes.", client)[0].status == "met"


def test_llm_missing_or_invalid_answer_becomes_insufficient():
    client = FakeClient([{"id": "c1", "status": "probably", "evidence": "x"}])
    criteria = [crit("A"), crit("B", cid="c2")]
    assert [c.status for c in check_llm(criteria, "text", client)] == ["insufficient", "insufficient"]


def test_hybrid_keeps_numeric_and_screening_in_code():
    text = "58-year-old woman with asthma."
    criteria = [crit("Age 18 years or older", cid="a"), crit("Signed informed consent", cid="b", screening_only=True), crit("Has asthma", cid="c")]
    client = FakeClient([{"id": "c", "status": "met", "evidence": "with asthma", "reasoning": "r"}])
    checks = check_hybrid(criteria, text, extract_rule(text), client)
    assert [c.source for c in checks] == ["rule:numeric", "screening", "llm"]
    assert client.calls == 1


# ---- rule checker ----

@pytest.mark.parametrize("criterion,age,want", [
    ("Age 18 years or older", 40, "met"), ("Age 18 years or older", 12, "not_met"),
    ("Age between 18 and 65 years", 70, "not_met"), ("Aged 18 to 65 years", 30, "met"),
    ("Age under 18 years", 25, "not_met"), ("Age ≥ 21", 21, "met"),
])
def test_age_comparisons(criterion, age, want):
    text = f"{age}-year-old patient."
    assert check_rule([crit(criterion)], text)[0].status == want


@pytest.mark.parametrize("criterion,text,want", [
    ("HbA1c between 7.0% and 10.0%", "HbA1c 8.4%.", "met"),
    ("HbA1c between 7.0% and 10.0%", "HbA1c 11%.", "not_met"),
    ("eGFR below 30", "eGFR 72.", "not_met"),
    ("eGFR below 30", "eGFR 24.", "met"),
    ("HbA1c above 7", "Nothing about sugar.", "insufficient"),
])
def test_lab_comparisons(criterion, text, want):
    assert check_rule([crit(criterion)], text)[0].status == want


def test_silence_is_insufficient():
    assert check_rule([crit("History of stroke", "exclusion")], "Patient has asthma.")[0].status == "insufficient"


def test_denied_condition_is_not_met():
    check = check_rule([crit("History of heart failure", "exclusion")], "She denies any history of heart failure.")[0]
    assert check.status == "not_met" and "denies" in check.evidence


def test_undated_mention_does_not_satisfy_time_window():
    text = "He has had a stroke."
    assert check_rule([crit("Stroke within the last 6 months", "exclusion")], text)[0].status == "insufficient"


def test_followup_answer_format_is_understood():
    text = "Patient has asthma.\nFollow-up: Has the patient had a stroke? No."
    assert check_rule([crit("History of stroke", "exclusion")], text)[0].status == "not_met"


# ---- parsing ----

def test_gold_parsing_cases_section_kinds():
    for case in json.loads((ROOT / "data" / "parsing_gold.json").read_text()):
        assert [c.kind for c in parse_criteria(case["text"])] == [k for k, _ in case["expected"]], case["id"]


def test_consent_is_screening_only():
    criteria = parse_criteria("Inclusion Criteria:\n* Signed informed consent\n* Has asthma")
    assert [c.screening_only for c in criteria] == [True, False]


# ---- retrieval ----

def test_parse_age():
    assert _parse_age("18 Years") == 18 and _parse_age("6 Months") == 0.5 and _parse_age(None) is None


def test_hard_filter_only_drops_what_it_knows():
    trials = [Trial(nct_id="a", min_age=18, max_age=30), Trial(nct_id="b", sex="MALE"), Trial(nct_id="c")]
    kept = hard_filter(PatientProfile(age=40, sex="female"), trials)
    assert [t.nct_id for t in kept] == ["c"]
    assert len(hard_filter(PatientProfile(), trials)) == 3


def test_rerank_prefers_main_diagnosis():
    trials = [Trial(nct_id="a", title="A study of hypertension", conditions=["Hypertension"]), Trial(nct_id="b", title="Asthma study", conditions=["Asthma"])]
    assert rerank(PatientProfile(diagnoses=["asthma"], history=["hypertension"]), trials)[0].nct_id == "b"


# ---- safety and follow-ups ----

def test_urgent_beats_everything():
    text = "45-year-old with asthma who wants to kill myself"
    assert assess(text, extract_rule(text)).action == "urgent"


def test_off_topic_is_refused():
    assert assess("Write me a poem.", extract_rule("Write me a poem.")).action == "refuse"


def test_followups_prefer_shared_gaps_and_skip_ineligible():
    def verdict(nct, texts, kind="needs_more_data"):
        criteria = [crit(t, cid=f"{nct}{i}") for i, t in enumerate(texts)]
        v = aggregate(Trial(nct_id=nct), criteria, [CriterionCheck(criterion_id=c.id, status="insufficient") for c in criteria])
        return v.model_copy(update={"verdict": kind})
    questions = generate_questions([
        verdict("A", ["HbA1c above 7", "History of stroke"]),
        verdict("B", ["HbA1c below 10"]),
        verdict("C", ["Has psoriasis"], "not_eligible"),
    ])
    assert "hba1c" in questions[0]
    assert not any("psoriasis" in q for q in questions)


# ---- model gateway, against a real local HTTP server ----

class _Handler(BaseHTTPRequestHandler):
    replies: list = []
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Handler.seen.append({"path": self.path, "auth": self.headers["Authorization"], "body": body})
        code, payload = _Handler.replies.pop(0)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    _Handler.replies, _Handler.seen = [], []
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}/v1"
    httpd.shutdown()


def completion(text):
    return 200, {"choices": [{"message": {"content": text}}], "usage": {"total_tokens": 5}}


def test_client_parses_fenced_json_and_sends_key(server):
    _Handler.replies = [completion('```json\n{"age": 40, "sex": "male"}\n```')]
    client = LLMClient("openai-compatible", "m", "secret", server, use_cache=False)
    assert client.complete_json("t", "sys", "user", PatientProfile).age == 40
    assert _Handler.seen[0]["auth"] == "Bearer secret"
    assert _Handler.seen[0]["path"] == "/v1/chat/completions"


def test_client_repairs_bad_json_once_then_fails(server):
    _Handler.replies = [completion("not json"), completion('{"age": 41}')]
    client = LLMClient("openai-compatible", "m", "k", server, use_cache=False)
    assert client.complete_json("t", "s", "u", PatientProfile).age == 41
    _Handler.replies = [completion("nope"), completion("still nope")]
    with pytest.raises(LLMError):
        client.complete_json("t", "s", "u", PatientProfile)


def test_client_does_not_retry_auth_error(server):
    _Handler.replies = [(401, {"error": "bad key"})]
    client = LLMClient("openai-compatible", "m", "k", server, use_cache=False)
    with pytest.raises(LLMError, match="401"):
        client.complete_json("t", "s", "u", PatientProfile)
    assert len(_Handler.seen) == 1


def test_parse_json_handles_prose():
    assert parse_json('Here you go: {"a": 1} done') == {"a": 1}


def test_qualified_concept_does_not_flip():
    text = "He has treated brain metastases."
    assert check_rule([crit("Untreated brain metastases", "exclusion")], text)[0].status == "insufficient"


@pytest.mark.parametrize("criterion,want", [("ECOG performance status of 0 or 1", "met"), ("ECOG performance status of 0", "not_met")])
def test_ecog_value_lists(criterion, want):
    assert check_rule([crit(criterion)], "ECOG 1.")[0].status == want


CHIA = ROOT / "data" / "raw" / "chia"


@pytest.mark.skipif(not CHIA.exists(), reason="Chia not downloaded")
def test_chia_offsets_align_with_annotation_text():
    from scripts.chia import read_raw
    checked = 0
    for ann in sorted(CHIA.glob("*.ann"))[:100]:
        text = read_raw(ann.with_suffix(".txt"))
        for line in read_raw(ann).splitlines():
            parts = line.split("\t")
            if line.startswith("T") and len(parts) >= 3 and ";" not in parts[1]:
                _, start, end = parts[1].split()[:3]
                assert text[int(start):int(end)].strip() == parts[2].strip(), (ann.name, line)
                checked += 1
    assert checked > 1000


@pytest.mark.parametrize("criterion,age,want", [
    ("Age ≥ 21 and ≤ 65 years at time of enrollment.", 70, "not_met"),
    ("Age ≥ 21 and ≤ 65 years at time of enrollment.", 40, "met"),
])
def test_both_bounds_are_checked(criterion, age, want):
    assert check_rule([crit(criterion)], f"{age}-year-old patient.")[0].status == want


def test_parenthetical_conversion_is_not_a_second_bound():
    assert check_rule([crit("HbA1c ≥ 7.0% and ≤ 9.0% (53-75 mmol/mol)")], "HbA1c 8.4%.")[0].status == "met"


def test_other_units_are_not_compared():
    assert check_rule([crit("Creatinine below 133 umol/L")], "Creatinine 1.2 mg/dL.")[0].status == "insufficient"


def test_every_criterion_reaches_the_model_across_batches():
    criteria = [crit(f"Condition {i}", cid=f"c{i}") for i in range(95)]
    client = FakeClient([])
    checks = check_llm(criteria, "text", client)
    assert len(checks) == 95 and client.calls == 3


def test_a_late_blocker_is_not_lost():
    from trialmatch.pipeline import evaluate
    lines = "\n".join(f"* Unrelated requirement number {i}" for i in range(60))
    trial = Trial(nct_id="N", eligibility_text=f"Inclusion Criteria:\n{lines}\nExclusion Criteria:\n* History of stroke")
    text = "Patient had a stroke."
    assert evaluate(trial, text, extract_rule(text)).verdict == "not_eligible"


def test_mention_does_not_settle_a_numeric_condition():
    text = "Patient has type 2 diabetes."
    assert check_rule([crit("Years of type 2 diabetes ≤ 10 years")], text)[0].status == "insufficient"
    assert check_rule([crit("Diagnosis of type 2 diabetes")], text)[0].status == "met"


@pytest.mark.parametrize("criterion", ["Other types of diabetes besides T2DM", "Current treatment except metformin"])
def test_other_and_except_do_not_create_false_blocks(criterion):
    text = "Woman with type 2 diabetes on metformin."
    assert check_rule([crit(criterion, "exclusion")], text)[0].status == "insufficient"


def test_questions_do_not_ask_what_the_patient_text_already_says():
    v = aggregate(Trial(nct_id="A"), [crit("Type 2 diabetes for at least 5 years", cid="a"), crit("History of stroke", cid="b")],
                  [CriterionCheck(criterion_id="a", status="insufficient"), CriterionCheck(criterion_id="b", status="insufficient")])
    questions = generate_questions([v], patient_text="Patient has type 2 diabetes.")
    assert not any(q.startswith("Does the patient have, or has the patient had, type 2") for q in questions)
    assert any("stroke" in q for q in questions)


def test_negated_gazetteer_term_is_not_a_diagnosis():
    assert extract_rule("A 50-year-old patient with no known allergies.").diagnoses == []


def test_healthy_is_not_a_diagnosis():
    assert extract_rule("A 22-year-old otherwise healthy woman.").diagnoses == []


def test_repair_prompt_shows_the_bad_reply(server):
    _Handler.replies = [completion('{"age": oops}'), completion('{"age": 41}')]
    client = LLMClient("openrouter", "m", "k", server, use_cache=False)
    assert client.complete_json("t", "s", "u", PatientProfile).age == 41
    assert "oops" in _Handler.seen[1]["body"]["messages"][1]["content"]
    assert _Handler.seen[0]["body"]["response_format"] == {"type": "json_object"}


def test_invalid_output_abstains_but_quota_errors_still_raise(server):
    client = LLMClient("openai-compatible", "m", "k", server, use_cache=False)
    _Handler.replies = [completion("nope"), completion("still nope")]
    check = check_llm([crit("Has asthma")], "Patient has asthma.", client)[0]
    assert check.status == "insufficient" and check.source == "guard"
    _Handler.replies = [(401, {"error": "bad key"})]
    with pytest.raises(LLMError):
        check_llm([crit("Has asthma")], "Patient has asthma.", client)


def test_model_lab_names_are_normalised_and_gaps_filled():
    from trialmatch.profile import normalise_labs
    from trialmatch.schemas import Lab
    profile = PatientProfile(labs=[Lab(name="Serum Creatinine", value=2.6)])
    labs = {l.name: l.value for l in normalise_labs(profile, "Creatinine 2.6. Blood pressure 148/86.").labs}
    assert labs == {"creatinine": 2.6, "systolic bp": 148, "diastolic bp": 86}


def test_daily_limit_fails_fast_with_a_clear_message(server):
    _Handler.replies = [(429, {"error": {"message": "Rate limit exceeded: free-models-per-day"}})]
    client = LLMClient("openrouter", "m", "k", server, use_cache=False)
    with pytest.raises(LLMError, match="Daily free-model limit"):
        client.complete_json("t", "s", "u", PatientProfile)
    assert len(_Handler.seen) == 1


def test_throttle_spaces_calls(monkeypatch):
    import time
    monkeypatch.setenv("LLM_RPM", "600")
    client = LLMClient("openai-compatible", "m", "k", "http://x", use_cache=False)
    started = time.monotonic()
    for _ in range(4):
        client._wait_for_slot()
    assert time.monotonic() - started >= 0.28


def test_google_per_day_quota_fails_fast(server):
    _Handler.replies = [(429, {"error": {"details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}})]
    client = LLMClient("openai-compatible", "m", "k", server, use_cache=False)
    with pytest.raises(LLMError, match="Daily free-model limit"):
        client.complete_json("t", "s", "u", PatientProfile)
    assert len(_Handler.seen) == 1


def test_advice_question_is_refused_even_if_a_symptom_reads_as_a_diagnosis():
    profile = PatientProfile(diagnoses=["headache"])
    assert assess("Should I take ibuprofen for this headache?", profile).action == "refuse"


def test_advice_question_with_a_real_description_proceeds():
    profile = PatientProfile(age=58, diagnoses=["type 2 diabetes"])
    assert assess("58-year-old with type 2 diabetes. Should I take metformin?", profile).action == "proceed"


def test_env_file_edits_reach_a_running_process(tmp_path, monkeypatch):
    import trialmatch.llm as llm
    for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, "ROOT", tmp_path)
    env = tmp_path / ".env"
    env.write_text("LLM_BASE_URL=http://x\nLLM_API_KEY=k\nLLM_MODEL=old\n")
    assert llm.get_client().model == "old"
    env.write_text("LLM_BASE_URL=http://x\nLLM_API_KEY=k\nLLM_MODEL=new\n")
    assert llm.get_client().model == "new"
    monkeypatch.delenv("LLM_MODEL", raising=False)


def test_provider_overload_gives_a_readable_message(server, monkeypatch):
    monkeypatch.setattr("trialmatch.llm.time.sleep", lambda s: None)
    _Handler.replies = [(503, [{"error": {"status": "UNAVAILABLE"}}])] * 5
    client = LLMClient("openai-compatible", "m", "k", server, use_cache=False)
    with pytest.raises(LLMError, match="overloaded") as caught:
        client.complete_json("t", "s", "u", PatientProfile)
    assert "UNAVAILABLE" not in str(caught.value)
    assert len(_Handler.seen) == 5


def test_query_candidates_try_other_diagnoses_before_shortening():
    from trialmatch.retrieval import query_candidates
    got = query_candidates(["cutaneous lesions on the right leg", "Crohn's disease"])
    assert got.index("Crohn's disease") < got.index("cutaneous lesions")
    assert not any(q.lower().startswith(("the ", "right ", "leg")) for q in got)
    assert "lesions" not in got and "right leg" not in got


def test_retrieve_uses_the_second_diagnosis_when_the_first_finds_nothing(monkeypatch):
    import trialmatch.retrieval as r
    seen = []
    def fake_search(query, status, page_size):
        seen.append(query)
        return [Trial(nct_id="NCT1", title="Crohn's study", conditions=["Crohn Disease"])] if query == "Crohn's disease" else []
    monkeypatch.setattr(r, "search_trials", fake_search)
    query, ranked = r.retrieve(PatientProfile(diagnoses=["cutaneous lesions on the right leg", "Crohn's disease"]))
    assert query == "Crohn's disease" and ranked[0].nct_id == "NCT1"
    assert seen == ["cutaneous lesions on the right leg", "Crohn's disease"]


def test_specific_phrase_is_still_relaxed_when_nothing_else_matches(monkeypatch):
    import trialmatch.retrieval as r
    monkeypatch.setattr(r, "search_trials", lambda q, s, n: [Trial(nct_id="NCT2")] if q == "astrocytoma" else [])
    assert r.retrieve(PatientProfile(diagnoses=["anaplastic astrocytoma of the spine"]))[0] == "astrocytoma"


# Cohort search


def test_patient_search_ranks_condition_match_first():
    from trialmatch.patient_search import rank_patients
    trial = Trial(nct_id="NCT1", title="Drug X in rheumatoid arthritis", conditions=["Rheumatoid Arthritis"], status="RECRUITING")
    patients = {"a": "62-year-old man with gout.", "b": "55-year-old woman with rheumatoid arthritis on methotrexate.", "c": "Healthy 30-year-old."}
    assert rank_patients(trial, patients)[0].patient_id == "b"


def test_patient_search_flags_age_and_sex_but_never_on_unknowns():
    from trialmatch.patient_search import rank_patients
    trial = Trial(nct_id="NCT1", title="Asthma", conditions=["Asthma"], status="RECRUITING", min_age=18, sex="FEMALE")
    patients = {"child": "A 9-year-old girl with asthma.", "man": "A 40-year-old man with asthma.", "unknown": "Asthma since childhood."}
    ranked = {c.patient_id: c for c in rank_patients(trial, patients)}
    assert ranked["child"].ruled_out.startswith("younger")
    assert ranked["man"].ruled_out
    assert ranked["unknown"].ruled_out == ""
    assert rank_patients(trial, patients)[0].patient_id == "unknown"


def test_patient_search_prefers_structured_fields_over_text():
    from trialmatch.patient_search import rank_patients
    trial = Trial(nct_id="NCT1", title="Asthma", conditions=["Asthma"], status="RECRUITING", max_age=2)
    # The text alone can't give the age of a 5-month-old in years; the dataset field can.
    ranked = rank_patients(trial, {"p": "A 5 months old boy with asthma."}, known={"p": (5 / 12, "male")})
    assert ranked[0].ruled_out == ""


def test_case_report_age_units():
    from trialmatch.case_reports import _age
    assert _age([[34.0, "year"]]) == 34
    assert _age([[6.0, "month"]]) == 0.5
    assert _age([]) is None


# ---- trial structure kept by parsing and used by aggregation ----

def _verdict(text, statuses):
    """Parse a trial text, give each criterion the status for the first matching key, and aggregate."""
    criteria = parse_criteria(text, "T")
    checks = []
    for c in criteria:
        status = next((s for key, s in statuses.items() if key in c.text), "insufficient")
        checks.append(CriterionCheck(criterion_id=c.id, status=status))
    return criteria, aggregate(Trial(nct_id="T"), criteria, checks)


def test_section_headers_with_a_prefix_set_the_kind_and_skip_donors():
    text = ("Participant Inclusion Criteria\n* Multiple myeloma\nParticipant Exclusion Criteria\n* Active infection\n"
            "Donor Inclusion Criteria\n* ECOG performance status 0 or 1")
    criteria, v = _verdict(text, {"myeloma": "met", "infection": "not_met", "ECOG": "not_met"})
    assert [(c.text, c.kind) for c in criteria][:2] == [("Multiple myeloma", "inclusion"), ("Active infection", "exclusion")]
    assert criteria[2].cohort == "other person"
    assert v.verdict == "likely_eligible"  # the donor's ECOG says nothing about the patient


def test_option_list_needs_one_option_not_all():
    text = "Inclusion Criteria:\n* Eligible diseases listed below\n  * Acute leukemia in remission\n  * Burkitt's lymphoma in CR2\n  * Multiple myeloma"
    criteria, v = _verdict(text, {"Eligible": "met", "leukemia": "not_met", "Burkitt": "not_met", "myeloma": "met"})
    assert {c.group for c in criteria[1:]} == {"T-g1"}
    assert v.verdict == "likely_eligible"
    _, v = _verdict(text, {"Eligible": "met", "leukemia": "not_met", "Burkitt": "not_met", "myeloma": "not_met"})
    assert v.verdict == "not_eligible"  # no option fits


def test_option_list_with_a_number_needs_that_many():
    text = "Inclusion Criteria:\n* Adults\n* Migraine with 2 of following:\n  * Unilateral\n  * Pulsatile\n  * Severe"
    criteria, v = _verdict(text, {"Adults": "met", "Unilateral": "met", "Pulsatile": "not_met", "Severe": "insufficient"})
    assert [c.group_needed for c in criteria] == [1, 2, 2, 2]  # the short heading itself is dropped
    assert v.verdict == "needs_more_data"  # one met, one open: two are still possible
    _, v = _verdict(text, {"Adults": "met", "Unilateral": "met", "Pulsatile": "not_met", "Severe": "not_met"})
    assert v.verdict == "not_eligible"


def test_criterion_for_a_subgroup_cannot_block_alone():
    text = ("Inclusion Criteria:\n* Multiple sclerosis\n* For SPMS, EDSS worsening in the last year\n* AD subjects with MMSE 20-26\n"
            "* Women of child-bearing potential must use contraception\n* Healthy women of reproductive age (18-39 years old)")
    criteria, v = _verdict(text, {"sclerosis": "met", "SPMS": "not_met", "MMSE": "not_met", "Healthy": "met"})
    assert [c.conditional for c in criteria] == [False, True, True, True, False]  # an age group is a real requirement
    assert v.verdict != "not_eligible" and {"T-2", "T-3"} <= set(v.missing)
    assert not parse_criteria("Inclusion Criteria:\n* COPD patients Gold B or C\n* Adults 18 or older (must agree to use contraception)")[1].conditional


def test_exclusion_written_in_the_inclusion_list_is_an_exclusion():
    text = ("Inclusion Criteria:\n* Participants with a history of diabetes are not eligible.\n"
            "* Participants must not have ischemic heart disease.\n"
            "* Participants with use of anticoagulants (e.g. Warfarin) are not eligible.\n"
            "* Patients must have documented carcinoma; patients with ampullary carcinoma are not eligible\n"
            "* Patients who are not eligible for surgery\n* Episiotomy (third degree extensions will be excluded)")
    kinds = [c.kind for c in parse_criteria(text)]
    assert kinds == ["exclusion", "exclusion", "exclusion", "inclusion", "inclusion", "inclusion"]


def test_patient_gets_the_best_fitting_cohort():
    text = ("Cardiovascular Disease Eligibility Criteria\nINCLUSION CRITERIA:\n* Diagnosis of CAD\n"
            "Healthy Volunteers:\nINCLUSION CRITERIA:\n* Adults 18 or older\nEXCLUSION CRITERIA:\n* Diagnosis of diabetes or cardiovascular disease")
    criteria, v = _verdict(text, {"CAD": "met", "Adults": "met", "diabetes or": "met"})
    assert {c.cohort for c in criteria} == {"cardiovascular disease", "healthy volunteers"}
    assert v.verdict == "likely_eligible" and v.cohort == "cardiovascular disease"


def test_eligibility_sentence_is_not_a_cohort_heading():
    criteria = parse_criteria("Inclusion Criteria:\n* Subject meets anatomical eligibility criteria\n* Adults")
    assert [c.text for c in criteria] == ["Subject meets anatomical eligibility criteria", "Adults"]
    assert all(c.cohort == "" for c in criteria)
