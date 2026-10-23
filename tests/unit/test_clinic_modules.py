"""Catálogo de claves y dependencias de los módulos de clínica (research R2, R3)."""

import pytest

from src.clinic_modules import CLINIC_MODULE_KEYS, MODULE_DEPENDENCIES, PATIENTS_KEY, missing_prerequisite


def test_patients_key():
    assert PATIENTS_KEY == "patients"


def test_the_module_dependencies_are_exactly_the_four_pairs_of_the_mockup():
    assert MODULE_DEPENDENCIES == {
        "reminders": "scheduling",
        "clinical_record_templates": "clinical_records",
        "prescriptions": "clinical_records",
        "billing": "finance",
    }


def test_the_clinic_module_keys_are_exactly_the_nine_proposed():
    assert CLINIC_MODULE_KEYS == frozenset(
        {
            "patients",
            "scheduling",
            "reminders",
            "clinical_records",
            "clinical_record_templates",
            "prescriptions",
            "finance",
            "reports",
            "billing",
        }
    )


@pytest.mark.parametrize(
    ("dependent", "prerequisite"),
    [
        ("reminders", "scheduling"),
        ("clinical_record_templates", "clinical_records"),
        ("prescriptions", "clinical_records"),
        ("billing", "finance"),
    ],
)
def test_missing_prerequisite_is_reported_when_the_dependent_is_alone(dependent, prerequisite):
    assert missing_prerequisite(frozenset({dependent})) == (dependent, prerequisite)


@pytest.mark.parametrize(
    ("dependent", "prerequisite"),
    [
        ("reminders", "scheduling"),
        ("clinical_record_templates", "clinical_records"),
        ("prescriptions", "clinical_records"),
        ("billing", "finance"),
    ],
)
def test_no_missing_prerequisite_when_both_are_present(dependent, prerequisite):
    assert missing_prerequisite(frozenset({dependent, prerequisite})) is None


def test_no_missing_prerequisite_with_an_empty_set():
    assert missing_prerequisite(frozenset()) is None


def test_no_missing_prerequisite_with_only_patients():
    assert missing_prerequisite(frozenset({PATIENTS_KEY})) is None


def test_no_missing_prerequisite_with_modules_that_have_none():
    assert missing_prerequisite(frozenset({"scheduling", "clinical_records", "finance", "reports"})) is None


def test_the_first_missing_prerequisite_found_is_reported():
    # Two dependants missing their prerequisite at once: must return a valid pair, never raise.
    result = missing_prerequisite(frozenset({"reminders", "billing"}))
    assert result in {("reminders", "scheduling"), ("billing", "finance")}
