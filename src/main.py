"""FastAPI application: `uvicorn src.main:app`.

`create_app()` has no side effects (it opens no connection and demands no variable: the engine is
created on first use and the integrations are configured by `lifespan`), so the application can be
imported and built in the tests.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from src import VERSION
from src.config import (
    InvalidSettingsError,
    configuration_error_message,
    database_schedule_from,
    get_build_settings,
    get_cors_settings,
    get_dashboard_settings,
    get_database_schedule_settings,
    get_health_settings,
    get_integration_settings,
    get_settings,
    health_config_from,
    insecure_url_warnings,
)
from src.dependencies import build_dashboard_source
from src.error_handlers import register_error_handlers
from src.integrations.health_probe import create_health_http_client
from src.routers import dashboard, health, monitored_components, subscriptions
from src.services.health_state import HealthState

logger = logging.getLogger(__name__)

# Logged at every start-up while the dashboard answers fictitious data (FR-024), so it does not reach
# production unnoticed. It names no address, token or secret.
DUMMY_DASHBOARD_NOTICE = (
    "The dashboard is returning DUMMY data (phase 1): the clinics, doctors, patients and users are "
    "fictitious and must be replaced by the real sources before production"
)

TITLE = "MailySoft System API"
DESCRIPTION = """\
Servicio REST de MailySoft. Su primer dominio es el catálogo de **suscripciones** (planes) que se
asignan a las clínicas: precio mensual y anual, días de prueba, autoconsumo, módulos de clínica,
límites de la clínica y otras funcionalidades.

- Cada suscripción tiene un `subscription_type` (hoy, 1 Individual o 2 Empresarial) tomado de un
  catálogo administrado a mano, igual que el estatus. Se devuelve como un objeto con `id` y `name`.
  Al crear se envía `subscription_type_id` (el entero); es obligatorio y fijo para siempre:
  ninguna operación permite modificarlo después.
- `clinics_limit` es un quinto límite de la clínica cuyo rango depende del tipo: exactamente `1`
  y fijo para siempre si es Individual; de `1` a `100` y modificable si no lo es. Es un techo
  informativo (como los otros cuatro): no se compara contra el número real de clínicas
  (`clinics_count`, de solo lectura).
- Cada suscripción tiene un estatus tomado de un catálogo (1 Activa, 2 Inactiva, 3 Bloqueada,
  4 Eliminada). Se devuelve como un objeto con `id` y `name`; quien consume la API debe basarse en
  el `id`: el nombre puede cambiar. Las suscripciones eliminadas no aparecen.
- `module_keys` son claves de un catálogo de módulos de tipo Clínica que es propiedad de la API de
  usuarios, no de este servicio; esta API solo guarda y valida las claves (nunca su nombre ni su
  descripción) y siempre incluye `patients`.
- **Todas las operaciones exigen un token de acceso y un permiso**, que decide el API de usuarios
  en cada petición, salvo las cuatro rutas públicas de salud (`/health/live`, `/health/ready`,
  `/info` y `/health/status`). La documentación no exige token.
- Todos los errores tienen el mismo formato (`code`, `message` y, en las validaciones, `errors`) y
  sus mensajes están en español.
- `clinics_count` lo aporta el API de clínicas en cada lectura; si no está disponible vale `null`.

El **dashboard de plataforma** (`GET /api/v1/dashboard`, «Panel de Maily») es de solo lectura y no
se guarda en caché: devuelve en una sola consulta seis indicadores y las clínicas más recientes (sin
paginar, hasta 10). Si una fuente de datos falla, su valor llega como `null`, nunca como un cero
inventado. En la Fase 1 sus datos son ficticios.

La **salud de servicios** cumple el contrato de salud de Maily v1 en la raíz (`/health/live`,
`/health/ready` e `/info`, públicos) y agrega la salud de la plataforma en `GET /api/v1/health`
(siempre 200 una vez concedido el acceso): este servicio, la base de datos y los servicios y
frontends del registro de componentes, que se administra sin redesplegar. `/health/status` publica
sin token un estado mínimo, sin versiones, direcciones ni detalles técnicos.
"""

OPENAPI_TAGS = [
    {
        "name": "subscriptions",
        "description": (
            "Catálogo de suscripciones (planes) y su estatus. El listado se devuelve completo, sin "
            "paginar."
        ),
    },
    {
        "name": "dashboard",
        "description": (
            "Resumen general de la plataforma de Maily («Panel de Maily»). Solo lectura; los datos "
            "de la Fase 1 son ficticios."
        ),
    },
    {
        "name": "Salud",
        "description": (
            "Salud de los servicios de Maily: contrato de salud v1 (público), estado público de la "
            "plataforma, consulta agregada de salud y registro de componentes monitoreados."
        ),
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Validate the configuration, warn about insecure addresses and own the shared HTTP clients."""
    # Every configuration is loaded before giving up, so one message names all the wrong variables.
    # `get_settings` holds DATABASE_URL, which the service needs to start (spec 005, research R16).
    errors = []
    loaders = (
        get_settings,
        get_integration_settings,
        get_dashboard_settings,
        get_health_settings,
        get_build_settings,
    )
    for load in loaders:
        try:
            load()
        except ValidationError as error:
            errors.append(error)
    # The four variables of the schedule of the database go together, so Pydantic cannot name them:
    # they are read on their own, also when another health variable is wrong (research R16).
    invalid_variables: list[str] = []
    missing_variables: list[str] = []
    try:
        database_schedule_from(get_database_schedule_settings())
    except InvalidSettingsError as error:
        (missing_variables if error.missing else invalid_variables).extend(error.variables)
    if errors or invalid_variables or missing_variables:
        message = configuration_error_message(
            *errors, invalid_variables=invalid_variables, missing_variables=missing_variables
        )
        logger.error(message)
        # `from None`: the validation error repeats the values that were received.
        raise RuntimeError(message) from None
    settings = get_integration_settings()

    for warning in insecure_url_warnings(settings):
        logger.warning(warning)
    if build_dashboard_source().is_dummy:
        logger.warning(DUMMY_DASHBOARD_NOTICE)

    client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        follow_redirects=False,  # the token must never follow a redirection to another server
    )
    app.state.http_client = client
    # The only client that calls the monitored components: it never carries the token (spec 005).
    health_client = create_health_http_client(
        timeout_seconds=health_config_from(get_health_settings()).check_timeout_seconds,
        user_agent=f"maily-system-api-health/{VERSION}",
    )
    app.state.health_http_client = health_client
    try:
        yield
    finally:
        await health_client.aclose()
        await client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=TITLE,
        version=VERSION,
        description=DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    register_error_handlers(app)
    # Memory of the health feature in this process (cache, aggregation in progress, registry copy).
    app.state.health = HealthState()
    app.include_router(subscriptions.router)
    app.include_router(dashboard.router)
    app.include_router(health.public_router)
    app.include_router(health.router)
    app.include_router(monitored_components.router)
    # `httpx` logs every URL at INFO level; only warnings are wanted.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    origins = get_cors_settings().origins
    if origins:  # FR-025: without a list no web site is allowed
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,
        )
    return app


app = create_app()
