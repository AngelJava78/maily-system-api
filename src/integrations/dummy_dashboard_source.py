"""Fictitious data of the platform dashboard for phase 1 (spec 003, data-model.md section 6).

The clinics, doctors, patients and users belong to other MailySoft APIs that do not exist yet. Until
they do, this source answers fixed, coherent data from the code itself: nothing is stored in the
database of the service, and nothing depends on the clock, on chance or on the network, so every
call (and every restart) gives the same values.

The set is stored by name, neither by date nor by id, so the answers are only right if they are
really sorted; the two clinics that share an instant are stored in the opposite order of their ids,
so they are only right if the tie is really broken by id.

It is meant to disappear: when a real source replaces it, `is_dummy` goes away with it and so does the
start-up notice.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from src.integrations.dashboard_source import ClinicCounts, ClinicRecord, ClinicStatusRecord

# Catalog of clinic statuses that the dummy set uses (the real one belongs to the clinics API).
ACTIVE_STATUS = ClinicStatusRecord(1, "Activa")
TRIAL_STATUS = ClinicStatusRecord(2, "En prueba")
SUSPENDED_STATUS = ClinicStatusRecord(3, "Suspendida")

# Stored alphabetically by name. Newest first they are: Santa Aurora, Del Valle, Horizonte, Dental
# Sonríe and San Rafael (the last two share an instant), Arcoíris, Los Pinos, Salud Integral, Alba,
# Nueva Vida, Reforma and Vista Hermosa.
DUMMY_CLINICS: tuple[ClinicRecord, ...] = (
    ClinicRecord(
        UUID("ca8b4382-8b86-4916-b3cb-002680986de3"),
        "Centro Médico Horizonte",
        datetime(2026, 10, 9, 18, 40, tzinfo=UTC),
        ACTIVE_STATUS,
    ),
    ClinicRecord(
        UUID("dd5600ca-3d55-4f38-8c91-c843ec327e9c"),
        "Centro de Salud Integral",
        datetime(2026, 9, 18, 10, 0, tzinfo=UTC),
        ACTIVE_STATUS,
    ),
    ClinicRecord(
        UUID("820e815b-8a28-448e-bb4e-152c2f89a2ad"),
        "Clínica Los Pinos",
        datetime(2026, 9, 26, 14, 10, tzinfo=UTC),
        ACTIVE_STATUS,
    ),
    ClinicRecord(
        UUID("c9e9c89d-96b1-4aef-9373-98771c6557e6"),
        "Clínica Nueva Vida",
        datetime(2026, 8, 21, 13, 15, tzinfo=UTC),
        ACTIVE_STATUS,
    ),
    ClinicRecord(
        UUID("e042d32c-3886-4777-953c-68db1d969e0e"),
        "Clínica San Rafael",
        datetime(2026, 10, 8, 15, 0, tzinfo=UTC),
        ACTIVE_STATUS,
    ),
    ClinicRecord(
        UUID("5457da22-336d-49d8-8876-4d7edb5586ae"),
        "Clínica Santa Aurora",
        datetime(2026, 10, 15, 16, 20, tzinfo=UTC),
        TRIAL_STATUS,
    ),
    ClinicRecord(
        UUID("8c292a31-e02e-4377-b64b-3f95d1933512"),
        "Clínica Vista Hermosa",
        datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
        SUSPENDED_STATUS,
    ),
    ClinicRecord(
        UUID("a3e85cc2-e5c9-4106-a055-5e7dcc32bf8b"),
        "Consultorio Alba",
        datetime(2026, 9, 5, 17, 45, tzinfo=UTC),
        ACTIVE_STATUS,
    ),
    ClinicRecord(
        UUID("7513bda5-dd0f-48a0-9053-383ac7ec2c92"),
        "Consultorio Del Valle",
        datetime(2026, 10, 12, 9, 5, tzinfo=UTC),
        TRIAL_STATUS,
    ),
    ClinicRecord(
        UUID("41902d77-45cb-451e-9e11-65c60e56ecf8"),
        "Dental Sonríe",
        datetime(2026, 10, 8, 15, 0, tzinfo=UTC),
        TRIAL_STATUS,
    ),
    ClinicRecord(
        UUID("ecb1488c-d9cf-4d3c-bb5f-dd8e9365339d"),
        "Pediatría Arcoíris",
        datetime(2026, 10, 2, 11, 30, tzinfo=UTC),
        ACTIVE_STATUS,
    ),
    ClinicRecord(
        UUID("c0b2ebc7-9b5d-45e8-b8e1-f590ed886e9e"),
        "Policlínica Reforma",
        datetime(2026, 7, 30, 8, 30, tzinfo=UTC),
        ACTIVE_STATUS,
    ),
)


class DummyDashboardSource:
    """The fictitious `DashboardSource` of phase 1. Never fails and ignores the token."""

    is_dummy = True

    def __init__(
        self,
        clinics: Sequence[ClinicRecord] = DUMMY_CLINICS,
        doctors: int = 37,
        patients: int = 1284,
        users: int = 52,
    ) -> None:
        self._clinics = tuple(clinics)
        self._doctors = doctors
        self._patients = patients
        self._users = users

    async def clinic_counts(self, token: str) -> ClinicCounts:
        # Derived from the same set, so the counts and the list can never contradict each other.
        return ClinicCounts(
            total=len(self._clinics),
            active=sum(1 for c in self._clinics if c.status.id == ACTIVE_STATUS.id),
            trial=sum(1 for c in self._clinics if c.status.id == TRIAL_STATUS.id),
        )

    async def recent_clinics(self, token: str, limit: int) -> list[ClinicRecord]:
        # The contract of the port: newest first and, for the same instant, `id` ascending. The sort
        # is stable and `reverse=True` keeps the order of equal elements, so the id order of the
        # first pass survives the second one.
        by_id = sorted(self._clinics, key=lambda clinic: clinic.id)
        return sorted(by_id, key=lambda clinic: clinic.created_at, reverse=True)[:limit]

    async def doctors_total(self, token: str) -> int:
        return self._doctors

    async def patients_total(self, token: str) -> int:
        return self._patients

    async def users_total(self, token: str) -> int:
        return self._users
