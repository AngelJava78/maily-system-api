"""DTOs of the dashboard response: seven mandatory, nullable fields, UTC dates, no personal data."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.dtos.dashboard import ClinicStatusRead, DashboardRead, RecentClinicRead
from src.integrations.dashboard_source import ClinicRecord, ClinicStatusRecord

FIELDS = (
    "total_clinics",
    "active_clinics",
    "trial_clinics",
    "total_doctors",
    "total_patients",
    "total_users",
    "recent_clinics",
)
CLINIC_ID = UUID("5457da22-336d-49d8-8876-4d7edb5586ae")


def clinic(**changes) -> ClinicRecord:
    values = {
        "id": CLINIC_ID,
        "name": "Clínica Santa Aurora",
        "created_at": datetime(2026, 10, 15, 16, 20, tzinfo=UTC),
        "status": ClinicStatusRecord(2, "En prueba"),
    }
    return ClinicRecord(**{**values, **changes})


def all_null() -> dict:
    return {field: None for field in FIELDS}


def test_a_dashboard_with_every_value_missing_is_valid_and_keeps_every_key():
    dumped = DashboardRead(**all_null()).model_dump(mode="json")

    assert dumped == all_null()


@pytest.mark.parametrize("field", FIELDS)
def test_every_field_is_mandatory(field):
    values = all_null()
    del values[field]

    with pytest.raises(ValidationError):
        DashboardRead(**values)


def test_the_published_schema_requires_the_seven_fields_and_allows_null_in_each():
    schema = DashboardRead.model_json_schema()

    assert set(schema["required"]) == set(FIELDS)
    for field in FIELDS:
        options = schema["properties"][field]["anyOf"]
        assert {"type": "null"} in options, field


def test_a_negative_count_is_not_valid():
    with pytest.raises(ValidationError):
        DashboardRead(**{**all_null(), "total_clinics": -1})


def test_zero_is_a_valid_count_and_is_not_confused_with_null():
    dumped = DashboardRead(**{**all_null(), "total_doctors": 0, "recent_clinics": []}).model_dump(
        mode="json"
    )

    assert dumped["total_doctors"] == 0
    assert dumped["recent_clinics"] == []


def test_the_list_of_recent_clinics_has_at_most_ten_elements():
    recent = [RecentClinicRead.model_validate(clinic()) for _ in range(11)]

    with pytest.raises(ValidationError):
        DashboardRead(**{**all_null(), "recent_clinics": recent})

    DashboardRead(**{**all_null(), "recent_clinics": recent[:10]})


def test_a_recent_clinic_is_read_from_the_record_and_its_nested_status():
    read = RecentClinicRead.model_validate(clinic())

    assert read.model_dump(mode="json") == {
        "id": "5457da22-336d-49d8-8876-4d7edb5586ae",
        "name": "Clínica Santa Aurora",
        "created_at": "2026-10-15T16:20:00Z",
        "status": {"id": 2, "name": "En prueba"},
    }


def test_the_date_is_published_in_utc_whatever_zone_it_came_in():
    local = datetime(2026, 10, 15, 10, 20, tzinfo=timezone(timedelta(hours=-6)))

    read = RecentClinicRead.model_validate(clinic(created_at=local))

    assert read.model_dump(mode="json")["created_at"] == "2026-10-15T16:20:00Z"


def test_a_date_without_a_time_zone_is_not_valid():
    with pytest.raises(ValidationError):
        RecentClinicRead.model_validate(clinic(created_at=datetime(2026, 10, 15, 16, 20)))


def test_the_id_is_published_as_a_lowercase_uuid():
    upper = UUID("5457DA22-336D-49D8-8876-4D7EDB5586AE")

    read = RecentClinicRead.model_validate(clinic(id=upper))

    assert read.model_dump(mode="json")["id"] == "5457da22-336d-49d8-8876-4d7edb5586ae"


def test_the_outputs_have_exactly_the_fields_of_the_contract_and_nothing_personal():
    assert set(DashboardRead.model_fields) == set(FIELDS)
    assert set(RecentClinicRead.model_fields) == {"id", "name", "created_at", "status"}
    assert set(ClinicStatusRead.model_fields) == {"id", "name"}
