"""Curated terms for the offline baseline. Small on purpose: the baseline should abstain when unsure."""
import re

LABS = {
    "hba1c": ["hba1c", "a1c", "hemoglobin a1c", "haemoglobin a1c", "glycated hemoglobin", "glycosylated hemoglobin"],
    "egfr": ["egfr", "estimated glomerular filtration rate", "glomerular filtration rate", "gfr"],
    "bmi": ["bmi", "body mass index"],
    "creatinine": ["serum creatinine", "creatinine"],
    "ldl": ["ldl-c", "ldl cholesterol", "ldl"],
    "hdl": ["hdl-c", "hdl cholesterol", "hdl"],
    "total cholesterol": ["total cholesterol"],
    "triglycerides": ["triglycerides", "triglyceride"],
    "hemoglobin": ["hemoglobin", "haemoglobin", "hgb"],
    "platelets": ["platelet count", "platelets"],
    "anc": ["absolute neutrophil count", "anc"],
    "alt": ["alanine aminotransferase", "alt"],
    "ast": ["aspartate aminotransferase", "ast"],
    "bilirubin": ["total bilirubin", "bilirubin"],
    "ecog": ["ecog performance status", "ecog ps", "ecog"],
    "fev1": ["fev1"],
    "lvef": ["left ventricular ejection fraction", "ejection fraction", "lvef"],
    "mmse": ["mini-mental state examination", "mmse"],
    "moca": ["montreal cognitive assessment", "moca"],
    "phq-9": ["phq-9", "phq9"],
    "edss": ["expanded disability status scale", "edss"],
    "das28": ["das28", "das-28"],
    "tsh": ["tsh"],
    "psa": ["psa", "prostate-specific antigen"],
    "albumin": ["serum albumin", "albumin"],
    "potassium": ["serum potassium", "potassium"],
    "inr": ["inr"],
    "systolic bp": ["systolic blood pressure", "systolic bp", "sbp"],
    "diastolic bp": ["diastolic blood pressure", "diastolic bp", "dbp"],
}

CONCEPTS = {
    "type 2 diabetes": ["type 2 diabetes mellitus", "type 2 diabetes", "type ii diabetes", "t2dm", "t2d"],
    "type 1 diabetes": ["type 1 diabetes mellitus", "type 1 diabetes", "type i diabetes", "t1dm"],
    "hypertension": ["hypertension", "high blood pressure"],
    "chronic kidney disease": ["chronic kidney disease", "ckd"],
    "dialysis": ["dialysis", "hemodialysis", "haemodialysis"],
    "heart failure": ["heart failure", "chf", "hfref", "hfpef"],
    "myocardial infarction": ["myocardial infarction", "heart attack"],
    "stroke": ["stroke", "cerebrovascular accident"],
    "atrial fibrillation": ["atrial fibrillation", "afib"],
    "coronary artery disease": ["coronary artery disease", "cad"],
    "asthma": ["asthma"],
    "copd": ["chronic obstructive pulmonary disease", "copd"],
    "breast cancer": ["breast cancer", "breast carcinoma"],
    "lung cancer": ["non-small cell lung cancer", "non-small-cell lung cancer", "nsclc", "lung cancer", "lung adenocarcinoma"],
    "prostate cancer": ["prostate cancer", "prostate adenocarcinoma"],
    "colorectal cancer": ["colorectal cancer", "colon cancer", "rectal cancer"],
    "glioblastoma": ["glioblastoma", "gbm"],
    "melanoma": ["melanoma"],
    "brain metastases": ["brain metastases", "brain metastasis", "cns metastases"],
    "rheumatoid arthritis": ["rheumatoid arthritis"],
    "multiple sclerosis": ["multiple sclerosis"],
    "alzheimer's disease": ["alzheimer's disease", "alzheimer disease", "alzheimers disease", "alzheimer's"],
    "parkinson's disease": ["parkinson's disease", "parkinson disease"],
    "major depressive disorder": ["major depressive disorder", "major depression", "depression"],
    "bipolar disorder": ["bipolar disorder"],
    "schizophrenia": ["schizophrenia"],
    "migraine": ["migraine"],
    "epilepsy": ["epilepsy", "seizure disorder"],
    "crohn's disease": ["crohn's disease", "crohn disease"],
    "ulcerative colitis": ["ulcerative colitis"],
    "hiv": ["hiv", "human immunodeficiency virus"],
    "hepatitis b": ["hepatitis b", "hbv"],
    "hepatitis c": ["hepatitis c", "hcv"],
    "cirrhosis": ["cirrhosis"],
    "pregnancy": ["pregnant", "pregnancy"],
    "breastfeeding": ["breastfeeding", "breast-feeding", "lactating", "nursing"],
    "smoking": ["current smoker", "active smoker", "smoker", "smoking", "smoked"],
    "obesity": ["obesity", "obese"],
    "psoriasis": ["psoriasis"],
    "osteoporosis": ["osteoporosis"],
    "sleep apnea": ["obstructive sleep apnea", "sleep apnea"],
    "metformin": ["metformin"],
    "insulin": ["insulin"],
    "sglt2 inhibitor": ["sglt2 inhibitor", "empagliflozin", "dapagliflozin", "canagliflozin"],
    "glp-1 agonist": ["glp-1 receptor agonist", "glp-1 agonist", "semaglutide", "liraglutide", "dulaglutide"],
    "statin": ["statin", "atorvastatin", "rosuvastatin", "simvastatin"],
    "anticoagulant": ["anticoagulant", "anticoagulation", "warfarin", "apixaban", "rivaroxaban"],
    "methotrexate": ["methotrexate"],
    "biologic": ["biologic", "adalimumab", "etanercept", "infliximab"],
    "chemotherapy": ["chemotherapy"],
    "radiation": ["radiation therapy", "radiotherapy", "radiation"],
    "immunotherapy": ["immunotherapy", "pembrolizumab", "nivolumab"],
    "corticosteroid": ["corticosteroid", "prednisone", "systemic steroids"],
    "ssri": ["ssri", "sertraline", "fluoxetine", "escitalopram"],
    "donepezil": ["donepezil"],
    "levodopa": ["levodopa"],
    "lisinopril": ["lisinopril"],
    "amlodipine": ["amlodipine"],
    "inhaled corticosteroid": ["inhaled corticosteroid", "fluticasone", "budesonide"],
}

DRUG_CONCEPTS = {
    "metformin", "insulin", "sglt2 inhibitor", "glp-1 agonist", "statin", "anticoagulant", "methotrexate",
    "biologic", "chemotherapy", "immunotherapy", "corticosteroid", "ssri", "donepezil", "levodopa",
    "lisinopril", "amlodipine", "inhaled corticosteroid",
}
NON_DIAGNOSIS = DRUG_CONCEPTS | {"pregnancy", "breastfeeding", "smoking", "radiation", "dialysis"}


def term_regex(term: str) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", re.I)


LAB_PATTERNS = {name: [term_regex(a) for a in aliases] for name, aliases in LABS.items()}
CONCEPT_PATTERNS = {name: [term_regex(a) for a in aliases] for name, aliases in CONCEPTS.items()}


def find_concepts(text: str) -> list[str]:
    return [name for name, patterns in CONCEPT_PATTERNS.items() if any(p.search(text) for p in patterns)]


def find_lab_in(name: str, text: str) -> bool:
    return any(p.search(text) for p in LAB_PATTERNS[name])


def find_lab(text: str) -> list[tuple[str, re.Match]]:
    """Return (lab, match) pairs, longest alias first per lab, ordered by position."""
    found = []
    for name, patterns in LAB_PATTERNS.items():
        matches = [m for p in patterns for m in p.finditer(text)]
        if matches:
            found.append((name, min(matches, key=lambda m: (m.start(), -len(m.group())))))
    # "hemoglobin a1c" must not also count as "hemoglobin"
    spans = sorted(found, key=lambda x: -(x[1].end() - x[1].start()))
    kept: list[tuple[str, re.Match]] = []
    for name, m in spans:
        if not any(k.start() <= m.start() and m.end() <= k.end() for _, k in kept):
            kept.append((name, m))
    return sorted(kept, key=lambda x: x[1].start())
