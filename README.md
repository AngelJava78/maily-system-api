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

### Dashboard de plataforma («Panel de Maily»)

Spec [`003-platform-dashboard`](specs/003-platform-dashboard/spec.md): una operación de **solo lectura**
que alimenta la pantalla de resumen general del administrador de plataforma (contrato en
[`openapi-dashboard.yaml`](specs/003-platform-dashboard/contracts/openapi-dashboard.yaml)).

| Operación | Método y ruta | Permiso |
|---|---|---|
| `get_dashboard` | `GET /api/v1/dashboard` | `dashboard:read` |

- **Qué devuelve**, en una sola consulta: `total_clinics`, `active_clinics`, `trial_clinics`,
  `total_doctors`, `total_patients`, `total_users` y `recent_clinics` (cada una con `id`, `name`,
  `created_at` en UTC y `status`). Solo datos agregados: nada personal. La respuesta lleva
  `Cache-Control: no-store`.
- **`limit`** (opcional): de 1 a 10 clínicas recientes, de la más nueva a la más antigua (a igualdad de
  fecha, por `id`). Más de 10 **no** es un error: devuelve 10. Sin `limit` rige el valor por defecto
  (`DASHBOARD_RECENT_CLINICS_LIMIT`: 3, 5 o 10; 5 si no se configura). Un `limit` que no sea un entero
  válido (menor que 1, decimal, vacío o repetido) se rechaza con 422, **después** de comprobar el permiso.
- **Datos ficticios (Fase 1)**: las clínicas, los doctores, los pacientes y los usuarios pertenecen a otros
  APIs que aún no existen. Mientras tanto la API devuelve datos ficticios y deterministas, que **no** se
  guardan en la base de datos, y **al arrancar registra un aviso** para que nadie los lleve a producción sin
  darse cuenta. Cuando existan las fuentes reales solo cambia de dónde salen los datos: el contrato no.
- **`null` significa «no disponible»**: si una fuente falla, solo su valor llega como `null` (nunca un cero
  inventado) y el resto del dashboard se devuelve con 200. Un `0` o un `[]` solo dicen que no hay datos.

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
| `DASHBOARD_RECENT_CLINICS_LIMIT` | no | `5` | Clínicas recientes del dashboard cuando no se envía `limit`: solo `3`, `5` o `10` (cualquier otro valor impide arrancar). Un cambio requiere reiniciar |

El arranque valida la configuración y, si falta una variable obligatoria o una opcional no es válida, se
niega a iniciar y nombra la variable (nunca su valor).

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

Las pruebas del dashboard **no necesitan PostgreSQL ni Docker** (la operación no usa la base de datos):

```powershell
uv run pytest -k dashboard
```

Guías de validación con el mapa historia → pruebas:
[`specs/001-subscriptions-api/quickstart.md`](specs/001-subscriptions-api/quickstart.md) (suscripciones) y
[`specs/003-platform-dashboard/quickstart.md`](specs/003-platform-dashboard/quickstart.md) (dashboard).

## Pruebas de punta a punta (Postman)

Hay **dos colecciones automáticas** para Newman, una por recurso, que recorren la API real contra las
simulaciones de sus dependencias: la de **suscripciones** (las 6 operaciones y los errores clave: 401, 403,
404, 409, 422 y 503) y la del **dashboard** (`get_dashboard`: el resumen, `limit`, el orden y los errores 401,
403, 422 y 503; es de solo lectura). **Complementan a pytest, que sigue siendo la puerta de calidad; no lo
sustituyen.** No necesitan cuenta de Postman ni envían nada a servicios externos. Viven en `tests/postman/` y
se ejecutan con [Newman](https://github.com/postmanlabs/newman).

```powershell
npm ci --prefix tests/postman            # instala Newman (una vez)
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml up -d --wait api
npm run e2e --prefix tests/postman       # suscripciones: consola + tests/postman/reports/junit.xml
npm run e2e --prefix tests/postman -- --folder "5. Control de acceso"   # solo una carpeta (las 2 a 4 usan lo que crea la 1)
npm run e2e:dashboard --prefix tests/postman   # dashboard → tests/postman/reports/junit-dashboard.xml
npm run e2e:all --prefix tests/postman         # las dos, una tras otra
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml down -v
```

- **Pila aislada**: el proyecto `maily-system-e2e` tiene su propia base de datos desechable (sin puerto
  publicado), la API en `127.0.0.1:8011` y las simulaciones del API de usuarios (`:8012`) y del de
  clínicas (`:8013`). **No apuntes nunca la colección a un servicio con datos reales**: crea y elimina de
  forma lógica suscripciones, así que quedan filas «Eliminada» (la del dashboard no escribe nada).
- **Resultado**: código de salida `0` si todo pasa y `1` si falla una comprobación o la pila no responde.
- **Si la API cambia**: cada recurso tiene su colección y toda feature que añada, quite o cambie operaciones
  actualiza la de su recurso (y, si es de suscripciones, también la [manual](#colección-manual-de-postman))
  en el mismo cambio. `test_postman_collection.py`, `test_manual_postman_collection.py` y
  `test_dashboard_postman_collection.py` (parte de `uv run pytest`) fallan nombrando las operaciones que
  faltan o sobran, y esta última comprueba además que **las tres colecciones juntas cubren toda la API**.

## Colección manual de Postman

Una colección **nueva e independiente** para probar a mano la API desde la aplicación de escritorio de Postman:
las 6 operaciones de `/api/v1/subscriptions`, la documentación pública y los errores clave (401, 403, 404, 409,
422 y 503), con datos de ejemplo y descripciones en español. **No se ejecuta con Newman ni en integración
continua** (para eso está la anterior), no necesita iniciar sesión en Postman y solo habla con **Auth0** (para
pedir el token) y con **la API que pruebas**. La persona **no pega nunca un token**: un script previo de la
colección lo pide con *client credentials*, lo reutiliza y lo renueva 60 segundos antes de que venza.

Está en `tests/postman/`: `collections/MailySoft-System-Manual.postman_collection.json` y los entornos
`environments/manual-local.postman_environment.json` y `environments/manual-deployed-test.postman_environment.json`.

### Qué necesitas antes (fuera de la colección)

1. **Auth0**: una aplicación *Machine to Machine* autorizada para el *audience* del API de usuarios (el que verifica el
   token). Los tokens de esa aplicación llevan un `sub` terminado en `@clients` (`<client_id>@clients`).
2. **API de usuarios** (`mailySoft-usuarios`): ese `sub` registrado como usuario, con un rol que tenga
   `subscriptions:read`, `subscriptions:write`, `subscriptions:update` y `subscriptions:delete`. El catálogo de ese API
   ya trae los cuatro permisos, pero su `project-definition/bootstrap_admin.sql` solo asocia al *Administrator* los 12
   de usuarios, roles y permisos: **hay que asociar los cuatro a un rol de la aplicación**. Ejemplo (se ejecuta en la
   base de datos del API de usuarios, con `psql -v ON_ERROR_STOP=1 -v app_auth0_id='<client_id>@clients' -v
   app_email=app-manual@clients.local -f -`; es idempotente):

   ```sql
   INSERT INTO users (auth0_id, email, first_name, paternal_last_name)
   VALUES (:'app_auth0_id', lower(:'app_email'), 'Colección', 'Manual')
   ON CONFLICT DO NOTHING;

   INSERT INTO roles (name, description)
   VALUES ('Subscriptions tester', 'Pruebas manuales de la API de suscripciones')
   ON CONFLICT DO NOTHING;

   INSERT INTO role_permissions (role_id, permission_id)
   SELECT r.id, p.id
   FROM roles r
   JOIN permissions p ON p.name IN (
       'subscriptions:read', 'subscriptions:write', 'subscriptions:update', 'subscriptions:delete'
   )
   WHERE r.name = 'Subscriptions tester'
   ON CONFLICT DO NOTHING;

   INSERT INTO user_roles (user_id, role_id)
   SELECT u.id, r.id
   FROM users u
   JOIN roles r ON r.name = 'Subscriptions tester'
   WHERE u.auth0_id = :'app_auth0_id'
   ON CONFLICT DO NOTHING;
   ```

#### Persona sin permisos (opcional)

Solo para los dos casos 403 de la carpeta de errores. Una **segunda aplicación** *Machine to Machine*, autorizada para el
mismo *audience* y registrada en el API de usuarios **sin ningún rol**:

```sql
INSERT INTO users (auth0_id, email, first_name, paternal_last_name)
VALUES (:'plain_auth0_id', lower(:'plain_email'), 'Colección', 'SinPermisos')
ON CONFLICT DO NOTHING;
```

Su identificador y su secreto van en `plainClientId` y `plainClientSecret`. Sin ella, esas dos peticiones se omiten, lo
explican en la Consola y **no cuentan como fallo**.

### Base de datos dedicada a las pruebas manuales

La colección crea y elimina (de forma lógica) suscripciones, así que la API que pruebes en local debe usar una base de
datos **dedicada a pruebas**: no la de desarrollo (`maily_system`) ni la de pytest (`maily_system_test`, que pytest borra
y recrea). Se crea una vez y se migra; Alembic y uvicorn leen `DATABASE_URL` del entorno antes que del `.env`:

```powershell
docker compose exec db psql -U postgres -c "CREATE DATABASE maily_system_manual"
$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5434/maily_system_manual"
uv run alembic upgrade head
uv run uvicorn src.main:app --port 8010      # en esta misma terminal
```

No uses `docker compose up api` para esto: esa API usa `maily_system`. (El script de `docker/postgres/init/` solo corre al
crear el volumen, por eso la base se crea a mano.)

### Levantar lo necesario en local

- **La API** en `http://127.0.0.1:8010` (arriba), con `USERS_API_BASE_URL` (por defecto `http://localhost:8000`, el API de
  usuarios real) y `CLINICS_API_BASE_URL` (`http://localhost:8001`) en su `.env`.
- **La simulación de clínicas** (opcional, solo local), en el puerto 8001 que ya usa el `.env`:

  ```powershell
  uv run uvicorn app:app --app-dir tests/stubs/clinics_api --port 8001
  ```

  Sin ella ni API de clínicas, `clinics_count` sale `null` y eliminar responde 503: es lo esperado.

### Importar y enviar la primera petición

1. En Postman, *Import* → la colección y el entorno `manual-local`. No hace falta iniciar sesión.
2. Elige el entorno «MailySoft System API - Manual - local (solo bases de datos de pruebas)».
3. En el entorno rellena `auth0Domain` (sin `https://`), `auth0Audience` (idéntico al identificador del API de usuarios, con
   su barra final si la tiene), `auth0ClientId` y `auth0ClientSecret`. **El secreto va solo en tu copia local de la
   variable**, nunca en un valor que se sincronice ni en los archivos.
4. Envía `0. Empezar → list_subscriptions: comprobar el acceso y ver el catálogo`: responde 200 sin que pegues ningún token.

Después recorre `1. Ciclo de vida…` (en orden), `2. Casos de error` y, si levantaste la simulación, `3. Simulación de
clínicas (solo local)`. Las peticiones que modifican o eliminan **solo actúan sobre lo que crea la propia colección**: antes
de enviarlas comprueba que la suscripción guardada sigue existiendo y se llama como ella la creó.

### Entorno desplegado de pruebas

Importa `manual-deployed-test` y rellena `baseUrl` (la dirección de la API desplegada) y los valores de acceso. **No se edita
ninguna petición.** Al cambiar de entorno la colección pide un token nuevo y descarta los identificadores guardados. La carpeta
3 no funciona allí (no hay simulación) y se omite sola. Ese entorno **debe apuntar a una base de datos de pruebas dedicada**.

### Si no pasa nada al pulsar «Enviar»

La petición **no se envió** y el motivo está en la **Consola de Postman** (*Ver → Mostrar Consola de Postman*) y en la variable
de colección `accessProblem`. Nunca sale una petición que exige token sin token.

| Mensaje (resumen) | Qué hacer |
|---|---|
| A-01 «faltan valores en el entorno activo (…)» | Rellena en el entorno las variables que nombra; el secreto, en tu copia local |
| A-02 «auth0Domain debe ir sin https://» | Escribe solo el dominio (`mi-tenant.us.auth0.com`) |
| A-03 «Auth0 no respondió» | Revisa `auth0Domain` y tu conexión |
| A-04 «Auth0 rechazó las credenciales» | Revisa `auth0ClientId` y `auth0ClientSecret` |
| A-05 «Auth0 no autoriza a la aplicación para el destinatario» | `auth0Audience` debe ser idéntico al identificador de la API de usuarios, y la aplicación debe estar autorizada para esa API en Auth0 |
| A-06 «Auth0 limitó las solicitudes» | Espera un minuto |
| A-07 «Auth0 respondió algo inesperado» | Revisa `auth0Domain` y `auth0Audience` |
| A-08 «(opcional) configura plainClientId y plainClientSecret» | Ver «Persona sin permisos»; si no la necesitas, ignóralo |
| A-09 «la variable … no tiene valor» | Envía antes la petición que crea la suscripción de prueba (la Consola dice cuál), o rellena la variable del entorno |
| A-10 «la suscripción … ya no existe en este entorno» | Crea otra con la petición que indica |
| A-11 «no se pudo comprobar la suscripción» | La persona de acceso necesita `subscriptions:read`, o la API no respondió |
| A-12 «no hay un nombre guardado» | Envía la petición que crea la suscripción de prueba |
| A-13 «ya no es la que creó la colección» | Otra persona reutilizó ese identificador (p. ej. tras reiniciar la base de pruebas): crea otra suscripción |

- **Todas las respuestas son 403**: la aplicación no está registrada en el API de usuarios o su rol no tiene los cuatro
  permisos de suscripciones (ver «Qué necesitas antes»).
- **Todo responde 503 con `authorization_unavailable`**: el API de usuarios no responde.

### Advertencias

- **Solo bases de datos de pruebas**, nunca datos reales. El borrado es lógico: cada recorrido deja filas «Eliminada».
- **El secreto va solo en tu copia local.** Los archivos de la colección y de los entornos no contienen secretos ni tokens, y
  `test_manual_postman_collection.py` lo comprueba por estructura.
- La Consola de Postman registra la petición a Auth0, cuerpo incluido. Es local, pero **no compartas capturas de ella**.

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
├── integrations/      # clientes del API de usuarios y del de clínicas, y el puerto de datos del dashboard
│                      # (`dashboard_source.py`) con su fuente ficticia de la Fase 1
├── dtos/              # esquemas de entrada y salida (Pydantic)
├── database/          # engine y sesiones async
└── models/            # modelos SQLAlchemy (sin lógica de negocio)
alembic/versions/      # 0001 esquema, 0002 catálogo de estatus
tests/unit/            # sin base de datos (DTOs, Services, seguridad, configuración, capas)
tests/integration/     # PostgreSQL real (esquema, migraciones y Repositories)
tests/contract/        # la API por HTTP, el documento OpenAPI, la cobertura de permisos y las tres colecciones de Postman
                       # (postman_support.py: apoyo compartido; conftest.py: fixtures del dashboard, sin base de datos)
tests/dashboard_support.py   # fuente de datos doble y ayudas de las pruebas del dashboard
tests/stubs/           # simulaciones del API de usuarios y del API de clínicas
tests/postman/         # colecciones (suscripciones y dashboard), entornos y pila aislada de las pruebas de
                       # punta a punta (Newman) y colección y entornos de la colección manual
project-definition/    # esquema de datos objetivo (DATA_SCHEMA.md)
specs/                 # especificaciones de Spec Kit
.specify/memory/constitution.md   # reglas del proyecto (capas, async, pruebas, migraciones, acceso)
```
