"""The fictitious data of phase 1 (spec 003, data-model.md section 6): fixed, coherent, deterministic."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from src.integrations.dashboard_source import ClinicCounts
from src.integrations.dummy_dashboard_source import DUMMY_CLINICS, DummyDashboardSource
from tests.dashboard_support import make_clinic, newest_first

# data-model.md section 6, newest first: (id, name, created_at, status id)
EXPECTED = [
    ("5457da22-336d-49d8-8876-4d7edb5586ae", "Clínica Santa Aurora", "2026-10-15T16:20:00Z", 2),
    ("7513bda5-dd0f-48a0-9053-383ac7ec2c92", "Consultorio Del Valle", "2026-10-12T09:05:00Z", 2),
    ("ca8b4382-8b86-4916-b3cb-002680986de3", "Centro Médico Horizonte", "2026-10-09T18:40:00Z", 1),
    ("41902d77-45cb-451e-9e11-65c60e56ecf8", "Dental Sonríe", "2026-10-08T15:00:00Z", 2),
    ("e042d32c-3886-4777-953c-68db1d969e0e", "Clínica San Rafael", "2026-10-08T15:00:00Z", 1),
    ("ecb1488c-d9cf-4d3c-bb5f-dd8e9365339d", "Pediatría Arcoíris", "2026-10-02T11:30:00Z", 1),
    ("820e815b-8a28-448e-bb4e-152c2f89a2ad", "Clínica Los Pinos", "2026-09-26T14:10:00Z", 1),
    ("dd5600ca-3d55-4f38-8c91-c843ec327e9c", "Centro de Salud Integral", "2026-09-18T10:00:00Z", 1),
    ("a3e85cc2-e5c9-4106-a055-5e7dcc32bf8b", "Consultorio Alba", "2026-09-05T17:45:00Z", 1),
    ("c9e9c89d-96b1-4aef-9373-98771c6557e6", "Clínica Nueva Vida", "2026-08-21T13:15:00Z", 1),
    ("c0b2ebc7-9b5d-45e8-b8e1-f590ed886e9e", "Policlínica Reforma", "2026-07-30T08:30:00Z", 1),
    ("8c292a31-e02e-4377-b64b-3f95d1933512", "Clínica Vista Hermosa", "2026-06-11T12:00:00Z", 3),
]
TIE_FIRST = "41902d77-45cb-451e-9e11-65c60e56ecf8"  # Dental Sonríe: the smaller id of the tie
TIE_SECOND = "e042d32c-3886-4777-953c-68db1d969e0e"  # Clínica San Rafael


def as_tuples(clinics) -> list[tuple[str, str, datetime, int]]:
    return [(str(c.id), c.name, c.created_at, c.status.id) for c in clinics]


EXPECTED_RECORDS = [
    (id_, name, datetime.fromisoformat(iso.replace("Z", "+00:00")), status)
    for id_, name, iso, status in EXPECTED
]


@pytest.fixture
def source() -> DummyDashboardSource:
    return DummyDashboardSource()


# --- the stored set ---


def test_the_set_has_twelve_clinics_stored_by_name_so_that_sorting_is_always_needed():
    names = [clinic.name for clinic in DUMMY_CLINICS]

    assert len(DUMMY_CLINICS) == 12
    assert names == sorted(names)
    assert list(DUMMY_CLINICS) != newest_first(DUMMY_CLINICS)
    assert [c.id for c in DUMMY_CLINICS] != sorted(c.id for c in DUMMY_CLINICS)


def test_the_tied_pair_is_stored_in_the_opposite_order_of_its_ids():
    stored = [str(c.id) for c in DUMMY_CLINICS]

    assert stored.index(TIE_SECOND) < stored.index(TIE_FIRST)


# --- the answers ---


async def test_the_counts_are_derived_from_the_set(source):
    assert await source.clinic_counts("t") == ClinicCounts(total=12, active=8, trial=3)


async def test_the_other_totals_are_the_documented_constants(source):
    assert (
        await source.doctors_total("t"),
        await source.patients_total("t"),
        await source.users_total("t"),
    ) == (37, 1284, 52)


@pytest.mark.parametrize("limit", range(1, 13))
async def test_it_returns_the_most_recent_clinics_up_to_the_limit(source, limit):
    recent = await source.recent_clinics("t", limit)

    assert as_tuples(recent) == EXPECTED_RECORDS[: min(limit, 12)]


async def test_the_tie_is_decided_by_the_smaller_id_even_if_it_is_stored_later(source):
    ten = [str(c.id) for c in await source.recent_clinics("t", 10)]
    four = [str(c.id) for c in await source.recent_clinics("t", 4)]

    assert ten.index(TIE_FIRST) + 1 == ten.index(TIE_SECOND)
    assert four[-1] == TIE_FIRST  # with limit=4 the tie keeps the clinic with the smaller id


# --- invariants I1 to I8 ---


async def test_the_counts_are_coherent(source):
    counts = await source.clinic_counts("t")
    recent = await source.recent_clinics("t", 10)

    assert counts.active + counts.trial <= counts.total  # I1 (and the total is greater: 12 > 11)
    assert counts.active + counts.trial < counts.total
    assert len(recent) <= counts.total  # I2
    assert sum(1 for c in recent if c.status.id == 1) <= counts.active  # I3
    assert sum(1 for c in recent if c.status.id == 2) <= counts.trial
    assert await source.users_total("t") >= await source.doctors_total("t")  # I4


def test_the_ids_are_valid_distinct_version_four_uuids():  # I5
    ids = [c.id for c in DUMMY_CLINICS]

    assert len(set(ids)) == len(ids)
    assert all(isinstance(i, UUID) and i.version == 4 for i in ids)
    assert all(UUID(str(i)) == i for i in ids)


async def test_the_ten_most_recent_have_both_statuses_and_one_tied_pair(source):  # I6
    ten = await source.recent_clinics("t", 10)
    instants = [c.created_at for c in ten]

    assert {c.status.id for c in ten} == {1, 2}
    assert {c.status.name for c in ten} == {"Activa", "En prueba"}
    assert len(ten) >= 10
    assert len(instants) - len(set(instants)) == 1  # exactly one repeated instant (two clinics)


def test_every_date_has_a_time_zone_and_is_utc():  # I7
    assert all(c.created_at.tzinfo is not None for c in DUMMY_CLINICS)
    assert all(c.created_at.utcoffset().total_seconds() == 0 for c in DUMMY_CLINICS)
    assert all(c.created_at.tzinfo == UTC for c in DUMMY_CLINICS)


async def test_two_instances_and_two_calls_give_the_same_answers():  # I8
    first, second = DummyDashboardSource(), DummyDashboardSource()

    assert await first.recent_clinics("t", 10) == await second.recent_clinics("t", 10)
    assert await first.recent_clinics("t", 10) == await first.recent_clinics("t", 10)
    assert await first.clinic_counts("t") == await second.clinic_counts("t")


# --- behavior ---


async def test_it_is_the_dummy_source_and_ignores_the_token(source):
    assert source.is_dummy is True
    assert await source.recent_clinics("", 5) == await source.recent_clinics("another", 5)
    assert await source.users_total("") == await source.users_total("another")


async def test_an_empty_set_answers_zeros_and_an_empty_list():
    empty = DummyDashboardSource(clinics=(), doctors=0, patients=0, users=0)

    assert await empty.clinic_counts("t") == ClinicCounts(0, 0, 0)
    assert await empty.recent_clinics("t", 10) == []
    assert (await empty.doctors_total("t"), await empty.patients_total("t")) == (0, 0)
    assert await empty.users_total("t") == 0


async def test_another_set_gets_its_own_counts_by_status():
    clinics = [
        make_clinic(1, status_id=1),
        make_clinic(2, status_id=2),
        make_clinic(3, status_id=2),
        make_clinic(4, status_id=3),
    ]

    other = DummyDashboardSource(clinics=clinics, doctors=2, patients=3, users=4)

    assert await other.clinic_counts("t") == ClinicCounts(total=4, active=1, trial=2)
    assert [c.id for c in await other.recent_clinics("t", 10)] == [c.id for c in newest_first(clinics)]
    assert (await other.doctors_total("t"), await other.patients_total("t")) == (2, 3)
