"""The one clinic-module key this service still knows about on its own (spec 009)."""

from src.clinic_modules import PATIENTS_KEY


def test_patients_key():
    assert PATIENTS_KEY == "patients"
