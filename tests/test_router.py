"""Question routing: policy first, structured where records answer directly, generation otherwise."""
import pytest

from backend.assistant.router import route

CASES = [
    ("What brought this patient to the hospital recently?", "rag"),
    ("What were the documented concerns during the last encounter?", "rag"),
    ("How have the recorded vital signs changed?", "structured"),
    ("What medications are recorded for this patient?", "structured"),
    ("What follow-up instructions are documented?", "structured"),
    ("What questions did the patient send through the portal?", "structured"),
    ("What imaging records are available, and what does the associated report actually say?", "structured"),
    ("What information cannot be established from the available records?", "structured"),
    ("How has LDL cholesterol changed over time?", "structured"),
    ("What did the endocrinologist recommend?", "rag"),
    ("Why was aspirin stopped?", "rag"),
    ("Should we increase the glargine dose?", "policy_advice"),
    ("Can you recommend a treatment plan?", "policy_advice"),
    ("What is the prognosis?", "policy_advice"),
    ("What does the chest x-ray show?", "policy_imaging"),
    ("Is there any fracture on the radiograph?", "policy_imaging"),
    ("Interpret the DICOM image", "policy_imaging"),
    ("What about CN-P004?", "policy_scope"),
    ("How does this compare with other patients?", "policy_scope"),
]


@pytest.mark.parametrize("q,expected", CASES)
def test_route(q, expected):
    assert route(q, "CN-P001")[0] == expected


def test_own_patient_id_is_not_a_scope_violation():
    assert route("Summarize CN-P001's latest labs", "CN-P001")[0] != "policy_scope"
