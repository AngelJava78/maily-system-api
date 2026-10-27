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

### Salud de servicios

Spec [`005-health-monitoring`](specs/005-health-monitoring/spec.md): cuatro rutas **públicas** (el contrato de
salud v1 de MailySoft y el estado público), la consulta agregada de salud de toda la plataforma y el **registro
de componentes monitoreados**, que se administra sin redesplegar (contrato en
[`openapi-health.yaml`](specs/005-health-monitoring/contracts/openapi-health.yaml)).

| Operación | Método y ruta | Permiso |
|---|---|---|
| `get_health_live` | `GET /health/live` | pública |
| `get_health_ready` | `GET /health/ready` | pública |
| `get_info` | `GET /info` | pública |
| `get_health_status` | `GET /health/status` | pública |
| `get_health` | `GET /api/v1/health` | `health:read` |
| `list_monitored_components` | `GET /api/v1/monitored-components` | `health:read` |
| `get_monitored_component` | `GET /api/v1/monitored-components/{id}` | `health:read` |
| `create_monitored_component` | `POST /api/v1/monitored-components` | `health:write` |
| `update_monitored_component` | `PATCH /api/v1/monitored-components/{id}` | `health:update` |
| `delete_monitored_component` | `DELETE /api/v1/monitored-components/{id}` | `health:delete` |

- **Contrato de salud v1** (`/health/live`, `/health/ready`, `/info`): están en la raíz, sin token y con
  `Cache-Control: no-store`; cumplen el contrato que comparten los servicios de MailySoft.
  `/health/live` responde 200 mientras el proceso atienda HTTP, sin consultar nada más. `/health/ready`
  consulta **solo** la base de datos, con `HEALTH_READY_TIMEOUT_SECONDS`: 200 si responde y 503 si no, con el
  mismo cuerpo (`status` y `checks`). `/info` identifica el build: servicio, versión (la del documento OpenAPI),
  commit, fecha de build y entorno.
- **Consulta agregada** (`GET /api/v1/health`): una sola respuesta con el estado global y el de cada
  componente, primero los dos integrados (`maily-system-api` y `database`) y después los registrados y
  habilitados, por `sort_order` y `code`. Concedido el acceso responde **siempre 200**: un componente caído se
  informa en su elemento, nunca como error de la consulta. El estado global es `down` si alguno está caído,
  `degraded` si alguno está degradado, detenido o desconocido, y `ok` si no. Todas las consultas comparten una
  sola agregación y su resultado durante `HEALTH_CACHE_SECONDS`. Nunca trae direcciones ni cuerpos de otros
  servicios.
- **Estado público** (`GET /health/status`): pensado para quien no puede comprobar su acceso (por ejemplo, el
  Backoffice de noche). Sale del **mismo resultado y de la misma caché** que la consulta agregada, pero solo
  publica el estado global, cuándo se comprobó y, de cada componente, `code`, `name`, `kind`, `status` y
  `next_start_at`: nunca versiones, direcciones, latencias, chequeos ni códigos de error. No autoriza la
  petición (ignora la cabecera `Authorization`), responde 200 aunque todo esté caído y reutiliza el último
  resultado al menos `max(HEALTH_CACHE_SECONDS, 15)` segundos, así que por muchas peticiones que reciba no
  provoca más de una ronda de chequeos por periodo.
  **No es una *probe*: no lo uses para *liveness* ni para *readiness*** (responde 200 con todo caído y puede
  provocar chequeos de todos los componentes). Para eso están `/health/live` y `/health/ready`.
- **Registro sin redesplegar**: servicios que cumplen el contrato v1 (`service`: sus tres rutas) y frontends (su
  ruta de salud). El `code` es único entre los no eliminados (`maily-system-api` y `database` están
  reservados), la baja es lógica y se libera el código. Las respuestas del registro son el **único** lugar de la
  API donde se ve la `base_url`. El permiso se comprueba antes que los datos.
- **Lista permitida** (`HEALTH_ALLOWED_HOSTS`): como este servicio llama a las direcciones registradas, solo
  admite hosts de una lista que fija quien lo opera; sin lista no se puede registrar ninguno. Las llamadas
  nunca llevan el token ni cookies, no siguen redirecciones y leen a lo más 64 KiB. **Conviene listar hosts
  exactos**: un sufijo de una plataforma compartida, como `.up.railway.app`, admitiría aplicaciones de
  terceros.
- **Base de datos detenida por horario**: con las cuatro `DATABASE_SCHEDULE_*` (valores del runbook
  `Deploy-PgAutoShutdown.ps1`: `America/Mexico_City`, de lunes a viernes, de 08:00 a 20:00), una base que no
  responde **fuera** de su horario se informa como `stopped` con su próximo encendido (`next_start_at`, en
  UTC), no como caída; dentro del horario, o sin horario, es `down`. `/health/ready` no tiene en cuenta el
  horario: sin base de datos el servicio no puede atender.
- **Tiempos**: `HEALTH_READY_TIMEOUT_SECONDS` (2 s) es menor que `HEALTH_CHECK_TIMEOUT_SECONDS` (3 s), el de cada
  llamada a un componente, y la *probe* de *readiness* del orquestador debe tener un tiempo mayor que el de
  `/health/ready`.
- **Si el registro no se puede leer**, la consulta usa la última copia que leyó (en memoria) con
  `registry_available: false`; sin copia, solo trae los dos integrados.

**Identificar el build**: `/info` publica `APP_COMMIT_SHA` y `APP_BUILD_DATE`, que se pasan al **construir** la
imagen (sin ellos valen `unknown`), y `APP_ENVIRONMENT`, que se inyecta al desplegar:

```powershell
docker build -t maily-system-api `
  --build-arg APP_COMMIT_SHA=$(git rev-parse HEAD) `
  --build-arg APP_BUILD_DATE=$((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")) .
```

Con Docker Compose basta con definir `APP_COMMIT_SHA` y `APP_BUILD_DATE` en el entorno al construir.

**Probes de Kubernetes** (ejemplo; la imagen arranca por defecto con `alembic upgrade head`, así que el
contenedor de la API fija el comando de uvicorn):

```yaml
livenessProbe:            # el proceso atiende; no depende de la base de datos
  httpGet: { path: /health/live, port: 8000 }
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
readinessProbe:           # falla mientras la base de datos está detenida: deja de recibir tráfico
  httpGet: { path: /health/ready, port: 8000 }
  periodSeconds: 10
  timeoutSeconds: 3       # mayor que HEALTH_READY_TIMEOUT_SECONDS (2 s)
  failureThreshold: 3
startupProbe:             # arranque rápido; umbral amplio
  httpGet: { path: /health/live, port: 8000 }
  periodSeconds: 5
  failureThreshold: 30
```

*Readiness* falla mientras la base de datos está detenida (lo esperado: el orquestador deja de enviarle
tráfico) y *liveness* no (no se reinicia el contenedor).

> **Permisos**: los cuatro `health:*` los administra el API de usuarios. Mientras no existan allí (con su
> módulo «Salud de servicios»), las seis operaciones protegidas responden 403 en ambientes reales.

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
| `HEALTH_CHECK_TIMEOUT_SECONDS` | no | `3` | Tiempo máximo de cada llamada a un componente monitoreado (entero de 1 a 10) |
| `HEALTH_CACHE_SECONDS` | no | `15` | Segundos que se reutiliza el resultado de salud entre consultas (entero de 0 a 300); `/health/status` lo reutiliza al menos 15 |
| `HEALTH_READY_TIMEOUT_SECONDS` | no | `2` | Tiempo máximo de `/health/ready` (entero de 1 a 10); conviene que sea menor que el de los chequeos |
| `HEALTH_ALLOWED_HOSTS` | no | vacía | Hosts a los que puede llamar la salud, separados por comas (exactos, o con punto inicial para un sufijo); vacía = no se puede registrar ningún componente |
| `DATABASE_SCHEDULE_TIMEZONE` | no | — | Zona IANA del horario de la base de datos (`America/Mexico_City`). Las cuatro `DATABASE_SCHEDULE_*` van juntas o ninguna |
| `DATABASE_SCHEDULE_DAYS` | no | — | Días de encendido en inglés, separados por comas (`Monday,Tuesday,Wednesday,Thursday,Friday`) |
| `DATABASE_SCHEDULE_START` | no | — | Hora de encendido, `HH:MM` de 24 horas (`08:00`) |
| `DATABASE_SCHEDULE_END` | no | — | Hora de apagado, `HH:MM` de 24 horas y posterior al inicio (`20:00`) |
| `APP_COMMIT_SHA` | no | `unknown` | Commit del build que publica `/info` (7 a 64 hexadecimales); se pasa al construir la imagen |
| `APP_BUILD_DATE` | no | `unknown` | Fecha del build que publica `/info` (ISO 8601 con zona); se pasa al construir la imagen |
| `APP_ENVIRONMENT` | no | `unknown` | Entorno del despliegue que publica `/info` (1 a 50 letras, dígitos, `.`, `_` o `-`) |

El arranque valida la configuración (también `DATABASE_URL`) y, si falta una variable obligatoria o una
opcional no es válida, se niega a iniciar y nombra la variable (nunca su valor); un horario de la base de
datos incompleto o con un valor no válido también impide arrancar.

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

**Tipo de suscripción, una sola vez por entorno** (spec 006): después de `migrate`, toda suscripción
que ya existiera queda con el tipo `individual` (lo asigna la propia migración `0005`). Para que las
que ya tenían más de una clínica queden como `enterprise`, ejecuta a mano, una vez por entorno (no es
parte del arranque normal ni bloquea `api`):

```powershell
docker compose run --rm -e BACKFILL_ACCESS_TOKEN=<token-con-permiso-para-leer-conteos> backfill-subscription-types
```

El token necesita el mismo permiso que ya exige el API de clínicas para leer conteos (no hay
credencial de servicio nueva). Reintenta sin límite si esa API no responde: nunca adivina un tipo.

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
todo el esquema (equivale a las migraciones `0001` a `0005`), carga los 4 estatus y registra la versión
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

Las de salud usan PostgreSQL real y la simulación de componentes (`tests/stubs/components/`), con un reloj
controlable para el horario de la base de datos.

Guías de validación con el mapa historia → pruebas:
[`specs/001-subscriptions-api/quickstart.md`](specs/001-subscriptions-api/quickstart.md) (suscripciones),
[`specs/003-platform-dashboard/quickstart.md`](specs/003-platform-dashboard/quickstart.md) (dashboard) y
[`specs/005-health-monitoring/quickstart.md`](specs/005-health-monitoring/quickstart.md) (salud).

## Pruebas de punta a punta (Postman)

Hay **tres colecciones automáticas** para Newman, una por recurso, que recorren la API real contra las
simulaciones de sus dependencias: la de **suscripciones** (las 6 operaciones y los errores clave: 401, 403,
404, 409, 422 y 503), la del **dashboard** (`get_dashboard`: el resumen, `limit`, el orden y los errores 401,
403, 422 y 503; es de solo lectura) y la de **salud** (las 10 operaciones de salud: el contrato público, el
registro de componentes, componentes caídos y los errores 401, 403, 404, 409, 422 y 503). **Complementan a
pytest, que sigue siendo la puerta de calidad; no lo sustituyen.** No necesitan cuenta de Postman ni envían nada a servicios externos. Viven en `tests/postman/` y
se ejecutan con [Newman](https://github.com/postmanlabs/newman).

```powershell
npm ci --prefix tests/postman            # instala Newman (una vez)
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml up -d --build --wait api
npm run e2e --prefix tests/postman       # suscripciones: consola + tests/postman/reports/junit.xml
npm run e2e --prefix tests/postman -- --folder "5. Control de acceso"   # solo una carpeta (las 2 a 4 usan lo que crea la 1)
npm run e2e:dashboard --prefix tests/postman   # dashboard → tests/postman/reports/junit-dashboard.xml
npm run e2e:health --prefix tests/postman      # salud → tests/postman/reports/junit-health.xml
npm run e2e:all --prefix tests/postman         # las tres, una tras otra
docker compose -p maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml down -v
```

- **Pila aislada**: el proyecto `maily-system-e2e` tiene su propia base de datos desechable (sin puerto
  publicado), la API en `127.0.0.1:8011` y las simulaciones del API de usuarios (`:8012`), del de
  clínicas (`:8013`) y de los componentes monitoreados (`:8014`). Usa `--build` para que la imagen lleve el
  código actual (sin él, Compose reutiliza la de una ejecución anterior). **No apuntes nunca la colección a un
  servicio con datos reales**: la de suscripciones crea y elimina de forma lógica suscripciones, así que
  quedan filas «Eliminada», y la de salud crea, modifica y elimina componentes del registro (la del dashboard
  no escribe nada).
- **Resultado**: código de salida `0` si todo pasa y `1` si falla una comprobación o la pila no responde.
- **Si la API cambia**: cada recurso tiene su colección y toda feature que añada, quite o cambie operaciones
  actualiza la de su recurso (y, si es de suscripciones, también la [manual](#colección-manual-de-postman))
  en el mismo cambio. `test_postman_collection.py`, `test_manual_postman_collection.py`,
  `test_dashboard_postman_collection.py` y `test_health_postman_collection.py` (parte de `uv run pytest`)
  fallan nombrando las operaciones que faltan o sobran, y la del dashboard comprueba además que **las cuatro
  colecciones juntas cubren toda la API**.

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
├── services/          # reglas de negocio y autorización; la salud (`health_service.py`, `health_schedule.py`,
│                      # `health_state.py`) y el registro de componentes (`monitored_component_service.py`)
├── repositories/      # acceso a datos (únicas consultas SQL)
├── integrations/      # clientes del API de usuarios y del de clínicas, y el puerto de datos del dashboard
│                      # (`dashboard_source.py`) con su fuente ficticia de la Fase 1; y el cliente de los
│                      # chequeos de salud (`health_probe.py`) con el contrato v1 (`health_contract.py`)
├── dtos/              # esquemas de entrada y salida (Pydantic)
├── database/          # engine y sesiones async
├── models/            # modelos SQLAlchemy (sin lógica de negocio)
└── scripts/           # pasos de despliegue de un solo uso (p. ej. backfill_subscription_types.py);
                       # no son rutas de la API ni los ejecuta Alembic
alembic/versions/      # 0001 esquema, 0002 catálogo de estatus, 0003 corrección de suscripciones,
                       # 0004 registro de componentes, 0005 tipo de suscripción
tests/unit/            # sin base de datos (DTOs, Services, seguridad, configuración, capas)
tests/integration/     # PostgreSQL real (esquema, migraciones y Repositories)
tests/contract/        # la API por HTTP, el documento OpenAPI, la cobertura de permisos y las colecciones de Postman
                       # (postman_support.py: apoyo compartido; conftest.py: fixtures del dashboard, sin base de datos)
tests/dashboard_support.py   # fuente de datos doble y ayudas de las pruebas del dashboard
tests/health_support.py     # reloj, transporte con fallas y ayudas de las pruebas de salud
tests/stubs/           # simulaciones del API de usuarios, del API de clínicas y de los componentes monitoreados
tests/postman/         # colecciones (suscripciones, dashboard y salud), entornos y pila aislada de las pruebas de
                       # punta a punta (Newman) y colección y entornos de la colección manual
project-definition/    # esquema de datos objetivo (DATA_SCHEMA.md)
specs/                 # especificaciones de Spec Kit
.specify/memory/constitution.md   # reglas del proyecto (capas, async, pruebas, migraciones, acceso)
```
