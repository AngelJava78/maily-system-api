---

description: "Task list for 011-payment-return-url"
---

# Tasks: Regreso automático a MailySoft después de pagar la suscripción («Dirección de regreso del pago»)

**Input**: Design documents from `/specs/011-payment-return-url/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/payments-api-integration.md,
quickstart.md

**Tests**: obligatorias por la constitución (Principio V): se escriben antes del código que prueban y deben
fallar primero (salvo T001, que fija el comportamiento de hoy y pasa antes y después). Durante
`/speckit-implement` solo corre el nivel rápido (`uv run pytest`); la suite completa (`uv run pytest -m ""`)
y Newman son la puerta de la fase «Verificación completa».

**Organization**: tareas agrupadas por historia de usuario.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ir en paralelo (otro archivo, sin depender de tareas pendientes)
- **[Story]**: historia de usuario de [spec.md](spec.md) (US1 a US4)

## Convenciones de esta feature (valen para todas las tareas)

- Comandos de Python (`uv run …`) desde PowerShell en `C:\Maily\code\maily-system-api`.
- Comentarios, docstrings y nombres en inglés; mensajes y documentos en español (Principio VII).
- La dirección **nunca** aparece en mensajes, registros ni respuestas (FR-004, FR-010).
- La tabla «Direcciones de referencia» de [spec.md](spec.md) es la fuente de los casos de configuración.
- Ninguna comprobación existente cambia (SC-005): solo se ajusta el soporte de las pruebas (plan, «Ajustes a
  las pruebas existentes»).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: fijar el comportamiento de hoy antes de tocar el código.

- [X] T001 Fijar la clave de la spec 010 en `tests/unit/test_billing_rules.py`: constante
  `SPEC_010_KEY = "sub-0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b-bb0e695d1931407f10e6ec5a"` (calculada el
  2026-11-25 con el código sin cambios para las entradas por omisión de `key()`) y la prueba
  `test_without_a_return_address_the_key_is_the_one_of_spec_010` (`key() == SPEC_010_KEY` y
  `key(return_url=None) == SPEC_010_KEY` una vez que exista el argumento; hasta entonces solo la primera
  comprobación). Debe pasar antes y después de la feature (FR-008, SC-002).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: aislamiento de las pruebas, simulación y dobles de Pagos, y el campo de configuración.

**⚠️ CRITICAL**: ninguna historia empieza antes de terminar esta fase.

- [X] T002 [P] Aislar la variable en `tests/conftest.py` (fixture automático `billing_environment`):
  `monkeypatch.delenv("PAYMENTS_RETURN_URL", raising=False)` y
  `monkeypatch.setitem(PaymentsSettings.model_config, "env_file", None)` (ya define sus dos variables
  obligatorias), actualizando su docstring: el `.env` local nunca activa la dirección en una prueba.
- [X] T003 [P] Agregar `"PAYMENTS_RETURN_URL"` a `ENV_NAMES` en `tests/unit/test_billing_startup.py` (solo
  aislamiento; ninguna comprobación cambia).
- [X] T004 [P] Simulación de Pagos en `tests/stubs/payments_api/app.py` (FR-014, contrato «Simulación en las
  pruebas»): en `create_payment`, si el cuerpo trae `redirect_urls` no nulo, exigir un objeto con solo
  `success`, `pending` y `failure`, `success` presente y cada valor un texto que empiece con `https://` y
  tenga de 1 a 2048 caracteres; si no, 422 `validation_error`. Guardar `redirect_urls` en el pago **solo si
  la clave venía en el cuerpo** (así una prueba distingue «ausente» de «nulo»). Agregar el modo de falla
  `return_not_allowed` a `FAULT_MODES` y a `early_answer`: 422 con `code` `validation_error`, el mensaje con
  la marca interna de la simulación y
  `errors: [{"field": "body.redirect_urls.success", "message": "El origen de la dirección de regreso no está permitido."}]`.
  `GET /__test__/payments` agrega `redirect_urls` a cada pago que lo trajo (Pagos no lo devuelve en
  `PaymentRead`).
- [X] T005 [P] Doble de Pagos en `tests/billing_support.py`: `FakePaymentsApi.create_payment` acepta
  `return_url: str | None = None`, lo guarda en `create_calls` (`"return_url"`) y lo agrega a su huella
  (`repr((…, metadata, return_url))`); `make_world` acepta `return_url: str | None = None` y lo pasa al
  Service. No tocar el doble del cobro de clínicas (`tests/unit/fakes.py`): su `create_payment` sin
  `return_url` es la guarda de FR-011.
- [X] T006 Campo en `src/config.py`: `PaymentsSettings.payments_return_url: str | None = None` (variable
  `PAYMENTS_RETURN_URL`, opcional, vacía = no definida por `env_ignore_empty`), con docstring que cite la spec
  011; actualizar el docstring del módulo. La validación llega en T024 (US3). Y el constructor de
  `SubscriptionPeriodService` (`src/services/subscription_period_service.py`) acepta
  `return_url: str | None = None` y lo guarda (lo necesita `make_world` de T005; se usa en T013).

**Checkpoint**: la suite rápida sigue en verde.

---

## Phase 3: User Story 1 - El Dueño vuelve solo a MailySoft después de pagar (Priority: P1) 🎯 MVP

**Goal**: con la dirección configurada, cada creación de pago de un periodo lleva
`redirect_urls.success` con exactamente esa dirección, y la clave la incluye.

**Independent Test**: con Pagos simulado y la dirección configurada, iniciar el pago y comprobar el cuerpo
que recibió Pagos y que la respuesta de la API no cambia.

### Tests for User Story 1 ⚠️

- [X] T007 [P] [US1] Cliente en `tests/unit/test_payments_api_client.py`: con
  `return_url="https://app.mailysoft.com/payment"`, el cuerpo exacto (`client_answering`) es el de hoy más
  `"redirect_urls": {"success": "https://app.mailysoft.com/payment"}` y nada más dentro de `redirect_urls`;
  contra la simulación, el pago guardado tiene ese objeto; la misma clave con el mismo cuerpo da el mismo
  pago; la misma clave con otra dirección es `PaymentsApiIdempotencyConflict` (nunca el pago anterior); una
  dirección con consulta o barra final viaja tal cual (escenario 5).
- [X] T008 [P] [US1] Clave en `tests/unit/test_billing_rules.py`: con dirección es distinta de
  `SPEC_010_KEY`, determinista, de 65 caracteres ASCII con el prefijo `sub-<organización>-`; dos direcciones
  distintas dan claves distintas; una descripción que termina en `|https://x` sin dirección y la descripción
  sin ese final con la dirección `https://x` dan claves distintas (codificación sin ambigüedad, R5).
- [X] T009 [P] [US1] Service en `tests/unit/test_subscription_period_service.py` (con
  `make_world(return_url=…)`): la creación recibe `return_url` igual a la dirección; su clave es
  `billing_rules.idempotency_key(…, return_url)`; iniciar dos veces el mismo periodo no crea otro pago (200
  con el mismo checkout); con una respuesta perdida (`lose_answer`), el reintento con la misma dirección
  registra un solo cobro con el mismo pago; si entre ambos cambia la dirección (otro Service sobre el mismo
  mundo con otra dirección), se crea otro pago y solo ese queda registrado.
- [X] T010 [P] [US1] Contrato en `tests/contract/test_subscription_periods_return_url.py` (nuevo; usa
  `billing_api`, nivel lento): con `PAYMENTS_RETURN_URL` definida (`monkeypatch.setenv` y
  `get_payments_settings.cache_clear()`), iniciar el pago da 201 con las mismas claves de respuesta que sin
  la variable y sin la dirección en ella; el pago que guardó la simulación tiene
  `redirect_urls == {"success": <dirección>}`; repetirlo da 200 con el mismo checkout y un solo pago en la
  simulación.

### Implementation for User Story 1

- [X] T011 [US1] Cliente en `src/integrations/payments_api.py`: argumento nombrado
  `return_url: str | None = None` en `create_payment`; con valor, `body["redirect_urls"] = {"success": return_url}`;
  sin él, el cuerpo no cambia. Docstrings (módulo y método) con la spec 011 (R4).
- [X] T012 [US1] Clave en `src/services/billing_rules.py`: `idempotency_key(…, description, return_url=None)`;
  sin dirección, el texto resumido es exactamente el de hoy; con dirección,
  `json.dumps([texto_de_hoy, return_url])` (R5, [data-model](data-model.md)). Docstring con el porqué.
- [X] T013 [US1] Service en `src/services/subscription_period_service.py`: `start_payment` pasa
  `self._return_url` (guardado por el constructor, T006) a `billing_rules.idempotency_key` y a
  `create_payment(…, return_url=self._return_url)` (R6). Docstring de `start_payment` con FR-006 y FR-008.
- [X] T014 [US1] Inyección en `src/dependencies.py`: `get_subscription_period_service` pasa
  `return_url=get_payments_settings().payments_return_url` (leída una vez por la caché: un cambio requiere
  reiniciar, FR-001).

**Checkpoint**: `uv run pytest` en verde; con la dirección configurada, Pagos la recibe.

---

## Phase 4: User Story 2 - Sin la dirección configurada, todo sigue exactamente como hoy (Priority: P1)

**Goal**: sin la variable (o vacía), cuerpo y claves idénticos a los de hoy; el cobro de clínicas no cambia.

**Independent Test**: sin la variable, comparar el cuerpo y la clave que recibe Pagos con los de la versión
anterior.

### Tests for User Story 2 ⚠️

- [X] T015 [P] [US2] Cliente en `tests/unit/test_payments_api_client.py`: sin `return_url` (y con
  `return_url=None` explícito), el cuerpo no tiene la clave `redirect_urls` y el pago guardado en la
  simulación tampoco.
- [X] T016 [P] [US2] Service en `tests/unit/test_subscription_period_service.py`: con `make_world()` sin
  dirección, la creación recibe `return_url=None` y su clave es la de la spec 010
  (`billing_rules.idempotency_key` sin dirección, mismas condiciones).
- [X] T017 [P] [US2] Configuración en `tests/unit/test_billing_config.py`: sin la variable o con la variable
  vacía, `PaymentsSettings().payments_return_url is None` (fila 1 de la tabla).
- [X] T018 [P] [US2] Contrato en `tests/contract/test_subscription_periods_return_url.py`: sin la variable,
  iniciar el pago da 201 y el pago de la simulación no tiene la clave `redirect_urls`; con la variable vacía,
  lo mismo.

### Implementation for User Story 2

- [X] T019 [US2] Completar en `tests/unit/test_billing_rules.py` la prueba de T001 con
  `key(return_url=None) == SPEC_010_KEY` y verificar que `src/services/clinic_subscription_service.py` no
  pasa `return_url` (sin cambios en ese archivo; FR-011).

**Checkpoint**: US1 y US2 en verde por separado.

---

## Phase 5: User Story 3 - Quien opera configura la dirección y una dirección inválida impide arrancar (Priority: P2)

**Goal**: la tabla «Direcciones de referencia» al arrancar, el registro del 422 de Pagos y la documentación.

**Independent Test**: arrancar el servicio con cada valor de la tabla y comprobar arranque, mensaje y registro.

### Tests for User Story 3 ⚠️

- [X] T020 [P] [US3] Tabla en `tests/unit/test_billing_config.py`: filas 2 a 5 se aceptan y se guardan como
  dice la tabla (fila 5 sin los espacios externos; ni minúsculas ni barra final quitada); filas 6 a 16 y un
  valor de solo espacios dan `ValidationError`, y `configuration_error_message(error)` nombra
  `PAYMENTS_RETURN_URL` y no contiene el valor ni parte de él (equipo o ruta).
- [X] T021 [P] [US3] Arranque en `tests/unit/test_billing_startup.py`: con
  `PAYMENTS_RETURN_URL=https://app.mailysoft.com/payment` arranca; con
  `https://usuario:clave@pagos-secreto.example.com/payment` (y con `http://…`, `https://localhost/payment`)
  no arranca y el mensaje nombra la variable sin el valor; el registro (`caplog`) tampoco lo contiene; con la
  dirección inválida y `BILLING_CUTOFF_AT` ausente, un solo mensaje nombra las dos; cambiar la variable
  después de leer la configuración no cambia el valor leído hasta limpiar la caché (reinicio).
- [X] T022 [P] [US3] Registro del 422 en `tests/unit/test_payments_api_client.py`: con `return_url` y una
  respuesta 422, `PaymentsApiUnavailable` y un registro de error que dice que se envió una dirección de
  regreso y no contiene la dirección; sin `return_url`, el registro de siempre.
- [X] T023 [P] [US3] Contrato en `tests/contract/test_subscription_periods_return_url.py`: con la variable y
  la falla `return_not_allowed` de la simulación, iniciar el pago da 503 `payments_unavailable`, no queda
  ningún cobro registrado y el registro del servicio no contiene la dirección.

### Implementation for User Story 3

- [X] T024 [US3] Validación en `src/config.py`: función pura `_return_address(value)` y
  `_is_local_or_private_host(host)` con las reglas de [data-model.md](data-model.md) en su orden («Después de
  quitar los espacios externos, no está vacía»; «Sin espacios ni caracteres de control en su interior»; «A lo
  más 2048 caracteres»; «Sin el carácter `#`»; «`urlsplit` la entiende y su puerto, si lo hay, está entre 0 y
  65535»; «Esquema `https`»; «Equipo (host) presente»; «Sin usuario ni contraseña (tampoco una `@` sin
  usuario)»; «Equipo que no es local ni privado»), un `ValueError` sin el valor y un `field_validator` de
  `payments_return_url` que la use (R2, R3). Constante `RETURN_ADDRESS_MAX_LENGTH = 2048`.
- [X] T025 [US3] Registro del 422 en `src/integrations/payments_api.py`: si la creación llevaba `return_url` y
  Pagos respondió 422, `logger.error` que dice que se envió una dirección de regreso y que se revise que su
  origen esté permitido en Pagos, sin la dirección; el mapeo a `PaymentsApiUnavailable` no cambia (R7).
- [X] T026 [P] [US3] `.env.example`: `PAYMENTS_RETURN_URL` comentada entre las opcionales con su explicación
  (vacía en desarrollo local; en otros ambientes la pantalla `/payment` del frontend; su origen en
  `CHECKOUT_RETURN_ALLOWED_ORIGINS` de Pagos; `https` y nunca local).
- [X] T027 [P] [US3] `README.md`: fila de `PAYMENTS_RETURN_URL` en «Configuración» (no obligatoria, sin valor
  por omisión) y una viñeta en la sección de periodos de suscripción: regreso automático, requisito en Pagos
  y que el regreso no es prueba de pago; actualizar la mención del pedido de regreso a Pagos.
- [X] T028 [P] [US3] `docker-compose.yml`: `PAYMENTS_RETURN_URL: ${PAYMENTS_RETURN_URL:-}` junto a las
  variables de Pagos del servicio `api`; y en `tests/postman/docker-compose.e2e.yml`,
  `PAYMENTS_RETURN_URL: ""` (la pila aislada no hereda la variable del `.env` de quien la corre).

**Checkpoint**: las 16 filas de la tabla se reproducen.

---

## Phase 6: User Story 4 - El regreso nunca es prueba de pago (Priority: P2)

**Goal**: los parámetros de regreso no cambian ningún cobro; la API publicada no cambia.

**Independent Test**: con un cobro que Pagos reporta pendiente, leer el periodo con parámetros de «aprobado»
y comprobar que nada se mueve; comparar el contrato publicado.

### Tests for User Story 4 ⚠️

- [X] T029 [P] [US4] Contrato en `tests/contract/test_subscription_periods_return_url.py`: con un cobro
  iniciado y la simulación en `pending`, leer el periodo con
  `?collection_status=approved&status=approved&payment_id=1&external_reference=x` da 200 con
  `payment_in_progress: true` y la misma `payment_due_at`, y el cobro sigue sin resolver; al pasar la
  simulación a `approved`, la siguiente lectura lo aplica una sola vez.

### Implementation for User Story 4

- [X] T030 [US4] Sin código nuevo (FR-012): comprobar que ningún Router cambió (`git diff main -- src/routers
  src/dtos` vacío) y dejar la comparación de `/openapi.json` para la fase de verificación (T034).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T031 Revisar capas y documentación: `tests/unit/test_layering.py` y `tests/unit/test_billing_design_rules.py`
  en verde; docstrings de los módulos tocados mencionan la spec 011; los ejemplos de dirección usan dominios de
  ejemplo, nunca reales de un cliente.
- [X] T032 Nivel rápido completo: `uv run pytest` en verde (cierre de `/speckit-implement`).

---

## Phase 8: Verificación completa (la puerta de la constitución antes de integrar en `main`)

- [X] T033 Suite completa con PostgreSQL 17 real: `uv run pytest -m ""` en verde (incluye migraciones desde
  cero, cobertura de permisos, OpenAPI, capas y el archivo de contrato nuevo).
- [X] T034 OpenAPI idéntico: generar `create_app().openapi()` en `main` (árbol de trabajo aparte) y en la rama
  y compararlos (quickstart §4, FR-013).
- [X] T035 Postman/Newman: levantar la pila `maily-system-e2e`, `npm run e2e:all --prefix tests/postman` en
  verde (cuatro colecciones) y bajar la pila (quickstart §5).

---

## Phase 9: Integración (solicitada por la persona responsable el 2026-11-25)

- [X] T036 Commit (Conventional Commits en inglés) y push de la rama `011-payment-return-url`; Pull Request a
  `main` con el resumen, las decisiones por defecto y los resultados de las puertas.
- [X] T037 Integrar el Pull Request en `main`, confirmar que `main` en GitHub contiene los cambios y borrar las
  ramas `011-payment-return-url` local y remota.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias; T001 va **antes** de cambiar `billing_rules.py`.
- **Foundational (Phase 2)**: después de Setup; bloquea las historias.
- **US1 (Phase 3)** y **US2 (Phase 4)**: después de Foundational. US2 comparte archivos de prueba con US1, así
  que se hace después de US1 (sus pruebas deben pasar sin código nuevo, salvo T019).
- **US3 (Phase 5)**: después de Foundational; T025 toca el mismo archivo que T011 (hacerla después).
- **US4 (Phase 6)**: después de US1 (usa la creación de cobros con la simulación).
- **Polish (Phase 7)** → **Verificación (Phase 8)** → **Integración (Phase 9)**.

### Within Each User Story

- Pruebas primero (deben fallar), luego el código; un archivo a la vez cuando dos tareas lo comparten.

### Parallel Opportunities

- T002 a T005 (archivos distintos).
- T007 a T010 (archivos distintos); T015 a T018; T020 a T023; T026 a T028.

---

## Parallel Example: User Story 1

```text
Task: "T007 Cliente en tests/unit/test_payments_api_client.py"
Task: "T008 Clave en tests/unit/test_billing_rules.py"
Task: "T009 Service en tests/unit/test_subscription_period_service.py"
Task: "T010 Contrato en tests/contract/test_subscription_periods_return_url.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Setup (T001) y Foundational (T002 a T006).
2. US1 (T007 a T014): Pagos recibe la dirección.
3. **STOP and VALIDATE**: `uv run pytest`.

### Incremental Delivery

1. US1 → US2 (nada cambia sin la variable) → US3 (validación al arrancar y documentación) → US4 (el regreso no
   es prueba de pago).
2. Verificación completa y luego integración.

---

## Notes

- [P] = archivos distintos, sin dependencias pendientes.
- La dirección nunca se registra ni se devuelve.
- Si una prueba existente falla, se corrige el código, no la comprobación (SC-005).
