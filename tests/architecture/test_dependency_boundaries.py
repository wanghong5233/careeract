import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = REPOSITORY_ROOT / "services"

DOMAIN_FORBIDDEN_IMPORTS = (
    "agno",
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "starlette",
    "temporalio",
    "services.api.application",
    "services.api.infrastructure",
    "services.api.integrations",
    "services.api.routes",
    "services.api.tools",
)
APPLICATION_FORBIDDEN_IMPORTS = (
    "agno",
    "fastapi",
    "playwright",
    "sqlalchemy",
    "starlette",
    "temporalio",
    "services.api.infrastructure",
    "services.api.integrations",
    "services.api.routes",
    "services.api.tools",
)
ROUTES_FORBIDDEN_IMPORTS = ("services.api.infrastructure",)
WORKFLOW_FORBIDDEN_IMPORTS = (
    "asyncpg",
    "browser_use",
    "httpx",
    "playwright",
    "psycopg",
    "requests",
    "sqlalchemy",
    "services.worker.activities",
)


def python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def assert_no_forbidden_imports(root: Path, forbidden: tuple[str, ...]) -> None:
    violations: list[str] = []
    for path in python_files(root):
        for module in imported_modules(path):
            if module.startswith(forbidden):
                relative_path = path.relative_to(REPOSITORY_ROOT)
                violations.append(f"{relative_path}: {module}")
    assert not violations, "Forbidden dependency direction:\n" + "\n".join(violations)


def test_domain_is_framework_free_and_depends_on_no_outer_layer() -> None:
    assert_no_forbidden_imports(SERVICES_ROOT / "api" / "domain", DOMAIN_FORBIDDEN_IMPORTS)


def test_application_does_not_depend_on_adapters() -> None:
    assert_no_forbidden_imports(
        SERVICES_ROOT / "api" / "application",
        APPLICATION_FORBIDDEN_IMPORTS,
    )


def test_routes_depend_on_use_cases_not_infrastructure() -> None:
    assert_no_forbidden_imports(SERVICES_ROOT / "api" / "routes", ROUTES_FORBIDDEN_IMPORTS)


def test_temporal_workflows_do_not_perform_io() -> None:
    assert_no_forbidden_imports(
        SERVICES_ROOT / "worker" / "workflows",
        WORKFLOW_FORBIDDEN_IMPORTS,
    )


def test_services_do_not_import_each_other_in_process() -> None:
    service_forbidden_imports = {
        "api": ("services.browser", "services.worker"),
        "browser": ("services.api", "services.worker"),
        "worker": ("services.api", "services.browser"),
    }
    for service, forbidden in service_forbidden_imports.items():
        assert_no_forbidden_imports(SERVICES_ROOT / service, forbidden)
