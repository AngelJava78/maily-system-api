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

from src.config import (
    configuration_error_message,
    get_cors_settings,
    get_dashboard_settings,
    get_integration_settings,
    insecure_url_warnings,
)
from src.dependencies import build_dashboard_source
from src.error_handlers import register_error_handlers
from src.routers import dashboard, subscriptions

logger = logging.getLogger(__name__)

# Logged at every start-up while the dashboard answers fictitious data (FR-024), so it does not reach
# production unnoticed. It names no address, token or secret.
DUMMY_DASHBOARD_NOTICE = (
    "The dashboard is returning DUMMY data (phase 1): the clinics, doctors, patients and users are "
    "fictitious and must be replaced by the real sources before production"
)

TITLE = "MailySoft System API"
VERSION = "2.0.0"
DESCRIPTION = """\
Servicio REST de MailySoft. Su primer dominio es el catálogo de **suscripciones** (planes) que se
asignan a las clínicas: precio mensual y anual, días de prueba, autoconsumo, módulos de clínica,
límites de la clínica y otras funcionalidades.

- Cada suscripción tiene un estatus tomado de un catálogo (1 Activa, 2 Inactiva, 3 Bloqueada,
  4 Eliminada). Se devuelve como un objeto con `id` y `name`; quien consume la API debe basarse en
  el `id`: el nombre puede cambiar. Las suscripciones eliminadas no aparecen.
- `module_keys` son claves de un catálogo de módulos de tipo Clínica que es propiedad de la API de
  usuarios, no de este servicio; esta API solo guarda y valida las claves (nunca su nombre ni su
  descripción) y siempre incluye `patients`.
- **Todas las operaciones exigen un token de acceso y un permiso**, que decide el API de usuarios
  en cada petición. La documentación no exige token.
- Todos los errores tienen el mismo formato (`code`, `message` y, en las validaciones, `errors`) y
  sus mensajes están en español.
- `clinics_count` lo aporta el API de clínicas en cada lectura; si no está disponible vale `null`.

El **dashboard de plataforma** (`GET /api/v1/dashboard`, «Panel de Maily») es de solo lectura y no
se guarda en caché: devuelve en una sola consulta seis indicadores y las clínicas más recientes (sin
paginar, hasta 10). Si una fuente de datos falla, su valor llega como `null`, nunca como un cero
inventado. En la Fase 1 sus datos son ficticios.
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
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Validate the configuration, warn about insecure addresses and own the shared HTTP client."""
    # Every configuration is loaded before giving up, so one message names all the wrong variables.
    errors = []
    for load in (get_integration_settings, get_dashboard_settings):
        try:
            load()
        except ValidationError as error:
            errors.append(error)
    if errors:
        message = configuration_error_message(*errors)
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
    try:
        yield
    finally:
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
    app.include_router(subscriptions.router)
    app.include_router(dashboard.router)
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
