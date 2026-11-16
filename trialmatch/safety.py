"""Component 6a: decide whether to run at all. Refusal is a designed outcome, not an error."""
import re

from . import lexicon
from .schemas import PatientProfile, SafetyDecision

URGENT = re.compile(
    r"\b(suicid\w*|kill (?:myself|himself|herself)|end my life|overdos\w*|can'?t breathe|cannot breathe|"
    r"chest pain (?:right )?now|having a (?:stroke|heart attack))\b", re.I,
)
ADVICE = re.compile(
    r"\b(should (?:i|he|she|they|we) (?:take|stop|start|get|use)|what dose|which (?:drug|medication|treatment) is best|"
    r"do i have|is it cancer|diagnose me|how much .{0,20} should|can you prescribe)\b", re.I,
)
CLINICAL_CUE = re.compile(
    r"\b(patient|diagnos\w*|years?[\s-]old|y/?o|history of|treated|treatment|on \w+ \d+ ?mg|cancer|carcinoma|"
    r"disease|disorder|syndrome|symptoms?|hba1c|egfr|chemo\w*|medication)\b", re.I,
)


def assess(text: str, profile: PatientProfile) -> SafetyDecision:
    if URGENT.search(text):
        return SafetyDecision(action="urgent", message=(
            "This sounds urgent. Please contact emergency services or a clinician now. "
            "This tool only screens clinical-trial criteria and cannot help in an emergency."
        ))
    # A model can read "this headache" as a diagnosis, so a diagnosis alone doesn't make this a patient description.
    described = profile.age is not None or bool(profile.labs) or bool(profile.medications)
    if ADVICE.search(text) and not described:
        return SafetyDecision(action="refuse", message=(
            "I can't diagnose or give treatment advice. I only compare a patient description with trial "
            "eligibility criteria. Please ask a clinician, or describe the patient's diagnosis, age, and treatments."
        ))
    if profile.diagnoses:
        return SafetyDecision(action="proceed")
    if CLINICAL_CUE.search(text) or profile.age is not None or profile.labs or profile.medications or lexicon.find_concepts(text):
        return SafetyDecision(action="ask_diagnosis", message=(
            "I need the main diagnosis to search for trials. What condition should the trial be for?"
        ))
    return SafetyDecision(action="refuse", message=(
        "I can only help with matching a patient to clinical trials. Please describe the patient: "
        "diagnosis, age, sex, treatments, and any recent lab results."
    ))
