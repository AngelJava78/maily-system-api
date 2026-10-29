"""Business rules of the subscriptions, with the Repository and the clinics API replaced by doubles."""

import asyncio
from decimal import Decimal

import pytest

from src.dtos.subscription import (
    SubscriptionCreate,
    SubscriptionStatusChange,
    SubscriptionUpdate,
)
from src.clinic_modules import PATIENTS_KEY
from src.exceptions import (
    ClinicsCheckUnavailableError,
    ModuleCheckUnavailableError,
    SubscriptionDataError,
    SubscriptionHasClinicsError,
    SubscriptionModuleNotFoundError,
    SubscriptionNameAlreadyExistsError,
    SubscriptionNotFoundError,
    SubscriptionStatusUnchangedError,
    SubscriptionTypeNotFoundError,
)
from src.integrations.errors import ClinicsApiUnavailable
from src.messages import SUBSCRIPTION_CLINICS_LIMIT_IMMUTABLE_MESSAGE
from src.models.subscription_type import SubscriptionType
from src.repositories.errors import ForeignKeyViolationError, UniqueViolationError
from src.services.subscription_service import SubscriptionService
from tests.unit.fakes import FakeClinicsApi, FakeSubscriptionRepository, FakeUsersApi

TOKEN = "the-token"


def service(repository=None, clinics=None, users=None) -> SubscriptionService:
    return SubscriptionService(
        repository or FakeSubscriptionRepository(), clinics or FakeClinicsApi(), users or FakeUsersApi()
    )


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
    base = {
        "name": "Pro",
        "subscription_type_id": 1,
        "monthly_price": "4500",
        "annual_price": "45000",
        "consulting_rooms_limit": 1,
        "doctors_limit": 1,
        "assistants_limit": 1,
        "new_patients_per_year_limit": 100,
        "clinics_limit": 1,
    }
    return SubscriptionCreate.model_validate({**base, **values})


async def test_create_passes_the_validated_values_to_the_repository():
    repository = FakeSubscriptionRepository()
    users = FakeUsersApi(clinic_module_keys=frozenset({"scheduling"}))

    view = await service(repository, users=users).create(
        create_data(
            description="Para clínicas",
            other_features=["Uno", "Dos"],
            module_keys=["scheduling"],
            trial_days=14,
            self_service=True,
        ),
        TOKEN,
    )

    stored = repository.items[view.subscription.id]
    assert (stored.name, stored.description, stored.other_features) == (
        "Pro",
        "Para clínicas",
        ["Uno", "Dos"],
    )
    assert stored.monthly_price == Decimal("4500.00")
    assert stored.annual_price == Decimal("45000.00")
    assert stored.trial_days == 14
    assert stored.self_service is True
    assert stored.module_keys == [PATIENTS_KEY, "scheduling"]
    assert stored.status_id == 1


@pytest.mark.parametrize("subscription_type_id", [1, 2])
async def test_create_passes_the_subscription_type_id_through_unchanged(subscription_type_id):
    repository = FakeSubscriptionRepository()

    view = await service(repository).create(
        create_data(subscription_type_id=subscription_type_id), TOKEN
    )

    assert repository.items[view.subscription.id].subscription_type_id == subscription_type_id


@pytest.mark.parametrize(
    ("subscription_type_id", "clinics_limit"), [(1, 1), (2, 25)]
)
async def test_create_passes_the_clinics_limit_through_unchanged(subscription_type_id, clinics_limit):
    repository = FakeSubscriptionRepository()

    view = await service(repository).create(
        create_data(subscription_type_id=subscription_type_id, clinics_limit=clinics_limit), TOKEN
    )

    assert repository.items[view.subscription.id].clinics_limit == clinics_limit


async def test_a_nonexistent_subscription_type_id_becomes_the_type_not_found_error():
    class Broken(FakeSubscriptionRepository):
        async def create(self, *args, **kwargs):
            raise ForeignKeyViolationError("subscriptions_subscription_type_id_fkey")

    with pytest.raises(SubscriptionTypeNotFoundError) as error:
        await service(Broken()).create(create_data(subscription_type_id=99), TOKEN)

    assert "99" in error.value.message


async def test_another_foreign_key_violation_is_not_mistaken_for_the_type_not_found():
    class Broken(FakeSubscriptionRepository):
        async def create(self, *args, **kwargs):
            raise ForeignKeyViolationError("some_other_constraint")

    with pytest.raises(ForeignKeyViolationError):
        await service(Broken()).create(create_data(), TOKEN)


async def test_a_new_subscription_has_a_true_zero_without_asking_the_clinics_api():
    clinics = FakeClinicsApi({1: 99})

    view = await service(clinics=clinics).create(create_data(), TOKEN)

    assert view.clinics_count == 0
    assert clinics.calls == []


async def test_a_repeated_name_becomes_the_name_conflict_with_the_name_in_the_message():
    repository = FakeSubscriptionRepository()
    repository.add(name="Pro")

    with pytest.raises(SubscriptionNameAlreadyExistsError) as error:
        await service(repository).create(create_data(name="pro"), TOKEN)

    assert "«pro»" in error.value.message


async def test_the_name_of_a_deleted_subscription_can_be_used_again():
    repository = FakeSubscriptionRepository()
    repository.add(name="Solo", status_id=4)

    view = await service(repository).create(create_data(name="Solo"), TOKEN)

    assert view.subscription.name == "Solo"


async def test_another_unique_violation_is_not_mistaken_for_the_name_conflict():
    class Broken(FakeSubscriptionRepository):
        async def create(self, *args, **kwargs):
            raise UniqueViolationError("some_other_constraint")

    with pytest.raises(UniqueViolationError):
        await service(Broken()).create(create_data(), TOKEN)


async def test_the_name_is_not_checked_before_inserting_to_avoid_a_race():
    repository = FakeSubscriptionRepository()

    await service(repository).create(create_data(), TOKEN)

    assert dict(repository.calls) == {"create": 1}


# --- US3: module validation (FR-015 a FR-020) ---


async def test_create_without_extra_modules_never_asks_the_users_api():
    users = FakeUsersApi()

    view = await service(users=users).create(create_data(), TOKEN)

    assert view.subscription.module_keys == [PATIENTS_KEY]
    assert users.module_calls == []


async def test_create_with_a_recognised_module_asks_the_users_api_once():
    users = FakeUsersApi(clinic_module_keys=frozenset({"scheduling"}))

    view = await service(users=users).create(create_data(module_keys=["scheduling"]), TOKEN)

    assert view.subscription.module_keys == [PATIENTS_KEY, "scheduling"]
    assert users.module_calls == [TOKEN]


async def test_create_with_an_unrecognised_module_fails():
    users = FakeUsersApi(clinic_module_keys=frozenset({"scheduling"}))

    with pytest.raises(SubscriptionModuleNotFoundError) as error:
        await service(users=users).create(create_data(module_keys=["billing", "finance"]), TOKEN)

    assert "«billing»" in error.value.message


async def test_create_with_a_retired_module_key_like_scheduling_fails():
    # "scheduling" is spec.md's own example of a key no catalog recognises any more (US2).
    users = FakeUsersApi(clinic_module_keys=frozenset({"patients", "reminders"}))

    with pytest.raises(SubscriptionModuleNotFoundError) as error:
        await service(users=users).create(create_data(module_keys=["scheduling"]), TOKEN)

    assert "«scheduling»" in error.value.message


async def test_create_when_the_users_api_cannot_answer_about_modules():
    users = FakeUsersApi(modules_unavailable=True)

    with pytest.raises(ModuleCheckUnavailableError):
        await service(users=users).create(create_data(module_keys=["scheduling"]), TOKEN)


async def test_patients_is_always_included_even_if_excluded_from_the_request():
    view = await service().create(create_data(module_keys=[]), TOKEN)

    assert view.subscription.module_keys == [PATIENTS_KEY]


async def test_a_brand_new_module_the_service_never_coded_is_accepted():
    # No list of known module keys lives in this service's code any more (FR-004 of spec 009): a
    # key invented for this test, that appears nowhere else in the repository, is accepted just
    # the same as any other, because the only thing that decides is what the users API answers.
    novel_key = "un_modulo_que_nadie_codifico"
    users = FakeUsersApi(clinic_module_keys=frozenset({PATIENTS_KEY, novel_key}))

    view = await service(users=users).create(create_data(module_keys=[novel_key]), TOKEN)

    assert view.subscription.module_keys == [PATIENTS_KEY, novel_key]


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
    repository.add(
        name="Pro", monthly_price="4500", other_features=["Uno"], description="Para clínicas"
    )

    view = await service(repository).update(1, SubscriptionUpdate(monthly_price="4700"), TOKEN)

    assert repository.received == [{"monthly_price": Decimal("4700")}]
    stored = view.subscription
    assert (stored.name, stored.description, stored.other_features) == ("Pro", "Para clínicas", ["Uno"])
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


# --- US3 (007-add-clinics-limit): clinics_limit depends on the subscription's current type ---


def fields_of(error: pytest.ExceptionInfo) -> list[str]:
    return [item["loc"][-1] for item in error.value.errors]


@pytest.mark.parametrize("new_value", [1, 50])
async def test_sending_clinics_limit_on_an_individual_subscription_is_rejected(new_value):
    # Sending it at all is "trying to change it", even with the value it already has (1).
    repository = RecordingRepository()
    repository.add(subscription_type_id=SubscriptionType.INDIVIDUAL, clinics_limit=1)

    with pytest.raises(SubscriptionDataError) as error:
        await service(repository).update(1, SubscriptionUpdate(clinics_limit=new_value), TOKEN)

    assert fields_of(error) == ["clinics_limit"]
    assert error.value.errors[0]["msg"] == SUBSCRIPTION_CLINICS_LIMIT_IMMUTABLE_MESSAGE
    assert repository.received == []


async def test_sending_clinics_limit_with_another_valid_field_on_an_individual_is_rejected_whole():
    repository = RecordingRepository()
    repository.add(
        subscription_type_id=SubscriptionType.INDIVIDUAL, clinics_limit=1, monthly_price="900"
    )

    with pytest.raises(SubscriptionDataError):
        await service(repository).update(
            1, SubscriptionUpdate(clinics_limit=1, monthly_price=Decimal("950.00")), TOKEN
        )

    assert repository.received == []
    assert repository.items[1].monthly_price == Decimal("900.00")


async def test_updating_clinics_limit_of_an_enterprise_subscription_works_normally():
    repository = RecordingRepository()
    repository.add(subscription_type_id=SubscriptionType.ENTERPRISE, clinics_limit=10)

    view = await service(repository).update(1, SubscriptionUpdate(clinics_limit=80), TOKEN)

    assert repository.received == [{"clinics_limit": 80}]
    assert view.subscription.clinics_limit == 80


async def test_updating_clinics_limit_of_a_missing_subscription_is_not_found():
    with pytest.raises(SubscriptionNotFoundError):
        await service().update(99, SubscriptionUpdate(clinics_limit=50), TOKEN)


# --- US5: module validation on update (research R6) ---


async def test_updating_modules_of_a_missing_subscription_is_not_found_without_asking_the_users_api():
    users = FakeUsersApi(clinic_module_keys=frozenset({"scheduling"}))

    with pytest.raises(SubscriptionNotFoundError):
        await service(users=users).update(99, SubscriptionUpdate(module_keys=["scheduling"]), TOKEN)

    assert users.module_calls == []


async def test_updating_modules_without_touching_them_does_not_pre_check_existence_or_ask_the_users_api():
    class CountingRepository(FakeSubscriptionRepository):
        def __init__(self):
            super().__init__()
            self.extra_lookups = 0

        async def get_current_by_id(self, subscription_id):
            self.extra_lookups += 1
            return await super().get_current_by_id(subscription_id)

    repository = CountingRepository()
    repository.add()
    users = FakeUsersApi()

    await service(repository, users=users).update(1, SubscriptionUpdate(name="Nuevo"), TOKEN)

    assert repository.extra_lookups == 0
    assert users.module_calls == []


async def test_updating_modules_replaces_the_whole_set_and_keeps_patients():
    repository = FakeSubscriptionRepository()
    repository.add(module_keys=[PATIENTS_KEY, "scheduling", "reminders"])
    users = FakeUsersApi(clinic_module_keys=frozenset({"finance"}))

    view = await service(repository, users=users).update(
        1, SubscriptionUpdate(module_keys=["finance"]), TOKEN
    )

    assert view.subscription.module_keys == ["finance", PATIENTS_KEY]  # alphabetical order


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


# --- Datos existentes: reconciliación de tipos (FR-009, FR-010; sin historia de usuario) ---


async def test_reconcile_marks_only_the_subscriptions_with_more_than_one_clinic():
    repository = FakeSubscriptionRepository()
    repository.add(name="Una")
    repository.add(name="Dos")
    repository.add(name="Varias")
    clinics = FakeClinicsApi({1: 1, 2: 2, 3: 5})

    marked = await service(repository, clinics).reconcile_types_from_clinic_counts(TOKEN)

    assert marked == 2
    assert repository.calls["mark_enterprise"] == 1
    assert sorted(
        s.id for s in repository.items.values() if s.subscription_type_id == SubscriptionType.ENTERPRISE
    ) == [2, 3]
    assert repository.items[1].subscription_type_id == SubscriptionType.INDIVIDUAL


async def test_reconcile_asks_for_every_subscription_without_a_filter():
    repository = FakeSubscriptionRepository()
    repository.add(name="Una")
    clinics = FakeClinicsApi({1: 2})

    await service(repository, clinics).reconcile_types_from_clinic_counts(TOKEN)

    assert clinics.calls == [(TOKEN, None)]


async def test_reconcile_does_not_write_anything_when_nobody_has_more_than_one_clinic():
    repository = FakeSubscriptionRepository()
    repository.add(name="Una")
    clinics = FakeClinicsApi({1: 1})

    marked = await service(repository, clinics).reconcile_types_from_clinic_counts(TOKEN)

    assert marked == 0
    assert repository.calls["mark_enterprise"] == 0


async def test_reconcile_propagates_the_clinics_failure_without_retrying_it_itself():
    repository = FakeSubscriptionRepository()
    repository.add(name="Una")

    with pytest.raises(ClinicsApiUnavailable):
        await service(repository, FakeClinicsApi(fail=True)).reconcile_types_from_clinic_counts(TOKEN)

    assert repository.calls["mark_enterprise"] == 0


# --- US7: delete ---


async def test_deleting_a_subscription_without_clinics_marks_it_deleted_and_keeps_its_data():
    repository = FakeSubscriptionRepository()
    repository.add(name="Pro", monthly_price="4500", other_features=["Uno"])
    clinics = FakeClinicsApi({})

    await service(repository, clinics).delete(1, TOKEN)

    assert repository.items[1].status_id == 4  # the row and its data are kept
    assert (repository.items[1].name, repository.items[1].other_features) == ("Pro", ["Uno"])
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
