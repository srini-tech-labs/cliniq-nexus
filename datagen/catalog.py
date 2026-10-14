"""Measurement catalog: LOINC codes, UCUM units, display units and reference ranges.

Reference ranges are typical adult ranges used only to label synthetic demonstration
values. They are not clinical guidance.
"""

VITALS = {
    "hr":   {"code": "8867-4",  "name": "Heart rate",               "unit": "/min",   "display_unit": "bpm",     "low": 60,   "high": 100},
    "sbp":  {"code": "8480-6",  "name": "Systolic blood pressure",  "unit": "mm[Hg]", "display_unit": "mmHg",    "low": 90,   "high": 129},
    "dbp":  {"code": "8462-4",  "name": "Diastolic blood pressure", "unit": "mm[Hg]", "display_unit": "mmHg",    "low": 60,   "high": 79},
    "rr":   {"code": "9279-1",  "name": "Respiratory rate",         "unit": "/min",   "display_unit": "breaths/min", "low": 12, "high": 20},
    "spo2": {"code": "59408-5", "name": "Oxygen saturation",        "unit": "%",      "display_unit": "%",       "low": 95,   "high": 100},
    "temp": {"code": "8310-5",  "name": "Body temperature",         "unit": "Cel",    "display_unit": "°C",      "low": 36.1, "high": 37.9},
    "wt":   {"code": "29463-7", "name": "Body weight",              "unit": "kg",     "display_unit": "kg",      "low": None, "high": None},
    "pain": {"code": "72514-3", "name": "Pain severity (0-10)",     "unit": "{score}", "display_unit": "/10",    "low": None, "high": None},
}

LABS = {
    "wbc":  {"code": "6690-2",  "name": "White blood cell count",   "unit": "10*3/uL", "display_unit": "×10³/µL", "low": 4.0, "high": 11.0},
    "crp":  {"code": "1988-5",  "name": "C-reactive protein",       "unit": "mg/L",    "display_unit": "mg/L",    "low": None, "high": 10.0},
    "glu":  {"code": "2345-7",  "name": "Glucose",                  "unit": "mg/dL",   "display_unit": "mg/dL",   "low": 70,  "high": 99},
    "a1c":  {"code": "4548-4",  "name": "Hemoglobin A1c",           "unit": "%",       "display_unit": "%",       "low": None, "high": 5.6},
    "cr":   {"code": "2160-0",  "name": "Creatinine",               "unit": "mg/dL",   "display_unit": "mg/dL",   "low": 0.6, "high": 1.3},
    "egfr": {"code": "98979-8", "name": "eGFR (CKD-EPI 2021)",      "unit": "mL/min/{1.73_m2}", "display_unit": "mL/min/1.73m²", "low": 60, "high": None},
    "k":    {"code": "2823-3",  "name": "Potassium",                "unit": "mmol/L",  "display_unit": "mmol/L",  "low": 3.5, "high": 5.1},
    "na":   {"code": "2951-2",  "name": "Sodium",                   "unit": "mmol/L",  "display_unit": "mmol/L",  "low": 135, "high": 145},
    "bnp":  {"code": "30934-4", "name": "B-type natriuretic peptide", "unit": "pg/mL", "display_unit": "pg/mL",   "low": None, "high": 100},
    "hgb":  {"code": "718-7",   "name": "Hemoglobin",               "unit": "g/dL",    "display_unit": "g/dL",    "low": None, "high": None},  # sex-specific, set below
    "ferritin": {"code": "2276-4", "name": "Ferritin",              "unit": "ng/mL",   "display_unit": "ng/mL",   "low": 15,  "high": 150},
    "mcv":  {"code": "787-2",   "name": "Mean corpuscular volume",  "unit": "fL",      "display_unit": "fL",      "low": 80,  "high": 100},
    "ldl":  {"code": "13457-7", "name": "LDL cholesterol (calculated)", "unit": "mg/dL", "display_unit": "mg/dL", "low": None, "high": 99},
    "tc":   {"code": "2093-3",  "name": "Total cholesterol",        "unit": "mg/dL",   "display_unit": "mg/dL",   "low": None, "high": 199},
    "hdl":  {"code": "2085-9",  "name": "HDL cholesterol",          "unit": "mg/dL",   "display_unit": "mg/dL",   "low": 40,  "high": None},
    "tg":   {"code": "2571-8",  "name": "Triglycerides",            "unit": "mg/dL",   "display_unit": "mg/dL",   "low": None, "high": 149},
    "alt":  {"code": "1742-6",  "name": "Alanine aminotransferase", "unit": "U/L",     "display_unit": "U/L",     "low": 7,   "high": 56},
    "uacr": {"code": "9318-7",  "name": "Urine albumin/creatinine ratio", "unit": "mg/g", "display_unit": "mg/g", "low": None, "high": 29},
    "tsh":  {"code": "3016-3",  "name": "Thyrotropin (TSH)",        "unit": "m[IU]/L", "display_unit": "mIU/L",   "low": 0.4, "high": 4.0},
    "fev1": {"code": "20150-9", "name": "FEV1",                     "unit": "L",       "display_unit": "L",       "low": None, "high": None},
}

HGB_RANGE = {"female": (12.0, 15.5), "male": (13.5, 17.5)}

ENCOUNTER_CLASS = {
    "AMB": "Ambulatory",
    "EMER": "Emergency",
    "IMP": "Inpatient",
    "VR": "Virtual",
}


def ref_range(key: str, sex: str):
    spec = VITALS.get(key) or LABS[key]
    if key == "hgb":
        return HGB_RANGE[sex]
    return spec["low"], spec["high"]


def interpret(key: str, value: float, sex: str) -> str:
    """Return the recorded flag (H, L or N) for a value, as a lab system would."""
    low, high = ref_range(key, sex)
    if low is not None and value < low:
        return "L"
    if high is not None and value > high:
        return "H"
    return "N"
