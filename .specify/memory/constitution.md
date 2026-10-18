<!--
SYNC IMPACT REPORT
==================
Version change: (plantilla sin ratificar) → 1.0.0
Bump rationale: adopción inicial de la constitución. No hay versión anterior de la que partir.

Origen: se adapta la constitución de `mailySoft-usuarios` (v1.5.0, C:\maily\code\mailySoft-usuarios)
para el servicio MailySoft System API, cuyo primer dominio es la gestión de suscripciones (planes).
Se conservan el stack, la arquitectura en capas, el idioma, las pruebas, Alembic, Docker, Postman y
el flujo de Spec Kit; cambia el dominio y la forma de controlar el acceso.

Principios añadidos (todos nuevos):
  - I. Arquitectura en Capas Estricta
  - II. Separación entre Modelos ORM y DTOs
  - III. Asincronía de Extremo a Extremo
  - IV. Contratos de API Documentados con OpenAPI
  - V. Pruebas Automatizadas con pytest
  - VI. Esquema de Datos Versionado con Alembic
  - VII. Idioma: Código en Inglés, Textos para Personas en Español
  - VIII. Control de Acceso Delegado al API de Usuarios
  - IX. Integraciones con Otros APIs de MailySoft
Principios modificados / eliminados: no aplica (versión inicial)
Secciones añadidas: Stack Tecnológico y Restricciones; Flujo de Desarrollo y Puertas de Calidad;
Governance

Diferencias deliberadas respecto a mailySoft-usuarios v1.5.0:
  - El token de Auth0 NO se verifica aquí: se reenvía al API de usuarios, que lo verifica y decide
    el permiso (decisión del responsable, 2026-10-17). Por eso desaparecen PyJWT, el JWKS, la
    configuración de Auth0 y el cliente de la API de administración de Auth0.
  - Se añade el Principio IX (integraciones con el API de usuarios y el API de clínicas).
  - El listado de suscripciones se devuelve completo, sin paginar (excepción del Principio IV ya
    prevista en la referencia, ahora declarada para este recurso).
  - La baja de una suscripción es lógica, con un cuarto estatus «Eliminada» (decisión del
    responsable, 2026-10-17).
  - El número de clínicas por plan lo aporta el API de clínicas; este servicio no lo almacena
    (decisión del responsable, 2026-10-17).
  - Principio VII: el servicio es nuevo y no hay código previo que traducir, así que se descarta el
    TODO(COMMENT_LANGUAGE) de la referencia y se conserva «SHOULD» para los comentarios en inglés.

Supuestos NO confirmados por el responsable (revisar; cambiarlos es una enmienda PATCH o MINOR):
  - Los permisos siguen la convención `<recurso>:<acción>` de la referencia: `subscriptions:read`,
    `subscriptions:write` (crear), `subscriptions:update` y `subscriptions:delete`.
  - Las decisiones de permiso no se cachean (igual que la referencia).
  - Si el API de clínicas no responde, el conteo de clínicas se omite de forma explícita y el resto
    de la suscripción se sigue devolviendo.
  - Los seis planes de los pantallazos (Básico, Pro, Premium, Enterprise, Solo, Legacy full) son
    ejemplos, no datos iniciales obligatorios.

TODOs diferidos (a resolver en la primera especificación, no son huecos de esta constitución):
  - Qué impide cada estatus (Inactiva: por ejemplo «no se ofrece a clientes nuevos»; Bloqueada) y
    si una suscripción con clínicas asignadas puede bloquearse o eliminarse.
  - Contrato del API de clínicas (operación que devuelve el conteo por plan) y moneda y periodo de
    cobro de los importes.
  - Estructura de lo que incluye cada plan (consultorios, usuarios y funciones).
  - El API de usuarios debe tener dado de alta el catálogo `subscriptions:*` y publicar su
    operación de consulta de permisos (spec 008 de mailySoft-usuarios) antes de integrarse.

Plantillas revisadas (no se modifican aquí): .specify/templates/* leen la constitución en tiempo
de ejecución.
-->

# MailySoft System API Constitution

Servicio REST de MailySoft cuyo primer dominio es la gestión de **suscripciones** (planes que se
asignan a las clínicas: precio, límites y funciones incluidas, y su estatus). Es una API distinta
del API de usuarios, roles y permisos: consulta a ese API para decidir quién puede operar y no
administra identidades.

## Core Principles

### I. Arquitectura en Capas Estricta

El código se organiza en las capas Routers → Services → Repositories → Database, apoyadas por
`src/models/` (modelos ORM) y `src/dtos/` (esquemas de API). Reglas no negociables:

- Todo el código fuente de la aplicación MUST residir en la carpeta `src/` en la raíz del
  repositorio, con una subcarpeta por capa: `src/routers/`, `src/services/`,
  `src/repositories/`, `src/integrations/`, `src/database/`, `src/models/` y `src/dtos/`.
  Fuera de `src/` solo se permiten pruebas (`tests/`), migraciones (`alembic/`), configuración,
  Docker y documentación.
- Los **Routers** MUST limitarse a recibir la petición HTTP, validar con DTOs, invocar Services
  y serializar la respuesta. Los Routers MUST NOT acceder a la base de datos, a sesiones de
  SQLAlchemy ni a Repositories directamente.
- Los **Services** MUST contener toda la lógica de negocio (unicidad, transiciones de estatus,
  reglas de baja y de bloqueo, validaciones de dominio) y coordinar uno o más Repositories y
  clientes de integración.
- Los **Repositories** MUST encapsular toda la persistencia: son la única capa que construye
  consultas y lee/escribe modelos ORM. MUST NOT contener reglas de negocio.
- Los clientes de otros sistemas (el API de usuarios y el API de clínicas, ver Principios VIII y
  IX) MUST residir en `src/integrations/` y MUST encapsular toda la comunicación con ese sistema
  (llamadas HTTP, traducción de sus respuestas y de sus fallos). Solo los invocan los Services y
  las dependencias de seguridad (Principio VIII); MUST NOT importar Routers, Services,
  Repositories, modelos ni DTOs, y MUST NOT contener reglas de negocio.
- La capa **Database** MUST centralizar la configuración del engine async, la fábrica de
  sesiones y su ciclo de vida (inyectado vía dependencias de FastAPI).
- Las dependencias MUST fluir en un solo sentido (Router → Service → Repository o Integración →
  Database); una capa inferior MUST NOT importar una superior.

**Rationale**: El aislamiento de responsabilidades permite probar cada capa por separado,
sustituir la persistencia o un sistema externo sin tocar la API y mantener la lógica de negocio
en un único lugar.

### II. Separación entre Modelos ORM y DTOs

- `src/models/` MUST contener solo modelos SQLAlchemy 2.0 que representan tablas y relaciones;
  MUST NOT concentrar reglas de negocio.
- `src/dtos/` MUST contener los esquemas Pydantic v2 de entrada y salida de la API, separados de
  los modelos de persistencia (p. ej. `SubscriptionCreate`, `SubscriptionUpdate`,
  `SubscriptionRead`).
- Los Routers MUST validar la entrada y serializar la salida exclusivamente con DTOs; MUST NOT
  exponer entidades ORM en respuestas HTTP. La conversión ORM → DTO MUST hacerse de forma
  explícita (p. ej. `model_validate` con `from_attributes=True`).
- Los DTOs de salida MUST NOT incluir campos internos o sensibles que no formen parte del
  contrato publicado. Los datos que pertenecen a otro sistema (p. ej. el número de clínicas) se
  modelan como campos de solo lectura del DTO de salida, no como columnas propias.

**Rationale**: Desacoplar el contrato público del esquema de base de datos evita fugas de datos
y permite evolucionar la persistencia sin romper a los consumidores.

### III. Asincronía de Extremo a Extremo

- Toda operación de I/O (base de datos, llamadas HTTP a otras APIs, archivos, red) MUST ser
  asíncrona usando `async`/`await`.
- El acceso a PostgreSQL MUST usar SQLAlchemy 2.0 en modo async con el driver `asyncpg`
  (`AsyncEngine`, `AsyncSession`).
- La comunicación con otras APIs MUST realizarse con un cliente HTTP asíncrono (httpx); las
  llamadas bloqueantes (p. ej. `requests`, drivers síncronos) MUST NOT usarse en el camino de una
  petición.
- Cuando una librería solo ofrezca API síncrona, su uso MUST aislarse (p. ej.
  `run_in_threadpool`) y justificarse en el plan de la feature.

**Rationale**: Un único hilo de eventos bloqueado degrada a todas las peticiones concurrentes;
la asincronía consistente es requisito de escalabilidad del servicio, que además depende de
llamadas de red en cada petición.

### IV. Contratos de API Documentados con OpenAPI

- Cada endpoint MUST estar documentado en el esquema OpenAPI generado por FastAPI, con
  `response_model`, códigos de estado, `tags` (p. ej. `subscriptions`) y descripciones.
- Las APIs MUST seguir convenciones REST: recursos en plural, verbos HTTP semánticos
  (GET, POST, PUT/PATCH, DELETE) y códigos de estado coherentes (201 al crear, 204 al eliminar
  sin cuerpo, 401 sin identidad válida, 403 sin permiso, 404 si no existe, 409 ante conflictos
  de unicidad o de estado, 422 ante validación, 503 si una dependencia obligatoria no responde).
- Los errores MUST devolverse con un formato de cuerpo consistente y documentado.
- Los listados MUST soportar paginación. Excepción: un catálogo pequeño y acotado por diseño
  puede devolverse completo, sin paginar, solo si la especificación de la feature lo declara
  expresamente, fija un máximo esperado de elementos (no superior a 500) y define un orden
  determinista. Si el catálogo supera ese máximo, el listado MUST pasar a paginarse, lo que es un
  cambio incompatible del contrato y se versiona.
- El listado de suscripciones es un caso de esa excepción: MUST devolver todas las suscripciones
  vigentes (Activa, Inactiva y Bloqueada), sin paginar, cada una con su estatus como objeto con
  `id` y `name`. Las suscripciones Eliminadas no aparecen y se comportan como inexistentes (404 al
  consultarlas). La especificación MUST fijar el máximo y el orden.
- Los cambios incompatibles en un contrato publicado MUST versionarse (p. ej. prefijo
  `/api/v1`) y declararse en la especificación de la feature.

**Rationale**: El contrato OpenAPI es la fuente de verdad para los consumidores del servicio y
para la generación de pruebas de contrato. Paginar evita respuestas sin límite; la excepción acota
los catálogos pequeños, donde paginar añade complejidad sin beneficio.

### V. Pruebas Automatizadas con pytest

- Toda funcionalidad MUST tener pruebas automatizadas con `pytest` (y soporte async,
  p. ej. `pytest-asyncio`/`anyio`).
- Los Services MUST tener pruebas unitarias de sus reglas de negocio con Repositories y clientes
  de integración sustituidos por dobles de prueba.
- Cada endpoint MUST tener pruebas de integración/contrato contra la API (cliente HTTP async)
  que verifiquen códigos de estado y forma de los DTOs.
- Las pruebas de Repositories MUST ejecutarse contra PostgreSQL 17 real (contenedor Docker),
  no contra un motor sustituto como SQLite.
- Las pruebas automatizadas MUST NOT llamar al API de usuarios ni al API de clínicas reales: usan
  simulaciones que reproducen sus contratos, incluidos sus fallos (sin permiso, token rechazado,
  tiempo agotado, servicio caído).
- Una prueba MUST recorrer las rutas de la API y fallar si alguna carece de permiso declarado
  (Principio VIII) y no es una de las excepciones.
- Las colecciones de Postman (ver «Stack Tecnológico y Restricciones») complementan, sin
  sustituir, las pruebas de pytest: MUST limitarse a recorridos de punta a punta contra el
  servicio real y a los errores clave de cada recurso, y MUST NOT repetir las pruebas
  unitarias ni las de Repositories. Una colección en verde no exime de ejecutar la suite de
  pytest.
- La suite completa MUST pasar antes de integrar cambios en `main`.

**Rationale**: Las suscripciones determinan qué puede usar cada clínica y cuánto paga; los errores
deben detectarse antes de desplegar. Probar con simulaciones mantiene la suite rápida,
reproducible y sin depender de servicios ajenos. Las colecciones de Postman añaden una
comprobación desde fuera del proceso, contra el contenedor real.

### VI. Esquema de Datos Versionado con Alembic

- Todo cambio en el esquema de base de datos MUST realizarse mediante una migración de
  Alembic revisada y versionada en el repositorio; MUST NOT aplicarse DDL manual.
- Las migraciones MUST ser reversibles (`downgrade` implementado) salvo justificación explícita.
- Los modelos en `src/models/` MUST mantenerse consistentes con las migraciones.
- Los datos iniciales (catálogos de estatus y, si la especificación los exige, suscripciones
  iniciales) MUST cargarse mediante migraciones, no con scripts manuales.
- El estatus de una suscripción MUST salir de un catálogo en base de datos
  (`subscription_statuses`) con al menos: 1 Activa, 2 Inactiva, 3 Bloqueada y 4 Eliminada. Los
  estatus del sistema se reconocen por su identificador, no por su nombre, y no se eliminan ni se
  renumeran. La baja de una suscripción es lógica: su fila se conserva con estatus Eliminada
  porque hay clínicas que la referencian.
- Los importes (precios) MUST guardarse y transportarse con tipos decimales exactos (`NUMERIC`
  en la base de datos y `Decimal` en Python); MUST NOT usarse `float`. La moneda y el periodo de
  cobro los fija la especificación.
- El esquema vigente (el desplegado) es el que resulta de aplicar las migraciones. Todo cambio
  de esquema MUST declararse en la especificación y en el `data-model.md` de la feature que lo
  introduce, indicando en qué se diferencia del esquema vigente anterior.
- `project-definition/DATA_SCHEMA.md` es el **esquema objetivo** del proyecto: reúne las
  estructuras (tablas, restricciones, índices y datos iniciales) que exigen las especificaciones.
  MUST crearse con la primera especificación que defina datos y mantenerse al día: toda
  especificación o plan que cambie una regla de datos MUST reflejarla en ese archivo, marcada con
  un comentario `-- [spec NNN-nombre]`.
- Alembic MUST configurarse para operar con el engine async.

**Rationale**: Un esquema reproducible y versionado garantiza entornos idénticos en
desarrollo, pruebas y producción. Separar el esquema vigente (migraciones) del objetivo
(`DATA_SCHEMA.md`) permite especificar los cambios de datos antes de implementarlos sin perder la
trazabilidad de qué está desplegado. La baja lógica y los decimales exactos protegen el historial
y la facturación.

### VII. Idioma: Código en Inglés, Textos para Personas en Español

- Todos los identificadores del código (clases, funciones, métodos, variables, constantes y
  módulos) MUST estar en inglés.
- Los nombres de campos y parámetros de la API y los códigos de error MUST estar en inglés
  (p. ej. `status`, `monthly_price`, `subscription_not_found`).
- Los mensajes dirigidos a personas (validaciones, errores y confirmaciones que devuelve la API),
  la documentación publicada de la API (descripciones y ejemplos de OpenAPI) y los documentos del
  proyecto (especificaciones, planes y guías) MUST estar en español.
- Los comentarios y docstrings del código SHOULD escribirse en inglés; toda excepción MUST
  justificarse en la revisión.

**Rationale**: Los consumidores técnicos de la API dependen de nombres y códigos estables y en un
único idioma, mientras que las personas que usan las aplicaciones necesitan mensajes que entiendan.
Separar ambos evita mezclarlos y hace comprobable cada regla.

### VIII. Control de Acceso Delegado al API de Usuarios

- Toda operación de la API MUST exigir un token de acceso (`Authorization: Bearer …`) emitido por
  el proveedor de identidad (Auth0) y el permiso que le corresponde. Las únicas excepciones son la
  documentación publicada (`/docs`, `/redoc`, `/openapi.json`) y las comprobaciones de salud, si
  la especificación las define.
- Este servicio MUST NOT verificar el token por sí mismo ni comunicarse con Auth0: MUST reenviar
  el token recibido, sin modificarlo, al API de usuarios y MUST aceptar como única autoridad su
  respuesta sobre la identidad y el permiso. El contrato que se consume (la operación de consulta
  de permisos de la persona autenticada) MUST documentarse en la especificación de la feature.
- La decisión MUST tomarse por cada petición, con una consulta al API de usuarios por el permiso
  exacto de la operación, y MUST NOT cachearse: un bloqueo o un cambio de roles surte efecto en la
  siguiente petición. La comprobación MUST ocurrir antes de validar la solicitud o buscar el
  recurso.
- Si el API de usuarios rechaza el token, la petición MUST rechazarse con 401; si responde que no
  hay permiso, con 403; si no responde, agota el tiempo de espera o contesta algo inesperado, con
  503. En cualquier duda MUST fallar cerrado: nunca se ejecuta la operación.
- Cada operación MUST declarar el permiso que exige con la extensión OpenAPI `x-required-permission`
  y con el esquema de seguridad `BearerAuth`. Los nombres de los permisos siguen el formato
  `recurso:acción` en minúsculas y, para las suscripciones, son `subscriptions:read` (leer),
  `subscriptions:write` (crear), `subscriptions:update` (actualizar y cambiar de estatus) y
  `subscriptions:delete` (eliminar).
- La lista de operaciones y de permisos puede ampliarse sin enmendar esta constitución: basta
  con añadir la operación a la matriz «operación → permiso» de la especificación correspondiente,
  declarar el permiso en la ruta y darlo de alta en el catálogo del API de usuarios, que es su
  dueño. Una ruta sin permiso declarado que no sea una excepción MUST hacer fallar la prueba de
  cobertura (Principio V).
- La autenticación y la autorización MUST implementarse como dependencias de FastAPI en
  `src/security.py`, aplicadas por los Routers; la decisión de permisos MUST pasar por un Service
  que use el cliente de `src/integrations/`.
- Los tokens, las contraseñas y los secretos MUST NOT guardarse en la base de datos ni aparecer en
  respuestas, mensajes de error ni registros.

**Rationale**: Un único servicio decide la identidad y los permisos de todo el ecosistema; repetir
esa lógica aquí duplicaría configuración y criptografía y permitiría que dos servicios discrepen.
Consultar en cada petición y fallar cerrado hace que un bloqueo surta efecto de inmediato, y
declarar el permiso en cada ruta hace comprobable que ninguna operación quedó abierta.

### IX. Integraciones con Otros APIs de MailySoft

- Los datos que pertenecen a otro sistema MUST consultarse a ese sistema y MUST NOT copiarse ni
  almacenarse aquí. En particular, el número de clínicas de una suscripción lo aporta el API de
  clínicas en cada lectura; esta base de datos no guarda clínicas ni su asignación a planes.
- Toda llamada a otro API MUST ser asíncrona, tener un tiempo máximo de espera total y MUST
  NOT reintentarse de forma automática si no es idempotente. Las direcciones, los tiempos de espera
  y las credenciales de cada API MUST provenir de variables de entorno.
- Las fallas de una dependencia MUST traducirse a los errores propios del servicio (con un código
  en inglés y un mensaje en español); MUST NOT filtrarse al cliente su cuerpo de error, sus
  direcciones internas ni sus credenciales.
- La disponibilidad de los datos propios de las suscripciones MUST NOT depender de una
  dependencia que solo aporta datos complementarios: si el API de clínicas no responde, la
  suscripción se devuelve igualmente con el conteo omitido de forma explícita (p. ej. `null`), sin
  inventar un cero. La especificación MUST definir esa degradación. La excepción es el control de
  acceso, que siempre falla cerrado (Principio VIII).
- Cada integración MUST tener su contrato consumido documentado en la especificación de la feature
  que la introduce (operaciones, formato de respuesta y errores esperados) y su simulación en las
  pruebas (Principio V).

**Rationale**: Copiar datos ajenos obliga a sincronizarlos y los deja desactualizados; una caída de
un servicio secundario no debe tumbar el catálogo de planes, pero una duda sobre los permisos nunca
debe abrir una operación.

## Stack Tecnológico y Restricciones

| Ámbito                              | Tecnología obligatoria                                              |
|-------------------------------------|---------------------------------------------------------------------|
| Lenguaje                            | Python 3.14 o superior                                              |
| Framework web                       | FastAPI                                                             |
| Servidor de aplicación              | uvicorn (ASGI)                                                      |
| Base de datos                       | PostgreSQL 17                                                       |
| ORM                                 | SQLAlchemy 2.0 (async) con asyncpg                                  |
| Migraciones                         | Alembic                                                             |
| Validación, DTOs y configuración    | Pydantic v2 (con pydantic-settings)                                 |
| Pruebas                             | pytest (con pytest-asyncio y python-dotenv)                         |
| Pruebas de API de punta a punta     | Postman (colecciones v2.1) con Newman                               |
| Documentación de APIs               | OpenAPI (generado por FastAPI)                                      |
| Comunicación con otras APIs         | Asíncrona (async/await)                                             |
| Cliente HTTP                        | httpx (asíncrono; en el servicio y en las pruebas de la API)        |
| Identidad                           | Auth0 emite los tokens; este servicio no los verifica ni lo consulta |
| Autorización                        | API de usuarios de MailySoft, consultada con httpx                  |
| Gestión de dependencias             | uv (con `uv.lock`)                                                  |
| Contenerización                     | Docker                                                              |
| Metodología                         | GitHub Spec Kit                                                     |
| IDE de referencia                   | Visual Studio Code                                                  |

Restricciones adicionales:

- El servicio MUST ejecutarse en un contenedor Docker; el entorno local MUST poder levantarse
  (servicio + PostgreSQL 17) con Docker Compose.
- La configuración (cadena de conexión, credenciales, direcciones y tiempos de espera de los otros
  APIs) MUST provenir de variables de entorno validadas al arrancar; los secretos MUST NOT
  versionarse.
- Si falta una variable obligatoria (p. ej. la dirección del API de usuarios), el servicio MUST
  NOT arrancar y MUST indicar cuál falta sin mostrar secretos.
- pytest sigue siendo el marco principal de pruebas y la puerta de calidad; las colecciones de
  Postman lo complementan y NO lo sustituyen (ver Principio V).
- Las colecciones de Postman, sus entornos y sus archivos de datos MUST residir en
  `tests/postman/` (`collections/`, `environments/`, `data/` opcional y `reports/`, esta última
  fuera de Git), de acuerdo con la regla de que las pruebas viven en `tests/`.
- La pila de las pruebas de punta a punta MUST ser aislada (otro proyecto de Compose, con base de
  datos desechable y sin puertos publicados salvo el de la API en `127.0.0.1`) y MUST sustituir el
  API de usuarios y el API de clínicas por simulaciones.
- Node.js y npm MUST usarse únicamente como herramientas de desarrollo para instalar y ejecutar
  Newman (paquete npm `newman`); MUST NOT incluirse en la imagen de la aplicación ni ser
  dependencia del servicio.
- Las ejecuciones de una colección MUST hacerse sin iniciar sesión en Postman y sin subir
  resultados a servicios externos, y MUST apuntar a una base de datos dedicada a pruebas, nunca
  a datos reales.
- Las colecciones y los entornos de Postman MUST NOT contener secretos (aplica la regla anterior
  sobre secretos no versionados). Un bloque de autenticación Bearer que solo referencia una
  variable (p. ej. `{{accessToken}}`), rellenada al ejecutar con un token que acepta la
  simulación del API de usuarios, no es un secreto; un token escrito en el archivo sí lo es.
- Sustituir o añadir una tecnología fuera de esta tabla MUST requerir una enmienda de esta
  constitución.

## Flujo de Desarrollo y Puertas de Calidad

- Toda feature MUST seguir el flujo de Spec Kit: `/speckit-specify` → `/speckit-clarify`
  (cuando haya ambigüedad) → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`.
- El plan de cada feature MUST incluir una verificación explícita ("Constitution Check") contra
  los principios I–IX; cualquier desviación MUST quedar justificada en la sección de
  complejidad del plan.
- Estructura del repositorio obligatoria (ver Principio I): código de la aplicación en `src/`
  (`src/routers/`, `src/services/`, `src/repositories/`, `src/integrations/`, `src/database/`,
  `src/models/`, `src/dtos/`), pruebas en `tests/` (las colecciones de Postman, en
  `tests/postman/`) y migraciones en `alembic/`.
- Cada cambio integrado en `main` MUST cumplir: suite de pytest en verde, migraciones aplicables
  desde cero, esquema OpenAPI generado sin errores, prueba de cobertura de permisos en verde y
  revisión de cumplimiento de capas.
- Si cambia la API (operaciones añadidas, quitadas o modificadas), la colección de Postman y la
  matriz «operación → permiso» MUST actualizarse en el mismo cambio.

## Governance

- Esta constitución prevalece sobre cualquier otra práctica o guía del proyecto. En caso de
  conflicto, rige este documento.
- **Enmiendas**: se proponen mediante `/speckit-constitution`, deben documentar el motivo y el
  impacto (Sync Impact Report), ser revisadas y aprobadas por el responsable del proyecto, e
  incluir un plan de migración cuando afecten código existente.
- **Versionado** (semántico):
  - MAJOR: eliminación o redefinición incompatible de principios o reglas de gobierno.
  - MINOR: nuevo principio o sección, o ampliación material de una guía existente.
  - PATCH: aclaraciones, redacción o correcciones sin cambio semántico.
- **Cumplimiento**: toda revisión de código y todo plan MUST verificar el cumplimiento de esta
  constitución; la complejidad adicional MUST justificarse. `project-definition/` contiene la
  guía de referencia de datos para el desarrollo.

**Version**: 1.0.0 | **Ratified**: 2026-10-17 | **Last Amended**: 2026-10-17
