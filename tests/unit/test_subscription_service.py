"""Business rules of the subscriptions, with the Repository and the clinics API replaced by doubles."""

import asyncio
from decimal import Decimal

import pytest

from src.dtos.subscription import (
    SubscriptionCreate,
    SubscriptionStatusChange,
    SubscriptionUpdate,
)
from src.exceptions import (
    ClinicsCheckUnavailableError,
    SubscriptionHasClinicsError,
    SubscriptionNameAlreadyExistsError,
    SubscriptionNotFoundError,
    SubscriptionStatusUnchangedError,
)
from src.integrations.errors import ClinicsApiUnavailable
from src.repositories.errors import UniqueViolationError
from src.services.subscription_service import SubscriptionService
from tests.unit.fakes import FakeClinicsApi, FakeSubscriptionRepository

TOKEN = "the-token"


def service(repository=None, clinics=None) -> SubscriptionService:
    return SubscriptionService(repository or FakeSubscriptionRepository(), clinics or FakeClinicsApi())


# --- US1: the catalog ---


async def test_the_catalog_has_one_view_per_current_subscription_with_its_count():
    repository = FakeSubscriptionRepository()
    repository.add(name="Básico")
    repository.add(name="Pro", status_id=2)
    repository.add(name="Eliminada", status_id=4)
    clinics = FakeClinicsApi({1: 2})

    views = await service(repository, clinics).list(TOKEN)

    assert [(v.subscription.name, v.clinics_count) for v in views] == [("Básico", 2), ("Pro", 0)]


async def test_a_subscription_missing_from_the_clinics_answer_has_a_true_zero():
    repository = FakeSubscriptionRepository()
    repository.add(name="Solo")

    views = await service(repository, FakeClinicsApi({})).list(TOKEN)

    assert views[0].clinics_count == 0


async def test_when_the_clinics_api_fails_every_count_is_unavailable_never_zero():
    repository = FakeSubscriptionRepository()
    repository.add(name="A")
    repository.add(name="B")

    views = await service(repository, FakeClinicsApi({1: 5}, fail=True)).list(TOKEN)

    assert [v.subscription.name for v in views] == ["A", "B"]
    assert [v.clinics_count for v in views] == [None, None]


async def test_the_clinics_api_is_asked_once_without_filter_and_with_the_token_received():
    repository = FakeSubscriptionRepository()
    repository.add()
    clinics = FakeClinicsApi()

    await service(repository, clinics).list(TOKEN)

    assert clinics.calls == [(TOKEN, None)]


async def test_an_empty_catalog_is_an_empty_list():
    assert await service().list(TOKEN) == []


async def test_the_catalog_keeps_the_order_of_creation():
    repository = FakeSubscriptionRepository()
    for name in ("Primera", "Segunda", "Tercera"):
        repository.add(name=name)

    views = await service(repository).list(TOKEN)

    assert [v.subscription.name for v in views] == ["Primera", "Segunda", "Tercera"]


async def test_the_database_and_the_clinics_api_are_asked_at_the_same_time():
    """Each one waits for the other to start: a sequential implementation would never finish."""
    repository_started = asyncio.Event()
    clinics_started = asyncio.Event()

    class GatedRepository(FakeSubscriptionRepository):
        async def list_current(self):
            repository_started.set()
            await clinics_started.wait()
            return await super().list_current()

    class GatedClinics(FakeClinicsApi):
        async def get_counts(self, token, subscription_ids=None):
            clinics_started.set()
            await repository_started.wait()
            return await super().get_counts(token, subscription_ids)

    repository = GatedRepository()
    repository.add()

    views = await asyncio.wait_for(service(repository, GatedClinics({1: 3})).list(TOKEN), 1)

    assert views[0].clinics_count == 3


async def test_a_failure_of_the_database_is_not_hidden_by_the_clinics_degradation():
    class BrokenRepository(FakeSubscriptionRepository):
        async def list_current(self):
            raise RuntimeError("database down")

    with pytest.raises(RuntimeError):
        await service(BrokenRepository(), FakeClinicsApi()).list(TOKEN)


async def test_the_clinics_failure_is_logged_without_the_token(caplog):
    repository = FakeSubscriptionRepository()
    repository.add()

    await service(repository, FakeClinicsApi(fail=True)).list(TOKEN)

    assert TOKEN not in caplog.text


def test_the_clinics_double_really_raises_the_integration_error():
    clinics = FakeClinicsApi(fail=True)

    with pytest.raises(ClinicsApiUnavailable):
        asyncio.run(clinics.get_counts(TOKEN))


# --- US3: create ---


def create_data(**values) -> SubscriptionCreate:
    return SubscriptionCreate.model_validate({"name": "Pro", "monthly_price": "4500", **values})


async def test_create_passes_the_validated_values_to_the_repository():
    repository = FakeSubscriptionRepository()

    view = await service(repository).create(
        create_data(description="Para clínicas", features=["Uno", "Dos"])
    )

    stored = repository.items[view.subscription.id]
    assert (stored.name, stored.description, stored.features) == ("Pro", "Para clínicas", ["Uno", "Dos"])
    assert stored.monthly_price == Decimal("4500.00")
    assert stored.status_id == 1


async def test_a_new_subscription_has_a_true_zero_without_asking_the_clinics_api():
    clinics = FakeClinicsApi({1: 99})

    view = await service(clinics=clinics).create(create_data())

    assert view.clinics_count == 0
    assert clinics.calls == []


async def test_a_repeated_name_becomes_the_name_conflict_with_the_name_in_the_message():
    repository = FakeSubscriptionRepository()
    repository.add(name="Pro")

    with pytest.raises(SubscriptionNameAlreadyExistsError) as error:
        await service(repository).create(create_data(name="pro"))

    assert "«pro»" in error.value.message


async def test_the_name_of_a_deleted_subscription_can_be_used_again():
    repository = FakeSubscriptionRepository()
    repository.add(name="Solo", status_id=4)

    view = await service(repository).create(create_data(name="Solo"))

    assert view.subscription.name == "Solo"


async def test_another_unique_violation_is_not_mistaken_for_the_name_conflict():
    class Broken(FakeSubscriptionRepository):
        async def create(self, *args, **kwargs):
            raise UniqueViolationError("some_other_constraint")

    with pytest.raises(UniqueViolationError):
        await service(Broken()).create(create_data())


async def test_the_name_is_not_checked_before_inserting_to_avoid_a_race():
    repository = FakeSubscriptionRepository()

    await service(repository).create(create_data())

    assert dict(repository.calls) == {"create": 1}


# --- US4: get ---


async def test_get_returns_the_view_with_the_count_asked_for_that_subscription_only():
    repository = FakeSubscriptionRepository()
    repository.add(name="Una")
    repository.add(name="Otra")
    clinics = FakeClinicsApi({1: 5, 2: 7})

    view = await service(repository, clinics).get(2, TOKEN)

    assert (view.subscription.name, view.clinics_count) == ("Otra", 7)
    assert clinics.calls == [(TOKEN, [2])]


@pytest.mark.parametrize("status_id", [1, 2, 3, 5])
async def test_get_finds_every_current_subscription_whatever_its_status(status_id):
    repository = FakeSubscriptionRepository()
    repository.add(status_id=status_id)

    view = await service(repository).get(1, TOKEN)

    assert view.subscription.status_id == status_id


async def test_get_of_a_deleted_or_missing_subscription_is_not_found_without_asking_clinics():
    repository = FakeSubscriptionRepository()
    repository.add(name="Eliminada", status_id=4)
    clinics = FakeClinicsApi()

    for subscription_id in (1, 99):
        with pytest.raises(SubscriptionNotFoundError) as error:
            await service(repository, clinics).get(subscription_id, TOKEN)
        assert str(subscription_id) in error.value.message

    assert clinics.calls == []


async def test_get_still_answers_when_the_clinics_api_fails():
    repository = FakeSubscriptionRepository()
    repository.add()

    view = await service(repository, FakeClinicsApi({1: 3}, fail=True)).get(1, TOKEN)

    assert view.clinics_count is None


# --- US5: update ---


class RecordingRepository(FakeSubscriptionRepository):
    """Keeps the `changes` it receives, to prove that only what was sent is written."""

    def __init__(self):
        super().__init__()
        self.received: list[dict] = []

    async def update(self, subscription_id, changes):
        self.received.append(dict(changes))
        return await super().update(subscription_id, changes)


async def test_update_writes_only_the_fields_that_were_sent():
    repository = RecordingRepository()
    repository.add(name="Pro", monthly_price="4500", features=["Uno"], description="Para clínicas")

    view = await service(repository).update(1, SubscriptionUpdate(monthly_price="4700"), TOKEN)

    assert repository.received == [{"monthly_price": Decimal("4700")}]
    stored = view.subscription
    assert (stored.name, stored.description, stored.features) == ("Pro", "Para clínicas", ["Uno"])
    assert stored.monthly_price == Decimal("4700")


async def test_update_keeps_a_description_that_was_sent_as_null():
    repository = RecordingRepository()
    repository.add(description="Antes")

    view = await service(repository).update(1, SubscriptionUpdate(description=None), TOKEN)

    assert repository.received == [{"description": None}]
    assert view.subscription.description is None


async def test_update_of_a_missing_or_deleted_subscription_is_not_found():
    repository = FakeSubscriptionRepository()
    repository.add(status_id=4)

    for subscription_id in (1, 99):
        with pytest.raises(SubscriptionNotFoundError):
            await service(repository).update(subscription_id, SubscriptionUpdate(name="X"), TOKEN)


async def test_update_to_the_name_of_another_subscription_is_the_name_conflict():
    repository = FakeSubscriptionRepository()
    repository.add(name="Pro")
    repository.add(name="Básico")

    with pytest.raises(SubscriptionNameAlreadyExistsError) as error:
        await service(repository).update(2, SubscriptionUpdate(name="pro"), TOKEN)

    assert "«pro»" in error.value.message


async def test_update_may_keep_the_own_name_with_other_capitals():
    repository = FakeSubscriptionRepository()
    repository.add(name="Pro")

    view = await service(repository).update(1, SubscriptionUpdate(name="PRO"), TOKEN)

    assert view.subscription.name == "PRO"


async def test_update_asks_the_clinics_api_after_writing_and_degrades_to_unavailable():
    repository = FakeSubscriptionRepository()
    repository.add()
    clinics = FakeClinicsApi({1: 4})

    view = await service(repository, clinics).update(1, SubscriptionUpdate(name="Nuevo"), TOKEN)

    assert (view.clinics_count, clinics.calls) == (4, [(TOKEN, [1])])

    degraded = await service(repository, FakeClinicsApi({1: 4}, fail=True)).update(
        1, SubscriptionUpdate(name="Otro"), TOKEN
    )
    assert degraded.clinics_count is None  # the update itself succeeded


# --- US6: change the status ---


def to_status(status_id: int) -> SubscriptionStatusChange:
    return SubscriptionStatusChange(status_id=status_id)


MOVES = [(current, target) for current in (1, 2, 3, 5) for target in (1, 2, 3) if current != target]


@pytest.mark.parametrize(("current", "target"), MOVES)
async def test_a_current_subscription_can_go_to_any_other_manageable_status(current, target):
    repository = FakeSubscriptionRepository()
    repository.add(status_id=current)

    view = await service(repository).change_status(1, to_status(target), TOKEN)

    assert view.subscription.status_id == target
    assert view.subscription.status.id == target


async def test_asking_for_the_status_it_already_has_is_a_conflict_naming_the_status():
    repository = FakeSubscriptionRepository()
    repository.add(status_id=2)

    with pytest.raises(SubscriptionStatusUnchangedError) as error:
        await service(repository).change_status(1, to_status(2), TOKEN)

    assert error.value.message == "La suscripción con el identificador 1 ya tiene el estatus Inactiva."


async def test_a_deleted_or_missing_subscription_is_not_found():
    repository = FakeSubscriptionRepository()
    repository.add(status_id=4)

    for subscription_id in (1, 99):
        with pytest.raises(SubscriptionNotFoundError):
            await service(repository).change_status(subscription_id, to_status(1), TOKEN)


async def test_the_decision_never_asks_the_clinics_api_but_the_answer_does_afterwards():
    repository = FakeSubscriptionRepository()
    repository.add(status_id=1)
    clinics = FakeClinicsApi({1: 3})

    view = await service(repository, clinics).change_status(1, to_status(3), TOKEN)

    assert view.clinics_count == 3
    assert clinics.calls == [(TOKEN, [1])]  # only to fill the answer, with clinics assigned


async def test_the_status_change_succeeds_when_the_clinics_api_is_down():
    repository = FakeSubscriptionRepository()
    repository.add()

    view = await service(repository, FakeClinicsApi({1: 3}, fail=True)).change_status(
        1, to_status(2), TOKEN
    )

    assert (view.subscription.status_id, view.clinics_count) == (2, None)


async def test_a_conflict_with_another_request_is_retried_once():
    class LosesTheRaceOnce(FakeSubscriptionRepository):
        attempts = 0

        async def change_status(self, subscription_id, to_status_id):
            self.attempts += 1
            if self.attempts == 1:
                return None  # another request changed the status between the two reads
            return await super().change_status(subscription_id, to_status_id)

    repository = LosesTheRaceOnce()
    repository.add(status_id=1)

    view = await service(repository).change_status(1, to_status(2), TOKEN)

    assert view.subscription.status_id == 2
    assert repository.attempts == 2


async def test_when_it_still_cannot_decide_after_the_retry_it_reports_the_current_status():
    class AlwaysLoses(FakeSubscriptionRepository):
        async def change_status(self, subscription_id, to_status_id):
            return None

    repository = AlwaysLoses()
    repository.add(status_id=3)

    with pytest.raises(SubscriptionStatusUnchangedError) as error:
        await service(repository).change_status(1, to_status(1), TOKEN)

    assert "Bloqueada" in error.value.message


# --- US7: delete ---


async def test_deleting_a_subscription_without_clinics_marks_it_deleted_and_keeps_its_data():
    repository = FakeSubscriptionRepository()
    repository.add(name="Pro", monthly_price="4500", features=["Uno"])
    clinics = FakeClinicsApi({})

    await service(repository, clinics).delete(1, TOKEN)

    assert repository.items[1].status_id == 4  # the row and its data are kept
    assert (repository.items[1].name, repository.items[1].features) == ("Pro", ["Uno"])
    assert clinics.calls == [(TOKEN, [1])]


async def test_deleting_a_subscription_with_clinics_is_refused_and_nothing_changes():
    repository = FakeSubscriptionRepository()
    repository.add()

    with pytest.raises(SubscriptionHasClinicsError) as error:
        await service(repository, FakeClinicsApi({1: 2})).delete(1, TOKEN)

    assert "identificador 1" in error.value.message
    assert repository.calls["soft_delete"] == 0
    assert repository.items[1].status_id == 1


async def test_when_the_clinics_cannot_be_checked_nothing_is_deleted():
    repository = FakeSubscriptionRepository()
    repository.add()

    with pytest.raises(ClinicsCheckUnavailableError):
        await service(repository, FakeClinicsApi({}, fail=True)).delete(1, TOKEN)

    assert repository.calls["soft_delete"] == 0
    assert repository.items[1].status_id == 1


async def test_deleting_a_missing_or_deleted_subscription_is_not_found_without_asking_clinics():
    repository = FakeSubscriptionRepository()
    repository.add(status_id=4)
    clinics = FakeClinicsApi()

    for subscription_id in (1, 99):
        with pytest.raises(SubscriptionNotFoundError):
            await service(repository, clinics).delete(subscription_id, TOKEN)

    assert clinics.calls == []


async def test_if_another_request_deleted_it_first_the_answer_is_not_found():
    class LosesTheRace(FakeSubscriptionRepository):
        async def soft_delete(self, subscription_id):
            return False

    repository = LosesTheRace()
    repository.add()

    with pytest.raises(SubscriptionNotFoundError):
        await service(repository).delete(1, TOKEN)


async def test_the_unavailable_check_is_the_only_read_that_fails_closed():
    """Reads degrade to `None`; the destructive write refuses (principle IX)."""
    repository = FakeSubscriptionRepository()
    repository.add()
    failing = FakeClinicsApi({}, fail=True)

    assert (await service(repository, failing).get(1, TOKEN)).clinics_count is None
    with pytest.raises(ClinicsCheckUnavailableError):
        await service(repository, failing).delete(1, TOKEN)
