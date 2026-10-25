# Feature Specification: Monitoreo de salud de los servicios de Maily

**Feature Branch**: `005-health-monitoring`

**Created**: 2026-10-24

**Status**: Draft

**Input**: User description: "Monitorear desde la MailySoft System API la salud de los servicios de Maily
(mailySoft-usuarios, mailySoft-pacientes y este mismo servicio), de la base de datos PostgreSQL de Azure que
comparten y del frontend de usuarios (MailySoft, servido por Maily360), y prepararse para agregar
microservicios futuros sin redesplegar. Este servicio debe cumplir el contrato de salud de Maily v1
(`/health/live`, `/health/ready` con la base de datos e `/info` con versión, commit y fecha de build, públicos
y fuera de `/api/v1`); ofrecer un agregador `GET /api/v1/health` (permiso `health:read`, siempre 200) con el
estado de cada componente y el estado global; mantener un registro dinámico de componentes
(`/api/v1/monitored-components`, permisos `health:read`, `health:write`, `health:update` y `health:delete`,
con protecciones contra SSRF); mostrar la base de datos como «detenida por horario», y no como caída, cuando
falla fuera del horario de encendido del runbook de Azure Automation; y seguir respondiendo con la última
copia del registro cuando la base de datos no esté disponible. Es una de cuatro specs coordinadas
(mailySoft-usuarios 016, mailySoft-pacientes 008 y maily-backoffice 016)."

## User Scenarios & Testing *(mandatory)*

Hay cuatro actores:

- **Quien administra la plataforma de Maily** (personal de MailySoft, desde la página «Salud de servicios»
  del Backoffice, spec 016-health-dashboard de maily-backoffice): consulta la salud y administra el registro
  de componentes. Se identifica con un token de acceso y solo puede hacer lo que le autorizan sus permisos
  `health:*`, que decide el API de usuarios (mailySoft-usuarios), no este servicio.
- **Quien no puede comprobar su acceso** (cualquier persona que abre el Backoffice cuando este no puede
  comprobar su acceso —por ejemplo, de noche, con la base de datos detenida—; como la ruta es pública,
  también cualquiera que alcance el servicio): consulta sin token el estado público de la plataforma para
  saber, por ejemplo, que la base de datos está detenida por horario y cuándo vuelve, sin ver versiones,
  direcciones ni detalles técnicos.
- **La infraestructura** (Kubernetes, Docker y el propio agregador): consulta sin token las rutas del
  contrato de salud de Maily v1 para saber si un servicio está vivo, si puede atender y qué build corre.
- **Quien opera el servicio**: fija con variables de entorno a qué hosts se puede llamar, los tiempos
  máximos, la caché y el horario de encendido de la base de datos.

Un **componente** es cada cosa cuya salud se informa: un servicio (`service`), la base de datos (`database`)
o un frontend (`frontend`). Dos son **integrados** y siempre aparecen —este servicio y la base de datos—; los
demás son **registrados** desde el Backoffice. Una **agregación** es la ronda de chequeos que produce el
resultado de salud, y el **estado público** (`/health/status`) es una vista mínima de ese mismo resultado,
sin token.

### User Story 1 - Ver en una sola consulta la salud de todos los componentes (Priority: P1)

Quien tiene el permiso `health:read` consulta `GET /api/v1/health` y recibe, en una sola respuesta, el estado
global de la plataforma y el de cada componente: este servicio, la base de datos y los servicios y frontends
registrados y habilitados. De cada componente obtiene su estado, su latencia, cuándo se comprobó, su versión,
su commit, su fecha de build, su entorno, el detalle de sus chequeos, un código de error si algo falla y, si
es la base de datos detenida por horario, cuándo vuelve a encenderse. Una vez concedido el acceso, la
respuesta es siempre 200: un componente caído se informa en su propio elemento, no como un error de la
consulta. La respuesta nunca trae direcciones, cuerpos crudos de otros servicios ni secretos.

**Why this priority**: Es la razón de ser de la feature: sin esta consulta, la página «Salud de servicios» del
Backoffice no tiene qué mostrar.

**Independent Test**: Con la simulación del API de usuarios concediendo `health:read` y dos servicios simulados
registrados (uno sano y otro que no responde), consultar la salud y comprobar el 200, el estado global `down`,
los dos integrados primero y después los registrados en su orden, todos los campos de cada componente y que
ninguno trae direcciones ni cuerpos crudos; repetir sin token, sin el permiso y con el API de usuarios caído y
comprobar 401, 403 y 503 sin ningún dato.

**Acceptance Scenarios**:

1. **Given** una persona con `health:read` y todos los componentes sanos, **When** consulta la salud,
   **Then** recibe 200 con `status` `ok`, `registry_available` `true`, `checked_at` en UTC y un elemento por
   componente, todos `up`: primero `maily-system-api` y `database`, y después los registrados habilitados por
   `sort_order` y `code`.
2. **Given** un servicio registrado cuyo `/health/live` responde bien pero cuyo `/health/ready` responde 503,
   **When** se consulta la salud, **Then** ese componente está `degraded` con el error `not_ready` y los
   chequeos que reportó, y el estado global es `degraded`.
3. **Given** un servicio registrado que no responde dentro del tiempo máximo, **When** se consulta la salud,
   **Then** ese componente está `down` con el error `timeout`, el estado global es `down` y la respuesta sigue
   siendo 200.
4. **Given** un servicio sano cuyo `/info` falla, **When** se consulta la salud, **Then** sigue `up` y su
   versión, su commit, su fecha de build y su entorno valen `unknown`.
5. **Given** un frontend registrado, **When** su ruta de salud responde 2xx, **Then** está `up`; **When**
   responde cualquier otro código, **Then** está `down` con `unexpected_status`.
6. **Given** la respuesta, **When** se revisa cada componente, **Then** trae `code`, `name`, `kind`, `status`,
   `latency_ms`, `checked_at`, `version`, `commit`, `build_date`, `environment`, `checks`, `error` y
   `next_start_at`, y ninguno trae la dirección del componente, el cuerpo de sus respuestas ni mensajes de
   excepción.
7. **Given** una petición sin token, con un token rechazado o vencido, de una persona sin `health:read`
   (aunque tenga otros permisos, como `dashboard:read`) o con el API de usuarios caído, **When** se consulta la
   salud, **Then** se rechaza con 401, 401, 403 o 503 respectivamente, sin ningún dato y sin consultar ningún
   componente.
8. **Given** una consulta que responde 200, **When** se examinan sus cabeceras, **Then** indican que no debe
   guardarse en caché (`Cache-Control: no-store`).

---

### User Story 2 - Este servicio cumple el contrato de salud v1 y aparece como componente integrado (Priority: P1)

La infraestructura consulta sin token tres rutas en la raíz del servicio: `/health/live` (el proceso está
vivo), `/health/ready` (puede atender: la base de datos responde) e `/info` (qué build corre: `service` =
`maily-system-api`, versión, commit, fecha de build y entorno). La versión sale de una sola fuente: hoy el
servicio tiene dos que no coinciden (`VERSION = "2.0.0"` en `src/main.py` y `0.1.0` en `pyproject.toml`).
Además, en la consulta agregada este servicio aparece como el componente integrado `maily-system-api`,
calculado por dentro, sin llamarse a sí mismo por HTTP.

**Why this priority**: Los orquestadores necesitan estas rutas para decidir si reinician el contenedor o le
envían tráfico, y es la parte del contrato que el agregador espera de todos los servicios; sin una sola
fuente, la versión que se ve en el panel no sería confiable.

**Independent Test**: Sin token, consultar las tres rutas con la base de datos disponible y sin ella, y
comprobar códigos, cuerpos y `Cache-Control: no-store`; comprobar que `/health/live` responde en menos de
100 ms aunque la base no responda, que la versión de `/info` es la del documento OpenAPI, que sin las
variables de build devuelve `unknown` y arranca igual, y que la consulta agregada muestra `maily-system-api`
sin ninguna petición HTTP del servicio a sí mismo.

**Acceptance Scenarios**:

1. **Given** el servicio en marcha, incluso con la base de datos caída, **When** se consulta `/health/live`
   sin token, **Then** responde 200 `{"status":"ok"}` en menos de 100 ms, sin consultar ninguna dependencia.
2. **Given** la base de datos responde, **When** se consulta `/health/ready`, **Then** responde 200 con
   `status` `ok` y el chequeo `database` en `ok`, con su latencia.
3. **Given** la base de datos no responde dentro de `HEALTH_READY_TIMEOUT_SECONDS`, **When** se consulta
   `/health/ready`, **Then** responde 503 con `status` `unavailable` y el chequeo `database` en `error` con
   `timeout` (o `connection_error` si rechazó la conexión), sin nombres de host, cadenas de conexión ni
   mensajes de excepción.
4. **Given** el API de usuarios o el de clínicas no responden, **When** se consulta `/health/ready`,
   **Then** el resultado no cambia por eso: solo se comprueba la base de datos.
5. **Given** una imagen construida con `APP_COMMIT_SHA` y `APP_BUILD_DATE` y desplegada con
   `APP_ENVIRONMENT`, **When** se consulta `/info`, **Then** responde 200 con `service` `maily-system-api`, la
   versión del documento OpenAPI, ese commit, esa fecha en UTC y ese entorno.
6. **Given** que no se configuró ninguna de esas tres variables, **When** el servicio arranca y se consulta
   `/info`, **Then** arranca igual y `commit`, `build_date` y `environment` valen `unknown`.
7. **Given** la documentación publicada, **When** se revisan las tres rutas, **Then** aparecen con la
   etiqueta «Salud», sin seguridad ni permiso, y todas las demás operaciones, salvo el estado público
   `/health/status` (historia 6), siguen exigiendo token.
8. **Given** una consulta agregada, **When** se revisa el componente `maily-system-api`, **Then** trae los
   mismos datos de build que `/info` y está `up` si la base de datos responde o `degraded` con `not_ready` si
   no, sin que el servicio se haya hecho una petición HTTP a sí mismo.

---

### User Story 3 - Registrar componentes sin redesplegar (Priority: P2)

Quien tiene los permisos `health:*` administra el registro de componentes desde el Backoffice: da de alta
servicios y frontends (`health:write`), los consulta (`health:read`), los modifica, habilita o deshabilita
(`health:update`) y los da de baja (`health:delete`, baja lógica). El registro empieza vacío: después del
despliegue se registran mailySoft-usuarios, mailySoft-pacientes y MailySoft y, más adelante, cualquier
microservicio nuevo que cumpla el contrato v1, sin redesplegar este servicio. Como este servicio llamará a
las direcciones registradas, solo admite hosts de una lista permitida que fija quien lo opera, nunca reenvía
el token de la persona y nunca devuelve tal cual lo que esas direcciones responden.

**Why this priority**: Sin registro solo se ven los dos componentes integrados. Es lo que permite monitorear
los demás servicios y el frontend, y crecer sin desplegar; depende de la consulta de salud (P1) para tener
efecto visible.

**Independent Test**: Con `HEALTH_ALLOWED_HOSTS` configurada, registrar un servicio simulado, consultar la
salud y verlo; modificarlo, deshabilitarlo y eliminarlo, y comprobar cada efecto en la siguiente consulta;
volver a registrar el mismo código; y comprobar 409 (código repetido o reservado), 422 (host no permitido,
credenciales, query, fragmento, otro esquema, ruta que cambia de host, campo no reconocido), 404 (inexistente
o eliminado) y 401, 403 y 503.

**Acceptance Scenarios**:

1. **Given** una persona con `health:write` y un host permitido, **When** registra un servicio con `code`,
   `name`, `kind` y `base_url`, **Then** recibe 201 con el componente (identificador UUID, rutas por defecto
   del contrato v1, habilitado, `sort_order` 0 y sus fechas), y aparece en la siguiente consulta de salud.
2. **Given** ya existe un componente vigente con ese `code`, o el `code` es `maily-system-api` o `database`,
   **When** se intenta registrar, **Then** se rechaza con 409 y no se crea nada.
3. **Given** una `base_url` cuyo host no está en la lista permitida, o con usuario o contraseña, query,
   fragmento o un esquema distinto de `http` y `https`, **When** se registra o se modifica, **Then** se
   rechaza con 422 en `base_url`, con un mensaje en español que no repite la dirección ni revela la lista.
4. **Given** una ruta que no empieza con una sola `/`, o que contiene `..`, `\`, `?` o `#`, **When** se
   envía, **Then** se rechaza con 422 en ese campo.
5. **Given** un frontend, **When** se registra con su ruta de salud y sin ruta de disponibilidad, **Then** se
   acepta; **When** trae ruta de disponibilidad, **Then** se rechaza con 422.
6. **Given** un componente registrado, **When** se deshabilita, **Then** deja de consultarse y de aparecer en
   la consulta de salud, y sigue en el registro como deshabilitado; **When** se vuelve a habilitar, **Then**
   reaparece en la siguiente consulta.
7. **Given** un componente registrado, **When** se elimina, **Then** responde 204, desaparece del registro y
   de la consulta de salud, consultarlo después responde 404, y su `code` puede registrarse de nuevo como un
   componente distinto (con otro identificador).
8. **Given** un identificador inexistente o eliminado, **When** se consulta, se modifica o se elimina,
   **Then** responde 404.
9. **Given** una solicitud con un campo no reconocido o una modificación sin ningún dato, **When** se envía,
   **Then** se rechaza con 422 y no cambia nada.
10. **Given** una persona sin el permiso de la operación (por ejemplo, solo `health:read` al registrar),
    **When** la invoca con datos además inválidos, **Then** se rechaza con 403 —el permiso se comprueba
    antes de validar— y no cambia nada.
11. **Given** cualquier componente registrado, **When** se consulta la salud, **Then** las llamadas a ese
    componente no llevan el token de la persona ni ninguna cabecera de la petición original.
12. **Given** varios componentes, **When** se lista el registro, **Then** llegan todos los no eliminados,
    habilitados y deshabilitados, sin paginar y ordenados por `sort_order` y `code`.

---

### User Story 4 - La base de datos detenida por horario no se reporta como caída (Priority: P2)

El servidor de PostgreSQL de Azure se apaga a propósito fuera de horario con los runbooks de Azure
Automation de este repositorio (`Deploy-PgAutoShutdown.ps1` y `Set-PgFlexServerState.ps1`; por defecto, se
enciende de lunes a viernes de 08:00 a 20:00, America/Mexico_City). Quien opera el servicio configura las
variables `DATABASE_SCHEDULE_*` con los mismos valores del runbook y, entonces, una falla de la base de datos
fuera de ese horario se informa como «detenida por horario» (`stopped`), y no como caída (`down`), junto con
su próximo encendido programado (`next_start_at`). Dentro del horario, o si no se configuró ningún horario,
una falla es `down`.

**Why this priority**: Sin esto, la plataforma se vería caída casi dos tercios de la semana (las noches y los
fines de semana), y las caídas reales se perderían entre falsas alarmas.

**Independent Test**: Con el horario por defecto configurado y un reloj controlable, simular que la base no
responde un martes a las 21:00, un sábado a las 10:00 y un martes a las 10:00 (hora de la Ciudad de México) y
comprobar `stopped` con el próximo encendido el miércoles a las 08:00, `stopped` con el próximo encendido el
lunes a las 08:00 y `down` sin próximo encendido; simular que responde un domingo y comprobar `up`; quitar el
horario y comprobar `down`; arrancar con un horario incompleto o inválido y comprobar que no arranca.

**Acceptance Scenarios**:

1. **Given** el horario de lunes a viernes de 08:00 a 20:00 en America/Mexico_City, **When** la base de datos
   no responde un martes a las 21:00 de esa zona, **Then** el componente `database` está `stopped` y, por su
   causa, el estado global no pasa de `degraded`.
2. **Given** el mismo horario, **When** la base no responde un martes a las 10:00, **Then** está `down` y el
   estado global es `down`.
3. **Given** el mismo horario, **When** la base responde un domingo (alguien la encendió a mano), **Then**
   está `up`.
4. **Given** que no se configuró ningún horario, **When** la base no responde, **Then** está `down`, a
   cualquier hora.
5. **Given** un viernes a las 19:30 en la Ciudad de México (sábado 01:30 en UTC), **When** la base no
   responde, **Then** está `down`: el día y la hora se evalúan en la zona configurada, no en UTC.
6. **Given** el horario de 08:00 a 20:00, **When** la falla se observa a las 20:00 en punto, **Then** está
   `stopped`; **When** se observa a las 08:00 en punto, **Then** está `down`.
7. **Given** la base `stopped`, **When** se revisa la respuesta, **Then** su `error` conserva la causa
   observada (por ejemplo, `connection_error`), y los servicios que dependen de ella aparecen `degraded` (no
   `down`) porque siguen vivos.
8. **Given** solo algunas de las cuatro variables, o un valor no válido (zona inexistente, día desconocido,
   hora mal escrita o inicio no anterior al fin), **When** se intenta arrancar el servicio, **Then** no
   arranca y el mensaje nombra la variable sin mostrar su valor.
9. **Given** el mismo horario y la base sin responder un viernes a las 21:00 de la Ciudad de México, **When**
   se consulta la salud, **Then** el componente `database` está `stopped` y su `next_start_at` es el lunes
   siguiente a las 08:00 de esa zona, expresado en UTC (14:00): el fin de semana se salta; **When** la base
   está `up` o `down`, o no hay horario, **Then** su `next_start_at` es `null`, como el de los demás
   componentes.

---

### User Story 5 - Seguir informando cuando la base de datos o el registro no responden (Priority: P3)

El registro vive en la misma base de datos que se apaga por horario o que puede fallar. Por eso este servicio
guarda en memoria la última copia del registro que leyó con éxito: si no puede leerlo, consulta igual los
componentes de esa copia y lo avisa con `registry_available: false`. Si desde que arrancó nunca lo pudo leer,
solo muestra los dos componentes integrados.

**Why this priority**: Evita que una falla de la base de datos haga desaparecer del panel a todos los
servicios justo cuando más importa saber cómo están; es menos frecuente que los casos anteriores.

**Independent Test**: Consultar la salud una vez con la base disponible; hacer que la lectura del registro
falle y volver a consultar: aparecen los mismos componentes registrados, consultados de verdad, con
`registry_available: false`; reiniciar el servicio con la lectura fallando: solo los integrados y `false`;
restablecer la lectura: `true` y la copia al día.

**Acceptance Scenarios**:

1. **Given** el registro se leyó con éxito antes y ahora no puede leerse, **When** se consulta la salud,
   **Then** responde 200 con `registry_available` `false` y los componentes registrados de la copia, cada uno
   consultado normalmente.
2. **Given** que el servicio arrancó y nunca pudo leer el registro, **When** se consulta la salud, **Then**
   solo aparecen `maily-system-api` y `database`, con `registry_available` `false`.
3. **Given** el registro vuelve a poder leerse, **When** se consulta la salud, **Then** `registry_available`
   vuelve a `true` y la copia se renueva con los cambios hechos mientras tanto.
4. **Given** el registro se lee con éxito y está vacío, **When** se consulta la salud, **Then** solo aparecen
   los integrados, con `registry_available` `true`: vacío no es lo mismo que no disponible.
5. **Given** la lectura del registro agota su tiempo, **When** se consulta la salud, **Then** la respuesta
   llega en a lo más dos veces `HEALTH_CHECK_TIMEOUT_SECONDS` más 1 segundo.
6. **Given** la base de datos no está disponible, **When** se intenta registrar, modificar o eliminar un
   componente, **Then** la operación falla sin cambiar nada y la consulta de salud sigue respondiendo.

---

### User Story 6 - Ver el estado de la plataforma sin iniciar sesión (Priority: P2)

Cuando el Backoffice no puede comprobar el acceso de una persona —por ejemplo, de noche, cuando la base de
datos está detenida por horario y mailySoft-usuarios no puede autorizar—, la página «Salud de servicios» no
puede cargar la consulta de salud. Para que aun así se sepa qué pasa, este servicio publica sin token
`GET /health/status`, el estado público de la plataforma: sale del mismo resultado y de la misma caché que la
consulta de salud, pero solo trae el estado global, cuándo se comprobó y, de cada componente, su código, su
nombre, su tipo, su estado y, si es la base de datos detenida por horario, cuándo vuelve a encenderse. Nunca
publica versiones, commits, fechas de build, entornos, direcciones, latencias, chequeos ni códigos de error.
El Backoffice (spec 016-health-dashboard) lo muestra en su pantalla de comprobación de acceso fallida, para
que de noche se lea «Base de datos detenida por horario» y no solo un error de acceso.

**Why this priority**: Sin esta ruta, la base de datos detenida por horario casi nunca se vería: justo cuando
ocurre, el panel autenticado no carga (ver «Limitación conocida»), y una falla de acceso nocturna parecería
una caída de la plataforma. Es P2 y no P1 porque solo muestra una parte del resultado y depende de la
consulta agregada (historia 1) y del horario (historia 4).

**Independent Test**: Sin token, con la simulación del API de usuarios caída, el horario por defecto y un
reloj controlable, simular que la base no responde el viernes 23 de octubre de 2026 a las 21:15 de la Ciudad
de México y consultar `/health/status`: comprobar el 200, la base `stopped` con su próximo encendido y que
solo vienen los campos permitidos; repetir con un componente deshabilitado (no aparece), con el registro
ilegible (salen los de la copia en memoria), con 100 peticiones dentro del periodo mínimo (una sola ronda de
chequeos) y sin horario (`next_start_at` en `null`).

**Acceptance Scenarios**:

1. **Given** el horario por defecto y la base de datos sin responder el viernes 23 de octubre de 2026 a las
   21:15 de la Ciudad de México (`2026-10-24T03:15:00Z`), **When** se consulta `/health/status` sin token,
   **Then** responde 200 con `Cache-Control: no-store`, el componente `database` está `stopped` con
   `next_start_at` `2026-10-26T14:00:00Z` (el lunes a las 08:00 de esa zona: el fin de semana se salta),
   `maily-system-api` está `degraded` y, si ningún otro componente está `down`, el estado global es
   `degraded`.
2. **Given** el API de usuarios caído o sin poder autorizar, **When** se consulta `/health/status`, **Then**
   responde 200 igual, sin ninguna consulta de permisos, y si mailySoft-usuarios está registrado aparece con
   el estado que dio su chequeo (por ejemplo, `down`).
3. **Given** el registro se leyó antes y ahora no puede leerse, **When** se consulta `/health/status`,
   **Then** responde 200 con los componentes registrados de la copia en memoria y sin `registry_available`;
   **When** el servicio nunca pudo leerlo desde que arrancó, **Then** solo aparecen `maily-system-api` y
   `database`.
4. **Given** componentes con versión, commit, fecha de build, entorno, latencia, chequeos y códigos de error
   en el resultado de salud, **When** se revisa la respuesta pública, **Then** solo trae `status`,
   `checked_at` y `components` y, de cada componente, solo `code`, `name`, `kind`, `status` y
   `next_start_at`: ninguno de esos datos, ni direcciones, hosts o `registry_available`.
5. **Given** un componente registrado deshabilitado y otro eliminado, **When** se consulta `/health/status`,
   **Then** ninguno de los dos aparece, y los demás aparecen en el mismo orden y con el mismo estado que en
   `GET /api/v1/health`.
6. **Given** 100 peticiones públicas dentro de un mismo periodo de `max(HEALTH_CACHE_SECONDS, 15)` segundos,
   sin consultas autenticadas ni cambios en el registro e incluso con `HEALTH_CACHE_SECONDS` en 0, **When**
   se cuentan las llamadas a los componentes, **Then** cada uno recibió a lo más una ronda de chequeos, todas
   las peticiones recibieron 200 con el mismo resultado y su `checked_at` original, y el API de usuarios no
   recibió ninguna consulta de permisos.
7. **Given** que no se configuró ningún horario, **When** la base no responde y se consulta
   `/health/status`, **Then** la base está `down` y su `next_start_at` es `null`, como el de los demás
   componentes.
8. **Given** la documentación publicada, **When** se revisa `/health/status`, **Then** aparece con la
   etiqueta «Salud», sin seguridad ni permiso; **When** una petición trae una cabecera `Authorization`,
   válida o no, **Then** responde lo mismo que sin ella y el token no se valida ni se reenvía a nadie.

---

### Edge Cases

- **Componente que responde HTML o un cuerpo que no es JSON** (por ejemplo, el *catch-all* de Maily360, que
  responde 200 con `index.html` a cualquier ruta): en un servicio no cuenta como sano. Si `/health/live`
  responde así, está `down` con `invalid_response`; si es `/health/ready`, `degraded` con `invalid_response`;
  si es `/info`, sus datos de build valen `unknown`. En un frontend solo cuenta el código de estado: un 200 con
  HTML es `up`. Por eso la ruta de salud de un frontend debe existir de verdad (`/healthz/` en MailySoft): con
  una ruta inexistente, el *catch-all* lo haría parecer sano. Por la misma razón, la ruta de información de un
  frontend solo se toma en cuenta si responde el JSON del contrato.
- **Redirecciones**: no se siguen; un 3xx es `unexpected_status`. Por ejemplo, `/healthz` sin la barra final
  puede redirigir a `/healthz/` y dejaría el frontend `down`.
- **Tiempo agotado**: en `/health/live`, `down` con `timeout`; en `/health/ready` con la vida bien,
  `degraded` con `timeout`; en `/info`, solo los datos de build pasan a `unknown`. Un componente lento no
  alarga la consulta más allá del límite (FR-019).
- **DNS que no resuelve**: `down` con `dns_error`. El registro no comprueba que la dirección responda: se
  puede registrar un componente antes de desplegarlo, y aparecerá `down` hasta entonces.
- **Host no permitido**: al registrar o modificar, 422. Si la lista cambia después y el host ya no está, el
  componente aparece `unknown` con `host_not_allowed` y no se le llama. Sin lista no se puede registrar
  ninguno, y los que ya estaban aparecen así.
- **Dirección o ruta tramposa**: credenciales (`https://usuario:clave@host`), query, fragmento, un esquema
  distinto de `http` y `https`, un host que no es ASCII, o rutas como `//otro-host/x`, `/\otro-host` o
  `/../admin` → 422. La dirección de cada llamada siempre tiene el host de `base_url`.
- **Componente deshabilitado**: no se consulta, no aparece en la consulta de salud ni cuenta para el estado
  global; sigue en el registro y reaparece al habilitarlo.
- **Baja lógica y reutilización del código**: un componente eliminado no aparece en ningún lado y responde
  404; su fila se conserva y su código queda libre: registrarlo de nuevo crea otro componente, con otro
  identificador.
- **Códigos reservados**: `maily-system-api` y `database` → 409, porque ya los usan los integrados.
- **Dos altas simultáneas con el mismo código**: solo una se crea; la otra recibe 409.
- **Muchas consultas simultáneas de varias personas**: cada una se autoriza por separado, pero comparten la
  agregación en curso y la caché: los componentes reciben a lo más una ronda de chequeos por proceso y periodo
  de caché.
- **Caché en 0**: la consulta de salud no reutiliza resultados terminados, pero las consultas simultáneas
  comparten igual la agregación en curso; el estado público los reutiliza igual durante 15 segundos (FR-048).
- **«Actualizar» dentro del periodo de caché**: devuelve el resultado guardado, con sus `checked_at`
  originales; no hay forma de saltarse la caché.
- **El registro empieza vacío**: solo aparecen los integrados, con `registry_available: true`.
- **El registro no se puede leer pero la base de datos responde** (por ejemplo, una migración pendiente):
  `registry_available: false` con la copia en memoria (o solo los integrados); el estado global sigue la regla
  general.
- **Respuesta demasiado grande** (más de 64 KiB) de un servicio: ese chequeo falla con `response_too_large` y
  no se lee el resto.
- **Datos raros en `/info` o en los chequeos de un componente**: los textos de más de 64 caracteres se
  recortan; los valores que no son texto y las fechas no válidas valen `unknown`; de más de 20 chequeos se
  toman los primeros 20 y los mal formados se descartan; un código de error que no es del contrato se
  convierte en `unexpected_error`. Nunca se devuelve el texto crudo.
- **Cambio de horario de verano**: la ventana se evalúa con las reglas de la zona configurada en el instante
  de la falla, así que conserva sus horas locales. America/Mexico_City no tiene horario de verano desde 2022
  (lo anota el runbook), por lo que hoy su desfase es UTC−6 todo el año.
- **Base de datos detenida justo en el límite del horario**: la ventana incluye la hora de inicio y excluye
  la de fin, y se evalúa en el instante en que se observa la falla: una falla a las 20:00 en punto o después es
  `stopped`; a las 08:00 en punto, `down`. Como el servidor tarda unos minutos en arrancar después de la hora
  de encendido, una falla en esos minutos se informa `down` (decisión revisable, ver «Assumptions»). Un
  resultado calculado justo antes del límite puede servirse desde la caché hasta `HEALTH_CACHE_SECONDS`
  después (en el estado público, hasta `max(HEALTH_CACHE_SECONDS, 15)` segundos).
- **Base de datos encendida fuera de horario**: si responde, `up`. Si está encendida pero este servicio no la
  alcanza, fuera de horario se informará `stopped`: la deducción por horario no distingue ese caso; es el
  costo de no consultar a Azure.
- **Horario incompleto, inválido o que cruza la medianoche**: el servicio no arranca.
- **Fuera de horario, el API de usuarios tampoco puede autorizar**: la consulta de salud y el registro
  responden 503, pero el estado público sigue respondiendo 200 con la base `stopped` y su `next_start_at`
  (historia 6); ver «Limitación conocida» en «Assumptions».
- **El API de usuarios no responde**: la consulta de salud y el registro responden 503; las rutas públicas de
  salud, incluido el estado público, siguen respondiendo.
- **Varias réplicas del servicio**: cada una tiene su caché, su copia del registro y su periodo mínimo del
  estado público (los componentes pueden recibir una ronda por réplica y periodo); un cambio en el registro
  se ve de inmediato en la réplica que lo atendió y en las demás cuando vence su caché.
- **Variables de build ausentes o no válidas**: si faltan, `unknown`; si tienen un valor no válido, el
  servicio no arranca.
- **El próximo encendido cae después de un fin de semana o cerca de un cambio de horario**: `next_start_at`
  se salta los días que no están en el horario (con el horario por defecto, una falla del viernes 23 de
  octubre de 2026 a las 21:15 da el lunes 26 a las 08:00, `2026-10-26T14:00:00Z`) y se convierte a UTC con
  las reglas de la zona en la fecha de ese inicio, no con el desfase del momento de la falla. Con
  America/Mexico_City, sin horario de verano, siempre cae a las 14:00 UTC; con una zona que sí lo tiene, como
  `America/Tijuana`, una falla el viernes 30 de octubre de 2026 a las 21:00 (UTC−7) da
  `2026-11-02T16:00:00Z`: el lunes a las 08:00, ya en UTC−8. Si la hora de inicio no existe ese día porque el
  reloj se adelanta, es el instante del salto; si existe dos veces porque se atrasa, la primera (FR-044).
- **La base de datos falla dentro del horario**: está `down` (FR-035) y su `next_start_at` es `null`, porque
  no hay un encendido que esperar: la falla es real. Pasa lo mismo en los minutos que tarda el servidor en
  arrancar después de la hora de encendido: esa hora ya pasó y la base aparece `down` (decisión 15).
- **Una petición pública llega justo cuando vence la caché**: para el estado público, un resultado vale
  mientras no hayan pasado `max(HEALTH_CACHE_SECONDS, 15)` segundos desde que terminó su agregación; en ese
  instante o después, la petición se une a la agregación en curso o lanza una, y espera su resultado (dentro
  del límite de FR-019) en lugar de recibir el vencido. Las peticiones que llegan mientras tanto comparten
  esa misma agregación: nunca hay dos a la vez por proceso ni más de una ronda provocada por peticiones
  públicas en cada periodo (FR-048). Un `next_start_at` servido desde la caché puede haber quedado unos
  segundos en el pasado.

## Requirements *(mandatory)*

### Functional Requirements

**Rutas, permisos y control de acceso**

- **FR-001**: Esta feature MUST añadir las operaciones de la tabla siguiente. Las seis protegidas se suman a
  la matriz «operación → permiso» sin alterar ninguna de sus siete filas actuales (las seis de suscripciones y
  la del dashboard), que queda con 13 operaciones protegidas; las cuatro públicas —las tres del contrato de
  salud y el estado público `/health/status`— se suman, en la tabla de rutas públicas de la matriz, a las
  cuatro de documentación (`/openapi.json`, `/docs`, `/docs/oauth2-redirect` y `/redoc`), que quedan en ocho.
  Las rutas, los permisos y los códigos de respuesta son parte del acuerdo con maily-backoffice 016; los
  identificadores de operación son una propuesta que fija el plan, salvo `get_health_status`, que fija esta
  especificación (FR-045). En las operaciones protegidas, 503 es la falla del control de acceso; en las del
  registro, 500 solo aparece si la base de datos no está disponible (FR-037).

| Operación (propuesta) | Método y ruta | Permiso | Respuestas |
|---|---|---|---|
| `get_health_live` | `GET /health/live` | ninguno (pública) | 200 |
| `get_health_ready` | `GET /health/ready` | ninguno (pública) | 200, 503 |
| `get_info` | `GET /info` | ninguno (pública) | 200 |
| `get_health_status` | `GET /health/status` | ninguno (pública) | 200 |
| `get_health` | `GET /api/v1/health` | `health:read` | 200, 401, 403, 503 |
| `list_monitored_components` | `GET /api/v1/monitored-components` | `health:read` | 200, 401, 403, 500, 503 |
| `get_monitored_component` | `GET /api/v1/monitored-components/{component_id}` | `health:read` | 200, 401, 403, 404, 422, 500, 503 |
| `create_monitored_component` | `POST /api/v1/monitored-components` | `health:write` | 201, 401, 403, 409, 422, 500, 503 |
| `update_monitored_component` | `PATCH /api/v1/monitored-components/{component_id}` | `health:update` | 200, 401, 403, 404, 409, 422, 500, 503 |
| `delete_monitored_component` | `DELETE /api/v1/monitored-components/{component_id}` | `health:delete` | 204, 401, 403, 404, 422, 500, 503 |

- **FR-002**: Las tres rutas del contrato de salud y el estado público MUST ser públicas (sin token): las
  tres primeras porque las consultan Kubernetes, Docker y el agregador, que no tienen token, y el estado
  público porque el Backoffice lo consulta justo cuando no puede comprobar el acceso (historia 6). El
  principio VIII de la constitución ya admite como excepción «las comprobaciones de salud, si la
  especificación las define»: **esta especificación las define y son solo `/health/live`, `/health/ready`,
  `/info` y `/health/status`** (`/info` forma parte del contrato de salud, y `/health/status` es una vista
  mínima del resultado de salud, sin datos sensibles; FR-047). No hace falta enmendar la constitución.
  Cualquier otra ruta nueva MUST exigir token y permiso.
- **FR-003**: Las seis operaciones protegidas MUST usar el control de acceso vigente del servicio (principio
  VIII): reenviar el token, sin modificarlo, a `GET /api/v1/authorization/check` del API de usuarios con el
  permiso exacto de la operación, en cada petición y sin guardar la decisión; responder 401 sin token o con un
  token rechazado o vencido, 403 sin el permiso (cada permiso autoriza solo su operación) y 503 si el API de
  usuarios no responde, agota el tiempo o contesta algo inesperado (falla cerrada). La comprobación MUST
  ocurrir antes de validar la solicitud, de buscar el componente y de consultar o servir cualquier resultado
  de salud; en ninguno de esos rechazos se devuelve dato alguno ni se consulta ningún componente. Cada
  operación MUST declarar su permiso con `x-required-permission` y el esquema Bearer. Los cuatro permisos
  `health:*` los crea su dueño, mailySoft-usuarios (spec 016-health-endpoints); este servicio no los crea.

**Contrato de salud de Maily v1 en este servicio**

- **FR-004**: `GET /health/live` MUST responder 200 con `{"status":"ok"}` mientras el proceso atienda HTTP,
  sin consultar ninguna dependencia (ni la base de datos, ni el API de usuarios, ni el de clínicas) y en
  menos de 100 ms. Sirve también como *startup probe*, porque el arranque es rápido.
- **FR-005**: `GET /health/ready` MUST comprobar solo la base de datos, con una consulta trivial limitada por
  `HEALTH_READY_TIMEOUT_SECONDS` (FR-038), y responder 200 si responde o 503 si falla, en ambos casos con el
  cuerpo `{"status":"ok"|"unavailable","checks":[{"name":"database","status":"ok"|"error","latency_ms":12,"error":null|"timeout"|"connection_error"|"not_configured"|"unexpected_error"}]}`,
  donde `latency_ms` es la duración del chequeo en milisegundos, también cuando falla. Este servicio no emite
  `not_configured`, porque no arranca sin `DATABASE_URL`. El contrato v1 lo reserva para los servicios que sí
  pueden arrancar sin esa configuración, como mailySoft-pacientes 008, y el agregador MUST aceptarlo en sus
  `checks`. MUST NOT consultar
  otros servicios HTTP (para no encadenar fallas) ni tener en cuenta el horario de la base de datos: sin base
  de datos el servicio no puede atender, esté detenida a propósito o no. Cualquier falla inesperada del
  chequeo MUST informarse como `unexpected_error` con 503, nunca como un error 500.
- **FR-006**: `GET /info` MUST responder 200 con
  `{"service":"maily-system-api","version":"<semver>","commit":"<sha>"|"unknown","build_date":"<ISO 8601 UTC>"|"unknown","environment":"<nombre>"|"unknown"}`.
  `commit`, `build_date` y `environment` MUST salir de las variables `APP_COMMIT_SHA`, `APP_BUILD_DATE` y
  `APP_ENVIRONMENT`, inyectadas al construir o al desplegar. No son obligatorias: si faltan o están vacías,
  el campo vale `"unknown"` y el servicio arranca igual. `build_date` se publica en UTC, con `Z`.
- **FR-007**: La versión MUST salir de **una sola fuente** en el código, y ese mismo valor MUST publicarse en
  `/info`, en el documento OpenAPI y en los metadatos del proyecto. Hoy hay dos que no coinciden:
  `VERSION = "2.0.0"` en `src/main.py` (la que publica el documento OpenAPI) y `version = "0.1.0"` en
  `pyproject.toml`. El plan elige cuál es la fuente y cómo se alinea la otra con ella; la versión publicada
  MUST NOT retroceder respecto a `2.0.0`.
- **FR-008**: Reglas comunes de las tres rutas: MUST responder con `Cache-Control: no-store`; MUST NOT
  incluir secretos, nombres de host, direcciones, cadenas de conexión, mensajes de excepción ni trazas; los
  campos van en inglés y las fechas en ISO 8601 UTC; y MUST documentarse en el contrato publicado (OpenAPI)
  con la etiqueta «Salud», con descripciones en español y sin esquema de seguridad ni `x-required-permission`.
- **FR-009**: La imagen Docker MUST recibir `APP_COMMIT_SHA` y `APP_BUILD_DATE` como argumentos de
  construcción (`ARG`) y publicarlos como variables de entorno (`ENV`); construirla sin ellos MUST seguir
  funcionando, con `"unknown"` en `/info`. `APP_ENVIRONMENT` se inyecta al desplegar, no al construir. El
  README MUST documentar un ejemplo de probes de Kubernetes —liveness → `/health/live`; readiness →
  `/health/ready`; startup → `/health/live` con un `failureThreshold` amplio— y explicar que readiness falla
  mientras la base de datos está detenida (el orquestador deja de enviarle tráfico, que es lo esperado) y
  liveness no (no se reinicia el contenedor). No se crean manifiestos de Kubernetes.

**Consulta de salud agregada**

- **FR-010**: Concedido el acceso, `GET /api/v1/health` MUST responder **siempre 200**, sea cual sea el
  estado de los componentes (todos caídos, base de datos detenida o registro no disponible): la degradación
  se informa por componente, igual que en `/api/v1/dashboard`. El cuerpo MUST ser
  `{"status":"ok"|"degraded"|"down","checked_at":"<ISO 8601 UTC>","registry_available":true|false,"components":[…]}`,
  donde `checked_at` es el instante en que terminó la agregación y `components` nunca es nulo. La respuesta
  MUST llevar `Cache-Control: no-store`. La operación no tiene parámetros; los parámetros de consulta
  desconocidos se ignoran.
- **FR-011**: `components` MUST contener, en este orden: los dos **componentes integrados**, que siempre
  aparecen y no se pueden editar —`maily-system-api` (este servicio) y `database` (la base de datos de
  Azure)—, y después los **componentes registrados** habilitados y no eliminados, por `sort_order` ascendente
  y, a igualdad, por `code` ascendente. Los deshabilitados y los eliminados no aparecen ni se consultan.
- **FR-012**: Cada componente MUST traer: `code`; `name`; `kind` (`service`, `database` o `frontend`);
  `status` (`up`, `degraded`, `down`, `stopped` o `unknown`); `latency_ms` (entero mayor o igual a 0 con la
  duración de su chequeo principal, también si falló, o `null` si no se llegó a intentar); `checked_at` (ISO
  8601 UTC, cuando terminó su chequeo); `version`, `commit`, `build_date` (ISO 8601 UTC) y `environment`
  (cada uno `"unknown"` si no está disponible); `checks` (lista de chequeos con la forma de `/health/ready`:
  `name`, `status` `ok` o `error`, `latency_ms` y `error`; vacía si no aplica); `error` (`null` si está
  `up`, o un código de FR-018); y `next_start_at` (ISO 8601 UTC con el próximo encendido programado de la
  base de datos detenida por horario, o `null` en cualquier otro caso; FR-044). El chequeo principal es
  `/health/live` en un servicio, la ruta de salud en un frontend y la consulta trivial en la base de datos.
- **FR-013**: Lo que responde un componente MUST depurarse: MUST NOT devolverse nunca su cuerpo crudo, solo
  los campos conocidos del contrato v1. Cada texto que venga de un componente (versión, commit, entorno,
  nombre de un chequeo) se recorta a 64 caracteres y se le quitan los caracteres de control; un valor que no
  es texto, o un `build_date` que no es una fecha y hora ISO 8601 válida, vale `"unknown"` (las fechas
  válidas se normalizan a UTC); se toman a lo más 20 chequeos, con `status` solo `ok` o `error`,
  `latency_ms` entero o `null`, y cualquier `error` fuera de la lista del contrato se convierte en
  `unexpected_error`; un chequeo sin `name` de texto o con otro `status` se descarta. La respuesta MUST NOT
  incluir la dirección (`base_url`), los hosts ni las IP de ningún componente, ni el token.
- **FR-014**: **Estado de un servicio** (`kind` `service`), con sus tres llamadas en paralelo:
  - `/health/live` bien (200 con `{"status":"ok"}`) y `/health/ready` bien (200 con `status` `ok`) → `up`;
  - `/health/live` bien y `/health/ready` falla → `degraded`: con `not_ready` si respondió 503 con el cuerpo
    del contrato (y sus `checks`, depurados), o con el código de la falla en cualquier otro caso;
  - `/health/live` falla —otro código (`unexpected_status`), otro cuerpo (`invalid_response`), tiempo
    agotado, error de conexión o de DNS, o respuesta demasiado grande— → `down`, con el código de la falla;
  - si `/info` falla o no responde un objeto JSON, el estado no cambia y `version`, `commit`, `build_date` y
    `environment` valen `"unknown"`.
- **FR-015**: **Estado de un frontend** (`kind` `frontend`): un 2xx en su ruta de salud → `up`; cualquier
  otra respuesta o falla → `down`, con `unexpected_status` o el código de la falla. Solo cuenta el código de
  estado: su cuerpo no se lee. Si tiene ruta de información, se lee como la de un servicio; si no, sus datos
  de build valen `"unknown"`. Para MailySoft la ruta de salud es `/healthz/` y no tiene ruta de información.
- **FR-016**: **Componentes integrados**:
  - `database` («Base de datos»): una consulta trivial con su latencia. Si responde → `up`; si falla →
    `down` o `stopped` según el horario (FR-033 a FR-035), con `error` `timeout`, `connection_error` o
    `unexpected_error`. Su `checks` va vacío y sus datos de build valen `"unknown"`.
  - `maily-system-api` («MailySoft System API»): MUST calcularse dentro del proceso, sin que el servicio se
    haga peticiones HTTP a sí mismo. Su vida está bien por definición (está atendiendo la consulta) y su
    disponibilidad es el resultado del chequeo de la base de datos de esa misma agregación, que se reutiliza
    (una sola consulta a la base por agregación): `up` si la base respondió y `degraded` con `not_ready` si
    no. Sus `checks` son los de su `/health/ready` (`database`), su `latency_ms` es la de ese chequeo y sus
    datos de build son los de su `/info`.
- **FR-017**: **Estado global**: `down` si algún componente está `down`; si no, `degraded` si alguno está
  `degraded`, `stopped` o `unknown`; si no, `ok`. `registry_available` no cambia por sí mismo el estado
  global.
- **FR-018**: **Códigos de error de componente**: lista cerrada, en inglés; el Backoffice los explica en
  español. Agregar un código en el futuro es un cambio compatible que se documenta; quitar o renombrar uno no
  lo es.

| Código | Significado | Aparece en |
|---|---|---|
| `timeout` | No respondió dentro de `HEALTH_CHECK_TIMEOUT_SECONDS`. | servicios, frontends, base de datos |
| `connection_error` | No se pudo conectar: conexión rechazada o cortada, error de TLS o certificado no válido. | servicios, frontends, base de datos |
| `dns_error` | El nombre del host no se pudo resolver. | servicios, frontends |
| `host_not_allowed` | Su host ya no está en la lista permitida; no se le llamó (estado `unknown`). | servicios, frontends |
| `unexpected_status` | Respondió un código HTTP no previsto, incluidas las redirecciones, que no se siguen. | servicios, frontends |
| `invalid_response` | El cuerpo no es el del contrato v1: no es JSON (por ejemplo, HTML), le faltan campos o tienen otro tipo. | servicios |
| `response_too_large` | La respuesta superó 64 KiB. | servicios |
| `not_ready` | Está vivo, pero su disponibilidad falla: su `/health/ready` respondió 503 conforme al contrato (en `maily-system-api`, la base de datos no respondió). | servicios |
| `unexpected_error` | Cualquier otra falla del chequeo; si la falla es del propio agregador y no permite saber el estado, el componente queda `unknown`. | todos |

**Ejecución, caché y llamadas a los componentes**

- **FR-019**: Los chequeos MUST hacerse en el momento de la consulta —no hay trabajos en segundo plano— y
  **en paralelo**: todas las llamadas de todos los componentes a la vez, cada una con un tiempo máximo total
  de `HEALTH_CHECK_TIMEOUT_SECONDS` (incluidas la resolución DNS, la conexión y la lectura). La consulta a la
  base de datos y la lectura del registro tienen el mismo límite y van en paralelo entre sí; los chequeos de
  los componentes registrados empiezan cuando se conoce la lista (la leída o la copia en memoria). Sin
  reintentos, sin seguir redirecciones y leyendo a lo más 64 KiB de cada respuesta. Una agregación MUST
  terminar en a lo más `HEALTH_CHECK_TIMEOUT_SECONDS` + 1 s más lo que tarde la lectura del registro, y nunca
  en más de 2 × `HEALTH_CHECK_TIMEOUT_SECONDS` + 1 s, aunque haya componentes caídos o que no responden.
- **FR-020**: El resultado de una agregación MUST guardarse en caché y compartirse entre todas las consultas:
  la consulta de salud lo reutiliza durante `HEALTH_CACHE_SECONDS` (con 0, no reutiliza resultados
  terminados) y el estado público, durante `max(HEALTH_CACHE_SECONDS, 15)` segundos (FR-048). MUST haber a lo
  más una agregación en curso a la vez por proceso: las consultas que llegan mientras tanto y no pueden
  servirse de la caché esperan su resultado en lugar de lanzar otra. Un resultado servido desde la caché
  conserva sus `checked_at` originales. La caché guarda resultados de chequeos, **nunca** decisiones de
  permiso: cada consulta de salud se autoriza (FR-003). Registrar, modificar o eliminar un componente MUST
  invalidar la caché del proceso que atendió el cambio. La API no ofrece forma de saltarse la caché.
- **FR-021**: Las llamadas a los componentes MUST cumplir el principio IX: asíncronas, con tiempo máximo
  total, sin reintentos automáticos y con el límite y la lista permitida tomados de variables de entorno.
  Además MUST ser solo `GET`, con verificación de certificados TLS, y MUST NOT llevar el token de la persona,
  credenciales ni ninguna cabecera de la petición original. Sus fallas se traducen a los códigos de FR-018;
  si el servicio deja constancia de una falla en su log, nombra el código del componente y el de la falla,
  nunca la dirección, el token ni el cuerpo.
- **FR-022**: Las direcciones de los componentes registrados salen del registro (la base de datos) y no de
  variables de entorno, como pide literalmente el principio IX («Las direcciones, los tiempos de espera y las
  credenciales de cada API MUST provenir de variables de entorno»). Lo que sí viene del entorno es la lista
  permitida `HEALTH_ALLOWED_HOSTS`, que acota a qué hosts puede llamar el servicio, y el tiempo máximo. El
  plan MUST justificar esta desviación en su «Constitution Check» o proponer la enmienda que la reconozca.

**Registro de componentes**

- **FR-023**: El servicio MUST mantener un **registro de componentes** (tabla `monitored_components`) con los
  servicios y frontends que se monitorean, administrable con las cinco operaciones de
  `/api/v1/monitored-components` de FR-001. El listado devuelve todos los componentes no eliminados
  —habilitados y deshabilitados— como una lista sin envoltorio, ordenada por `sort_order` y `code`, **sin
  paginar**: se declara para este catálogo la excepción del principio IV, con un máximo esperado de 50
  componentes y ese orden determinista (si se superara, el listado pasaría a paginarse, un cambio incompatible
  que se versiona). Las respuestas del registro son el único lugar donde se ve `base_url`.
- **FR-024**: Datos de un componente registrado:
  - `id`: UUID asignado por el servicio.
  - `code`: obligatorio; de 2 a 50 caracteres entre minúsculas sin acentos, dígitos y guiones; empieza con
    letra, no termina en guion ni tiene dos guiones seguidos; único entre los componentes no eliminados.
    `maily-system-api` y `database` están reservados para los integrados.
  - `name`: obligatorio, de 1 a 100 caracteres, guardado sin espacios al inicio ni al final.
  - `kind`: `service` o `frontend` (la base de datos solo es integrada).
  - `base_url` (FR-025) y las rutas `live_path`, `ready_path` e `info_path` (FR-026).
  - `enabled`: verdadero o falso; por defecto, verdadero.
  - `sort_order`: entero de 0 a 9999; por defecto, 0.
  - `created_at` y `updated_at` (ISO 8601 UTC), y la marca de baja lógica con su fecha, que no se publica.
- **FR-025**: **Dirección base** (`base_url`), protegida contra SSRF: es obligatoria; su esquema es `http` o
  `https`; tiene host; no lleva usuario ni contraseña, ni query (ni siquiera un `?` vacío), ni fragmento;
  tiene hasta 255 caracteres; su host es un nombre ASCII (letras, dígitos, guiones y puntos) o una IP
  literal; puede llevar puerto y ruta. Se guarda sin barra final y con el esquema y el host en minúsculas. Su
  host MUST estar en la lista permitida (FR-027). Se admite `http` porque nunca se envía el token.
- **FR-026**: **Rutas**: empiezan con una sola `/` (no `//`); no tienen `\`, ni segmentos `.` o `..`, ni `?`,
  ni `#`, ni espacios o caracteres de control; y tienen hasta 200 caracteres. La dirección de cada llamada se
  arma concatenando `base_url` y la ruta, y su host MUST ser el de `base_url`. En un `service`, las tres rutas
  toman por defecto `/health/live`, `/health/ready` e `/info`, y pueden cambiarse pero no anularse. En un
  `frontend`, `live_path` es su ruta de salud y es obligatoria, `ready_path` no aplica (MUST ser nula) e
  `info_path` es opcional (nula por defecto).
- **FR-027**: **Lista permitida** (`HEALTH_ALLOWED_HOSTS`): hosts o sufijos de dominio separados por comas,
  sin distinguir mayúsculas. Una entrada sin punto inicial admite solo ese host exacto, sea un nombre o una IP
  (por ejemplo, `mailysoft-usuarios` o `maily360-production.up.railway.app`); una con punto inicial (por
  ejemplo, `.maily.internal`) admite los subdominios de ese dominio, pero no el dominio solo ni los nombres que
  solo terminan igual (`otromaily.internal`). Una entrada con esquema, ruta, puerto o comodín (`*`), un punto
  solo o una entrada vacía hacen que el servicio no arranque. Sin la variable no se puede registrar ningún
  componente ni cambiar su dirección (422), y los ya registrados aparecen `unknown` con `host_not_allowed`,
  sin llamarlos. El host de cada componente MUST volver a compararse con la lista vigente en cada agregación.
- **FR-028**: **Alta y modificación**: el alta (201) aplica los valores por defecto y devuelve el componente
  completo. La modificación (200) cambia solo los campos enviados —cualquiera de FR-024 salvo `id`, las fechas
  y la marca de baja— y valida el componente resultante con las mismas reglas que un alta (por ejemplo, pasar
  `kind` a `frontend` exige `ready_path` nula); actualiza `updated_at`. Si dos altas o modificaciones
  simultáneas llevan al mismo `code`, solo una tiene éxito y la otra recibe 409.
- **FR-029**: **Baja lógica**: la eliminación (204) conserva la fila, marcada como eliminada con su fecha; el
  componente deja de aparecer en el registro y en la consulta de salud, y consultarlo, modificarlo o
  eliminarlo después responde 404. Su `code` queda libre: registrarlo de nuevo crea otro componente, con otro
  `id`.
- **FR-030**: **Errores del registro**, con el formato uniforme del servicio y mensajes en español,
  comprobados en este orden: acceso (401, 403 o 503; FR-003) → datos (422) → existencia (404) → conflicto
  (409).
  - 422 `validation_error`, con un elemento por campo con problema: datos fuera de las reglas, campos no
    reconocidos o no modificables, modificación sin ningún dato, identificador que no es un UUID, host fuera de
    la lista permitida. Los mensajes sobre `base_url` MUST NOT repetir la dirección recibida (podría traer
    credenciales) ni revelar la lista.
  - 404 `monitored_component_not_found`: el componente no existe o está eliminado.
  - 409 `monitored_component_code_already_exists`: el `code` lo usa otro componente no eliminado o está
    reservado.

  Son los dos únicos códigos de error nuevos de la API; los existentes no cambian.
- **FR-031**: **Sin redespliegue**: registrar, modificar, habilitar, deshabilitar o eliminar un componente
  MUST verse en la siguiente consulta de salud del proceso que atendió el cambio, y en los demás procesos a
  más tardar cuando venza su caché, sin redesplegar ni reiniciar. Para monitorear un microservicio futuro
  basta con que cumpla el contrato v1, que su host esté en la lista permitida y registrarlo. El registro
  empieza vacío, sin datos iniciales: después del despliegue, un administrador registra mailySoft-usuarios,
  mailySoft-pacientes y MailySoft desde el Backoffice.
- **FR-032**: El registro MUST crearse con una migración de Alembic reversible (principio VI) que crea
  `monitored_components` con la unicidad del `code` entre los componentes no eliminados; el modelo MUST
  coincidir con la migración, y `project-definition/DATA_SCHEMA.md` MUST reflejar la tabla con el comentario
  `-- [spec 005-health-monitoring]`. Ninguna otra tabla cambia.

**Horario de la base de datos**

- **FR-033**: El horario de encendido de la base de datos MUST configurarse con cuatro variables opcionales
  que van juntas, con los mismos valores del runbook (`Deploy-PgAutoShutdown.ps1`: de lunes a viernes, de
  08:00 a 20:00, America/Mexico_City):
  - `DATABASE_SCHEDULE_TIMEZONE`: zona horaria IANA (por ejemplo, `America/Mexico_City`).
  - `DATABASE_SCHEDULE_DAYS`: días en inglés separados por comas, como los nombra el runbook
    (`Monday,Tuesday,Wednesday,Thursday,Friday`), sin distinguir mayúsculas, sin repetir y sin importar los
    espacios alrededor de las comas.
  - `DATABASE_SCHEDULE_START` y `DATABASE_SCHEDULE_END`: horas `HH:MM` de 24 horas, con el inicio anterior al
    fin (no se admiten ventanas que crucen la medianoche).

  Si se define alguna sin las demás, o un valor no es válido (zona desconocida, día desconocido o repetido,
  hora mal escrita, inicio no anterior al fin), el servicio MUST NOT arrancar. Si no se define ninguna, no hay
  horario.
- **FR-034**: La ventana de encendido son los días listados, desde la hora de inicio (incluida) hasta la de
  fin (excluida), en la hora local de la zona configurada en el instante en que se observa la falla y con las
  reglas de esa zona (incluido su horario de verano, si lo tiene). El día de la semana también se evalúa en
  esa zona, no en UTC.
- **FR-035**: Estado del componente `database`: si la consulta responde, `up` (también fuera de la ventana);
  si falla dentro de la ventana, `down`; si falla fuera, `stopped` («detenida por horario»); sin horario
  configurado, cualquier falla es `down`. En `stopped`, `error` conserva la causa observada y `next_start_at`
  trae el próximo encendido (FR-044). El servicio MUST deducirlo solo del horario configurado y MUST NOT
  consultar el estado del servidor en Azure.

**Resiliencia del registro**

- **FR-036**: El servicio MUST conservar en memoria la última copia del registro leída con éxito (por
  proceso, sin caducidad y sin guardarla en disco) y renovarla en cada lectura exitosa. Si en una agregación
  no puede leer el registro (base de datos caída o detenida, tiempo agotado u otra falla), MUST consultar los
  componentes de esa copia y responder `registry_available: false`; si desde que arrancó nunca lo leyó, solo
  aparecen los integrados, también con `registry_available: false`. Un registro leído con éxito, aunque esté
  vacío, es `registry_available: true`.
- **FR-037**: Si la base de datos no está disponible, las operaciones del registro MUST fallar sin cambiar
  nada, con el error que hoy da el servicio en esa situación (500 `internal_error`, sin detalles), y la
  consulta de salud MUST seguir respondiendo según FR-036.

**Configuración**

- **FR-038**: Variables de entorno nuevas, todas opcionales:

| Variable | Valores admitidos | Por defecto |
|---|---|---|
| `HEALTH_CHECK_TIMEOUT_SECONDS` | Entero de 1 a 10 | `3` |
| `HEALTH_CACHE_SECONDS` | Entero de 0 a 300 | `15` |
| `HEALTH_ALLOWED_HOSTS` | Lista de FR-027 | Vacía: no se puede registrar ningún componente ni se consulta ninguno de los registrados |
| `HEALTH_READY_TIMEOUT_SECONDS` | Entero de 1 a 10 | `2` |
| `DATABASE_SCHEDULE_TIMEZONE`, `DATABASE_SCHEDULE_DAYS`, `DATABASE_SCHEDULE_START`, `DATABASE_SCHEDULE_END` | FR-033 | Sin horario |
| `APP_COMMIT_SHA` | De 7 a 64 caracteres hexadecimales | `unknown` en `/info` |
| `APP_BUILD_DATE` | Fecha y hora ISO 8601 con zona (`Z` o desfase) | `unknown` en `/info` |
| `APP_ENVIRONMENT` | De 1 a 50 caracteres: letras, dígitos, `.`, `_` o `-` | `unknown` en `/info` |

Las variables MUST validarse al arrancar junto con el resto de la configuración: con cualquier valor no
válido el servicio MUST NOT arrancar, y el mensaje MUST nombrar cada variable inválida sin mostrar su valor.
Una variable vacía equivale a no configurada, y un cambio de valor requiere reiniciar el servicio. MUST
documentarse en `.env.example` y en la tabla de configuración del README, y la pila local de Docker Compose
MUST pasarlas al servicio.

**Pruebas, alcance y calidad**

- **FR-039**: Las comprobaciones que vigilan el **conjunto completo** de la API MUST ajustarse solo para
  reconocer lo nuevo, sin debilitarse y sin cambiar lo que verifican sobre las suscripciones y el dashboard:
  en `test_permission_coverage`, `PUBLIC_ROUTES` incluye `/health/live`, `/health/ready`, `/info` y
  `/health/status` (ocho rutas públicas con las cuatro de documentación), y el conteo de operaciones
  recorridas pasa a las 13 protegidas de FR-001; la prueba de que toda operación documentada declara
  seguridad y permiso excluye solo esas cuatro rutas públicas de salud; la cobertura conjunta de las
  colecciones de Postman incluye la colección nueva, con sus diez operaciones (las cuatro públicas y las seis
  protegidas); y las pruebas que fijan el número de códigos de error reconocen los dos nuevos. El plan MUST
  enumerar y justificar cada ajuste.
- **FR-040**: Esta feature MUST NOT cambiar el comportamiento, el contrato ni los permisos de
  `GET /api/v1/dashboard` ni de las operaciones de suscripciones, ni modificar las colecciones de Postman
  existentes; sus pruebas MUST seguir pasando sin cambiar ninguna comprobación de comportamiento (salvo los
  ajustes de FR-039).
- **FR-041**: Las pruebas automatizadas MUST NOT llamar a servicios reales: el API de usuarios y los
  componentes se sustituyen por simulaciones que reproducen sus contratos y sus fallas (servicio sano,
  `/health/ready` en 503, 200 con HTML, cuerpo que no es JSON, redirección, tiempo agotado, DNS que no
  resuelve, respuesta demasiado grande, `/info` incompleto). Deben cubrir las reglas de estado y el estado
  global, la depuración, el orden, la caché y la agregación compartida, la validación contra SSRF y la lista
  permitida, el horario con un reloj controlable (límites, día en la zona y horario de verano), la copia en
  memoria, la validación de las variables al arrancar, el contrato v1 de este servicio y los errores 401, 403,
  503, 404, 409 y 422. El repositorio del registro se prueba contra PostgreSQL 17 real (principio V).
- **FR-042**: MUST añadirse una colección de Postman nueva e independiente en `tests/postman/`, automática y
  de punta a punta (contra el servicio real con las simulaciones de sus dependencias, como las existentes),
  con: las cuatro rutas públicas (en `/health/status`, el 200 sin token y solo con los campos permitidos de
  FR-047); la consulta de salud con componentes sanos y caídos; el registro completo (alta, consulta,
  listado, modificación, deshabilitar, baja y reutilización del código); y los errores clave
  (401, 403, 503, 404, 409, y 422 por host no permitido). MUST NOT repetir lo que ya cubren las pruebas
  automatizadas ni contener secretos. Según el flujo de trabajo de la constitución, la matriz «operación →
  permiso» (FR-001) y esta colección MUST actualizarse en el mismo cambio que añade las operaciones.
- **FR-043**: Esta feature MUST NOT añadir tecnología fuera de la tabla de stack de la constitución: ni
  APScheduler ni trabajos en segundo plano; las llamadas a los componentes usan httpx (ya en el stack) y el
  horario, `zoneinfo` de la biblioteca estándar. MUST respetar los principios de capas (I), separación entre
  modelos y DTOs (II), asincronía (III), documentación en OpenAPI (IV) e idioma (VII); el plan los verifica en
  su «Constitution Check».

**Próximo encendido y estado público de la plataforma**

- **FR-044**: Cada componente del resultado de salud MUST traer `next_start_at`, el **próximo encendido
  programado** de la base de datos. Solo lo trae con valor el componente `database` cuando está `stopped` y
  el horario `DATABASE_SCHEDULE_*` está configurado: el primer instante posterior a la observación de la
  falla en que se abre su ventana (FR-034), en ISO 8601 UTC con `Z`. Se salta los días que no están en
  `DATABASE_SCHEDULE_DAYS` (por ejemplo, el fin de semana) y se convierte a UTC con las reglas de la zona en
  la fecha de ese inicio, no con el desfase del momento de la falla, así que tiene en cuenta los cambios de
  horario de verano: si ese día la hora de inicio no existe porque el reloj se adelanta, es el instante del
  salto; si existe dos veces porque se atrasa, la primera. En cualquier otro caso —otro estado, otro
  componente o sin horario— MUST valer `null`. Se calcula en la agregación, junto con el estado, y se sirve
  tal cual desde la caché.
- **FR-045**: `GET /health/status` MUST publicar sin token el **estado público** de la plataforma, para quien
  no puede comprobar su acceso (historia 6). Va en la raíz del servicio, junto a las rutas del contrato de
  salud y fuera de `/api/v1`, aunque no forma parte del contrato v1; su operación es `get_health_status` y
  cumple las reglas comunes de FR-008 (`Cache-Control: no-store`, etiqueta «Salud», sin esquema de seguridad
  ni `x-required-permission`). Es una comprobación de salud que esta especificación define, así que entra en
  la excepción del principio VIII (FR-002). MUST responder **siempre 200** mientras el proceso atienda HTTP,
  aunque la base de datos esté detenida o caída, el registro no pueda leerse o mailySoft-usuarios no
  responda. MUST NOT autorizar la petición: no llama a `/api/v1/authorization/check` y, si llega una
  cabecera `Authorization`, la ignora (no la valida ni la reenvía). No tiene parámetros; los parámetros de
  consulta desconocidos se ignoran. No es una *probe*: responde 200 aunque todo esté caído y puede provocar
  chequeos de todos los componentes, así que el README MUST indicar que no se usa para liveness ni readiness.
- **FR-046**: El cuerpo MUST ser
  `{"status":"ok"|"degraded"|"down","checked_at":"<ISO 8601 UTC>","components":[{"code":"…","name":"…","kind":"service"|"database"|"frontend","status":"up"|"degraded"|"down"|"stopped"|"unknown","next_start_at":"<ISO 8601 UTC>"|null}]}`
  y MUST salir del **mismo resultado de agregación** que `GET /api/v1/health`, calculado con todas sus reglas
  (entre ellas, FR-011, FR-014 a FR-017, FR-019, FR-036 y FR-044): los mismos componentes, en el mismo orden
  y con los mismos estados, el mismo estado global y el mismo `checked_at`. MUST NOT hacer chequeos propios
  ni aplicar reglas de estado propias. Por eso no incluye los componentes deshabilitados ni
  los eliminados; si el registro no puede leerse, usa la copia en memoria y, si nunca lo leyó, solo trae los
  integrados. `components` nunca es nulo.
- **FR-047**: **Lista cerrada de campos**: el estado público MUST publicar solo `status`, `checked_at` y
  `components` y, de cada componente, solo `code`, `name`, `kind`, `status` y `next_start_at`. MUST NOT
  publicar nunca versiones, commits, fechas de build, entornos, direcciones (`base_url`), hosts o IP,
  latencias, `checks`, códigos de error (`error`) ni `registry_available`, ni ningún campo que se agregue en
  el futuro al resultado de salud si antes no se añade a esta lista revisando esta especificación. Una prueba
  de contrato MUST comprobar, con componentes en todos los estados y con versiones, chequeos y errores en el
  resultado de salud, que la respuesta pública no trae ningún campo fuera de la lista.
- **FR-048**: **Protección contra abuso**: el estado público comparte la caché y la agregación en curso de
  FR-020, con un periodo mínimo de `max(HEALTH_CACHE_SECONDS, 15)` segundos (15 con la configuración por
  defecto). Mientras no hayan pasado esos segundos desde que terminó la última agregación —la haya provocado
  una petición pública o una consulta de salud—, MUST devolver su resultado de inmediato, con sus
  `checked_at` originales, sin esperar ni lanzar chequeos; desde ese instante, o si todavía no hay ningún
  resultado, MUST unirse a la agregación en curso o, si no hay ninguna, lanzar una, cuyo resultado queda en
  la misma caché, y responder dentro del límite de FR-019. Así, por muchas peticiones públicas que lleguen,
  MUST NOT provocar más de una ronda de chequeos por proceso en cada periodo; solo pueden adelantar la
  siguiente una consulta de salud autorizada (con su propio periodo, FR-020) o un cambio en el registro, que
  invalida la caché (FR-020).
- **FR-049**: Las pruebas automatizadas (FR-041) MUST cubrir también `next_start_at` en las dos rutas, con un
  reloj controlable (noches entre semana, fines de semana, instantes límite y una zona con cambio de
  horario), y el estado público: con el API de usuarios caído, con el registro ilegible y nunca leído, con
  componentes deshabilitados y eliminados, su lista cerrada de campos (FR-047) y su periodo mínimo, también
  con `HEALTH_CACHE_SECONDS` en 0 (FR-048).
- **FR-050**: **CORS en las rutas de salud**: `GET /health/live`, `GET /health/ready` y `GET /health/status`
  MUST responder con las mismas cabeceras CORS que el resto de la API para los orígenes de
  `CORS_ALLOWED_ORIGINS`, sin credenciales. Así el Backoffice (maily-backoffice 016) puede consultarlas desde
  el navegador: el estado público en su pantalla de acceso fallido y, si el agregador no responde, la
  comprobación directa de este servicio, de mailySoft-usuarios y de mailySoft-pacientes.
  - Si el Backoffice llega al servicio por un proxy en su mismo origen, ese proxy MUST enrutar también estas
    rutas bajo la URL base del cliente `subscriptions`.
  - Las pruebas MUST verificar las cabeceras con un origen permitido y su ausencia con uno no permitido.

### Key Entities

Los nombres de campo están en inglés (principio VII) y son parte del acuerdo entre servicios: los del
registro, del resultado de salud y del estado público, con maily-backoffice 016; los del contrato v1, además,
con mailySoft-usuarios 016 y mailySoft-pacientes 008.

- **Componente registrado** (tabla `monitored_components`): `id` (UUID), `code`, `name`, `kind` (`service` o
  `frontend`), `base_url`, `live_path`, `ready_path`, `info_path`, `enabled`, `sort_order`, `created_at` y
  `updated_at` (UTC), más la marca de baja lógica con su fecha, que no se publica. Es lo que devuelven las
  operaciones del registro.
- **Componente integrado**: `maily-system-api` («MailySoft System API», `kind` `service`) y `database`
  («Base de datos», `kind` `database`). No se guardan en el registro ni se pueden editar; sus códigos están
  reservados.
- **Resultado de salud** (respuesta de `GET /api/v1/health`): `status` (`ok`, `degraded` o `down`),
  `checked_at`, `registry_available` y `components`. Se compone en cada agregación y solo se guarda en la
  caché en memoria.
- **Componente en el resultado**: `code`, `name`, `kind` (`service`, `database` o `frontend`), `status`
  (`up`, `degraded`, `down`, `stopped` o `unknown`), `latency_ms` (entero o `null`), `checked_at`, `version`,
  `commit`, `build_date` y `environment` (texto, o `unknown`), `checks`, `error` (`null` o un código de
  FR-018) y `next_start_at` (ISO 8601 UTC o `null`; solo tiene valor en la base de datos detenida por
  horario, FR-044). Nunca lleva la dirección del componente.
- **Estado público** (respuesta de `GET /health/status`): `status`, `checked_at` y `components`, cada uno con
  `code`, `name`, `kind`, `status` y `next_start_at`, y nada más (FR-047). Es una vista del mismo resultado de
  salud, sin token y sin datos sensibles; no se guarda aparte.
- **Chequeo**: `name`, `status` (`ok` o `error`), `latency_ms` (entero o `null`) y `error` (`null`,
  `timeout`, `connection_error`, `not_configured` o `unexpected_error`). Es la forma del contrato v1 en `/health/ready`,
  reutilizada en el resultado.
- **Identificación del build** (`/info`): `service`, `version`, `commit`, `build_date` y `environment`.
- **Horario de encendido de la base de datos**: zona, días y horas de inicio y de fin. Es opcional y vive en
  la configuración, no en la base de datos. De él se deducen `stopped` y `next_start_at`.
- **Lista de hosts permitidos**: hosts exactos y sufijos de dominio. Vive en la configuración.
- **Copia del registro en memoria**: la última lectura exitosa del registro, por proceso y sin caducidad.
- **Persona autenticada y permisos `health:*`** *(externos, del API de usuarios)*: quien consulta y los
  permisos `health:read`, `health:write`, `health:update` y `health:delete` del módulo «Salud de servicios»
  (código `health`, tipo Sistema), que crea mailySoft-usuarios 016. Este servicio no los guarda.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Con hasta 20 componentes registrados, aunque cualquiera de ellos esté caído o no responda, la
  consulta de salud responde —una vez concedido el acceso— en menos de `HEALTH_CHECK_TIMEOUT_SECONDS` + 1 s
  (4 s con la configuración por defecto) en el 100 % de las pruebas con la base de datos respondiendo con
  normalidad, y en menos de 2 × `HEALTH_CHECK_TIMEOUT_SECONDS` + 1 s cuando tampoco responde la base.
- **SC-002**: Un componente registrado aparece en la siguiente consulta de salud, sin redesplegar ni
  reiniciar el servicio (0 despliegues para monitorear un microservicio nuevo); lo mismo ocurre al
  modificarlo, deshabilitarlo o eliminarlo.
- **SC-003**: Con el horario configurado, el 100 % de las fallas de la base de datos observadas fuera de la
  ventana se informa como `stopped` y el 100 % de las observadas dentro, como `down`, incluidos los instantes
  límite y los días que difieren entre UTC y la zona configurada; sin horario, el 100 % se informa como
  `down`.
- **SC-004**: El 100 % de las direcciones con un host fuera de la lista permitida, con credenciales, query,
  fragmento u otro esquema, y de las rutas que intentan cambiar de host, se rechaza al registrar o al
  modificar; y 0 llamadas salen hacia un host fuera de la lista vigente, aunque la lista cambie después del
  registro.
- **SC-005**: 0 llamadas a componentes llevan el token de la persona o una cabecera de la petición original,
  y 0 respuestas de salud contienen direcciones, cuerpos crudos, mensajes de excepción o secretos.
- **SC-006**: Ante 50 consultas simultáneas de varias personas, cada componente recibe a lo más una ronda de
  chequeos por proceso y periodo de caché, mientras que el API de usuarios recibe una consulta de permiso por
  cada una (50).
- **SC-007**: `/health/live` responde en menos de 100 ms en el 95 % de las llamadas, también con la base de
  datos caída, y `/health/ready` responde 503 en menos de `HEALTH_READY_TIMEOUT_SECONDS` + 1 s cuando la base
  no responde.
- **SC-008**: En el 100 % de las imágenes construidas con los argumentos de build, `/info` publica ese commit
  y esa fecha, y su versión coincide con la del documento OpenAPI y la de los metadatos del proyecto (una
  sola fuente).
- **SC-009**: Con el registro ilegible después de haberlo leído al menos una vez, el 100 % de las consultas
  responde 200 con los componentes registrados de la copia y `registry_available: false`.
- **SC-010**: El servicio se niega a arrancar en el 100 % de los casos probados con un valor no válido en
  cualquiera de las variables nuevas o con un horario incompleto, y el mensaje nombra la variable sin mostrar
  su valor.
- **SC-011**: La suite existente sigue en verde con solo los ajustes de FR-039 (0 comprobaciones de
  comportamiento modificadas), y `GET /api/v1/dashboard` responde igual que antes de la feature.
- **SC-012**: La colección nueva de Postman se ejecuta en verde de punta a punta contra el servicio real con
  sus simulaciones y cubre todos los casos de FR-042.
- **SC-013**: Con la base de datos detenida por horario, `/health/status` informa `stopped` y el próximo
  encendido correcto en el 100 % de los casos probados —noches entre semana, fines de semana, instantes
  límite y una zona con cambio de horario—, también con mailySoft-usuarios caído o sin poder autorizar, y
  `GET /api/v1/health` trae el mismo `next_start_at`; sin horario, o con la base fallando dentro de su
  ventana, el 100 % de las respuestas trae `next_start_at` en `null`.
- **SC-014**: 0 respuestas públicas contienen campos fuera de la lista permitida (FR-047), verificado por una
  prueba de contrato con componentes en todos los estados y con versiones, chequeos y códigos de error en el
  resultado de salud.
- **SC-015**: `/health/status` responde 200 en el 100 % de las peticiones mientras el proceso atiende —con la
  base de datos detenida o caída, el registro ilegible o el API de usuarios caído— y siempre en menos de
  2 × `HEALTH_CHECK_TIMEOUT_SECONDS` + 1 s (7 s con la configuración por defecto), aun cuando espera una
  agregación.
- **SC-016**: Ante 1 000 peticiones públicas en un minuto, sin consultas autenticadas ni cambios en el
  registro, cada componente recibe a lo más una ronda de chequeos por proceso cada
  `max(HEALTH_CACHE_SECONDS, 15)` segundos (a lo más 4 en ese minuto con la configuración por defecto, y
  también con `HEALTH_CACHE_SECONDS` en 0), y el API de usuarios recibe 0 consultas de permiso.

## Assumptions

### Decisiones tomadas sin preguntar (revisables con /speckit-clarify)

Del contexto común de las cuatro specs:

1. **El agregador vive en maily-system-api**, no en un servicio nuevo.
2. **El registro vive en la base de datos y se administra desde el Backoffice**, no por configuración (de ahí
   la desviación del principio IX que debe justificar el plan, FR-022).
3. **«Detenida por horario» se deduce del horario configurado**, no del estado del servidor en la API de
   Azure, que pediría credenciales.
4. **MailySoft (el frontend que sirve Maily360) se monitorea con su `/healthz/` actual**; su versión queda
   «no disponible» (`unknown`) hasta que Maily360 agregue un `/info`, un pendiente aparte, fuera de estas
   cuatro specs.
5. **Solo el estado actual**: sin historial, uptime ni alertas.
6. **Rutas de salud públicas**, con la excepción registrada en cada constitución (en esta, ya prevista por el
   principio VIII; FR-002).
7. **Sin manifiestos de Kubernetes**: solo el ejemplo de probes del README.

Propias de esta especificación (el contexto no las fijaba):

8. **Códigos de error de componente** (FR-018): lista cerrada definida aquí; el Backoffice los traduce.
9. **«No disponible» es `"unknown"`, no `null`**, en los datos de build, también para la base de datos y para
   los frontends sin ruta de información.
10. **`latency_ms`** es la duración del chequeo principal aunque falle; `null` solo si no se intentó.
11. **Límites de depuración**: 64 KiB por respuesta, 64 caracteres por texto y 20 chequeos por componente.
12. **Los componentes deshabilitados no aparecen** en la consulta de salud (siguen en el registro).
13. **Orden**: primero los integrados; después, `sort_order` y `code`.
14. **`code` y `kind` se pueden modificar**, y el componente resultante se valida como en un alta; los
    códigos de los integrados están reservados (409).
15. **Ventana [inicio, fin) sin margen de arranque**: las fallas en los minutos en que el servidor arranca
    después de la hora de encendido se informan `down`. La alternativa sería un margen configurable.
16. **Formato del horario**: días en inglés como en el runbook y horas `HH:MM`; las cuatro variables juntas o
    ninguna; sin ventanas que crucen la medianoche.
17. **`HEALTH_ALLOWED_HOSTS` no se exige al arrancar**: «obligatoria si hay componentes registrados» se
    interpreta como «sin ella no se registra ni se consulta ninguno», porque comprobar al arrancar si hay
    registrados exigiría leer una base de datos que puede estar detenida.
18. **`registry_available: false` no cambia por sí solo el estado global.**
19. **Caché por proceso, con una sola agregación en curso**, y sin forma de saltarla desde la API.
20. **Las variables de build con un valor no válido impiden arrancar**, como el resto de la configuración; si
    faltan, `unknown`.
21. **La versión publicada no retrocede** de `2.0.0`, sea cual sea la fuente única que elija el plan.
22. **Tiempos en segundos enteros**; el de `/health/ready` se llama `HEALTH_READY_TIMEOUT_SECONDS` (si
    mailySoft-usuarios 016 y mailySoft-pacientes 008 usan otro nombre, el plan los alinea).
23. **Registro con la base de datos caída**: se usa el error vigente del servicio (hoy 500 `internal_error`),
    sin un código nuevo.
24. **Máximo esperado de 50 componentes**, declarado para el listado sin paginar; no se impone un tope.
25. **El estado público vive en `/health/status`** (operación `get_health_status`): en la raíz, junto a las
    rutas del contrato v1 pero fuera de él; usuarios 016 y pacientes 008 no lo implementan.
26. **`code` y `name` se consideran no sensibles**: identifican el componente sin decir cómo alcanzarlo, y por
    eso se publican sin token. Como `name` es texto libre, quien administra el registro no debe escribir en
    él direcciones ni datos internos.
27. **Periodo mínimo de 15 s en la ruta pública** (`max(HEALTH_CACHE_SECONDS, 15)`), aunque la consulta de
    salud use una caché menor o nula: acota los chequeos que pueden provocar las peticiones anónimas sin
    limitar cuántas peticiones se reciben.
28. **El Backoffice consulta `/health/status` sin sesión**, desde su pantalla de comprobación de acceso
    fallida: no envía token y, si lo enviara, se ignoraría (FR-045).
29. **`next_start_at` es el instante en que se abre la ventana**, sin contar los minutos que tarda el servidor
    en arrancar (decisión 15); con un cambio de horario, es el instante del salto si la hora de inicio no
    existe ese día y la primera vez si existe dos veces.

### Dependencias y relación con las otras specs

- **mailySoft-usuarios 016-health-endpoints** (esta spec depende de ella): crea por migración el módulo
  «Salud de servicios» (código `health`, tipo Sistema) y los permisos `health:read`, `health:write`,
  `health:update` y `health:delete`, asignados al rol de sistema `Administrator`, e implementa el contrato v1
  en ese servicio. Como la autorización pasa por `/authorization/check`, en un ambiente real **las seis
  operaciones protegidas no se pueden usar hasta que esos permisos existan** (responden 403). Mientras
  tanto, el desarrollo y las pruebas usan la simulación del API de usuarios, que debe poder conceder y negar
  los cuatro permisos.
- **mailySoft-pacientes 008-health-endpoints**: implementa el contrato v1 en ese servicio, que este agregador
  consume. No bloquea esta spec: hasta que se despliegue, pacientes registrado aparecerá `down` (por ejemplo,
  con `unexpected_status`).
- **maily-backoffice 016-health-dashboard** (depende de esta spec y de usuarios 016): consume
  `GET /api/v1/health` (incluido `next_start_at`) y las operaciones del registro con el cliente que apunta a
  este servicio, y `GET /health/status`, sin sesión, en su pantalla de comprobación de acceso fallida
  (historia 6). Las rutas, los códigos HTTP, los campos y los códigos de error de esta spec son el acuerdo que
  consume; esta spec no depende de él.
- **El contrato de salud v1 es común** a los tres servicios backend (usuarios 016, pacientes 008 y esta
  spec): cualquier cambio de rutas, campos o códigos MUST hacerse en las tres a la vez y avisarse al
  Backoffice. El estado público `/health/status` no forma parte de él: solo lo ofrece este servicio.
- **Orden sugerido**: usuarios 016, pacientes 008 y esta spec en paralelo (aquí, con simulaciones de los otros
  servicios); el Backoffice 016 puede empezar en paralelo con MSW. En ambientes reales, esta spec necesita los
  permisos de usuarios 016.
- **Maily360 (MailySoft v2)** queda fuera de estas cuatro specs: se monitorea como frontend con su
  `/healthz/` actual.

### Limitación conocida

La consulta de salud y el registro dependen de mailySoft-usuarios para autorizar, en cada petición y con
falla cerrada (principio VIII): **si usuarios cae, responden 503 y el panel autenticado del Backoffice no
carga** (tampoco funciona el inicio de sesión del Backoffice). Además, el API de usuarios evalúa los permisos
con datos vigentes de su base de datos (contrato de `/authorization/check`, spec 001 de este repositorio), y
esa base vive en el mismo servidor de Azure que se apaga por horario; por eso, **mientras la base está
detenida por horario, usuarios tampoco puede autorizar y el panel autenticado no carga**. Esa dependencia se
mantiene: el detalle completo (versiones, latencias, chequeos, códigos de error y `registry_available`) solo
se ve cuando usuarios puede autorizar.

**Mitigación** (decisión del responsable, 2026-10-24): el estado público `GET /health/status` (historia 6) no
depende ni de usuarios ni de la base de datos —no pide autorización y responde 200 aunque la base esté
detenida, con la copia en memoria del registro—, y el Backoffice 016 lo muestra en su pantalla de
comprobación de acceso fallida. Así, de noche se ve «Base de datos detenida por horario» y cuándo vuelve
(`next_start_at`), de modo que `stopped` (historia 4) y los componentes de la copia en memoria (historia 5)
sí llegan a verse. Quedan dos huecos: si el proceso se reinició mientras la base estaba detenida, solo
aparecen los componentes integrados hasta que pueda leer el registro; y si este servicio no responde,
tampoco hay estado público. Para esto último se recomienda como trabajo futuro un monitor externo con alertas
(por ejemplo, una prueba de disponibilidad de Azure) que consulte directamente las rutas públicas
`/health/live` y `/health/ready` de cada servicio, que no dependen de la autorización.

### Otros supuestos

- **Fuera de alcance**: historial, uptime, alertas y notificaciones; métricas; manifiestos de Kubernetes;
  cambios en Maily360; la interfaz del Backoffice (spec 016-health-dashboard de maily-backoffice); el monitor
  externo; limitar cuántas peticiones recibe `/health/status` por cliente (FR-048 solo acota los chequeos; un
  límite de peticiones, si hiciera falta, corresponde a la infraestructura); y consultar el estado del
  servidor en Azure.
- **Tiempos coordinados**: el tiempo de `/health/ready` de cada servicio (2 s por defecto) es menor que el
  del agregador (3 s), para que el agregador reciba el 503 con el detalle en vez de agotar su propio tiempo;
  quien opera debe conservar esa relación.
- **Zonas horarias**: `zoneinfo` usa la base de datos de zonas del sistema. En Windows (donde corre la suite
  local) y en las imágenes que no la traen hace falta el paquete de datos `tzdata`; el plan confirma cómo se
  provee y si cuenta como tecnología nueva (son los datos de la IANA, no una tecnología). Con una zona
  configurada y sin esos datos, el servicio no arranca (FR-033).
- **Lista permitida prudente**: conviene listar hosts exactos; un sufijo de una plataforma compartida (por
  ejemplo, `.up.railway.app`) permitiría llamar a aplicaciones de otros clientes de esa plataforma.
- **El componente `database` representa el servidor compartido**: es el mismo servidor de Azure que usan los
  tres servicios, así que su estado explica el `degraded` de los demás cuando se apaga.
- **Reparto de las pruebas**: el horario y `next_start_at` (con un reloj controlable), la copia en memoria,
  el periodo mínimo del estado público y los límites de depuración se verifican con las pruebas
  automatizadas, porque la colección de Postman no puede detener la base de datos ni mover el reloj del
  servicio real.
- **Documentación**: el README se mantiene al día con las rutas (incluido el estado público, que no es una
  *probe*), el registro, la lista permitida, el horario alineado con el runbook y el ejemplo de probes; el
  detalle lo fija el plan.
- **Idioma**: rutas, campos, permisos y códigos en inglés; mensajes, documentación publicada y este documento,
  en español (principio VII).
