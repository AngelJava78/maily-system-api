# Feature Specification: Regreso automático a MailySoft después de pagar la suscripción («Dirección de regreso del pago»)

**Feature Branch**: `011-payment-return-url`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "Atender en maily-system-api el pedido de mailySoft-pagos
(`mailySoft-pagos/specs/002-checkout-return-urls/contracts/pedido-system-api.md`): al iniciar el pago
de un periodo de suscripción (`start_payment`), enviar a Pagos la dirección de la pantalla de pago del
frontend para que Mercado Pago regrese solo al Dueño a MailySoft cuando su pago se aprueba. La dirección
sale de una variable de entorno nueva y opcional (`PAYMENTS_RETURN_URL`, la dirección absoluta
`https://…/payment` del frontend de ese ambiente). Con la variable, el cuerpo de `POST /api/v1/payments`
lleva `redirect_urls.success` con exactamente ese valor; sin ella (desarrollo local, porque Mercado Pago
no acepta direcciones locales), el cuerpo queda idéntico al de hoy. Se valida al arrancar como las demás
direcciones (`https`, sin credenciales ni fragmento) y una dirección mal formada impide arrancar con un
mensaje que nombra la variable sin repetir su valor. Los parámetros que Mercado Pago agrega a la
dirección de regreso nunca son prueba de pago: un cobro solo se aplica cuando Pagos lo reporta aprobado,
en la conciliación que ya ocurre al leer el periodo."

## Clarifications

### Session 2026-11-25

La persona responsable pidió ejecutar el ciclo completo de Spec Kit sin preguntas y con la opción
recomendada en cada duda. Las dudas que dejaba abierta la descripción se cierran así:

- Q: ¿Qué reglas revisa el arranque además de `https`, sin credenciales y sin fragmento? → A: Las mismas
  reglas propias de la dirección que aplica Pagos: con equipo (host) y puerto válido, sin espacios ni
  caracteres de control, de 2048 caracteres o menos y nunca un equipo local ni de una red privada. Solo
  la lista de orígenes permitidos queda del lado de Pagos (es su configuración). Así, una dirección con la
  que este servicio arranca solo puede ser rechazada por Pagos si su origen no está en esa lista.
- Q: ¿La dirección forma parte de la clave de idempotencia del cobro? → A: Sí, pero solo cuando está
  configurada: sin la variable, las claves son idénticas a las de hoy. Con ella, un cambio de la
  dirección entre una respuesta perdida y su reintento da otra clave (y otro pago) en vez de quedar
  atorado en el rechazo de Pagos por «misma clave con otro cuerpo», igual que ya ocurre con la descripción.
- Q: ¿El cobro de las suscripciones de clínicas (spec 010-cobro-real-suscripciones) también la envía? →
  A: No. El pedido es solo para el pago de los periodos de suscripción; ese otro cobro no cambia.
- Q: ¿Se normaliza la dirección (minúsculas, barra final, puerto)? → A: No. Se envía tal como se
  configuró, solo sin los espacios del principio y del final: la ruta y la consulta son del frontend.
- Q: ¿La pila de punta a punta (colecciones de Postman) se configura con la variable? → A: No. Esa pila
  reproduce la configuración del desarrollo local (sin la variable) y ninguna operación de esta API
  cambia; los dos casos, con y sin la variable, se prueban con pytest contra la simulación de Pagos.

## User Scenarios & Testing *(mandatory)*

El actor principal es **el Dueño (rol Owner) de una organización cliente de MailySoft**, que paga su
suscripción desde la aplicación (el frontend): la aplicación le pide a esta API que inicie el pago, la
API crea el cobro en Pagos y la aplicación lleva a la persona al checkout de Mercado Pago. Interviene
además **quien opera el servicio**, que configura la dirección de regreso de cada ambiente.

Hoy, al terminar de pagar, la persona se queda en la pantalla de Mercado Pago («¡Listo! Tu pago ya se
acreditó») y tiene que volver por su cuenta a MailySoft, que es donde el pago se aplica (al leer el
periodo). Desde su feature 002, Pagos puede pedirle a Mercado Pago que regrese a la persona
automáticamente cuando el pago se aprueba, pero necesita que quien crea el pago le diga **a qué
dirección**: esa dirección la conoce esta API, por configuración.

### User Story 1 - El Dueño vuelve solo a MailySoft después de pagar (Priority: P1)

Con la dirección de regreso configurada, cada vez que el Dueño inicia el pago de su suscripción, esta API
se la envía a Pagos junto con el cobro. Al aprobarse el pago, Mercado Pago lleva a la persona a esa
dirección (la pantalla de pago de la aplicación), la aplicación vuelve a leer el periodo y la
conciliación que ya existe aplica el pago: la persona ve su nueva fecha de pago sin haber navegado a mano.

**Why this priority**: Es todo el valor de la feature: cerrar el recorrido del pago dentro de MailySoft.

**Independent Test**: Con Pagos simulado y la dirección configurada, iniciar el pago de una organización
y comprobar que el cobro que recibió Pagos lleva la dirección de regreso, exactamente con el valor
configurado, y que la respuesta de la API no cambia.

**Acceptance Scenarios**:

1. **Given** la dirección de regreso configurada con `https://app.mailysoft.com/payment`, **When** el
   Dueño inicia el pago de un periodo, **Then** Pagos recibe una sola creación de pago cuyo cuerpo lleva
   `redirect_urls` con únicamente `success` igual a `https://app.mailysoft.com/payment`, además de los
   mismos campos de hoy (proveedor, importe, moneda, referencia, descripción y metadatos).
2. **Given** la dirección configurada, **When** el Dueño inicia el pago, **Then** la respuesta de la API es
   la misma de hoy (201 con la dirección del checkout, el importe, la moneda y el periodo de cobro): la
   dirección de regreso nunca aparece en la respuesta.
3. **Given** la dirección configurada y un cobro pendiente para el periodo, **When** el Dueño inicia el
   pago otra vez, **Then** no se crea otro pago (200 con el mismo checkout), como hoy.
4. **Given** la dirección configurada y una creación cuya respuesta se perdió, **When** el Dueño lo
   intenta de nuevo con la misma configuración, **Then** Pagos devuelve ese mismo pago (misma clave y
   mismo cuerpo) y queda un solo cobro registrado.
5. **Given** la dirección configurada con una consulta (`https://app.mailysoft.com/payment?origen=pago`)
   o con barra final, **When** se inicia el pago, **Then** Pagos recibe la dirección exactamente así.

---

### User Story 2 - Sin la dirección configurada, todo sigue exactamente como hoy (Priority: P1)

En el desarrollo local (Mercado Pago no acepta direcciones locales y Pagos las rechazaría) y en cualquier
ambiente donde todavía no se configure, la variable no existe o está vacía. Entonces esta API se comporta
exactamente igual que antes de esta feature: el cuerpo que envía a Pagos no lleva el campo y las claves
de idempotencia son las mismas.

**Why this priority**: Sin esto, desplegar la feature rompería el desarrollo local y los ambientes que aún
no tienen el origen del frontend permitido en Pagos.

**Independent Test**: Sin la variable (y con la variable vacía), iniciar el pago y comparar el cuerpo y la
clave de idempotencia que recibió Pagos con los de la versión anterior.

**Acceptance Scenarios**:

1. **Given** la variable no definida, **When** el Dueño inicia el pago, **Then** el cuerpo que recibe Pagos
   no tiene el campo `redirect_urls` (ni vacío ni nulo) y es idéntico al de hoy.
2. **Given** la variable definida pero vacía (como la pasa Docker Compose cuando el `.env` no la tiene),
   **When** arranca el servicio y se inicia el pago, **Then** arranca y se comporta como sin la variable.
3. **Given** la variable no definida, **When** se calcula la clave de idempotencia de un cobro, **Then**
   es idéntica, carácter por carácter, a la que daba la versión anterior para las mismas condiciones.
4. **Given** la variable definida, **When** se crea un cobro de las suscripciones de clínicas (spec
   010-cobro-real-suscripciones), **Then** su cuerpo no cambia: nunca lleva la dirección de regreso.

---

### User Story 3 - Quien opera configura la dirección y una dirección inválida impide arrancar (Priority: P2)

Quien opera el servicio escribe en la variable la dirección de la pantalla de pago del frontend de ese
ambiente y agrega su origen a la lista de orígenes permitidos de Pagos. Si la dirección no puede servir
(no es `https`, lleva credenciales o fragmento, apunta a un equipo local, etc.), el servicio no arranca y
el mensaje dice qué variable es, sin mostrar su valor; así el error aparece al desplegar y no en el primer
pago de un cliente.

**Why this priority**: Una dirección inválida haría fallar todos los pagos; detectarla al arrancar evita
descubrirlo con un cliente. Es P2 porque sin la variable (historia 2) nada se rompe.

**Independent Test**: Arrancar el servicio con cada valor de la tabla de direcciones válidas e inválidas y
comprobar si arranca, el mensaje y el registro (sin el valor).

**Acceptance Scenarios**:

1. **Given** la variable con `https://app.mailysoft.com/payment`, **When** arranca el servicio, **Then**
   arranca.
2. **Given** la variable con una dirección que incumple alguna regla (tabla «Direcciones de referencia»),
   **When** se intenta arrancar, **Then** no arranca y el mensaje nombra `PAYMENTS_RETURN_URL` y no
   contiene el valor; el registro del error tampoco lo contiene.
3. **Given** la variable inválida y además otra variable obligatoria ausente, **When** se intenta arrancar,
   **Then** un solo mensaje nombra las dos, como hoy con las demás variables.
4. **Given** el servicio en marcha, **When** cambia el valor de la variable en el entorno, **Then** sigue
   usando el valor con el que arrancó hasta que se reinicie.
5. **Given** el archivo `.env.example` y el README, **When** se consultan, **Then** documentan la variable,
   que es opcional, su valor de ejemplo por ambiente y que su origen debe estar permitido en Pagos.

---

### User Story 4 - El regreso nunca es prueba de pago (Priority: P2)

Mercado Pago agrega a la dirección de regreso parámetros con el resultado del pago (por ejemplo, un
estatus «aprobado» y el número de operación). Esos parámetros los ve la aplicación, que solo los usa para
volver a leer el periodo; esta API no los recibe ni los toma en cuenta. Un cobro solo se aplica cuando
Pagos lo reporta aprobado en la conciliación que ya existe.

**Why this priority**: Es una regla de seguridad: cualquiera puede escribir una dirección con
`?status=approved`; tomarla como pago regalaría periodos. Esta API ya la cumple; la feature solo debe no
romperla.

**Independent Test**: Comprobar que la API no publica ninguna operación nueva y que, con un cobro pendiente
que Pagos todavía reporta pendiente, la fecha del siguiente pago no se mueve por más lecturas que haga la
aplicación al volver.

**Acceptance Scenarios**:

1. **Given** un cobro pendiente que Pagos todavía reporta `pending`, **When** la persona vuelve a la
   aplicación con parámetros de «aprobado» en la dirección y la aplicación lee el periodo, **Then** el
   cobro sigue pendiente y la fecha del siguiente pago no se mueve.
2. **Given** el mismo cobro, **When** Pagos lo reporta `approved` y la aplicación lee el periodo, **Then**
   el cobro se aplica una sola vez, como hoy.
3. **Given** el contrato publicado de la API, **When** se compara con el anterior, **Then** no hay
   operaciones, campos ni permisos nuevos.

---

### Direcciones de referencia

Tabla que las pruebas deben reproducir (criterio SC-003). «Arranca» significa que el servicio arranca y la
envía tal cual (sin los espacios del principio y del final).

| # | Valor de `PAYMENTS_RETURN_URL` | Resultado | Regla |
|---|---|---|---|
| 1 | *(no definida)* o vacía | Arranca y **no** envía el campo | Historia 2 |
| 2 | `https://app.mailysoft.com/payment` | Arranca | — |
| 3 | `https://app.mailysoft.com:8443/payment?origen=pago` | Arranca (puerto y consulta se conservan) | — |
| 4 | `https://staging.mailysoft.com/payment/` | Arranca (la barra final se conserva) | — |
| 5 | `  https://app.mailysoft.com/payment  ` | Arranca y envía `https://app.mailysoft.com/payment` | Se quitan los espacios externos |
| 6 | `http://app.mailysoft.com/payment` | No arranca | Solo `https` |
| 7 | `ftp://app.mailysoft.com/payment` | No arranca | Solo `https` |
| 8 | `/payment` o `app.mailysoft.com/payment` | No arranca | Dirección absoluta con equipo |
| 9 | `https://usuario:clave@app.mailysoft.com/payment` | No arranca | Sin credenciales |
| 10 | `https://app.mailysoft.com/payment#pago` | No arranca | Sin fragmento |
| 11 | `https://app.mailysoft.com/pa yment` | No arranca | Sin espacios ni caracteres de control |
| 12 | `https://app.mailysoft.com/payment?x=` + 2100 caracteres | No arranca | A lo más 2048 caracteres |
| 13 | `https://localhost:8080/payment` o `https://app.localhost/payment` | No arranca | Nunca un equipo local |
| 14 | `https://127.0.0.1/payment`, `https://10.0.0.5/payment`, `https://192.168.1.20/payment` o `https://[::1]/payment` | No arranca | Nunca una red privada o local |
| 15 | `https://frontend/payment` | No arranca | Un nombre sin punto es de una red interna o de un contenedor |
| 16 | `https://app.mailysoft.com:99999/payment` | No arranca | Puerto válido |

### Edge Cases

- **La variable cambia con un cobro pendiente**: el cobro ya registrado conserva en Pagos la dirección con
  que se creó; volver a iniciar el pago de ese periodo lo lee (no lo crea de nuevo), así que no hay
  conflicto. La dirección nueva aplica a los cobros que se creen después.
- **La variable cambia entre una respuesta perdida y su reintento**: la clave cambia con la dirección, así
  que el reintento crea otro pago en Pagos; el primero nunca se registró ni se ofreció (queda pendiente en
  Pagos sin efecto), igual que cuando cambia la descripción del plan entre ambos.
- **Pagos rechaza la dirección** (su origen no está en la lista de permitidos de Pagos, o ese Pagos no
  tiene todavía su feature 002): iniciar el pago responde 503 (`payments_unavailable`), como ante
  cualquier respuesta inesperada, y no registra ningún cobro; el registro del servicio indica que se envió
  una dirección de regreso (sin la dirección) para orientar a quien opera.
- **El pago queda pendiente o se rechaza**: Mercado Pago solo regresa automáticamente los pagos aprobados;
  en los demás muestra su propia pantalla, cuyo botón de volver usa la misma dirección (Pagos la repite
  para pendiente y rechazo).
- **La persona vuelve antes de que Pagos sepa de la aprobación**: la lectura del periodo muestra el cobro
  en curso y la siguiente lectura lo aplica; nada nuevo en esta API.
- **Mayúsculas en el esquema o el equipo** (`HTTPS://App.MailySoft.com/payment`): se aceptan y se envían
  tal cual; Pagos compara el origen sin distinguir mayúsculas.
- **Dirección de otro dominio que el del frontend**: esta API no conoce el dominio del frontend; la lista
  de orígenes permitidos de Pagos es la que lo restringe.

## Requirements *(mandatory)*

### Functional Requirements

**Configuración**

- **FR-001**: La dirección de regreso MUST venir de una variable de entorno opcional, `PAYMENTS_RETURN_URL`:
  la dirección absoluta de la pantalla de pago del frontend de ese ambiente. Se lee al arrancar y un
  cambio MUST requerir reiniciar el servicio.
- **FR-002**: Una variable vacía MUST contar como no definida (Docker Compose pasa valores vacíos cuando el
  `.env` no la tiene).
- **FR-003**: Si está definida, MUST cumplir, después de quitarle los espacios del principio y del final:
  esquema `https`; equipo (host) presente y puerto válido; sin usuario ni contraseña; sin fragmento (ni el
  carácter `#`); sin espacios ni caracteres de control; a lo más 2048 caracteres; y un equipo que no sea
  local ni de una red privada (`localhost` y sus subdominios, direcciones IP de bucle local, privadas, de
  enlace local, no especificadas, reservadas o de multidifusión, y nombres sin ningún punto). La ruta y la
  consulta son libres.
- **FR-004**: Si no cumple FR-003, el servicio MUST NOT arrancar y el mensaje MUST nombrar
  `PAYMENTS_RETURN_URL` sin mostrar su valor, ni en el mensaje ni en el registro; si además faltan o
  fallan otras variables, un solo mensaje MUST nombrarlas todas (como hoy).
- **FR-005**: La dirección MUST conservarse tal como se configuró (salvo los espacios externos): sin pasar
  a minúsculas, sin quitar la barra final ni el puerto, sin tocar la consulta.

**Creación del cobro (periodos de suscripción)**

- **FR-006**: Con la dirección configurada, cada creación de pago que hace iniciar el pago de un periodo
  (spec 010-subscription-periods, FR-020) MUST incluir en el cuerpo `redirect_urls` con un único campo,
  `success`, igual a la dirección configurada. No se envían `pending` ni `failure`: Pagos usa `success`
  para los tres casos.
- **FR-007**: Sin la dirección configurada, el cuerpo MUST ser idéntico al de antes de esta feature: sin el
  campo `redirect_urls` (ni vacío ni nulo).
- **FR-008**: La clave de idempotencia del cobro MUST incluir la dirección de regreso cuando está
  configurada, y MUST ser idéntica a la de antes de esta feature cuando no lo está.
- **FR-009**: La respuesta de iniciar el pago MUST NOT cambiar: ni códigos, ni campos, ni la dirección de
  regreso en ella.
- **FR-010**: Si Pagos responde a la creación algo distinto de un pago válido (incluido el 422 por una
  dirección que no acepta), iniciar el pago MUST responder como hoy ante una respuesta inesperada (503
  `payments_unavailable`, sin registrar ningún cobro). Cuando la creación llevaba dirección de regreso y
  Pagos respondió 422, el registro MUST decir que se envió una dirección de regreso, sin la dirección.
- **FR-011**: La creación de cobros de las suscripciones de clínicas (spec 010-cobro-real-suscripciones)
  MUST NOT cambiar: su cuerpo nunca lleva la dirección de regreso.

**El regreso no es prueba de pago**

- **FR-012**: Esta API MUST NOT recibir ni interpretar el regreso de la persona ni los parámetros que
  Mercado Pago agrega a la dirección: no se publica ninguna operación nueva, y un cobro solo se aplica o se
  cierra en la conciliación con lo que Pagos reporta (spec 010-subscription-periods, FR-026 a FR-028).

**Contrato, documentación y pruebas**

- **FR-013**: Esta feature MUST NOT cambiar el contrato publicado (operaciones, campos, códigos y
  permisos), ni la matriz «operación → permiso», ni la base de datos.
- **FR-014**: El contrato que se consume de Pagos (el campo nuevo, sus reglas y sus errores) MUST
  documentarse en `contracts/` de esta feature (Principio IX), y la simulación de Pagos de las pruebas MUST
  validar y registrar el campo como lo hace Pagos (Principio V).
- **FR-015**: `.env.example`, el README y `docker-compose.yml` MUST documentar o pasar la variable: que es
  opcional, que se deja vacía en el desarrollo local, un valor de ejemplo y que su origen debe estar en la
  lista de orígenes permitidos de Pagos de ese ambiente (`CHECKOUT_RETURN_ALLOWED_ORIGINS`).

### Key Entities *(include if feature involves data)*

- **Dirección de regreso** *(configuración; no se guarda en la base de datos)*: la dirección `https` de la
  pantalla de pago del frontend de un ambiente. Una por ambiente; la misma para todas las organizaciones.
  Viaja a Pagos en cada creación de cobro de los periodos de suscripción y forma parte de la identidad
  (clave de idempotencia) de ese cobro.

### Contrato consumido de Pagos

Resumen (Principio IX); el detalle está en `contracts/payments-api-integration.md`. Lo que dice «existe»
se verificó leyendo mailySoft-pagos en solo lectura (su feature 002, integrada en su `main` el
2026-11-25).

| Qué | Estado | Para qué | Qué bloquea |
|---|---|---|---|
| Campo opcional `redirect_urls` (`success` obligatorio; `pending` y `failure` opcionales) en `POST /api/v1/payments` | Existe (Pagos 002) | Pedir a Mercado Pago el regreso automático | — |
| Rechazo 422 `validation_error` de una dirección inválida o de un origen no permitido | Existe | — | Sin el origen del frontend permitido en Pagos, cada inicio de pago responde 503 mientras la variable esté definida |
| La dirección forma parte de la idempotencia de Pagos (misma clave con otra dirección: 409) | Existe | — | Nada: FR-008 evita reutilizar una clave con otra dirección |
| Orígenes permitidos (`CHECKOUT_RETURN_ALLOWED_ORIGINS` de Pagos) | Configuración de Pagos | Que Pagos acepte la dirección | El regreso automático en ese ambiente |

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Con la dirección configurada y Pagos y Mercado Pago (pruebas) listos, el 100 % de los pagos
  aprobados regresa a la persona a la pantalla de pago de MailySoft sin que navegue a mano, y esa pantalla
  muestra la nueva fecha de pago en su primera o segunda lectura.
- **SC-002**: Sin la dirección configurada, el 100 % de los cuerpos y de las claves de idempotencia que
  recibe Pagos es idéntico al de la versión anterior para las mismas condiciones.
- **SC-003**: El 100 % de las filas de «Direcciones de referencia» se reproduce: las inválidas impiden
  arrancar con un mensaje que nombra la variable y no contiene el valor; las válidas arrancan y se envían
  como indica la tabla.
- **SC-004**: 0 cobros aplicados o cerrados por el regreso de la persona: solo la conciliación con Pagos
  cambia el estado de un cobro.
- **SC-005**: Las pruebas existentes siguen en verde sin cambiar ninguna de sus comprobaciones (solo se
  agrega la variable nueva a las listas de variables que las pruebas de arranque aíslan).

## Assumptions

- **Pagos con su feature 002 desplegada**: la variable se define en un ambiente solo cuando su Pagos ya
  acepta `redirect_urls` y tiene el origen del frontend en su lista de orígenes permitidos. Sin eso, Pagos
  rechaza la creación (422) y esta API responde 503 (FR-010).
- **La pantalla de pago del frontend** es `/payment` (existe en mailySoft-frontend) y al cargarse lee el
  periodo, lo que dispara la conciliación. La ruta no se valida aquí: es configuración de cada ambiente.
- **Mercado Pago** solo regresa automáticamente los pagos aprobados y no acepta direcciones locales; por eso
  en el desarrollo local la variable se deja vacía y la persona vuelve a mano (como hoy).
- **Una dirección por ambiente**, igual para todas las organizaciones; no hay dirección por organización ni
  por petición (la aplicación no la manda).
- **Sin cambios en las colecciones de punta a punta**: las colecciones de Postman no cambian porque ninguna
  operación cambia; su pila sigue sin la variable (la deja vacía para no heredarla del `.env` local).

### Fuera de alcance

- Recibir o procesar el regreso de la persona en esta API, o usar sus parámetros.
- Direcciones distintas para pendiente y rechazo.
- La dirección de regreso para los cobros de las suscripciones de clínicas (spec
  010-cobro-real-suscripciones).
- La lista de orígenes permitidos de Pagos y las pantallas del frontend.
- Cancelar en Pagos el pago que quedó sin registrar tras una respuesta perdida.
