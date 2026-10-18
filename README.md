# maily-system-api

**MailySoft System API**: servicio REST de MailySoft. Su primer dominio es el catálogo de
**suscripciones** (planes) que se asignan a las clínicas: precio mensual, lo que incluye cada plan y
su estatus. No administra identidades: **consulta al API de usuarios** para saber quién puede operar
y **al API de clínicas** para saber cuántas clínicas tiene cada plan.

## Qué incluye hoy

Spec [`001-subscriptions-api`](specs/001-subscriptions-api/spec.md): 6 operaciones bajo
`/api/v1/subscriptions` (contrato en [`openapi-subscriptions.yaml`](specs/001-subscriptions-api/contracts/openapi-subscriptions.yaml);
la documentación interactiva está en `/docs`).

| Operación | Método y ruta | Permiso |
|---|---|---|
| `list_subscriptions` | `GET /api/v1/subscriptions` | `subscriptions:read` |
| `get_subscription` | `GET /api/v1/subscriptions/{id}` | `subscriptions:read` |
| `create_subscription` | `POST /api/v1/subscriptions` | `subscriptions:write` |
| `update_subscription` | `PATCH /api/v1/subscriptions/{id}` | `subscriptions:update` |
| `change_subscription_status` | `PATCH /api/v1/subscriptions/{id}/status` | `subscriptions:update` |
| `delete_subscription` | `DELETE /api/v1/subscriptions/{id}` | `subscriptions:delete` |

- **Estatus**: catálogo `subscription_statuses` (1 Activa, 2 Inactiva, 3 Bloqueada, 4 Eliminada; se
  administra a mano). La baja es lógica. El listado se devuelve **completo, sin paginar**, con todas las
  suscripciones vigentes y su estatus; las eliminadas no aparecen. El nombre es único (sin distinguir
  mayúsculas) entre las no eliminadas.
- **Control de acceso**: toda operación exige un token de Auth0 (`Authorization: Bearer …`) y su permiso.
  **Este servicio no verifica el token**: lo reenvía, una vez por petición y sin caché, al API de usuarios
  (`GET /api/v1/authorization/check`) y obedece su respuesta. Cualquier duda se rechaza (401, 403 o 503).
- **Número de clínicas** (`clinics_count`): lo aporta el API de clínicas en cada lectura. Si no responde,
  las lecturas siguen funcionando con `clinics_count: null` (nunca un cero inventado); **eliminar** se
  rechaza si la suscripción tiene clínicas o si no puede comprobarse.
- **Errores**: todos con el mismo formato (`code`, `message` y, en las validaciones, `errors`) y mensajes
  en español ([catálogo](specs/001-subscriptions-api/contracts/error-catalog.md)).

> **Importante**: sin las direcciones del API de usuarios y del de clínicas el servicio **no arranca**, y si
> el API de usuarios no responde, **todas** las operaciones devuelven 503 (la documentación sigue
> pública). Para desarrollar sin esos servicios, usa las simulaciones de la pila de pruebas de punta a
> punta (más abajo).

## Requisitos

- Docker Desktop con Docker Compose 2.24 o superior (PostgreSQL 17, migraciones y API).
- [uv](https://docs.astral.sh/uv/) y Python 3.14 o superior (pruebas y desarrollo local).
- Node.js con npm, **solo** para las pruebas de punta a punta (Newman): no entran en la imagen del servicio.

## Configuración

Copia `.env.example` a `.env` (no se versiona). Variables del servicio:

| Variable | Obligatoria | Por defecto | Para qué |
|---|---|---|---|
| `DATABASE_URL` | sí | — | Base de datos (PostgreSQL, `postgresql+asyncpg://…`) |
| `USERS_API_BASE_URL` | sí | — | Dirección del API de usuarios, sin barra final |
| `CLINICS_API_BASE_URL` | sí | — | Dirección del API de clínicas, sin barra final |
| `USERS_API_TIMEOUT_SECONDS` | no | `5` | Tiempo máximo total de cada llamada (mayor que 0, hasta 30) |
| `CLINICS_API_TIMEOUT_SECONDS` | no | `5` | Ídem, para el API de clínicas |
| `CORS_ALLOWED_ORIGINS` | no | vacía | Sitios web del Front que pueden llamar desde el navegador (lista separada por comas); vacía = ninguno |

El arranque valida la configuración y, si falta una variable obligatoria, se niega a iniciar y nombra la
variable (nunca su valor).

**Seguridad de las direcciones**: a esas dos direcciones se reenvía el token de la persona. Usa `https://`
salvo en local o en la red de Docker: con una dirección `http://` no local el servicio arranca pero
registra una advertencia (el token viajaría sin cifrar). Las redirecciones nunca se siguen.

## Puesta en marcha

```powershell
Copy-Item .env.example .env              # ajusta credenciales, puertos y las dos direcciones
docker compose up -d db                  # PostgreSQL 17 (bases `maily_system` y `maily_system_test`, puerto 5434)
docker compose run --rm migrate          # aprovisiona el esquema y los estatus
docker compose up -d api                 # API en http://localhost:8010 (puerto `API_PORT`)
```

Con la API arriba, `http://localhost:8010/docs` muestra la documentación interactiva. Cada operación
necesita un token válido para el API de usuarios que hayas configurado.

Sin Docker para la API (con la base ya migrada y las variables en el entorno o en `.env`):

```powershell
uv sync                                  # instala las dependencias
uv run uvicorn src.main:app --port 8010
```

Los puertos por defecto (PostgreSQL `5434`, API `8010`) evitan chocar con otros proyectos de MailySoft
(`5432`/`5433` y `8000`). Si alguno está ocupado, cambia `POSTGRES_PORT` (y el puerto de las dos URLs de
base de datos) o `API_PORT` en `.env`.

Alembic también se puede usar directamente:

```powershell
uv run alembic upgrade head              # aplicar migraciones
uv run alembic downgrade base            # revertirlas todas (solo en desarrollo)
uv run alembic check                     # ¿los modelos coinciden con las migraciones?
```

Revertir `0002` borra el catálogo de estatus y falla si hay suscripciones que los usan; úsalo solo en
bases de desarrollo.

**Sin Alembic**: [`project-definition/create_database.sql`](project-definition/create_database.sql) crea
todo el esquema (equivale a las migraciones `0001` y `0002`), carga los 4 estatus y registra la versión
de Alembic, en una sola transacción. Úsalo en una base **propia** de este servicio (no en la de
mailySoft-usuarios: comparten el nombre de `alembic_version` y de `set_updated_at()`; si ya existen, el
script se detiene sin cambiar nada):

```powershell
psql -U postgres -d maily_system -v ON_ERROR_STOP=1 -f project-definition/create_database.sql
```

## Pruebas

Las pruebas usan un PostgreSQL real (`TEST_DATABASE_URL`) y **eliminan y recrean el esquema** de esa base,
por eso su nombre debe terminar en `_test`; si no, la suite se niega a ejecutarse. **Ninguna prueba llama
al API de usuarios ni al de clínicas reales**: usan simulaciones (`tests/stubs/`).

```powershell
docker compose up -d db
uv run pytest                            # suite completa
```

Guía de validación con el mapa historia → pruebas:
[`specs/001-subscriptions-api/quickstart.md`](specs/001-subscriptions-api/quickstart.md).

## Pruebas de punta a punta (Postman)

Una colección de Postman recorre las 6 operaciones y los errores clave (401, 403, 404, 409, 422 y 503)
contra el servicio real y las dos simulaciones. **Complementa a pytest, que sigue siendo la puerta de
calidad; no lo sustituye.** No necesita cuenta de Postman ni envía nada a servicios externos. Vive en
`tests/postman/` y se ejecuta con [Newman](https://github.com/postmanlabs/newman).

```powershell
npm ci --prefix tests/postman            # instala Newman (una vez)
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml up -d --wait api
npm run e2e --prefix tests/postman       # colección completa: consola + tests/postman/reports/junit.xml
npm run e2e --prefix tests/postman -- --folder "5. Control de acceso"   # solo una carpeta (las 2 a 4 usan lo que crea la 1)
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml down -v
```

- **Pila aislada**: el proyecto `maily-system-e2e` tiene su propia base de datos desechable (sin puerto
  publicado), la API en `127.0.0.1:8011` y las simulaciones del API de usuarios (`:8012`) y del de
  clínicas (`:8013`). **No apuntes nunca la colección a un servicio con datos reales**: crea y elimina de
  forma lógica suscripciones, así que quedan filas «Eliminada».
- **Resultado**: código de salida `0` si todo pasa y `1` si falla una comprobación o la pila no responde.
- **Si la API cambia**: actualiza la colección en el mismo cambio; `tests/contract/test_postman_collection.py`
  (parte de `uv run pytest`) falla nombrando las operaciones que faltan o sobran.

## Estructura

```text
src/
├── main.py            # aplicación FastAPI (`uvicorn src.main:app`) y su ciclo de vida
├── config.py          # configuración desde variables de entorno / .env
├── dependencies.py    # raíz de composición: clientes, Repository y Services de cada petición
├── security.py        # dependencias de seguridad: token y permiso de cada operación
├── exceptions.py      # errores de la aplicación (código en inglés, mensaje en español)
├── error_handlers.py  # formato uniforme de error (401, 403, 404, 409, 422, 500 y 503)
├── messages.py        # códigos de error y mensajes en español
├── routers/           # endpoints HTTP: solo validan, llaman a un Service y serializan
├── services/          # reglas de negocio y autorización
├── repositories/      # acceso a datos (únicas consultas SQL)
├── integrations/      # clientes del API de usuarios y del API de clínicas
├── dtos/              # esquemas de entrada y salida (Pydantic)
├── database/          # engine y sesiones async
└── models/            # modelos SQLAlchemy (sin lógica de negocio)
alembic/versions/      # 0001 esquema, 0002 catálogo de estatus
tests/unit/            # sin base de datos (DTOs, Services, seguridad, configuración, capas)
tests/integration/     # PostgreSQL real (esquema, migraciones y Repositories)
tests/contract/        # la API por HTTP, el documento OpenAPI, la cobertura de permisos y la colección
tests/stubs/           # simulaciones del API de usuarios y del API de clínicas
tests/postman/         # colección, entornos y pila aislada de las pruebas de punta a punta (Newman)
project-definition/    # esquema de datos objetivo (DATA_SCHEMA.md)
specs/                 # especificaciones de Spec Kit
.specify/memory/constitution.md   # reglas del proyecto (capas, async, pruebas, migraciones, acceso)
```
