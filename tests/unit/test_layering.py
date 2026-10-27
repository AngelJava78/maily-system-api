"""Layer compliance (Principle I): each layer only imports what the architecture allows.

It walks every module of `src/` with `ast`, so it also covers the ones that later features add.
The composition root and the shared vocabulary (`main`, `dependencies`, `security`, `exceptions`,
`error_handlers`, `messages`, `config` and `clinic_modules`) sit outside these rules.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"

# Layer (folder of `src/`) -> the packages it must not import.
# `src.integrations` (clients of other APIs) is only used by the Services and by the composition
# root; `src.security` (FastAPI dependencies) only by the Routers, `main` and `dependencies`
# (Principles I and VIII).
FORBIDDEN_IMPORTS = {
    "routers": ("src.repositories", "src.integrations", "src.database", "src.models", "sqlalchemy"),
    "services": ("src.routers", "src.security", "fastapi", "sqlalchemy"),
    "repositories": (
        "src.services",
        "src.routers",
        "src.integrations",
        "src.security",
        "src.dtos",
        "fastapi",
    ),
    "integrations": (
        "src.routers",
        "src.services",
        "src.repositories",
        "src.database",
        "src.models",
        "src.dtos",
        "src.security",
        "fastapi",
        "sqlalchemy",
    ),
    "database": (
        "src.models",
        "src.repositories",
        "src.services",
        "src.routers",
        "src.integrations",
        "src.security",
        "src.dtos",
    ),
    "models": (
        "src.routers",
        "src.services",
        "src.repositories",
        "src.database",
        "src.integrations",
        "src.security",
        "src.dtos",
    ),
    "dtos": (
        "src.routers",
        "src.services",
        "src.repositories",
        "src.database",
        "src.integrations",
        "src.security",
        "src.models",
        "sqlalchemy",
    ),
    # One-off deploy entrypoints (spec 006): they build their own Repository/Service/integration
    # clients like a tiny composition root, so they need those layers; they never serve an HTTP
    # request, so routers, security and DTOs (and touching sqlalchemy directly) stay forbidden.
    "scripts": ("src.routers", "src.security", "src.dtos", "fastapi", "sqlalchemy"),
}

# Modules that live directly in `src/` (composition root and shared vocabulary).
ROOT_MODULES = {
    "__init__",
    "main",
    "dependencies",
    "security",
    "exceptions",
    "error_handlers",
    "messages",
    "config",
    "clinic_modules",
}


def imported_modules(source: str) -> set[str]:
    """Every module that the source imports, including the ones under `TYPE_CHECKING`."""
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "the project uses absolute imports only"
            modules.add(node.module or "")
    return modules


def violations_in(source: str, forbidden: tuple[str, ...]) -> list[str]:
    return sorted(
        module
        for module in imported_modules(source)
        for package in forbidden
        if module == package or module.startswith(f"{package}.")
    )


def modules_of(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


@pytest.mark.parametrize("layer", FORBIDDEN_IMPORTS)
def test_the_layer_only_imports_what_the_architecture_allows(layer: str):
    modules = modules_of(layer)
    assert modules, f"src/{layer}/ has no modules: the rule would check nothing"

    found = [
        f"{path.relative_to(SRC.parent).as_posix()} imports {module}"
        for path in modules
        for module in violations_in(path.read_text(encoding="utf-8"), FORBIDDEN_IMPORTS[layer])
    ]

    assert not found, "\n".join(found)


def test_the_check_detects_forbidden_imports():
    source = (
        "import sqlalchemy\n"
        "from sqlalchemy.orm import Session\n"
        "from src.models.subscription import Subscription\n"
        "from src.dtos.subscription import SubscriptionRead\n"
    )

    assert violations_in(source, FORBIDDEN_IMPORTS["routers"]) == [
        "sqlalchemy",
        "sqlalchemy.orm",
        "src.models.subscription",
    ]


def test_only_the_services_may_import_the_integrations():
    source = "from src.integrations.errors import UsersApiUnavailable\n"

    assert violations_in(source, FORBIDDEN_IMPORTS["routers"]) == ["src.integrations.errors"]
    assert violations_in(source, FORBIDDEN_IMPORTS["repositories"]) == ["src.integrations.errors"]
    assert violations_in(source, FORBIDDEN_IMPORTS["services"]) == []
    assert violations_in(source, FORBIDDEN_IMPORTS["integrations"]) == []


def test_only_the_routers_may_import_the_security_dependencies():
    source = "from src.security import require_permission\n"

    assert violations_in(source, FORBIDDEN_IMPORTS["routers"]) == []
    for layer in ("services", "repositories", "integrations", "database", "models", "dtos"):
        assert violations_in(source, FORBIDDEN_IMPORTS[layer]) == ["src.security"], layer


def test_the_integrations_do_not_depend_on_fastapi_nor_on_the_database():
    source = "import fastapi\nfrom sqlalchemy import select\nfrom src.config import get_settings\n"

    assert violations_in(source, FORBIDDEN_IMPORTS["integrations"]) == ["fastapi", "sqlalchemy"]


def test_the_check_does_not_confuse_packages_with_similar_names():
    source = "import sqlalchemy_utils\nimport src.modelsx\n"

    assert violations_in(source, ("sqlalchemy", "src.models")) == []


def test_the_layers_cover_every_folder_of_the_source_tree():
    folders = {path.name for path in SRC.iterdir() if path.is_dir()} - {"__pycache__"}

    assert folders <= set(FORBIDDEN_IMPORTS), (
        f"a new folder of src/ needs import rules: {sorted(folders - set(FORBIDDEN_IMPORTS))}"
    )


def test_every_module_of_src_is_in_a_layer_or_is_a_known_root_module():
    unknown = sorted(
        path.name
        for path in SRC.glob("*.py")
        if path.stem not in ROOT_MODULES
    )

    assert not unknown, f"modules directly in src/ that no rule covers: {unknown}"
