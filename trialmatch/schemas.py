from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["met", "not_met", "insufficient"]
Verdict = Literal["likely_eligible", "needs_more_data", "not_eligible", "insufficient_data"]


class Lab(BaseModel):
    name: str
    value: float
    unit: str = ""


class PatientProfile(BaseModel):
    age: int | None = None
    sex: Literal["female", "male"] | None = None
    diagnoses: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    labs: list[Lab] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)
    absent: list[str] = Field(default_factory=list)  # explicitly denied facts


class Trial(BaseModel):
    nct_id: str
    title: str = ""
    conditions: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    status: str = ""
    min_age: float | None = None
    max_age: float | None = None
    sex: str = "ALL"
    eligibility_text: str = ""
    summary: str = ""  # only fetched for the trial picker, so eval cache keys stay the same

    @property
    def url(self) -> str:
        return f"https://clinicaltrials.gov/study/{self.nct_id}"


class Criterion(BaseModel):
    id: str
    kind: Literal["inclusion", "exclusion"]
    text: str
    screening_only: bool = False  # consent, investigator judgement: not decidable from a record
    # Structure that parsing keeps and aggregation uses. None of it is shown to the model.
    group: str = ""           # alternatives: the patient needs group_needed of them, not all
    group_needed: int = 1
    conditional: bool = False  # applies to some patients only ("For SPMS, ..."), so it can't block alone
    cohort: str = ""          # a section for one participant group; OTHER_PERSON sections are about a donor or relative


OTHER_PERSON = "other person"


class CriterionCheck(BaseModel):
    criterion_id: str
    status: Status
    evidence: str = ""
    reasoning: str = ""
    source: str = "rule"


class TrialVerdict(BaseModel):
    trial: Trial
    verdict: Verdict
    score: float
    criteria: list[Criterion]
    checks: list[CriterionCheck]
    blockers: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    cohort: str = ""  # for trials with several participant groups: the one this verdict is for
    fallback: bool = False  # the model failed, so rules decided this trial


class Entity(BaseModel):
    type: str
    start: int
    end: int
    text: str


class SafetyDecision(BaseModel):
    action: Literal["proceed", "ask_diagnosis", "refuse", "urgent"]
    message: str = ""


class MatchResult(BaseModel):
    safety: SafetyDecision
    profile: PatientProfile | None = None
    query: str = ""
    candidates: int = 0
    verdicts: list[TrialVerdict] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    note: str = ""
    fallback: bool = False  # the model failed at some step, so rules replaced it there
