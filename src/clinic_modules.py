"""Catalog of clinic modules and their dependencies (research R1 to R3).

The catalog of clinic modules itself belongs to the users API, not to this service (Principle IX):
this module only fixes the keys this service already knows about and the dependency rule between
them, which the users API does not model. No I/O here.
"""

PATIENTS_KEY = "patients"

# The nine proposed keys (contracts/users-api-integration.md); a module added later to the users
# API is still accepted as long as it is not one of the dependants below without its prerequisite.
CLINIC_MODULE_KEYS = frozenset(
    {
        PATIENTS_KEY,
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

# Dependent module key -> prerequisite module key (FR-018). Pure business rule of this service: the
# users API does not model dependencies between modules.
MODULE_DEPENDENCIES: dict[str, str] = {
    "reminders": "scheduling",
    "clinical_record_templates": "clinical_records",
    "prescriptions": "clinical_records",
    "billing": "finance",
}


def missing_prerequisite(keys: frozenset[str]) -> tuple[str, str] | None:
    """The first `(dependent, prerequisite)` pair in `keys` whose prerequisite is missing, if any."""
    for dependent, prerequisite in MODULE_DEPENDENCIES.items():
        if dependent in keys and prerequisite not in keys:
            return dependent, prerequisite
    return None
