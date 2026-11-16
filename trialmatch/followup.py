"""Component 6b: turn missing data into the few questions that would settle the most criteria."""
from collections import Counter

from . import lexicon
from .schemas import TrialVerdict

MAX_CRITERION_CHARS = 180


def topic_and_question(criterion_text: str, patient_text: str = "") -> tuple[str, str]:
    """A targeted question if the topic is new. If the patient text covers it, quote the criterion instead."""
    labs = [name for name, _ in lexicon.find_lab(criterion_text) if not lexicon.find_lab_in(name, patient_text)]
    if labs:
        name = labs[0]
        return f"lab:{name}", f"What is the patient's most recent {name} value?"
    known = set(lexicon.find_concepts(patient_text))
    concepts = [c for c in lexicon.find_concepts(criterion_text) if c not in known]
    if concepts:
        name = concepts[0]
        if name in ("pregnancy", "breastfeeding"):
            if "pregnancy" in known:
                return "concept:breastfeeding", "Is the patient breastfeeding?"
            return "concept:pregnancy", "Is the patient pregnant or breastfeeding?"
        if name in lexicon.DRUG_CONCEPTS:
            return f"concept:{name}", f"Is the patient taking, or has the patient taken, {name}? If yes, when?"
        return f"concept:{name}", f"Does the patient have, or has the patient had, {name}? If yes, when?"
    short = criterion_text if len(criterion_text) <= MAX_CRITERION_CHARS else criterion_text[:MAX_CRITERION_CHARS].rsplit(" ", 1)[0] + "…"
    return f"text:{criterion_text.lower()}", f"Is this true of the patient? “{short}”"


def generate_questions(verdicts: list[TrialVerdict], top: int = 3, patient_text: str = "") -> list[str]:
    """Most useful first: asked about by the most still-open trials. Ineligible trials are ignored."""
    counts: Counter = Counter()
    questions: dict[str, str] = {}
    for v in verdicts:
        if v.verdict == "not_eligible":
            continue
        by_id = {c.id: c for c in v.criteria}
        seen = set()
        for cid in v.missing:
            topic, question = topic_and_question(by_id[cid].text, patient_text)
            if topic not in seen:
                seen.add(topic)
                counts[topic] += 1
                questions.setdefault(topic, question)
    return [questions[t] for t, _ in counts.most_common(top)]
