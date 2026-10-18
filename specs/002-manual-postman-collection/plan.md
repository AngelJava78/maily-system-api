# Implementation Plan: Colección de Postman para Probar a Mano la API de Sistema

**Branch**: `002-manual-postman-collection` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-manual-postman-collection/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Una colección de Postman **nueva e independiente, solo manual**, para recorrer a mano las 6 operaciones de
`/api/v1/subscriptions`, la documentación pública y los errores clave (401, 403, 404, 409, 422 y 503) desde la
aplicación de escritorio, contra un entorno **local** y uno **desplegado de pruebas**. La persona no pega nunca un
token: un script previo de la colección lo pide a Auth0 con *client credentials*, lo reutiliza y lo renueva 60 s
antes de que venza. La feature **no toca la aplicación ni el esquema de datos**: añade archivos de Postman,
una prueba de desfase en pytest y documentación.

Enfoque técnico (decisiones y evidencia en [research.md](research.md); el comportamiento del script se verificó con un
prototipo en Newman 6.2.3 en 25 escenarios):

- **Acceso (US1)**: un único *pre-request* de colección (M1) con *callbacks* (M4: Newman 6.2.3 rechaza `await` de
  nivel superior y, ante un error de script, **envía la petición sin token**). Si algo falla, **no se envía**
  (`pm.execution.skipRequest()`, M2) y se explica en la Consola de Postman y en `accessProblem` (M3). Token,
  vencimiento y clave `dominio|audience|clientId` en variables de colección; se renueva con menos de 60 s (M5). Fallos de
  Auth0 traducidos a 7 mensajes en español (M6, [access-script.md](contracts/access-script.md)).
- **No tocar nada ajeno (US2, US4; SC-006)**: tres protecciones **antes de enviar** (M8): variables sin valor en
  URL y **cuerpo**; comprobación de que lo que se modifica *existe y se llama como lo creó la colección* (cubre la
  base de pruebas reiniciada donde otra persona reutiliza el mismo identificador); y descarte de los datos de la
  sesión si cambia la dirección de la API. Los casos 404 usan solo `GET`.
- **Colección (US2, US3, US5)**: 4 carpetas y 44 peticiones ([collection-structure.md](contracts/collection-structure.md)):
  empezar, ciclo de vida, casos de error (cada estatus con su caso) y simulación de clínicas opcional, que reutiliza
  la simulación de la spec 001 (`/__test__/…`) y se omite sola si no hay `clinicsStubUrl`.
- **Entornos (US4)**: dos archivos con las **mismas nueve variables**, todas con valor vacío salvo las direcciones locales
  y el aviso; los secretos son de tipo `secret` con valor vacío (M10). El formato de entorno v2.1 no tiene descripción:
  el aviso de bases de datos de pruebas va en el nombre y en `testDatabaseNotice`.
- **Desfase y secretos (US6)**: `test_manual_postman_collection.py` con las reglas D0 a D11
  ([drift-test.md](contracts/drift-test.md)), por **estructura del JSON**, no por palabras. Obliga a acotar la
  comprobación textual que ya hacía `test_postman_collection.py` (prohíbe la palabra «secret» en toda la carpeta) (M13).
- **Documentación (US7)**: sección nueva del README con los pasos, los requisitos previos de Auth0 y del API de usuarios, la
  tabla de fallos de acceso y las advertencias; y la regla «una feature que cambie operaciones actualiza **las dos**
  colecciones» (FR-021).

## Technical Context

**Language/Version**: JSON (colección y entornos, Postman v2.1); JavaScript del *sandbox* de Postman para los scripts
(sin `require`, sin `await` de nivel superior); Python 3.14+ para la prueba (el entorno de la referencia ejecuta 3.15.0).

**Primary Dependencies**: ninguna nueva. Aplicación de escritorio de Postman actual (la documentación de `pm.execution.skipRequest` no publica una versión mínima: se verifica en la versión instalada, quickstart V2) como herramienta de
quien prueba; pytest (ya existente) para la prueba de desfase. Newman 6.2.3 (ya presente en `tests/postman/`) solo para la
verificación desechable de quien implementa, no como dependencia de la feature.

**Storage**: N/A. Archivos versionados en `tests/postman/`; los valores de la sesión viven en las variables de colección del
equipo de cada persona.

**Testing**: pytest, solo lectura de archivos y de `create_app().openapi()` (sin servicio, Node ni Postman); verificación manual
en la aplicación ([quickstart.md](quickstart.md) V2 a V8); ejecución única con Newman contra la pila de la spec 001 y un Auth0
simulado (V9, fuera del repositorio).

**Target Platform**: Postman de escritorio (Windows, macOS, Linux) contra la API local (`http://127.0.0.1:8010`) o una
desplegada de pruebas; Auth0 y el API de usuarios reales.

**Project Type**: web-service (activos de prueba y documentación del servicio; no añade código de aplicación).

**Performance Goals**: primera respuesta correcta en < 10 min desde la importación (SC-001); ≥ 2 h de sesión sin tocar un
token (SC-002; el token de Auth0 suele durar 24 h y se renueva solo); una única llamada a Auth0 por token vigente.

**Constraints**: sin secretos ni tokens en archivos, descripciones ni consola (el secreto solo en el valor local de la
variable `secret`); sin iniciar sesión en Postman ni enviar datos a nada que no sea Auth0 y la API probada; una petición que
exige token **nunca** sale sin él; lo que se modifica o elimina es solo lo que creó la colección; las colecciones solo apuntan a
bases de datos dedicadas a pruebas (en local, `maily_system_manual`); la colección de la spec 001 no se modifica.

**Scale/Scope**: 1 colección (4 carpetas, 44 peticiones, 1 script de ~200 líneas); 2 entornos × 9 variables; 1 prueba nueva
(~20 casos, 12 reglas y sus casos negativos) y 1 módulo de apoyo; 1 prueba existente ajustada; 1 sección de README.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas y código en `src/` | ✅ No hay código de aplicación | ✅ Sin cambios en `src/`. Los archivos de Postman van en `tests/postman/` (`collections/`, `environments/`), como fija la constitución; la prueba, en `tests/contract/`. `test_layering.py` no se ve afectada |
| II. Modelos ≠ DTOs | ✅ N/A | ✅ N/A: no hay modelos ni DTOs nuevos |
| III. Asincronía | ✅ N/A | ✅ N/A en la aplicación. El script de Postman usa *callbacks* (el *sandbox* no es Python); la prueba no hace E/S de red |
| IV. OpenAPI y REST | ✅ La colección consume el contrato publicado | ✅ El contrato no cambia. La prueba de desfase lee el OpenAPI **generado** (`create_app().openapi()`), así que la colección no puede apartarse de él sin que la suite falle |
| V. Pruebas pytest | ✅ pytest sigue siendo la puerta de calidad | ✅ La prueba nueva corre con la suite, sin servicio ni red. La colección **complementa y no repite** pytest: comprobaciones ligeras (estatus, `code`, campos clave). **Nota de interpretación**: «las pruebas automatizadas MUST NOT llamar a APIs reales» se refiere a la suite automatizada; esta colección es manual, fuera de pytest, y usa las APIs reales *a propósito*, a mano |
| VI. Migraciones Alembic | ✅ Sin cambios de esquema | ✅ FR-024: ni modelos ni migraciones ni `DATA_SCHEMA.md` |
| VII. Idioma | ✅ | ✅ Mensajes, descripciones, títulos de pruebas y documentación en español; identificadores técnicos (archivos, variables, scripts, funciones) en inglés. **Los comentarios y docstrings** del script y de la prueba, en inglés (el script de prueba del prototipo los traía en español: se corrige al implementar) |
| VIII. Control de acceso delegado | ✅ No se altera | ✅ La colección es un **cliente**: obtiene un token real de Auth0 y la API sigue reenviándolo al API de usuarios. El secreto no se persiste; el 401/403/503 se provocan sin saltarse nada (el caso 401 usa un token inventado, el 403 una segunda aplicación real sin permisos). No debilita ninguna verificación |
| IX. Integraciones | ✅ | ✅ La colección contacta solo con Auth0 (token) y la API probada (FR-012); las simulaciones de clínicas se usan por HTTP, no se importan |
| Stack obligatorio | ✅ Postman v2.1; sin tecnologías nuevas | ✅ Sin dependencias nuevas. **Nota de interpretación**: la fila «Postman (colecciones v2.1) con Newman» describe la ejecución *automatizada*; esta colección es solo manual (decidido en la spec) y por eso no tiene comando de Newman. Node.js sigue sin entrar en la imagen ni ser dependencia del servicio |
| Postman: ubicación, sin sesión, sin subir resultados, base de pruebas | ✅ | ✅ `tests/postman/collections|environments`; funciona sin iniciar sesión; solo Auth0 y la API; el aviso de «bases de datos de pruebas» va en el nombre del entorno, en `testDatabaseNotice`, en la colección y en el README. **Base dedicada a pruebas** (constitución: «MUST apuntar a una base de datos dedicada a pruebas»): en local se usa `maily_system_manual`, creada y migrada según el README (`CREATE DATABASE` + `alembic upgrade head` con `DATABASE_URL` en la terminal); **nunca** la de desarrollo (`maily_system`) ni la de pytest. No se toca `docker-compose.yml` ni el script de inicio (FR-024) |
| Postman: sin secretos en colecciones ni entornos | ✅ | ✅ Valores de secretos y de acceso **vacíos** en los archivos; Bearer solo referencia `{{variable}}`; la regla D5 lo comprueba por estructura (no por palabras) |
| Configuración por entorno, sin secretos | ✅ | ✅ No añade variables de configuración al servicio; el `.env` no se toca |
| Docker y Compose | ✅ N/A | ✅ Sin cambios |
| Flujo y puertas de calidad | ✅ | ✅ Este plan incluye el Constitution Check. La regla «si cambia la API, se actualiza la colección» pasa a cubrir **las dos** colecciones (FR-021, README, y vigilado por las dos pruebas de desfase) |

**Resultado**: PASS contra los principios I a IX, **sin desviaciones** que enmendar. Dos reglas se interpretan
(arriba) porque su texto describe la automatización y esta feature es manual por decisión. Recomendación (no se hace aquí): una
enmienda PATCH de la constitución que nombre expresamente las colecciones manuales, para que esa interpretación no dependa de
este plan.

## Puntos a confirmar fuera de este repositorio (no bloquean el plan)

1. **Auth0**: que la aplicación M2M tenga *client grant* sobre el *audience* del API de usuarios, y que el comportamiento de los
   401/403 de `/oauth/token` sea el modelado (M6). Verificación V3.
2. **API de usuarios**: que el `sub` de la aplicación (`…@clients`) esté registrado y su rol tenga `subscriptions:read|write|update|delete`
   (`bootstrap_admin.sql` solo concede al *Administrator* los 12 de usuarios, roles y permisos).
3. **Aplicación de Postman**: la presentación de una petición omitida y de la Consola (M3), y el soporte de `skipRequest` en la
   versión instalada (M2): V2 y V3. Es el principal riesgo de experiencia y **no puede comprobarse sin la aplicación**.

## Project Structure

### Documentation (this feature)

```text
specs/002-manual-postman-collection/
├── plan.md                              # Este archivo
├── research.md                          # Fase 0: decisiones M1–M15, evidencia del prototipo y riesgos
├── data-model.md                        # Fase 1: colección, entornos, credenciales, token y datos de la sesión
├── quickstart.md                        # Fase 1: validación en 9 niveles (V1–V9)
├── contracts/
│   ├── collection-structure.md          # Fase 1: 4 carpetas y 44 peticiones con lo que esperan
│   ├── access-script.md                 # Fase 1: algoritmo, mensajes A-01…A-13 e invariantes del script
│   └── drift-test.md                    # Fase 1: reglas D0–D11 de la prueba de desfase y secretos
├── checklists/
│   └── requirements.md
└── tasks.md                             # Fase 2 (/speckit-tasks, aún no creado)
```

### Source Code (repository root)

No hay código de aplicación nuevo: solo archivos de Postman, una prueba y documentación.

```text
tests/postman/
├── collections/
│   ├── MailySoft-System-Suscripciones.postman_collection.json   # spec 001: NO se modifica
│   └── MailySoft-System-Manual.postman_collection.json          # NUEVO: la colección manual
├── environments/
│   ├── e2e.postman_environment.json                             # spec 001: NO se modifica
│   ├── dev.postman_environment.json                             # spec 001: NO se modifica
│   ├── manual-local.postman_environment.json                    # NUEVO
│   └── manual-deployed-test.postman_environment.json            # NUEVO
└── (package.json, docker-compose.e2e.yml, reports/)             # sin cambios

tests/contract/
├── postman_support.py                   # NUEVO: apoyo compartido (recorrer, nombrar, OpenAPI, patrones)
├── test_manual_postman_collection.py    # NUEVO: reglas D0–D11 y sus casos negativos
└── test_postman_collection.py           # MODIFICADO: usa el apoyo y acota la búsqueda de «secret» a los archivos de la spec 001

README.md                                # MODIFICADO: sección de la colección manual y regla de las dos colecciones
```

**Structure Decision**: se respeta la ubicación que fija la constitución para Postman (`tests/postman/`, con
`collections/` y `environments/`) y la regla de que las pruebas viven en `tests/`. No se versiona un `access.js` ni un generador: la
fuente de verdad del script es el JSON de la colección (M14). La verificación con Newman (M15) queda fuera del
repositorio.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No hay violaciones de la constitución. Se deja constancia de la complejidad propia del diseño, para que se revise con los ojos abiertos:

| Complejidad | Por qué hace falta | Alternativa más simple rechazada porque… |
|---|---|---|
| Un script de acceso de ~200 líneas con 5 responsabilidades (datos de sesión, identidad, variables, token, propiedad) | Una colección manual sin token pegado, sin enviar sin credenciales y sin tocar datos ajenos exige decidir todo antes de **cada** petición, en un único sitio | Un script por carpeta o petición se desincronizaría; sin las comprobaciones, la colección enviaría peticiones sin token o con `{{variables}}` sin resolver (probado en Newman) |
| Comprobación de propiedad: 1 `GET` extra antes de cada `PATCH`/`PUT`/`DELETE` | SC-006 pide 0 datos ajenos tocados; con una base de pruebas reiniciada y compartida, un identificador guardado puede apuntar a otra persona | Confiar en el identificador guardado: el `DELETE` de una suscripción ajena es posible (G2). Cuesta una petición extra y el permiso `subscriptions:read`, que ya forma parte del mínimo |
| Prueba de desfase **por estructura** (12 reglas) en lugar de una búsqueda de palabras | La colección manual debe contener la palabra «secret» (nombre de variable, tipo `secret`); una búsqueda textual dejaría falsos positivos permanentes o una lista de excepciones que se oxida | Mantener la búsqueda de palabras en toda la carpeta: obliga a no nombrar la variable secreta, es decir, a no poder implementar la feature |
| Módulo de apoyo `postman_support.py` y cambio en una prueba existente | Evitar copiar `requests_of`/`prefix_of`/OpenAPI entre dos archivos de prueba que deben evolucionar juntos (FR-021) | Duplicarlos: dos copias que vigilar |
