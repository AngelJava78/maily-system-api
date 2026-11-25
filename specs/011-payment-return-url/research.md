# Research: Dirección de regreso del pago (011-payment-return-url)

Fase 0 del plan. No quedó ningún «NEEDS CLARIFICATION» en el contexto técnico: la especificación cerró
sus cinco dudas con la opción recomendada («Clarifications») y lo demás se resolvió leyendo este
repositorio y mailySoft-pagos (en solo lectura). Cada decisión indica qué se eligió, por qué y qué se
descartó.

## R1. Dónde vive la variable

- **Decision**: un campo opcional más en `PaymentsSettings` (`src/config.py`):
  `payments_return_url: str | None = None`, leído de `PAYMENTS_RETURN_URL`. La clase ya ignora las
  variables vacías (`env_ignore_empty=True`, FR-002) y su `get_payments_settings()` está en caché: se lee
  una vez y un cambio requiere reiniciar (FR-001).
- **Rationale**: `PaymentsSettings` es la configuración del cliente de Pagos de los periodos de suscripción
  (spec 010, FR-040) y la valida el arranque (`lifespan`) junto con las demás, así que una dirección
  inválida entra sola en el mensaje único de configuración (FR-004) sin código nuevo de arranque.
- **Alternatives considered**: `IntegrationSettings` (la del cobro de clínicas y de los scripts; mezclaría
  features y FR-011 pide no tocar ese cobro); una clase nueva (más código en el arranque y en las pruebas
  para un solo campo).

## R2. Reglas de la dirección al arrancar

- **Decision**: una función pura en `src/config.py` que, tras quitar los espacios externos, exige: sin
  espacios ni caracteres de control dentro, sin `#`, 2048 caracteres o menos, que `urlsplit` la entienda
  con un puerto válido, esquema `https`, equipo presente, sin usuario ni contraseña (tampoco una `@` vacía)
  y un equipo que no sea local ni privado. «Local o privado» reproduce la regla de Pagos
  (`_is_local_or_private_host` de su `src/payments.py`): `localhost` y `*.localhost`; IP de bucle local,
  privada, de enlace local, no especificada, reservada o de multidifusión; y nombres sin ningún punto. El
  `ValueError` no lleva el valor y `configuration_error_message` solo nombra la variable.
- **Rationale**: son las reglas propias de la dirección que Pagos aplica antes de mirar su lista de
  orígenes permitidos; con ellas, una configuración con la que este servicio arranca solo puede fallar en
  Pagos por esa lista (configuración de Pagos). El pedido pedía como mínimo `https`, sin credenciales y sin
  fragmento; aceptar `https://localhost/...` arrancaría bien y haría fallar cada pago con 503.
- **Alternatives considered**: solo las tres reglas del pedido (deja pasar direcciones que Pagos siempre
  rechaza); reutilizar `_is_local_or_internal` de este archivo (solo mira `localhost`, `127.0.0.1`, `::1` y
  nombres sin punto: no cubre redes privadas); copiar también la lista de orígenes permitidos (es
  configuración de Pagos; duplicarla obligaría a mantener dos listas).

## R3. La dirección se envía tal como se configuró

- **Decision**: se guarda y se envía el texto configurado sin los espacios externos; no se pasa a
  minúsculas ni se quitan la barra final, el puerto o la consulta (FR-005).
- **Rationale**: la ruta y la consulta son del frontend; Pagos también conserva la dirección tal como llega
  («así es como viaja al proveedor») y compara el origen sin distinguir mayúsculas.
- **Alternatives considered**: normalizar como `_normalized_address` (quita la barra final: cambiaría
  `/payment/` por `/payment`, que para el enrutador del frontend puede no ser lo mismo).

## R4. El cuerpo de la creación

- **Decision**: `PaymentsApiClient.create_payment` recibe un argumento nombrado más,
  `return_url: str | None = None`. Con valor, agrega `"redirect_urls": {"success": return_url}`; sin él, el
  cuerpo no lleva la clave (FR-006, FR-007). El cobro de clínicas no pasa el argumento (FR-011).
- **Rationale**: Pagos repite `success` para pendiente y rechazo, así que basta un campo. El valor por
  omisión deja intactas las llamadas existentes (`clinic_subscription_service.py`) y sus pruebas.
- **Alternatives considered**: enviar `pending` y `failure` con el mismo valor (redundante y más cuerpo que
  validar); `"redirect_urls": null` sin la variable (cambiaría el cuerpo de hoy y la huella de idempotencia
  de Pagos: rompe FR-007 y SC-002).

## R5. La clave de idempotencia

- **Decision**: `billing_rules.idempotency_key` recibe `return_url: str | None = None`. Sin dirección, el
  texto que se resume es exactamente el de la spec 010 (`fecha|periodo|importe|intento|descripción`), así
  que la clave es idéntica carácter por carácter (FR-008, SC-002). Con dirección, se resume
  `json.dumps([texto_de_la_spec_010, dirección])`: un arreglo JSON nunca coincide con el texto sin dirección
  (que empieza con la fecha) y dos pares distintos nunca dan el mismo texto, aunque la descripción tenga
  `|`.
- **Rationale**: Pagos rechaza con 409 la misma clave con otro cuerpo, y desde su feature 002 la dirección
  es parte de ese cuerpo. La spec 010 ya resolvió el mismo problema con la descripción (research R6 de esa
  spec): si cambia entre una respuesta perdida y su reintento, la clave cambia y se crea otro pago en vez
  de quedar atorado en el 409 (que aquí es 503 en cada intento, porque el número de intento solo avanza al
  cerrarse un cobro).
- **Alternatives considered**: no incluirla (un cambio de configuración con una respuesta perdida dejaría
  ese periodo en 503 hasta que alguien cancele el pago a mano en Pagos, que no ofrece cancelar); incluirla
  siempre, también vacía (cambiaría todas las claves al desplegar: rompe SC-002); separarla con `|` (ambiguo
  si un nombre de plan termina en `|https://…`).

## R6. Quién conoce la dirección

- **Decision**: `SubscriptionPeriodService` recibe `return_url: str | None = None` en su constructor;
  `get_subscription_period_service` (`src/dependencies.py`) le pasa
  `get_payments_settings().payments_return_url`. `start_payment` la usa para la clave y para el cuerpo.
- **Rationale**: la clave se calcula en el Service, así que el Service la necesita de todos modos; tenerla
  en un solo lugar evita que la clave y el cuerpo se desincronicen. El valor por omisión mantiene válidas
  las construcciones existentes (pruebas y `make_world`).
- **Alternatives considered**: guardarla en el cliente, como el token de servicio (el Service tendría que
  pedírsela al cliente para la clave: dos fuentes de verdad); leer la configuración dentro del Service (los
  Services no leen el entorno; lo inyecta la capa de dependencias, Principio I).

## R7. Cuando Pagos rechaza la dirección

- **Decision**: el mapeo de respuestas no cambia: un 422 sigue siendo «respuesta inesperada»
  (`PaymentsApiUnavailable` → 503 `payments_unavailable`, sin registrar cobro), igual que un 409. Solo el
  registro cambia: si la creación llevaba dirección de regreso y Pagos respondió 422, el cliente registra un
  error que dice que se envió una dirección de regreso y que se revise que su origen esté permitido en
  Pagos, sin la dirección (FR-010).
- **Rationale**: el caso real es una configuración de Pagos incompleta (origen no permitido) o un Pagos sin
  su feature 002; quien opera necesita saberlo por el registro, y la persona recibe el mismo 503 de siempre.
- **Alternatives considered**: leer el cuerpo del 422 de Pagos para ver el campo señalado (acopla el
  cliente al formato de error de Pagos para un dato que no cambia la respuesta); reintentar sin la dirección
  (un reintento automático de una operación que crea pagos, prohibido por el Principio IX, y escondería el
  error de configuración).

## R8. Pruebas

- **Decision**:
  - **Unitarias (nivel rápido)**: la tabla «Direcciones de referencia» contra `PaymentsSettings` y contra el
    arranque (`lifespan`), incluidos el mensaje y el registro sin el valor; el cuerpo exacto del cliente
    con y sin dirección y el registro del 422; la clave (sin dirección, igual a un valor fijo calculado con
    el código de la spec 010; con dirección, distinta y determinista); el Service con el doble de Pagos de
    `tests/billing_support.py` (dirección enviada, clave, respuesta perdida con la misma configuración y con
    otra dirección).
  - **De contrato (nivel lento, PostgreSQL real)**: un archivo nuevo con la aplicación real y la simulación
    de Pagos: con la variable, Pagos guarda `redirect_urls.success`; sin ella, no hay campo; la respuesta no
    cambia; un 422 de Pagos da 503 sin cobro; leer el periodo con parámetros de «aprobado» en la petición no
    aplica nada mientras Pagos diga `pending`.
  - **Simulación de Pagos** (`tests/stubs/payments_api/app.py`): valida `redirect_urls` como Pagos (objeto
    solo con `success`, `pending` y `failure`; `success` obligatorio; textos `https://` de 1 a 2048
    caracteres; si no, 422 `validation_error`), lo guarda con el pago y agrega el modo de falla
    `return_not_allowed` (422 con el cuerpo de Pagos para un origen no permitido).
  - **Aislamiento**: el fixture automático `billing_environment` (`tests/conftest.py`) quita
    `PAYMENTS_RETURN_URL` y hace que `PaymentsSettings` no lea `.env` durante las pruebas (ya define sus dos
    variables obligatorias), para que el `.env` local de quien desarrolla nunca cambie un resultado; las
    pruebas de arranque agregan la variable a su lista `ENV_NAMES`.
- **Rationale**: Principio V (Service con dobles, cada endpoint por HTTP, simulaciones con fallas, niveles
  rápido y lento). Las colecciones de Postman no cambian porque ninguna operación cambia (Principio V: se
  actualizan con las features que cambian el contrato que cubren).
- **Alternatives considered**: definir la variable en la pila de punta a punta (dejaría sin cubrir ahí el
  caso sin variable, que es el del desarrollo local, y Postman no puede ver lo que recibió la simulación).

## R9. Documentación y despliegue

- **Decision**: `.env.example` (variable opcional comentada, vacía en desarrollo local, con un ejemplo),
  README (fila en la tabla de variables y una nota en la sección de periodos), `docker-compose.yml`
  (`PAYMENTS_RETURN_URL: ${PAYMENTS_RETURN_URL:-}`); en la pila aislada de punta a punta, la variable vacía a
  propósito, porque Docker Compose interpola con el `.env` de quien la corre. Sin cambios en OpenAPI, matriz
  de permisos, migraciones, `DATA_SCHEMA.md` ni colecciones de Postman.
- **Rationale**: FR-013 y FR-015. La nota operativa clave es que el origen del frontend debe estar en
  `CHECKOUT_RETURN_ALLOWED_ORIGINS` de Pagos de ese ambiente.

## R10. Puertas de calidad antes de integrar a `main`

- **Decision**: la suite completa (`uv run pytest -m ""`) contra la base de pruebas PostgreSQL 17 (incluye
  migraciones desde cero, cobertura de permisos, OpenAPI y capas); las colecciones de Postman con Newman
  contra la pila aislada; y la comparación de `/openapi.json` de `main` y de la rama (debe ser idéntico,
  FR-013).
- **Rationale**: «Flujo de Desarrollo y Puertas de Calidad» de la constitución. Durante
  `/speckit-implement` solo corre el nivel rápido (Principio V).
