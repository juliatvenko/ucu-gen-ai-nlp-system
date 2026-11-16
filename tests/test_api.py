"""The API over the real pipeline. Live ClinicalTrials.gov calls are replaced by a fixed trial."""
import json

import pytest
from fastapi.testclient import TestClient

import server
from trialmatch.llm import LLMError
from trialmatch.pipeline import match_patient
from trialmatch.schemas import Trial

TRIAL = Trial(
    nct_id="NCT00000001", title="Metformin add-on in type 2 diabetes", conditions=["Type 2 Diabetes"], status="RECRUITING",
    eligibility_text="Inclusion Criteria:\n* Age 18 years or older\n* HbA1c between 7.0% and 10.0%\n* Signed informed consent\n\n"
                     "Exclusion Criteria:\n* eGFR below 30\n* History of stroke",
)
PATIENT = "58-year-old woman with type 2 diabetes. HbA1c 8.4%. eGFR 72."


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("trialmatch.pipeline.retrieve", lambda profile, page_size=50: ("type 2 diabetes", [TRIAL]))
    monkeypatch.setattr(server, "get_trials", lambda ids: [TRIAL] if ids == ["NCT00000001"] else [])
    monkeypatch.setattr(server, "get_client", lambda: None)
    return TestClient(server.app)


def events(response) -> list[tuple[str, dict]]:
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_status_reports_offline_mode(client):
    assert client.get("/api/status").json() == {"mode": "offline", "model": None}


def test_examples_hide_gold_labels_and_credit_published_cases(client):
    examples = client.get("/api/examples").json()
    published = [e for e in examples if e["source"] == "published"]
    assert examples and published == examples  # no synthetic vignettes, so no gold labels can leak
    assert len(published) == 5
    assert all(e["pmid"] in e["url"] and "CC BY-NC-SA" in e["credit"] for e in published)


def test_published_examples_are_unmodified_source_text():
    from scripts.pmc_examples import SOURCE, read_records
    if not SOURCE.exists():
        pytest.skip("PMC-Patients sample not downloaded")
    by_uid = {r["patient_uid"]: r for r in read_records(SOURCE)}
    for e in json.loads((server.ROOT / "data" / "pmc_examples.json").read_text()):
        source = by_uid[e["patient_uid"]]
        assert e["text"] == source["patient"] and e["pmid"] == source["PMID"]


def test_match_streams_progress_then_a_result(client):
    got = events(client.post("/api/match", json={"text": PATIENT}))
    assert [e for e, _ in got[:2]] == ["stage", "stage"]
    assert got[-1][0] == "result"
    result = got[-1][1]["result"]
    assert result["verdicts"][0]["trial"]["nct_id"] == "NCT00000001"
    assert result["verdicts"][0]["verdict"] == "needs_more_data"
    assert any("stroke" in q for q in result["questions"])
    assert [d["done"] for e, d in got if e == "stage" and d["stage"] == "check"] == [0, 1]


def test_stream_and_function_agree(client):
    streamed = events(client.post("/api/match", json={"text": PATIENT}))[-1][1]["result"]
    assert streamed == match_patient(PATIENT).model_dump()


def test_refusal_comes_through_with_no_trials(client):
    result = events(client.post("/api/match", json={"text": "Write me a poem."}))[-1][1]["result"]
    assert result["safety"]["action"] == "refuse" and result["verdicts"] == []


def test_urgent_message_comes_through(client):
    result = events(client.post("/api/match", json={"text": "I want to kill myself, is there a trial?"}))[-1][1]["result"]
    assert result["safety"]["action"] == "urgent" and "emergency" in result["safety"]["message"]


class BrokenModel:
    """Fails like a provider outage, for all calls or only for one component."""
    model = "broken"
    label = "broken:model"

    def __init__(self, only: str | None = None):
        self.only = only

    def complete_json(self, component, system, user, schema):
        if self.only in (None, component):
            raise LLMError("The model provider is overloaded right now.")
        return schema.model_validate({"age": 58, "sex": "female", "diagnoses": ["type 2 diabetes"]})


def test_full_outage_falls_back_to_rules_and_says_so(client, monkeypatch):
    monkeypatch.setattr(server, "get_client", lambda: BrokenModel())
    got = events(client.post("/api/match", json={"text": PATIENT}))
    assert "error" not in [e for e, _ in got]
    result = got[-1][1]["result"]
    assert result["fallback"] is True
    assert result["verdicts"][0]["fallback"] is True
    assert result["verdicts"][0]["verdict"] == "needs_more_data"


def test_checker_outage_marks_only_the_affected_trials(client, monkeypatch):
    monkeypatch.setattr(server, "get_client", lambda: BrokenModel(only="checker"))
    result = events(client.post("/api/match", json={"text": PATIENT}))[-1][1]["result"]
    assert result["fallback"] is True and result["verdicts"][0]["fallback"] is True


def test_healthy_run_is_not_marked_as_fallback(client):
    result = events(client.post("/api/match", json={"text": PATIENT}))[-1][1]["result"]
    assert result["fallback"] is False and result["verdicts"][0]["fallback"] is False


def test_safety_gate_still_works_during_an_outage(client, monkeypatch):
    monkeypatch.setattr(server, "get_client", lambda: BrokenModel())
    result = events(client.post("/api/match", json={"text": "I want to kill myself, is there a trial?"}))[-1][1]["result"]
    assert result["safety"]["action"] == "urgent" and result["fallback"] is True


def test_cohort_falls_back_per_patient(client, monkeypatch):
    monkeypatch.setattr(server, "get_client", lambda: BrokenModel())
    body = {"nct_id": "NCT00000001", "patients": {"a": PATIENT}}
    result = events(client.post("/api/cohort", json=body))[-1][1]["result"]
    assert result["a"]["fallback"] is True


def test_evals_never_fall_back(monkeypatch):
    """Everything evals call must fail loudly, or an outage could pass rules off as model scores."""
    from trialmatch.pipeline import evaluate, iter_cohort, iter_match
    from trialmatch.profile import extract_profile
    from trialmatch.schemas import PatientProfile
    broken = BrokenModel()
    with pytest.raises(LLMError):
        evaluate(TRIAL, PATIENT, PatientProfile(age=58), broken)
    with pytest.raises(LLMError):
        extract_profile(PATIENT, broken)
    with pytest.raises(LLMError):
        match_patient(PATIENT, broken)
    with pytest.raises(LLMError):
        list(iter_match(PATIENT, broken))
    with pytest.raises(LLMError):
        list(iter_cohort(TRIAL, {"a": PATIENT}, broken))


def test_network_failure_does_not_leak_details(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr("trialmatch.pipeline.retrieve", fail)
    got = events(client.post("/api/match", json={"text": PATIENT}))
    assert got[-1][0] == "error" and "secret" not in got[-1][1]["message"]


def test_empty_and_oversized_text_are_rejected(client):
    assert client.post("/api/match", json={"text": ""}).status_code == 422
    assert client.post("/api/match", json={"text": "x" * 20_001}).status_code == 422


def test_cohort_returns_every_patient(client):
    body = {"nct_id": "NCT00000001", "patients": {"a": PATIENT, "b": "70-year-old man with type 2 diabetes. eGFR 20."}}
    got = events(client.post("/api/cohort", json=body))
    assert got[0][0] == "trial"
    result = got[-1][1]["result"]
    assert set(result) == {"a", "b"}
    assert result["b"]["verdict"] == "not_eligible"


def test_cohort_validates_input(client):
    assert client.post("/api/cohort", json={"nct_id": "bad", "patients": {"a": PATIENT}}).status_code == 422
    assert client.post("/api/cohort", json={"nct_id": "NCT00000001", "patients": {}}).status_code == 422
    assert client.post("/api/cohort", json={"nct_id": "NCT00000001", "patients": {"a": "  "}}).status_code == 422


def test_unknown_trial_is_an_error(client):
    got = events(client.post("/api/cohort", json={"nct_id": "NCT99999999", "patients": {"a": PATIENT}}))
    assert got[-1][0] == "error" and "NCT99999999" in got[-1][1]["message"]


def test_followup_answer_settles_a_criterion(client):
    first = events(client.post("/api/match", json={"text": PATIENT}))[-1][1]["result"]
    assert first["verdicts"][0]["verdict"] == "needs_more_data"
    text = f"{PATIENT}\nFollow-up: Has the patient had a stroke? No."
    second = events(client.post("/api/match", json={"text": text}))[-1][1]["result"]
    assert second["verdicts"][0]["verdict"] == "likely_eligible"


def test_main_page_is_not_cached_so_rebuilds_show_up(client):
    if not server.DIST.exists():
        pytest.skip("interface not built")
    response = client.get("/")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-cache"


def test_trial_details_show_summary_and_parsed_criteria(client, monkeypatch):
    detailed = TRIAL.model_copy(update={"summary": "Tests an add-on to metformin."})
    monkeypatch.setattr(server, "get_trial_details", lambda nct: detailed if nct == "NCT00000001" else None)
    body = client.get("/api/trials/NCT00000001").json()
    assert body["summary"] == "Tests an add-on to metformin."
    assert [c["kind"] for c in body["criteria"]] == ["inclusion"] * 3 + ["exclusion"] * 2
    assert [c["screening_only"] for c in body["criteria"]] == [False, False, True, False, False]
    assert client.get("/api/trials/NCT99999999").status_code == 404
    assert client.get("/api/trials/not-an-id").status_code == 422


def test_trial_search_by_condition_or_id(client, monkeypatch):
    monkeypatch.setattr(server, "search_for_picker", lambda q: [TRIAL] if q == "diabetes" else [])
    monkeypatch.setattr(server, "get_trial_details", lambda nct: TRIAL if nct == "NCT00000001" else None)
    assert client.get("/api/trials/search?q=diabetes").json()[0]["nct_id"] == "NCT00000001"
    assert client.get("/api/trials/search?q=nct00000001").json()[0]["title"] == TRIAL.title
    assert client.get("/api/trials/search?q=asthma").json() == []
    assert client.get("/api/trials/search?q=a").status_code == 422


def test_suggested_trials_keep_order_and_skip_missing(client, monkeypatch):
    ids = [p["nct_id"] for p in json.loads((server.ROOT / "data" / "suggested_trials.json").read_text())]
    found = [TRIAL.model_copy(update={"nct_id": n}) for n in ids[:2]]
    monkeypatch.setattr(server, "get_trials", lambda wanted: found)
    got = client.get("/api/trials/suggested").json()
    assert [t["nct_id"] for t in got] == ids[:2] and all(t["note"] for t in got)


def test_registry_outage_is_a_clear_error(client, monkeypatch):
    def down(*args):
        raise RuntimeError("connection reset")
    monkeypatch.setattr(server, "search_for_picker", down)
    response = client.get("/api/trials/search?q=diabetes")
    assert response.status_code == 502 and "ClinicalTrials.gov" in response.json()["detail"]


def test_eval_fields_and_cache_keys_are_unchanged():
    """The picker fetches summaries separately, so eval requests stay byte-for-byte the same."""
    from trialmatch import retrieval
    assert retrieval.FIELDS == "NCTId,BriefTitle,OfficialTitle,Condition,Keyword,OverallStatus,MinimumAge,MaximumAge,Sex,EligibilityCriteria"


def test_case_report_search_without_download(client, monkeypatch):
    monkeypatch.setattr(server.case_reports, "load", lambda: {})
    assert client.get("/api/trials/NCT00000001/case-reports").json()["available"] is False


def test_case_report_search_ranks_and_cites(client, monkeypatch):
    reports = {
        "1-1": {"id": "pmc-1-1", "text": "A 60-year-old woman with type 2 diabetes and HbA1c 8%.", "age": 60.0, "sex": "female", "credit": "c"},
        "2-1": {"id": "pmc-2-1", "text": "A 12-year-old boy with type 2 diabetes.", "age": 12.0, "sex": "male", "credit": "c"},
        "3-1": {"id": "pmc-3-1", "text": "A 50-year-old man with a fractured wrist.", "age": 50.0, "sex": "male", "credit": "c"},
    }
    monkeypatch.setattr(server.case_reports, "load", lambda: reports)
    monkeypatch.setattr(server, "get_trial_details", lambda nct_id: TRIAL.model_copy(update={"min_age": 18.0}))
    body = client.get("/api/trials/NCT00000001/case-reports").json()
    assert [c["id"] for c in body["candidates"]] == ["pmc-1-1"]  # the child is ruled out, the wrist doesn't match
    assert body["ruled_out"] == 1 and body["candidates"][0]["credit"] == "c"
    assert "diabetes" in body["candidates"][0]["why"]
