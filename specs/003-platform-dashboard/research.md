# Investigación (Fase 0): Dashboard de Plataforma

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Fecha**: 2026-10-18

Aquí se resuelven las incógnitas técnicas del plan. No quedan marcadores `NEEDS CLARIFICATION`: las
decisiones de negocio ya están en la especificación y en su sesión de aclaraciones. Lo marcado como
**Evidencia** se comprobó con un experimento en el entorno del proyecto (Python 3.15.0, FastAPI
0.143.3, Pydantic 2.14.1, Starlette 1.8.0, httpx 0.28.1); el resto se leyó del código existente.

## Resumen de decisiones

| Id | Tema | Decisión |
|---|---|---|
| R1 | De dónde salen los datos | Un puerto `DashboardSource` en `src/integrations/` con cinco consultas independientes; en la Fase 1 lo implementa `DummyDashboardSource` (datos fijos en el código) |
| R2 | Reglas de negocio | El Service fija el tope (10), el valor por defecto, el orden y el desempate, y convierte la falla de una fuente en `null` |
| R3 | Lectura de `limit` | Análisis manual y estricto (solo dígitos, sin repetidos), no `Query(int)` de Pydantic |
| R4 | Permiso antes de `limit` | `protected("dashboard:read")` de siempre; la dependencia de seguridad se resuelve antes que cualquier validación |
| R5 | Configuración | `DashboardSettings` con validador textual estricto; no `Literal[3, 5, 10]` |
| R6 | Validación al arrancar y aviso de datos ficticios | En `lifespan`, junto a la configuración existente; el aviso rompe una aserción antigua (FR-033b) |
| R7 | Sin caché | `Cache-Control: no-store` solo en la respuesta 200 |
| R8 | DTOs de salida | Campos obligatorios y anulables; fecha normalizada a UTC; estatus de clínica propio |
| R9 | Ruta y versión | `GET /api/v1/dashboard`; la versión publicada sigue en `1.0.0` |
| R10 | Datos ficticios | 12 clínicas fijas y conteos derivados del mismo conjunto |
| R11 | Pruebas sin servicios reales | Sin base de datos; la simulación del API de usuarios ya admite `dashboard:read` |
| R12 | Colección de Postman | Una colección nueva, de punta a punta, con el entorno `e2e` existente |
| R13 | Ajustes a pruebas existentes | Cuatro ajustes mínimos, todos de FR-033; ninguno cambia lo que se verifica de suscripciones |
| R14 | Esquema de datos | Sin cambios: ni tablas, ni migraciones, ni `DATA_SCHEMA.md` |
| R15 | Observabilidad y privacidad | Registros en inglés sin token ni detalles de las fuentes; ningún dato personal en los registros ni en la respuesta |

---

## R1. De dónde salen los datos: el puerto `DashboardSource` y su implementación ficticia

**Decisión**. `src/integrations/dashboard_source.py` define el puerto (un `Protocol`) y los registros que
intercambia (`dataclass` congeladas, sin Pydantic ni FastAPI). Cinco consultas asíncronas, cada una con
`token` como primer argumento:

| Consulta | Devuelve | Unidad de falla |
|---|---|---|
| `clinic_counts(token)` | `ClinicCounts(total, active, trial)` | los tres conteos de clínicas |
| `recent_clinics(token, limit)` | hasta `limit` `ClinicRecord`, de la más nueva a la más antigua | la lista de recientes |
| `doctors_total(token)` | `int` | el total de doctores |
| `patients_total(token)` | `int` | el total de pacientes |
| `users_total(token)` | `int` | el total de usuarios |

Cualquiera puede lanzar `DashboardSourceUnavailable` (nueva, en `src/integrations/errors.py`). El puerto
también expone `is_dummy: bool`. La implementación de la Fase 1 es `DummyDashboardSource`
(`src/integrations/dummy_dashboard_source.py`): datos fijos en el código, sin red ni base de datos,
configurable por constructor para las pruebas (otro conjunto de clínicas, o todo en cero).

**Por qué**.

- La spec exige que el indicador afectado sea `null` y el resto siga (FR-027). Eso obliga a que las
  consultas sean **independientes**: una consulta única `get_summary()` perdería todo el dashboard con
  una sola falla.
- `clinic_counts` y `recent_clinics` son consultas distintas aunque hoy salgan del mismo sitio: cuando
  exista el API de clínicas podría contestar una y fallar la otra, y el contrato ya lo admite
  (Aclaración 1: la lista es `null`, no `[]`).
- Cuando lleguen los APIs reales, solo se sustituye el objeto que cumple el puerto (FR-025): el Service,
  el Router, los DTOs y el contrato no cambian.
- El `token` ya viaja hasta el Service como en las suscripciones (`BearerTokenDep`). Hoy lo ignora la
  implementación ficticia; los clientes reales lo reenviarán, como hace `ClinicsApiClient.get_counts`.
  Incluirlo ahora evita cambiar la firma de todo el camino cuando se conecte el primer API real.
- Vive en `src/integrations/` porque ocupa el lugar de los clientes de otros sistemas (Principio I). Cumple
  las reglas de esa capa: solo `dataclass` y biblioteca estándar, nada de `fastapi`, `src.dtos`,
  `src.models` ni `sqlalchemy` (`tests/unit/test_layering.py` lo vigila).

**Alternativas rechazadas**.

- *Los datos ficticios dentro del Service*: mezclaría datos de relleno con las reglas de negocio y obligaría
  a tocar el Service al conectar las fuentes reales.
- *Una consulta por indicador (seis)*: separar total, activas y en prueba no aporta nada; vienen del mismo
  conteo y fallan juntos.
- *Guardar los datos ficticios en la base de datos*: prohibido por FR-020 (sin tablas ni migraciones).
- *Un cliente HTTP ficticio contra un servidor ficticio*: añade piezas sin beneficio en la Fase 1.

**Nota para las especificaciones futuras**. Cuando se conecte un API real, esa especificación documentará su
contrato consumido (Principio IX) y añadirá el tiempo máximo de espera y la traducción de sus fallos a
`DashboardSourceUnavailable`. Esta feature no define ningún API nuevo.

## R2. Reglas de negocio en el Service

**Decisión**. `DashboardService(source, default_limit)` tiene un único método,
`get(token, requested_limit) -> DashboardView`:

1. **Cantidad efectiva** (FR-010 a FR-012): `MAX_RECENT_CLINICS = 10` (constante, no configurable);
   `requested_limit is None` → `default_limit`; si no, `min(requested_limit, 10)`. El Router solo le pasa
   `None` o un entero mayor o igual a 1 (R3).
2. **Cinco consultas a la vez** con `asyncio.gather`, cada una envuelta para convertir
   `DashboardSourceUnavailable` en `None` (y registrar un aviso sin detalles, R15). Cualquier otra excepción
   **no** se traga: es un error de programación y responde 500.
3. **Orden y corte** (FR-015): aunque la fuente ya devuelva la lista ordenada y cortada (así lo exige su
   contrato, [data-sources.md](contracts/data-sources.md)), el Service la vuelve a ordenar con un
   ordenamiento estable en dos pasadas (primero por identificador ascendente y luego por fecha de creación
   descendente) y la corta a la cantidad efectiva. Es barato (como mucho 10 elementos) y hace que la regla
   no dependa de que cada fuente futura la cumpla.
4. Devuelve un `DashboardView` (dataclass) con los seis conteos y la lista, cada uno `None` si su fuente
   falló. No fuerza ceros: un `0` y un `[]` son lo que contestó la fuente.

**Por qué**. Es lógica de negocio, así que va en la capa de Services (Principio I). El Service no importa
`fastapi` ni `sqlalchemy` (regla de la capa).

**Nota sobre el orden**. `sorted(..., reverse=True)` conserva la estabilidad (los elementos con la misma
clave mantienen su orden previo), por lo que la segunda pasada respeta el orden por identificador de la
primera. Los `UUID` se comparan por su valor entero, que coincide con el orden alfabético de su forma
canónica en minúsculas.

## R3. Lectura de `limit`: análisis manual y estricto

**Decisión**. Una dependencia del Router (`requested_limit`) lee el valor **crudo** de la cadena de
consulta con `request.query_params.getlist("limit")` y aplica estas reglas:

| Entrada | Resultado |
|---|---|
| sin `limit` | `None` (rige el valor por defecto) |
| más de un `limit` | 422 |
| `limit` que no es solo dígitos ASCII (`abc`, vacío, `5.5`, `5.0`, `1e1`, `+3`, `-1`, ` 3`, `1_0`) | 422 |
| solo dígitos que valen 0 (`0`, `000`) | 422 |
| solo dígitos, 1 a 18 cifras significativas | ese entero |
| solo dígitos, más de 18 cifras significativas | un entero enorme fijo (`10**18`): solo importa que supera el máximo |

Los ceros a la izquierda se descartan antes de contar cifras (`007` vale 7). El 422 se lanza como
`RequestValidationError` con un error de estilo Pydantic (`type: "int_parsing"`, `loc: ("query", "limit")`),
para que el manejador existente produzca el cuerpo uniforme `validation_error` con `errors[]` y el mensaje
en español del bloque `dashboard` de `VALIDATION_MESSAGES` (R15; sin repetir el valor recibido).

**Por qué no `Query(int, ge=1)`**. **Evidencia** (experimento con `TypeAdapter` y con una ruta real):

- Pydantic acepta formas que la spec manda rechazar: `5.0` → 5, `+3` → 3, ` 3 ` → 3, `03` → 3 y `1_0` →
  10. La spec dice que un decimal (`5.5`, y por coherencia `5.0`) es 422.
- Rechaza una cifra de miles de dígitos con `int_parsing_size` (422), cuando la spec exige que **cualquier
  entero mayor que 10, por grande que sea, devuelva 10** (FR-011). Un `limit` de 5 000 dígitos cabe en una
  URL de 16 KB.
- Con un parámetro escalar, Starlette se queda con el **último** valor repetido: no hay forma de detectar
  `limit=3&limit=5` sin mirar la petición.

**El contrato sigue diciendo "entero"**. FastAPI no documenta un parámetro que no declara el endpoint, así
que el Router lo añade al OpenAPI con `openapi_extra={"parameters": [...]}` (esquema `integer`, `minimum:
1`, descripción en español con el tope y el valor por defecto). **Evidencia**: en una ruta de prueba con el
mismo montaje, el OpenAPI generado publica `limit` como `integer` con `minimum: 1` junto a
`x-required-permission` (el endpoint no declara otros parámetros, así que no hay nada que fusionar).
`protected()` ya devuelve un `openapi_extra` con `x-required-permission`; el Router le añade la clave
`parameters` a ese diccionario antes de decorar la ruta.

**Alternativa rechazada**: `Annotated[int | None, Query(ge=1)]` más una segunda comprobación sobre el valor
crudo. Sigue rechazando los enteros enormes (primer punto de arriba), así que no cumple FR-011.

## R4. El permiso se comprueba antes que `limit`

**Decisión**. La operación usa `protected(DASHBOARD_READ)` igual que las de suscripciones: la dependencia
`require_permission` va como `dependencies=[...]` de la ruta.

**Evidencia** (ruta de prueba con una dependencia de seguridad que falla y otra que lee `limit`): la
dependencia de seguridad se resuelve **siempre primero**; con permiso denegado, todas las variantes de
`limit` (`abc`, vacío, `0`, `5.0`, repetido, de 5 000 dígitos) respondieron 403 y la dependencia de `limit`
**no llegó a ejecutarse**. Con acceso concedido, `limit` inválido responde 422.

**Por qué no hay desviación del Principio VIII**. La feature 001 necesitó una excepción porque el servidor
decodifica el cuerpo JSON antes de resolver dependencias (su R4). Esta operación es un `GET` sin cuerpo y su
único dato es un parámetro de consulta, que se lee **dentro** de una dependencia posterior a la de seguridad.
No hay nada que se valide antes del permiso.

## R5. Configuración: `DashboardSettings`

**Decisión**. En `src/config.py`, una clase nueva con la forma de las existentes:

```text
class DashboardSettings(BaseSettings):
    dashboard_recent_clinics_limit: int = 5          # DASHBOARD_RECENT_CLINICS_LIMIT
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)
    # validador "before": solo acepta el texto exacto "3", "5" o "10" (tras quitar espacios en los extremos)
```

y `get_dashboard_settings()` con `lru_cache` (un cambio exige reiniciar el servicio, FR-019).

**Evidencia**.

- `Literal[3, 5, 10]` **no sirve**: una variable de entorno llega como texto y Pydantic no la convierte a un
  literal entero; con `DASHBOARD_RECENT_CLINICS_LIMIT=5` falló con `literal_error`, igual que `3` y `10`.
- Un `int` con un validador `ge/le` aceptaría `05`, `5.0`, `+5` y ` 5 `. Un validador **textual** estricto
  (`"3"`, `"5"` o `"10"`) deja una regla simple de documentar y de probar: la variable vale exactamente uno de
  esos tres números.
- `env_ignore_empty=True` ya se usa en las demás variables opcionales (docker-compose pasa vacías las que
  no están en `.env`): una variable vacía equivale a no configurarla y vale 5.
- El mensaje del arranque se construye solo con el nombre de la variable
  (`configuration_error_message` usa `loc` y `type`, nunca `input`); el error original de Pydantic sí trae el
  valor, pero `lifespan` lo descarta con `from None`.

**Cambios en lo existente (aditivos)**.

- `configuration_error_message(error)` pasa a `configuration_error_message(*errors)`: con un solo error el
  texto es idéntico; con varios, junta los problemas bajo un único encabezado. Así, si faltan una dirección
  de API **y** la variable del dashboard es inválida, el mensaje nombra ambas.
- `docker-compose.yml`: el servicio `api` enumera sus variables una por una, así que se añade
  `DASHBOARD_RECENT_CLINICS_LIMIT: ${DASHBOARD_RECENT_CLINICS_LIMIT:-}` (vacía = valor por defecto).
- `.env.example` documenta la variable comentada, con sus valores admitidos y su valor por defecto.

## R6. Validación al arrancar y aviso de datos ficticios

**Decisión**. En `lifespan` de `src/main.py`:

1. Cargar `get_integration_settings()` y `get_dashboard_settings()`, recogiendo los `ValidationError` de
   ambas; si hay alguno, `configuration_error_message(*errores)` → `logger.error` → `RuntimeError(...) from None`
   (el servicio no arranca, FR-018).
2. Después de la validación y del aviso de direcciones inseguras, si `build_dashboard_source().is_dummy`,
   `logger.warning("The dashboard is returning DUMMY data (phase 1): ...")`. Mensaje en inglés (como los
   demás registros del servicio), sin secretos (FR-024).

El aviso se define en términos de `is_dummy` (R1): cuando se conecte la primera fuente real, desaparece solo.

**Consecuencia en una prueba existente**. `tests/unit/test_main.py::test_docker_and_https_addresses_do_not_warn`
afirma `caplog.text == ""` (ningún registro) con direcciones válidas. El aviso nuevo, obligatorio por FR-024,
la hace fallar. Es la **única** aserción del repositorio que exige cero registros (`grep caplog` en
`tests/`). Decisión: acotarla a lo que su nombre dice verificar, que no hay aviso de dirección insegura
(`assert "BASE_URL" not in caplog.text`). Ajuste B1 de [plan.md](plan.md); la spec lo prevé en FR-033(b).

**Alternativas rechazadas**:

- *Registrar el aviso en `INFO`*: invisible con la configuración de registro por omisión (el logger raíz
  imprime desde `WARNING`); anularía la finalidad del aviso.
- *Registrarlo desde un `lifespan` propio del router del dashboard*, para que las pruebas que llaman a
  `src.main.lifespan` no lo vean: esquiva la prueba en lugar de corregirla, esconde el aviso en un sitio que
  nadie busca y separaría la validación de la configuración de su aviso. Si la persona responsable prefiere no
  tocar esa prueba, es la salida limpia a cambio de ese coste.
- *Emitirlo con `print`*: no es un registro.

## R7. Sin caché

**Decisión**. El Router recibe un `Response` y, solo en la respuesta 200, fija
`Cache-Control: no-store` (Aclaración 3). Las respuestas de error no llevan datos y no la necesitan. El
Service no guarda nada entre consultas: cada llamada vuelve a pedir las cinco fuentes (FR-029).

**Evidencia**: la cabecera fijada en el `Response` inyectado aparece en el 200 y no en los 403/422.

## R8. DTOs de salida

**Decisión**. `src/dtos/dashboard.py`:

- `ClinicStatusRead(id: int, name: str)`: **propio**; no se reutiliza `StatusRead`, cuya documentación
  describe el catálogo de estatus de las suscripciones (1 Activa … 4 Eliminada).
- `RecentClinicRead(id: UUID, name: str, created_at: AwareDatetime, status: ClinicStatusRead)` con
  `from_attributes=True` y un validador que **normaliza `created_at` a UTC**; Pydantic serializa un
  `datetime` en UTC con el sufijo `Z` (`2026-10-15T16:20:00Z`), que es el formato de FR-009.
- `DashboardRead` con `total_clinics`, `active_clinics`, `trial_clinics`, `total_doctors`,
  `total_patients`, `total_users` (cada uno `int | None`) y `recent_clinics` (`list[RecentClinicRead] |
  None`). **Todos obligatorios sin valor por defecto**: la clave siempre está en el JSON, con su valor o con
  `null`. Así "omitido de forma explícita" es literal y el contrato no cambia al activarse la degradación
  (FR-026). **Evidencia**: el esquema OpenAPI generado los publica como `anyOf: [integer, null]` y los lista
  en `required`; un `datetime` con zona `-06:00` sale como `2026-10-15T16:20:00Z`, y `model_validate`
  (`from_attributes`) lee `dataclass` anidadas sin problema.

**Datos personales**. Los registros del puerto (R1) solo tienen los campos del contrato, así que no hay
forma de que lleguen datos personales a la respuesta; una prueba compara el conjunto exacto de claves
(FR-008, SC-007).

## R9. Ruta, versión y nombres

**Decisión**. `GET /api/v1/dashboard`; `operationId` `get_dashboard`; etiqueta `dashboard`; permiso
`dashboard:read`; mensajes de validación bajo el recurso `dashboard` (el manejador de errores toma el
primer segmento después de `/api/v1/`).

- **Singular**: la convención de la constitución es "recursos en plural", pero esto no es una colección;
  es una vista única (como `/me`). Un dashboard por clínica, que queda fuera de alcance, vivirá bajo
  `/api/v1/clinics/{id}/dashboard`, sin ambigüedad.
- **`info.version` se queda en `1.0.0`**: añadir una operación es compatible hacia atrás, y subirla a 1.1.0
  obligaría a cambiar `test_the_document_is_generated_openapi_3_with_the_version_of_the_contract`, que afirma
  `"1.0.0"` (FR-032). Se revisa al publicar una versión.
- Se añade la etiqueta `dashboard` a `OPENAPI_TAGS` y un párrafo a `DESCRIPTION` en `src/main.py`
  (aditivo; ninguna prueba compara esos textos).

## R10. Los datos ficticios

**Decisión**. 12 clínicas fijas y conteos **derivados del mismo conjunto**, definidos en
[data-model.md](data-model.md): total 12, activas 8, en prueba 3 y una Suspendida (estatus 3, la más antigua).
Doctores 37, pacientes 1 284 y usuarios 52.

**Por qué**.

- Derivar los conteos del conjunto hace verdaderas **por construcción** las invariantes de FR-022 (activas +
  prueba ≤ total; recientes ≤ total; estatus de las recientes ≤ conteos) y deja el total mayor que la suma
  (12 > 8 + 3), que es el caso que el spec quiere ver.
- 12 > 10: las dos más antiguas quedan fuera de la lista máxima y se puede probar el corte. Las 10 más
  recientes tienen «Activa» y «En prueba» (FR-023). Las dos de la misma fecha están **almacenadas en orden
  contrario al de sus identificadores**, así que la prueba del desempate falla si alguien se salta el
  ordenamiento (FR-015).
- Valores y UUID **literales** (no calculados con el reloj ni al azar en cada arranque): FR-021 y las
  aserciones de Postman sobre identificadores concretos.
- Doctores ≤ usuarios (Aclaración 2).
- Los UUID salen de un generador con semilla fija y se escriben como literales; son versión 4 válidos.

## R11. Pruebas sin servicios reales

**Decisión**. Las pruebas del dashboard **no usan base de datos** (la operación no la toca), por lo que no
necesitan PostgreSQL ni Docker:

- Un `tests/contract/conftest.py` nuevo ofrece un cliente HTTP sobre `create_app()` con
  `get_users_api_client` apuntando a la simulación del API de usuarios montada en memoria
  (`ASGITransport`, como la fixture `api` existente) y `get_dashboard_source` / `get_dashboard_service`
  sustituibles. El código real de `UsersApiClient` y de `AuthorizationService` se ejercita completo.
- La simulación `tests/stubs/users_api/app.py` **no cambia**: acepta cualquier permiso con el formato
  `recurso:acción`, y `dashboard:read` lo cumple. La del API de clínicas no interviene.
- `tests/dashboard_support.py` (sin fixtures): `FakeDashboardSource` (configurable y con contadores de
  llamadas y fallas por consulta), constructores de clínicas y la ayuda `DashboardApi`.
- Se usa un doble propio, no la implementación ficticia, para las fallas, los conjuntos pequeños y los
  vacíos; la implementación ficticia se prueba aparte (determinismo e invariantes).

Las pruebas de Services/Repositories contra PostgreSQL no se amplían: no hay Repository nuevo.

## R12. Colección de Postman (Aclaración 4)

**Decisión**. `tests/postman/collections/MailySoft-System-Dashboard.postman_collection.json`, nueva e
independiente, que se ejecuta con Newman contra la pila aislada **y reutiliza** el entorno
`e2e.postman_environment.json` (usa `baseUrl` y `usersStubUrl`). Estructura y casos en
[e2e-collection.md](contracts/e2e-collection.md).

- Su script previo registra, en la simulación del API de usuarios, tres personas de prueba: una con
  `dashboard:read`, una sin permisos y una con solo permisos de suscripciones (para el 403 de "cada permiso
  autoriza su operación"). Mismo patrón que la colección de suscripciones: tokens al azar, solo en variables
  de colección, nunca en el archivo.
- `tests/postman/package.json` gana dos scripts (`e2e:dashboard` y `e2e:all`); `e2e` queda intacto.
- No se tocan la colección de suscripciones ni la manual (FR-036).
- No toca `docker-compose.e2e.yml`: la variable del dashboard no se define en la pila, así que rige el
  valor por defecto 5 (de eso dependen las aserciones).

## R13. Ajustes a las pruebas existentes (FR-032 y FR-033)

El resultado de buscar todo lo que da por hecho "exactamente estas operaciones" o "ningún aviso":

| Id | Archivo | Qué da por hecho | Ajuste | Excepción |
|---|---|---|---|---|
| A1 | `tests/contract/test_permission_coverage.py` | La matriz tiene exactamente las 6 operaciones (`checked == len(EXPECTED_PERMISSIONS)`, igualdad exacta con el OpenAPI) | **Ampliar**: una entrada en `EXPECTED_PERMISSIONS` y otra en `REQUESTS` para `get_dashboard`. No cambia ninguna aserción; las pruebas parametrizadas ejecutan sola la operación nueva con las mismas comprobaciones | FR-033(a) |
| A2 | `tests/contract/test_openapi_contract.py` | `test_it_has_exactly_the_six_operations_of_the_contract` compara **todas** las operaciones del OpenAPI con las 6 | **Acotar** a las rutas bajo `/api/v1/subscriptions` | FR-033(a) |
| A3 | `tests/contract/postman_support.py` | `operation_ids_of_the_api()` devuelve todas las operaciones; lo usan las pruebas de la colección de suscripciones y de la manual | **Acotar**: parámetro `path_prefix` con valor por defecto `/api/v1/subscriptions`. Los dos archivos que lo llaman no cambian | FR-033(a) |
| B1 | `tests/unit/test_main.py` | `test_docker_and_https_addresses_do_not_warn` exige `caplog.text == ""` | **Acotar** a `assert "BASE_URL" not in caplog.text` | FR-033(b) |

Nada se debilita en lo que respecta a las suscripciones, y lo que el acotamiento (A2, A3) deja de vigilar de
forma global se **recupera con pruebas nuevas**:

- La cobertura de permisos (A1) sigue siendo global: una ruta sin permiso o fuera de la matriz sigue
  rompiéndola.
- Una prueba nueva afirma que las tres colecciones de Postman **juntas** cubren exactamente las operaciones de
  la API (restituye la garantía global que A3 acota) y otra que cada operación del OpenAPI declara `security`
  y `x-required-permission`.
- Una prueba nueva de OpenAPI comprueba el contrato de `get_dashboard` (paralelo a la de suscripciones).

Las demás pruebas existentes **pasan sin tocarse**. Se revisaron `test_layering` (las carpetas de `src/` no
cambian y los módulos nuevos respetan sus reglas), `test_error_messages` (no se añaden códigos: siguen siendo
12), `test_postman_collection` (la colección nueva debe pasar su barrido de secretos: sin la palabra
«secret», sin JWT y sin `Bearer` literales), `test_config` y `test_migrations`.

## R14. Esquema de datos

Sin cambios (FR-020). No hay modelo, repositorio, migración ni fila en `project-definition/DATA_SCHEMA.md`.
Se vigila con `git diff` (quickstart) y con una prueba nueva que comprueba por análisis estático que los
módulos del dashboard no importan `sqlalchemy`, `src.database`, `src.models` ni `src.repositories`.

## R15. Observabilidad, mensajes y privacidad

- **Registros** (en inglés, como los existentes): el aviso de datos ficticios al arrancar (R6) y, por cada
  fuente que falle, `Dashboard source unavailable: <nombre de la consulta>` en `WARNING`, sin el token, sin
  direcciones y sin el cuerpo de error de la fuente (Principios VIII y IX). Una prueba comprueba que el token
  no aparece en los registros (como `test_the_token_never_appears_in_a_response_or_in_the_logs`).
- **Mensaje del 422**, en `src/messages.py`: `DASHBOARD_LIMIT_INVALID_MESSAGE = "El parámetro «limit» debe
  ser un número entero mayor o igual que 1."` y el bloque `VALIDATION_MESSAGES["dashboard"] = {("limit",
  "invalid"): ...}`. No se añade ningún `ErrorCode` (siguen siendo 12); el mensaje nunca repite el valor
  recibido.
- **Permiso**: constante `DASHBOARD_READ = "dashboard:read"` en `src/security.py`.
- **Ningún dato personal**: ni en la respuesta ni en los registros.
- **Rendimiento**: el único coste propio de la operación es la consulta de permiso al API de usuarios; las
  cinco consultas de datos corren en paralelo y las ficticias son instantáneas. Margen sobrado para SC-001.

## Puntos a confirmar fuera de este repositorio (no bloquean el plan)

1. **API de usuarios**: que el permiso `dashboard:read` exista en su catálogo y esté asociado al rol de
   administración de plataforma antes de integrar. Hasta entonces, la simulación lo concede y lo niega.
2. **APIs de clínicas, doctores, pacientes y usuarios** (futuros): cada especificación que conecte uno
   documentará su contrato consumido y cumplirá el puerto de R1, incluidos el tiempo máximo de espera y la
   traducción de fallas a `DashboardSourceUnavailable`.
