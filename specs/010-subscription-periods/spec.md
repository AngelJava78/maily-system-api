# Feature Specification: Periodo de prueba y siguiente pago de cada organización («Periodos de suscripción»)

**Feature Branch**: `010-subscription-periods`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "Que este API (maily-system-api) sea el dueño del control, para cada
organización cliente de MailySoft, de su periodo de prueba y de la fecha en la que debe hacer su
siguiente pago, y que se lo informe a la aplicación para que muestre cuánto tiempo le falta y lleve a
la persona a pagar. Con el token del Dueño (rol Owner) de la organización debe poder: (1) consultar el
estado —en prueba, al corriente, vencida o sin cobro—, cuándo termina la prueba, la fecha del siguiente
pago, los días que faltan (o de atraso), el plan, el periodo de cobro, el importe a pagar y si hay un
cobro en curso, verificando antes en Pagos los cobros iniciados sin resolver y aplicando los aprobados;
(2) iniciar el pago, creando el cobro en Pagos (referencia «system-api:subscription» con el id de la
organización) con un importe que calcula este API a partir de su catálogo y que nunca manda el
cliente; y (3) mover la fecha del siguiente pago cuando Pagos aprueba un cobro, exactamente una vez.
Este API guarda solo datos propios (inicio del primer periodo, fin de la prueba, hasta cuándo está
pagada y los cobros que inició y aplicó, con fecha y hora en UTC) y pide en cada uso a Clínicas
(organización, plan vigente, periodo de cobro) y a Pagos (pagos) lo que es suyo. El estado se calcula
al consultar, sin tareas programadas, con un reloj inyectable para las pruebas. Si Clínicas no
responde, 503 (el acceso falla cerrado); si Pagos no responde al consultar, se devuelve lo guardado
indicando que no se pudo verificar un cobro en curso, y al iniciar el pago, 503; nunca se inventan
fechas ni importes. Como Usuarios, Clínicas y Pagos todavía no ofrecen todo lo necesario, se documenta
el contrato consumido de cada uno, se desarrolla contra simulaciones en las pruebas y se escribe un
documento de pedidos por API. Cinco decisiones de negocio (periodo de gracia, fecha de corte,
reembolsos, IVA y fecha de alta) se resolvieron con su valor por defecto, sin sesión de preguntas, por
indicación de la persona responsable (ver «Clarifications»)."

## Clarifications

### Session 2026-11-18

La persona responsable pidió ejecutar el ciclo completo de Spec Kit aceptando todas las opciones
predeterminadas y sin preguntas. Por eso las cinco decisiones que la descripción original dejaba
abiertas para `/speckit-clarify` se cierran con el valor por defecto que esta especificación ya asumía
(en D1, D2, D3 y D5 coincide con la recomendación):

- Q: ¿Hay un periodo de gracia después de vencer? → A: No (D1). La organización es `overdue` desde que
  el reloj alcanza la fecha del siguiente pago; solo se informan el estado y los días de atraso.
- Q: ¿Qué fecha de corte rige para las organizaciones que ya existen al desplegar? → A: La del
  despliegue (D2). La variable es obligatoria y las organizaciones existentes empiezan su primer periodo
  en ese instante.
- Q: ¿Un reembolso revoca el periodo ya pagado? → A: No (D3); se atiende aparte.
- Q: ¿El importe cobrado suma IVA? → A: No (D4): se cobra el precio del catálogo tal cual. La alternativa
  recomendada (precio más IVA con una tasa configurable y desglose) queda registrada para añadirse
  después, sin cambiar los campos existentes, cuando quien lleva la contabilidad fije la tasa.
- Q: ¿La fecha de alta es la `created_at` de la organización que expone Clínicas? → A: Sí (D5).

## User Scenarios & Testing *(mandatory)*

El actor es **el Dueño (rol Owner) de una organización cliente de MailySoft**, que usa la aplicación de
las clínicas (el frontend). Toda persona que use la API se identifica con un token de acceso y solo
puede hacer lo que sus permisos le autorizan; la identidad y los permisos los decide el API de
usuarios, no este servicio. Esta API **informa y cobra**: no bloquea ni suspende el acceso de nadie al
vencer (esa es otra decisión). Intervienen además, fuera de la API, quien opera el servicio
(configuración, historia 7) y quien coordina con los demás equipos (pedidos, historia 8).

Vocabulario de esta especificación: **organización** (el cliente de MailySoft; dato de Clínicas),
**plan** (una suscripción del catálogo de esta API), **periodo de cobro** (mensual o anual, el que la
organización eligió; dato de Clínicas), **cobro** (la solicitud de pago que esta API crea en Pagos y
registra; corresponde a un pago de Pagos) y **periodo cubierto** (el lapso que paga un cobro aplicado).

### User Story 1 - Saber en qué punto está la prueba y cuándo toca pagar (Priority: P1)

El Dueño abre la aplicación y esta le pregunta a la API por el estado de su organización. La respuesta
dice si la organización está **en prueba**, **al corriente**, **vencida** o **sin cobro**; cuándo termina
la prueba; la fecha del siguiente pago; cuántos días faltan (o cuántos van de atraso); qué plan y qué
periodo de cobro tiene; cuánto debe pagar, en pesos mexicanos; y si hay un cobro en curso. La primera
vez que se consulta una organización, la API crea su registro con las fechas que le corresponden; las
veces siguientes lo reutiliza. Antes de responder, revisa en Pagos los cobros que ella inició y siguen
sin resolverse y aplica los aprobados (historia 3).

**Why this priority**: Es el motivo de la feature. Hoy nadie registra cuándo termina la prueba de una
organización ni hasta cuándo está pagada; sin esta consulta la aplicación no puede mostrar cuánto
tiempo le queda a la persona ni cuándo debe pagar, y la promesa del alta («El pago se solicita al
terminar la prueba») no tiene con qué cumplirse.

**Independent Test**: Con Clínicas, Pagos y Usuarios simulados y un reloj fijo, consultar una
organización nueva y comprobar su estado y sus fechas; mover el reloj a cada lado de los límites (fin de
la prueba y fecha del siguiente pago) y comprobar el estado y los días; repetir la consulta y comprobar
que las fechas no cambian.

**Acceptance Scenarios**:

1. **Given** una organización dada de alta el 2026-11-20T15:30:00Z, con un plan de 14 días de prueba,
   periodo de cobro mensual y precio mensual de 499.00, y una fecha de corte anterior a su alta,
   **When** su Dueño la consulta el 2026-11-25T15:30:00Z, **Then** el estado es `trial`, la prueba
   termina el 2026-12-04T15:30:00Z, el siguiente pago vence en esa misma fecha, faltan 9 días, el
   importe es «499.00» MXN y no hay cobro en curso.
2. **Given** esa misma organización sin pagos, **When** se consulta el 2026-12-10T09:00:00Z, **Then** el
   estado es `overdue`, la fecha del siguiente pago sigue siendo 2026-12-04T15:30:00Z y los días valen
   −5 (cinco días de atraso).
3. **Given** una organización cuyo plan tiene 0 días de prueba, **When** se consulta por primera vez,
   **Then** no hay fecha de fin de prueba (`trial_ends_at` es `null`), el siguiente pago vence en la
   fecha de inicio y el estado es `overdue` en cuanto esa fecha pasa.
4. **Given** una organización cuyo importe vigente (por su plan y su periodo de cobro) es 0.00, **When**
   se consulta, **Then** el estado es `no_charge`, no hay fecha del siguiente pago ni días (ambos
   `null`) y el importe es «0.00».
5. **Given** una organización dada de alta antes de la fecha de corte, **When** se consulta por primera
   vez, **Then** su primer periodo empieza en la fecha de corte (no en su alta) y su prueba cuenta los
   días completos de su plan desde esa fecha.
6. **Given** una organización ya consultada, **When** se consulta de nuevo —también después de cambiar su
   plan o los días de prueba de ese plan en el catálogo—, **Then** el inicio y el fin de la prueba son
   los mismos de antes.
7. **Given** diez primeras consultas simultáneas de una misma organización, **When** se procesan,
   **Then** existe un solo registro y las diez respuestas traen las mismas fechas.
8. **Given** Pagos no responde y la organización tiene un cobro iniciado sin resolver, **When** se
   consulta, **Then** la respuesta es 200, con las fechas, el estado y el importe calculados con lo
   guardado, e indica que no se pudo verificar un cobro en curso (`payment_in_progress` es `null`).
9. **Given** cualquier respuesta 200, **When** se examinan sus cabeceras y sus fechas, **Then** declara
   que no debe guardarse en caché y todas las fechas van en ISO 8601 con zona UTC explícita.

---

### User Story 2 - Iniciar el pago y llegar al checkout (Priority: P1)

Cuando el Dueño decide pagar —durante la prueba, antes de la fecha del siguiente pago o ya vencida—, la
aplicación le pide a la API que inicie el pago. La API calcula el importe con el precio de su catálogo
para el plan y el periodo de cobro vigentes de la organización (la petición no trae importe), crea el
cobro en Pagos con la referencia «system-api:subscription» y el identificador de la organización, lo
registra como un cobro propio (identificador del pago en Pagos, importe, moneda y periodo que cubre) y
devuelve la dirección del checkout, a la que la aplicación lleva a la persona.

**Why this priority**: Es el paso que convierte el aviso en un pago; sin él la aplicación solo informaría
y la persona no tendría cómo pagar.

**Independent Test**: Con Pagos simulado, iniciar el pago de una organización con plan y periodo de cobro
conocidos y comprobar lo que recibió Pagos (importe en la unidad mínima, moneda, referencia), el registro
propio del cobro y la dirección devuelta; repetir la operación y comprobar que no hay un segundo cobro;
provocar una falla de Pagos y comprobar el 503 sin ningún cobro registrado.

**Acceptance Scenarios**:

1. **Given** una organización vencida, con periodo de cobro mensual y precio mensual de 499.00, **When**
   su Dueño inicia el pago, **Then** la respuesta es 201 con la dirección del checkout; Pagos recibió
   exactamente una creación de pago por 49900 (unidad mínima), moneda `MXN`, `resource_type`
   «system-api:subscription» y `resource_id` igual al identificador de la organización; y la API
   registró un cobro pendiente con el identificador del pago en Pagos, 499.00 MXN y periodo mensual.
2. **Given** la misma organización con periodo de cobro anual y precio anual de 4990.00, **When** inicia el
   pago, **Then** el importe es el precio anual (499000 en la unidad mínima) y el periodo que cubre el
   cobro es de doce meses.
3. **Given** un cobro pendiente para el periodo vigente, **When** el Dueño inicia el pago otra vez para ese
   mismo periodo, **Then** no se crea un segundo cobro, se devuelve el mismo checkout y la respuesta es
   200 (la primera fue 201).
4. **Given** una petición para iniciar el pago que incluye un importe, una moneda o un periodo, **When** se
   procesa, **Then** esos datos se ignoran y se cobra el importe del catálogo.
5. **Given** una organización cuyo importe vigente es 0.00, **When** se inicia el pago, **Then** se rechaza
   con 409 y no se llama a Pagos.
6. **Given** Pagos no responde (o agota el tiempo o contesta algo inesperado), **When** se inicia el pago,
   **Then** la respuesta es 503 y no queda ningún cobro registrado.
7. **Given** el cobro anterior del periodo se cerró sin aplicarse (rechazado o cancelado), **When** se
   inicia el pago de nuevo, **Then** se crea un cobro nuevo, con su propio checkout.
8. **Given** una organización en prueba o al corriente (todavía no vence), **When** inicia el pago,
   **Then** se acepta: la persona puede pagar por adelantado (el periodo pagado empieza donde terminaría
   el anterior; historia 3).
9. **Given** un cobro pendiente que Pagos ya reporta como aprobado, **When** el Dueño inicia el pago,
   **Then** la API primero aplica ese pago (la fecha del siguiente pago se mueve) y el cobro nuevo, si
   se crea, es para el periodo siguiente: no se cobra dos veces el mismo periodo.
10. **Given** un cobro pendiente cuyo importe ya no coincide con el vigente (la organización cambió de
    plan), **When** se inicia el pago, **Then** se crea un cobro nuevo con el importe vigente; el
    anterior sigue sin cancelarse y, si se paga, se aplica con las condiciones con que se registró.

---

### User Story 3 - Que la fecha del siguiente pago se mueva, una sola vez, cuando el pago se aprueba (Priority: P1)

Cuando Pagos reporta como aprobado un cobro que esta API inició, y su importe y su moneda coinciden con
lo registrado, la fecha del siguiente pago se extiende por el periodo que cubre ese cobro (un mes
calendario o doce meses). Como Pagos no avisa cuando un pago cambia de estatus, la API lo descubre al
revisar sus cobros pendientes antes de responder una consulta o un inicio de pago. Cada cobro mueve la
fecha exactamente una vez, aunque se consulte muchas veces o a la vez. Un pago que la API no inició no
mueve nada, aunque exista en Pagos con la misma referencia.

**Why this priority**: Es lo que da sentido a pagar: sin él, la persona pagaría y la organización
seguiría figurando como vencida, o la fecha se movería dos veces por un mismo pago.

**Independent Test**: Con Pagos simulado, iniciar un pago, marcarlo como aprobado en la simulación y
consultar: la fecha se mueve; consultar otra vez (y de forma simultánea) y comprobar que no cambia; dejar
otro cobro rechazado y comprobar que se cierra sin mover nada; crear un pago directamente en Pagos y
comprobar que no tiene efecto.

**Acceptance Scenarios**:

1. **Given** una organización en prueba, con la prueba terminando el 2026-12-04T15:30:00Z, y un cobro
   mensual pendiente, **When** Pagos lo reporta aprobado el 2026-12-01T10:00:00Z y el Dueño consulta,
   **Then** la fecha del siguiente pago es 2027-01-04T15:30:00Z, el fin de la prueba sigue siendo
   2026-12-04T15:30:00Z (el pago no la recorta) y el estado sigue siendo `trial` hasta esa fecha.
2. **Given** una organización vencida desde el 2026-12-04T15:30:00Z y un cobro mensual pendiente,
   **When** Pagos lo reporta aprobado el 2026-12-10T09:30:00Z y el Dueño consulta, **Then** la fecha del
   siguiente pago es 2027-01-10T09:30:00Z y el estado es `current`.
3. **Given** un cobro anual pendiente de una organización cuyo periodo pagado empieza el
   2026-12-04T15:30:00Z, **When** se aprueba a tiempo, **Then** la fecha del siguiente pago es
   2027-12-04T15:30:00Z.
4. **Given** una organización al corriente con el siguiente pago el 2027-01-31T10:00:00Z y un cobro mensual
   aprobado antes de esa fecha, **When** se aplica, **Then** la fecha del siguiente pago es
   2027-02-28T10:00:00Z (el último día del mes más corto).
5. **Given** un cobro aprobado, **When** se consulta dos veces seguidas —y también cuando diez consultas
   llegan a la vez—, **Then** la fecha se movió una sola vez.
6. **Given** un pago aprobado antes de la fecha del siguiente pago pero que nadie había consultado hasta
   después de esa fecha, **When** se consulta, **Then** se trata como pago a tiempo (cuenta la fecha de
   aprobación que informa Pagos, no el momento de la consulta).
7. **Given** un cobro que Pagos reporta rechazado o cancelado, **When** el Dueño consulta, **Then** el cobro
   se cierra, ninguna fecha cambia y la consulta ya no informa un cobro en curso por ese cobro; iniciar el
   pago de nuevo crea un cobro nuevo.
8. **Given** un cobro que Pagos reporta aprobado pero con un importe o una moneda distintos de los
   registrados, **When** el Dueño consulta, **Then** no se aplica, el cobro se cierra como inconsistente y
   queda un registro para su revisión.
9. **Given** un pago creado directamente en Pagos (no por esta API) con la misma referencia de la
   organización, aprobado y de un importe correcto, **When** el Dueño consulta, **Then** ninguna fecha se
   mueve.
10. **Given** un cobro que Pagos reporta todavía pendiente, **When** se consulta, **Then** no cambia nada y
    se informa que hay un cobro en curso (`payment_in_progress` es `true`).
11. **Given** dos cobros distintos de la misma organización, ambos aprobados, **When** se consulta, **Then**
    cada uno mueve la fecha una vez y el segundo continúa donde termina el primero.

---

### User Story 4 - Solo el Dueño de la organización puede consultar y pagar (Priority: P1)

Las dos operaciones exigen que la persona esté autenticada, que tenga el permiso de la operación y que
sea el Dueño de la organización indicada. Si no está autenticada se le pide iniciar sesión; si no tiene el
permiso, se le niega; si la organización no es suya, responde como si no existiera; si no se puede
comprobar cualquiera de estas cosas, se le niega también (falla cerrado). La comprobación se hace en cada
petición con los datos vigentes, antes de validar la solicitud o buscar la organización.

**Why this priority**: Los datos de cobro de una organización son de su negocio; revelarlos o dejar que
alguien más inicie un pago sería una fuga de información y un riesgo de cobros indebidos. Es
indispensable desde la primera versión.

**Independent Test**: Probar ambas operaciones con (a) sin token, (b) token inválido o vencido, (c) persona
sin el permiso, (d) persona con el permiso de lectura que intenta iniciar el pago, (e) persona con el
permiso sobre una organización que no es suya, (f) Usuarios caído y (g) Clínicas caída, y comprobar que
solo el Dueño con el permiso, sobre su organización, obtiene respuesta.

**Acceptance Scenarios**:

1. **Given** una petición sin token (o con un esquema distinto de Bearer), **When** se consulta o se inicia
   el pago, **Then** la respuesta es 401 y no se devuelve ni se cambia ningún dato.
2. **Given** un token inválido o vencido, **When** se consulta o se inicia el pago, **Then** la respuesta
   es 401.
3. **Given** una persona autenticada sin `subscription_periods:read` (o sin `subscription_periods:write`
   al iniciar el pago), **When** hace la operación, **Then** la respuesta es 403 y el mensaje nombra el
   permiso que falta.
4. **Given** una persona con `subscription_periods:read` pero sin `subscription_periods:write`, **When**
   intenta iniciar el pago, **Then** la respuesta es 403: cada permiso autoriza solo su operación.
5. **Given** una persona con el permiso que indica la organización de otra persona, o una que no existe,
   **When** hace cualquiera de las dos operaciones, **Then** la respuesta es 404, idéntica en ambos
   casos, sin revelar si la organización existe ni de quién es, y no se crea ningún registro.
6. **Given** Clínicas no responde, agota el tiempo o contesta algo inesperado (incluidos 401, 403 y una
   redirección), **When** se hace cualquiera de las dos operaciones, **Then** la respuesta es 503 y no se
   crea ni cambia nada.
7. **Given** el API de usuarios no responde, agota el tiempo o contesta algo inesperado, **When** se hace
   cualquiera de las dos operaciones, **Then** la respuesta es 503 y no se devuelve ningún dato.
8. **Given** una petición sin permiso (o sin token, o con Usuarios caído) que además trae un identificador
   de organización con formato inválido, **When** se hace la operación, **Then** el rechazo es por acceso
   (401, 403 o 503), no por validación (422); con el permiso concedido, el formato inválido sí responde 422.
9. **Given** una persona a la que acaban de quitar el permiso o el rol en el API de usuarios, **When** hace
   su siguiente petición, **Then** se le niega, sin esperar a que caduque su token.
10. **Given** la documentación publicada de la API, **When** cualquiera la abre, **Then** se muestra sin pedir
    token e indica el permiso que exige cada operación.

---

### User Story 5 - Los cambios de plan no reescriben el pasado (Priority: P2)

Si Clínicas cambia el plan de la organización o su periodo de cobro, las fechas que ya estaban fijadas
no se mueven: ni el inicio, ni el fin de la prueba, ni la fecha del siguiente pago. Lo que cambia es lo
que viene: el siguiente cobro que se inicie usa el plan y el periodo de cobro vigentes en ese momento.
No hay prorrateo.

**Why this priority**: Evita que un cambio de plan —hecho por personal de MailySoft, no por el Dueño—
alargue o acorte una prueba o regale o quite días ya pagados; fija desde ahora qué cambia y qué no.

**Independent Test**: Con una organización ya consultada, cambiar su plan y su periodo de cobro en la
simulación de Clínicas, y los días de prueba del plan en el catálogo; consultar y comprobar que las
fechas son las mismas y que el plan, el periodo de cobro y el importe informados son los nuevos.

**Acceptance Scenarios**:

1. **Given** una organización en prueba cuyo plan cambia a otro con 30 días de prueba, **When** se
   consulta, **Then** el fin de la prueba es el de antes y el plan informado es el nuevo.
2. **Given** una organización con periodo de cobro mensual que pasa a anual, **When** se consulta,
   **Then** la fecha del siguiente pago es la de antes y el importe informado es el anual.
3. **Given** un cobro mensual pendiente y un cambio posterior a periodo anual, **When** ese cobro se
   aprueba, **Then** mueve la fecha un mes (el periodo con que se registró), no doce.
4. **Given** un plan cuyo estatus en el catálogo es Inactiva, Bloqueada o Eliminada, **When** se consulta
   una organización que lo tiene, **Then** se usa su precio y sus días de prueba como siempre: el estatus
   del plan no afecta al cobro.
5. **Given** que Clínicas informa un plan que no existe en el catálogo, **When** se consulta o se inicia
   el pago, **Then** la respuesta es 409 con un error propio, sin crear registro y sin inventar fechas ni
   importes.

---

### User Story 6 - Si falla un API ajeno, se degrada sin inventar nada (Priority: P2)

La API depende de otros tres: Usuarios (permisos), Clínicas (organización, plan y periodo de cobro) y
Pagos (pagos). Cuando uno falla, la respuesta es la que se define aquí, nunca un valor inventado.

| Si no responde (o agota el tiempo, o contesta algo inesperado) | Consultar el estado | Iniciar el pago |
|---|---|---|
| API de usuarios | 503; no se devuelve nada | 503; no se hace nada |
| Clínicas | 503; no se devuelve nada (sin ella no se puede comprobar al Dueño) | 503; no se hace nada |
| Pagos | 200 con lo guardado (fechas, estado e importe calculados) e indicación de que no se pudo verificar un cobro en curso | 503; no se registra ningún cobro |

**Why this priority**: Fija la disponibilidad esperada (Principio IX): el acceso siempre falla cerrado, y
Pagos, que solo aporta la verificación de cobros pendientes, no tumba la consulta de lo que la API ya sabe.

**Independent Test**: Con simulaciones que fallan una por una (sin respuesta, tiempo agotado, error del
servidor, cuerpo inesperado, redirección), comprobar cada celda de la tabla y que ninguna respuesta
contiene direcciones, cuerpos de error ni credenciales del API que falló.

**Acceptance Scenarios**:

1. **Given** Usuarios o Clínicas fallan, **When** se consulta o se inicia el pago, **Then** la respuesta es
   503 y no se crea registro ni cobro.
2. **Given** Clínicas responde 200 pero sin el periodo de cobro (todavía no lo publica), **When** se consulta
   o se inicia el pago, **Then** la respuesta es 503: la API no supone un periodo de cobro por omisión.
3. **Given** Pagos falla y la organización tiene cobros sin resolver, **When** se consulta, **Then** la
   respuesta es 200 con `payment_in_progress` en `null`, y las fechas, el estado y el importe salen de lo
   guardado.
4. **Given** Pagos falla y la organización no tiene cobros sin resolver, **When** se consulta, **Then** la
   respuesta es la normal (no hay nada que verificar) con `payment_in_progress` en `false`.
5. **Given** Pagos responde algo inesperado sobre un cobro (un estatus que no conoce, un 404, un cuerpo
   ilegible), **When** se consulta, **Then** ese cobro sigue sin resolver y se trata como no verificable.
6. **Given** cualquier falla de otro API, **When** se examina la respuesta, **Then** no revela sus
   direcciones, cuerpos de error ni credenciales, y su mensaje está en español con un código en inglés.

---

### User Story 7 - Quien opera el servicio configura la fecha de corte, Pagos y el origen del frontend (Priority: P2)

Quien opera el servicio fija con variables de entorno la **fecha de corte** (para que las organizaciones
que ya existen al desplegar no queden vencidas de golpe), la dirección y el tiempo de espera de Pagos
(como ya existen para Usuarios y Clínicas) y el origen del frontend en la variable de CORS que ya
existe. Una configuración incompleta o no válida impide arrancar y el mensaje dice qué variable es, sin
mostrar su valor.

**Why this priority**: Sin la fecha de corte, el primer despliegue dejaría vencidas a todas las
organizaciones existentes; sin el origen en CORS, el navegador del frontend no podría llamar a la API.

**Independent Test**: Arrancar el servicio con la configuración válida, con la fecha de corte ausente o
inválida, sin la dirección de Pagos, con una dirección de Pagos `http://` no local y con un origen
permitido y otro no; comprobar el arranque, los mensajes y las cabeceras de CORS.

**Acceptance Scenarios**:

1. **Given** la configuración completa y válida, **When** arranca el servicio, **Then** arranca.
2. **Given** la fecha de corte ausente o que no es una fecha y hora ISO 8601 con zona, **When** se intenta
   arrancar, **Then** no arranca y el mensaje nombra la variable sin mostrar su valor.
3. **Given** que falta la dirección de Pagos, **When** se intenta arrancar, **Then** no arranca y el mensaje
   nombra la variable.
4. **Given** una dirección de Pagos con `http://` fuera de una red local o de Docker, **When** arranca,
   **Then** arranca y registra una advertencia que nombra la variable (nunca la dirección), porque a esa
   dirección se reenvía el token de la persona.
5. **Given** el origen del frontend en `CORS_ALLOWED_ORIGINS`, **When** un navegador en ese origen llama a
   las dos operaciones (incluida la petición previa de verificación con la cabecera `Authorization`),
   **Then** se permite; desde un origen que no está en la lista no se habilita ninguno.
6. **Given** el servicio en marcha, **When** cambia el valor de la fecha de corte en el entorno, **Then**
   sigue usando el valor con el que arrancó hasta que se reinicie.
7. **Given** el archivo `.env.example`, **When** se consulta, **Then** documenta las variables nuevas.

---

### User Story 8 - Avanzar sin esperar a los demás APIs (Priority: P2)

Usuarios, Clínicas y Pagos todavía no ofrecen todo lo que esta API necesita. En lugar de esperar, el
trabajo avanza contra simulaciones: el contrato que se consume de cada API queda documentado (lo que
ofrece hoy y lo que se le pide), las pruebas usan simulaciones que lo reproducen, y por cada API se
escribe un documento de pedidos (qué falta, para qué, qué forma se propone y qué bloquea) que quien
coordina el proyecto hará llegar a su equipo.

**Why this priority**: Permite construir y probar toda la feature ya, y deja a cada equipo un pedido
concreto y autocontenido; es el mismo camino que siguieron el dashboard (spec 003) y el conteo de
clínicas (contrato propuesto de la spec 001).

**Independent Test**: Revisar que existe, por cada API, el contrato consumido y el documento de pedidos
con las cuatro partes en cada pedido; ejecutar la suite sin ningún API real y comprobar que pasa; comprobar
que, contra los APIs reales tal como están hoy, las operaciones fallan cerradas (403 o 503) y no devuelven
datos inventados.

**Acceptance Scenarios**:

1. **Given** el contrato consumido de cada API, **When** se revisa, **Then** distingue lo que el API ofrece
   hoy de lo que se le pide, con operaciones, forma de la respuesta y errores esperados.
2. **Given** los documentos de pedidos de Usuarios, Clínicas y Pagos, **When** se revisan, **Then** cada
   pedido dice qué falta, para qué lo necesita esta API, la forma propuesta y qué bloquea, y el texto se
   puede enviar tal cual al equipo dueño del API.
3. **Given** la suite automatizada, **When** se ejecuta sin acceso a ningún API real, **Then** pasa: las
   simulaciones reproducen los contratos documentados, incluidas las piezas pedidas que aún no existen, y
   sus fallas.
4. **Given** que un API entrega después lo que se le pidió, **When** se conecta, **Then** cambia solo la
   integración con ese API: el contrato publicado de esta API no cambia.
5. **Given** los APIs reales sin lo pedido, **When** se consulta o se inicia el pago, **Then** la respuesta
   es 403 (permiso sin dar de alta) o 503 (dato que falta o API que no responde), nunca un dato inventado.

---

### Ejemplos de referencia del cálculo de fechas

Todas las fechas en UTC. Estas filas son la referencia que las pruebas con reloj fijo reproducen
exactamente (criterio SC-004). Salvo que se diga otra cosa: prueba de 14 días, periodo de cobro mensual y
precio mensual de 499.00.

| # | Situación | Resultado |
|---|---|---|
| 1 | Alta 2026-11-20T15:30:00Z, fecha de corte anterior | Inicio 2026-11-20T15:30:00Z; fin de la prueba y siguiente pago 2026-12-04T15:30:00Z |
| 2 | Consulta 2026-11-25T15:30:00Z | `trial`, 9 días |
| 3 | Consulta 2026-11-25T16:00:00Z (faltan 8 d 23 h 30 min) | `trial`, 9 días (se redondea hacia arriba) |
| 4 | Consulta 2026-12-03T15:30:01Z | `trial`, 1 día |
| 5 | Consulta 2026-12-04T15:30:00Z (instante exacto del fin de la prueba) | `overdue`, 0 días |
| 6 | Consulta 2026-12-10T09:00:00Z (vencida hace 5 d 17 h 30 min) | `overdue`, −5 días |
| 7 | Pago mensual aprobado el 2026-12-01T10:00:00Z (en prueba) | Periodo cubierto 2026-12-04T15:30:00Z → 2027-01-04T15:30:00Z; consulta 2026-12-01T10:05:00Z: `trial`, siguiente pago 2027-01-04T15:30:00Z, 35 días |
| 8 | Pago mensual aprobado el 2026-12-10T09:30:00Z (vencida) | Periodo cubierto 2026-12-10T09:30:00Z → 2027-01-10T09:30:00Z; consulta 09:45: `current`, 31 días |
| 9 | Pago anual que empieza el 2026-12-04T15:30:00Z | Termina el 2027-12-04T15:30:00Z |
| 10 | Mensual que empieza 2027-01-31T10:00:00Z, 2028-01-31T10:00:00Z y 2027-02-28T10:00:00Z | Termina 2027-02-28T10:00:00Z, 2028-02-29T10:00:00Z y 2027-03-28T10:00:00Z (el día del mes que se acortó no se recupera) |
| 11 | Anual que empieza 2028-02-29T10:00:00Z | Termina 2029-02-28T10:00:00Z |
| 12 | Corte 2026-11-18T00:00:00Z; alta 2026-06-01T12:00:00Z | Inicio 2026-11-18T00:00:00Z; fin de la prueba 2026-12-02T00:00:00Z; consulta 2026-11-25T00:00:00Z: `trial`, 7 días |
| 13 | Sin prueba; alta 2026-11-20T15:30:00Z; consulta 2026-11-21T09:00:00Z | `trial_ends_at` `null`; siguiente pago 2026-11-20T15:30:00Z; `overdue`, 0 días |
| 14 | Sin prueba; corte 2026-11-18T00:00:00Z (el despliegue); consulta 2026-11-18T08:00:00Z de una organización anterior al corte | Siguiente pago 2026-11-18T00:00:00Z; `overdue`, 0 días (vence el mismo día del despliegue; ver decisión D2) |
| 15 | Sin prueba; corte futuro 2026-12-18T00:00:00Z; consulta 2026-11-25T00:00:00Z | `current`, 23 días |
| 16 | Redondeo de los días | Faltan 48 h → 2; 49 h → 3; 0.5 h → 1; vencida 0.5 h → 0; vencida 24 h → −1; vencida 137.5 h → −5 |

### Edge Cases

- **Límites del tiempo**: en el instante exacto del fin de la prueba o de la fecha del siguiente pago, el
  periodo ya terminó (`overdue`, 0 días). Mientras el estado es `trial` o `current` los días son 1 o más;
  con `overdue` son 0 o menos.
- **Primer contacto tardío**: una organización dada de alta hace semanas y consultada hoy por primera vez
  tiene sus fechas desde su alta (o desde la fecha de corte), no desde hoy: puede estar vencida en su
  primera consulta.
- **Fecha de corte futura**: si es posterior al momento de la consulta, el primer periodo empieza en el
  futuro; la organización no está vencida y, sin prueba, queda `current` hasta esa fecha.
- **Organización anterior al corte con un plan sin prueba**: con la fecha de corte igual a la del
  despliegue, vence desde ese mismo instante (ejemplo 14). Se evita con una fecha de corte posterior
  (decisión D2).
- **Plan cambiado antes de la primera consulta**: la prueba usa los días de prueba del plan vigente cuando
  se crea el registro, no los del plan con que se dio de alta la organización.
- **Una sola de las dos tarifas en 0.00**: el estado depende del importe del periodo de cobro vigente; la
  misma organización puede ser `no_charge` con un periodo de cobro y no serlo con el otro. Al volver de
  `no_charge` a un importe mayor, la fecha del siguiente pago es la ya fijada, que puede estar vencida.
- **Pago aprobado y nadie consulta**: la fecha no se mueve hasta la siguiente consulta o inicio de pago;
  entonces la fecha de aprobación que informa Pagos decide si el pago llegó a tiempo.
- **La persona paga y no regresa a la aplicación**: Pagos no permite hoy indicar la dirección de regreso
  tras el checkout; la persona vuelve por su cuenta y la siguiente consulta aplica el pago.
- **Cobros que nunca se pagan**: siguen sin resolverse y cada consulta los revisa; esta versión no los
  descarta por antigüedad ni los cancela en Pagos (Pagos no ofrece cancelar).
- **Dos cobros pendientes con condiciones distintas** (cambio de plan o de periodo de cobro entre ambos):
  los dos pueden pagarse; cada uno se aplica una vez con las condiciones con que se registró.
- **Pagos crea el pago pero la respuesta se pierde**: el siguiente intento reutiliza la misma clave de
  idempotencia, Pagos devuelve ese mismo pago y se registra: no queda un cobro duplicado ni huérfano.
- **Pagos no conoce un cobro registrado (404), responde un estatus que no está en su contrato o un cuerpo
  ilegible**: ese cobro no se puede verificar; sigue sin resolverse y no se descarta.
- **Importe o moneda distintos de lo registrado en un pago aprobado**: no se aplica; el cobro se cierra
  como inconsistente y queda un registro para su revisión, sin datos personales.
- **Un pago creado directamente en Pagos** (por otra vía) con la referencia de la organización: no es un
  cobro de esta API, así que nunca mueve fechas, aunque esté aprobado y su importe sea correcto.
- **Reembolsos y contracargos**: un cobro ya aplicado no se vuelve a consultar; un reembolso posterior no
  mueve fechas. Un cobro aún no aplicado cuyo pago ya aparece reembolsado se cierra sin aplicarse
  (decisión D3).
- **Identificador de organización con formato inválido**: 422, pero solo si el acceso ya se concedió.
- **Organización de otra persona o inexistente**: 404 idéntico, sin pistas de su existencia.
- **Organización dada de baja en Clínicas después**: si Clínicas todavía la devuelve se atiende con
  normalidad; si responde 404, esta API responde 404. Los registros propios no se borran.
- **Plan inexistente en el catálogo**: 409 con un error propio; no se crea registro ni se inventa nada.
- **Consultas y pagos simultáneos**: el registro se crea una vez, cada cobro se aplica una vez y dos
  inicios de pago simultáneos del mismo periodo crean un solo cobro.

## Requirements *(mandatory)*

### Functional Requirements

**Control de acceso**

- **FR-001**: Las dos operaciones MUST exigir un token de acceso válido y el permiso que les corresponde:
  consultar el estado, `subscription_periods:read`; iniciar el pago, `subscription_periods:write`
  (nombres propuestos; ver «Contratos consumidos y pedidos a otros APIs»). Cada permiso autoriza solo su
  operación. El servicio MUST NOT verificar el token por sí mismo: MUST reenviarlo, sin modificarlo, al
  API de usuarios y aceptar su respuesta como única autoridad (Principio VIII). La decisión MUST tomarse
  en cada petición, sin conservar decisiones anteriores, y MUST ocurrir antes de validar la solicitud o
  buscar la organización.
- **FR-002**: Sin token (o con un esquema distinto de Bearer) o con un token rechazado o vencido, MUST
  responderse 401. Con un token válido pero sin el permiso, 403, con un mensaje que nombra el permiso. Si
  el API de usuarios no responde, agota el tiempo o contesta algo inesperado, 503 (falla cerrado). En
  ninguno de estos casos MUST crearse ni cambiarse dato alguno, ni devolverse información de la
  organización.
- **FR-003**: La persona MUST ser el Dueño de la organización indicada. La API lo comprueba leyendo esa
  organización en Clínicas con el token de la persona (a un rol de clínica, como el Dueño, Clínicas solo
  le deja leer la organización de la que es Dueño). Si Clínicas la devuelve, la comprobación pasa. Si
  responde que no existe (404), la API MUST responder
  404 sin revelar si la organización existe ni de quién es. Ante cualquier otra cosa —sin respuesta,
  tiempo agotado, 401, 403, error del servidor, redirección o una respuesta que no trae lo que el
  contrato exige, incluido el periodo de cobro— MUST responder 503 y fallar cerrado. Mientras esta
  comprobación no pase, MUST NOT crearse ni cambiarse nada.
- **FR-004**: Cuando una petición falla en varias comprobaciones a la vez, MUST responder la primera de
  esta lista: (1) identidad (401); (2) permiso (403, o 503 si el API de usuarios no responde);
  (3) formato del identificador de la organización (422); (4) comprobación del Dueño en Clínicas (404 o
  503); (5) reglas de negocio (409); (6) Pagos (503 al iniciar el pago).
- **FR-005**: El servicio MUST NOT comunicarse con Auth0 ni tener credenciales de máquina: a Clínicas y a
  Pagos solo reenvía el token de la persona que llama. Todo lo que esta API pide a otro API MUST poder
  obtenerse con el token de un Dueño. Los tokens MUST NOT guardarse, registrarse ni aparecer en
  respuestas ni en mensajes de error (Principio VIII).
- **FR-006**: Cada operación MUST declarar en el contrato publicado el permiso que exige y el esquema de
  seguridad Bearer, y MUST añadirse a la matriz «operación → permiso» sin alterar ninguna fila
  existente. Ampliar la matriz no exige enmendar la constitución.

**Registro de la organización y sus fechas**

- **FR-007**: La API MUST crear el registro de una organización la primera vez que se consulta su estado
  (o, si el primer contacto fuera iniciar el pago, en esa operación), una sola vez por organización aunque
  lleguen peticiones simultáneas: todas reciben las mismas fechas.
- **FR-008**: El primer periodo MUST empezar en la fecha de alta de la organización que informa Clínicas,
  pero nunca antes de la fecha de corte configurable (FR-039): el inicio es la más reciente de las dos.
- **FR-009**: La prueba MUST durar los días de prueba (`trial_days`) del plan de la organización **en el
  momento de crear el registro**, contados en días completos de 24 horas desde el inicio: fin de la
  prueba = inicio + `trial_days`. Una vez fijado, el fin de la prueba MUST NOT cambiar, ni por un cambio de
  plan de la organización ni por un cambio de los días de prueba del plan en el catálogo. Con
  `trial_days` = 0 no hay prueba: `trial_ends_at` es `null` en la respuesta y el primer pago vence en la
  fecha de inicio.
- **FR-010**: La fecha del siguiente pago MUST ser, mientras no haya pagos aplicados, el fin de la prueba
  (o la fecha de inicio si no hay prueba); cada pago aplicado la mueve (FR-029).
- **FR-011**: Todas las fechas MUST llevar hora, guardarse y devolverse en UTC (ISO 8601 con zona
  explícita, por ejemplo `2026-12-04T15:30:00Z`); mostrarlas en la zona horaria de la clínica le toca a la
  aplicación. Todo cálculo que dependa del tiempo MUST usar un reloj inyectable que las pruebas pueden
  fijar y mover; ninguna regla lee la hora del sistema por su cuenta.

**Estado y días que faltan**

- **FR-012**: El estado, la fecha del siguiente pago que se informa y los días que faltan MUST calcularse
  en cada consulta con las fechas guardadas, el reloj y el importe vigente. MUST NOT guardarse, y el
  servicio MUST NOT depender de tareas programadas ni de procesos en segundo plano para cambiarlos.
- **FR-013**: El estado MUST ser uno de cuatro (valores propuestos, en inglés), evaluados en este orden:
  `no_charge` (el importe vigente es 0.00); `trial` (hay prueba y el reloj está antes de su fin);
  `overdue` (el reloj es igual o posterior a la fecha del siguiente pago); `current` (cualquier otro
  caso: la prueba ya terminó o no existió y la fecha del siguiente pago todavía no llega). No hay periodo de gracia
  (decisión D1). Un pago hecho durante la prueba no cambia el estado: sigue `trial` hasta que la prueba
  termina.
- **FR-014**: Los días que faltan (`days_remaining`) MUST ser un entero con signo: los días entre el reloj
  y la fecha del siguiente pago, redondeados hacia arriba. Positivo, faltan esos días; 0 o negativo, ya
  venció (−5 son cinco días completos de atraso; 0, menos de 24 horas de atraso o justo el instante). En
  `no_charge` MUST ser `null`.
- **FR-015**: La respuesta de la consulta MUST traer, con los nombres propuestos en «Key Entities»:
  `state`, `trial_ends_at`, `payment_due_at`, `days_remaining`, el plan, el periodo de cobro, el importe
  con su moneda y si hay un cobro en curso (`payment_in_progress`: `true` si algún cobro está verificado
  como pendiente; si no, `null` si algún cobro sin resolver no se pudo verificar; si no, `false`). En
  `no_charge`, `payment_due_at` y `days_remaining` MUST ser `null` porque no hay fecha de pago.

**Importe**

- **FR-016**: El importe MUST ser el del catálogo de esta API para el plan vigente de la organización y su
  periodo de cobro vigente (el precio mensual si es mensual, el anual si es anual), en pesos mexicanos
  (`MXN`), con decimales exactos (nunca punto flotante) y representado como los precios del catálogo
  (texto con dos decimales, por ejemplo «499.00»). MUST NOT venir de la petición del cliente: cualquier
  importe, moneda o periodo que esta traiga se ignora.
- **FR-017**: Hacia Pagos, el importe MUST enviarse en la unidad mínima de la moneda como entero (centavos:
  499.00 se envía como 49900).
- **FR-018**: Si el importe vigente es 0.00, no hay cobro ni fecha de pago: el estado es `no_charge` y
  iniciar el pago MUST rechazarse con 409, sin llamar a Pagos.
- **FR-019**: Por la decisión D4, el importe es el precio del catálogo tal cual: no se suma IVA ni se
  informa desglose. Si después se fija una tasa, se añade sin cambiar los campos existentes de la
  respuesta.

**Iniciar el pago**

- **FR-020**: Iniciar el pago MUST: asegurar el registro de la organización; verificar los cobros sin
  resolver (FR-026); calcular el importe (FR-016); crear el pago en Pagos con el token de la persona, con
  `resource_type` «system-api:subscription» y `resource_id` igual al identificador de la organización;
  registrar el cobro (FR-021); y devolver la dirección del checkout, el importe, la moneda y el periodo de
  cobro.
- **FR-021**: Cada cobro MUST registrarse con el identificador del pago en Pagos, el importe, la moneda, la
  duración del periodo de cobro (mensual o anual), la fecha de pago que salda (la fecha del siguiente pago
  vigente al iniciarlo) y, cuando se aplica, el periodo cubierto (inicio y fin). MUST NOT guardarse el
  estatus del pago ni su dirección de checkout: se piden a Pagos en cada uso.
- **FR-022**: Iniciar el pago dos veces para el mismo periodo (la misma fecha de pago que salda, la misma
  duración y el mismo importe) MUST NOT crear dos cobros: la API usa una clave de idempotencia
  determinista, derivada de la organización y del periodo, y mientras el cobro siga pendiente devuelve el
  mismo checkout.
- **FR-023**: Si el cobro anterior del periodo se cerró sin aplicarse (rechazado, cancelado o
  inconsistente), iniciar el pago MUST crear un cobro nuevo, con su propio checkout.
- **FR-024**: Si el importe vigente difiere del de un cobro pendiente del mismo periodo (por un cambio de
  plan), iniciar el pago MUST crear un cobro nuevo con el importe vigente. El cobro pendiente anterior no
  se cancela (Pagos no ofrece cancelar un pago) y, si se paga, se aplica con las condiciones con que se
  registró.
- **FR-025**: Iniciar el pago MUST responder 201 cuando crea un cobro nuevo y 200 cuando devuelve el cobro
  pendiente que ya existía; 409 si no hay nada que cobrar (FR-018); 404 o 503 según FR-003; y 503 si
  Pagos no responde, agota el tiempo o contesta algo inesperado, sin registrar ningún cobro.

**Cobros y fecha del siguiente pago**

- **FR-026**: Antes de responder una consulta o un inicio de pago, la API MUST revisar, uno por uno, los
  cobros que inició y siguen sin resolverse, preguntando su estado a Pagos con el token de la persona
  (Pagos no avisa de los cambios), y aplicarlos o cerrarlos según FR-028.
- **FR-027**: Un pago MUST mover la fecha del siguiente pago solo si **esta API lo inició** (registrado
  como cobro, con su identificador en Pagos), Pagos lo reporta como aprobado y su importe y su moneda
  coinciden con lo registrado. Un pago creado directamente en Pagos por otra vía MUST NOT mover ninguna
  fecha, aunque tenga la misma referencia, esté aprobado y su importe sea correcto.
- **FR-028**: El efecto de lo que Pagos reporta sobre un cobro sin resolver MUST ser:

  | Estatus del pago en Pagos | Efecto sobre el cobro |
  |---|---|
  | `pending` | Sigue sin resolver; cuenta como cobro en curso. |
  | `approved` | Se aplica si el importe y la moneda coinciden con lo registrado (FR-027). Si no coinciden, se cierra como inconsistente sin mover fechas y queda un registro para su revisión. |
  | `rejected`, `cancelled` | Se cierra sin mover fechas. |
  | `partially_refunded`, `refunded` | Se cierra sin mover fechas: Pagos ya no lo reporta como aprobado (decisión D3). Un cobro ya aplicado no se vuelve a consultar, así que un reembolso posterior no revoca su periodo. |
  | Un estatus desconocido, un 404, un cuerpo inesperado o cualquier otra falla | No se puede verificar: el cobro sigue sin resolver (FR-015, FR-036). |

- **FR-029**: El periodo cubierto por un cobro aplicado MUST ser de un mes calendario si el periodo de cobro
  es mensual y de doce meses si es anual. Empieza en la fecha del siguiente pago vigente cuando el pago
  llegó a tiempo (su fecha de aprobación es anterior a esa fecha) y en la fecha de aprobación si la
  organización ya estaba vencida. Un pago durante la prueba no la recorta: mientras no haya pagos, la fecha
  del siguiente pago es el fin de la prueba, así que el periodo pagado empieza cuando la prueba termina. La
  nueva fecha del siguiente pago MUST ser el fin del periodo cubierto.
- **FR-030**: Sumar un mes (o doce) MUST conservar la hora UTC y el día del mes; si ese día no existe en el
  mes resultante, se usa el último día de ese mes (31 de enero → 28 de febrero, o 29 en año bisiesto).
  Cada periodo parte del fin del anterior, de modo que un día que se acortó no se recupera.
- **FR-031**: La fecha de aprobación MUST ser la que informa Pagos: hoy, la fecha de la última actualización
  del pago aprobado, porque Pagos no publica una fecha de aprobación propia (se pide; ver «Contratos
  consumidos y pedidos a otros APIs»). Si esa fecha fuera posterior al reloj de esta API, MUST usarse el
  reloj.
- **FR-032**: Cada cobro MUST aplicarse exactamente una vez: ni las consultas repetidas, ni las simultáneas,
  ni los reintentos tras una falla (por ejemplo, si no se pudo guardar el resultado) pueden mover la fecha
  dos veces por el mismo cobro, ni dejar de moverla mientras el pago siga aprobado y el cobro sin aplicar.

**Cambios de plan**

- **FR-033**: Un cambio de plan o de periodo de cobro en Clínicas MUST NOT mover ninguna fecha ya fijada
  (inicio, fin de la prueba, fecha del siguiente pago). El siguiente cobro que se inicie MUST usar el plan y
  el periodo de cobro vigentes en ese momento; un cobro ya iniciado conserva el importe y el periodo con
  que se registró. No hay prorrateo.
- **FR-034**: El estatus del plan en el catálogo (Activa, Inactiva, Bloqueada o Eliminada) MUST NOT afectar
  al cobro: la organización paga el precio del plan que Clínicas informa. Si ese plan no existe en el
  catálogo, MUST responderse 409 con un error propio, sin crear registro ni inventar fechas o importes.

**Degradación**

- **FR-035**: Si el API de usuarios o Clínicas fallan, consultar e iniciar el pago MUST responder 503 y no
  crear ni cambiar nada (FR-002, FR-003).
- **FR-036**: Si Pagos falla al consultar, la API MUST responder 200 con lo guardado (fechas, estado e
  importe calculados) e indicar que no se pudo verificar un cobro en curso (`payment_in_progress` en
  `null`), solo cuando haya cobros sin resolver; sin ellos no hay nada que verificar y la respuesta es la
  normal. Si Pagos falla al iniciar el pago, MUST responder 503 y no registrar ningún cobro (FR-025).
- **FR-037**: La API MUST NOT inventar fechas ni importes: ningún valor por omisión sustituye a un dato que
  un API no entregó (por ejemplo, no se supone un periodo de cobro).
- **FR-038**: Las fallas de otro API MUST traducirse a errores propios del servicio (código en inglés,
  mensaje en español); MUST NOT revelarse sus direcciones, cuerpos de error ni credenciales. Toda llamada a
  otro API MUST ser asíncrona, tener un tiempo máximo de espera total y no reintentarse automáticamente
  (Principio IX).

**Configuración**

- **FR-039**: La fecha de corte MUST ser una variable de entorno (propuesta: `BILLING_CUTOFF_AT`), con fecha
  y hora y zona explícita (ISO 8601), validada al arrancar: si falta o no es válida, el servicio no arranca
  y el mensaje nombra la variable sin mostrar su valor. Un cambio MUST requerir reiniciar el servicio. Su
  valor en el primer despliegue es el instante del despliegue (decisión D2).
- **FR-040**: La dirección de Pagos y su tiempo máximo de espera MUST venir de variables de entorno
  validadas al arrancar, como las de Usuarios y Clínicas (propuestas: `PAYMENTS_API_BASE_URL`,
  obligatoria, y `PAYMENTS_API_TIMEOUT_SECONDS`, opcional, 5 segundos por omisión). Si la dirección usa
  `http://` fuera de una red local o de Docker, el arranque registra una advertencia que nombra la variable
  (nunca la dirección) y no se impide arrancar.
- **FR-041**: Con el origen del frontend en la variable de CORS que ya existe (`CORS_ALLOWED_ORIGINS`), un
  navegador en ese origen MUST poder llamar a las dos operaciones, incluida la petición previa de
  verificación con la cabecera `Authorization`; desde un origen que no está en la lista no se habilita
  ninguno. Esta feature no añade variables de CORS.

**Datos propios**

- **FR-042**: La API MUST guardar solo datos propios: por organización, el inicio de su primer periodo, el
  fin de su prueba, hasta cuándo está pagada y los cobros que inició y aplicó. MUST NOT guardar la
  organización, su plan vigente, su periodo de cobro, ni datos de los pagos (su estatus, su dirección de
  checkout): se piden al API que los tiene en cada uso (Principio IX). El identificador de la organización
  se guarda solo como referencia.
- **FR-043**: Esta feature añade estructuras de datos nuevas (el registro de la organización y sus cobros) y
  no cambia las existentes. El esquema MUST declararse en `data-model.md` y reflejarse en
  `project-definition/DATA_SCHEMA.md` con la marca `-- [spec 010-subscription-periods]`, con migraciones
  reversibles y los importes en tipos decimales exactos (Principio VI).

**Contrato y calidad de la API**

- **FR-044**: Las dos operaciones MUST documentarse en el contrato publicado, en español: resumen,
  descripción, etiqueta propia, permiso que exige, parámetros y las respuestas 200 o 201, 401, 403, 404,
  409, 422 y 503 con ejemplos.
- **FR-045**: Los errores MUST usar el formato uniforme del servicio (`code`, `message` y, en
  validaciones, `errors`), reutilizar los códigos que ya existen para 401, 403, 503 y 422, y añadir códigos
  propios, documentados en el catálogo de errores del plan, solo para las situaciones nuevas (organización
  no encontrada, Clínicas o Pagos no disponibles, nada que cobrar, plan inexistente en el catálogo).
- **FR-046**: Las respuestas 200 y 201 MUST declarar que no deben guardarse en caché
  (`Cache-Control: no-store`): contienen datos de cobro de una organización.

**Integraciones, simulaciones y pedidos**

- **FR-047**: El contrato que se consume de cada API (Usuarios, Clínicas y Pagos) MUST documentarse en los
  artefactos de esta feature: operaciones, forma de la respuesta y errores esperados, separando lo que el
  API ofrece hoy de lo que se le pide (Principio IX).
- **FR-048**: Cada API ajeno MUST consumirse detrás de una interfaz propia y sustituible. Las pruebas
  automatizadas y la pila aislada de punta a punta MUST usar simulaciones que reproducen esos contratos
  —incluidas las piezas pedidas que aún no existen— y sus fallas (sin permiso, token rechazado, tiempo
  agotado, servicio caído, respuesta inesperada, redirección). Ninguna prueba llama a un API real. El
  servicio MUST NOT incluir una fuente ficticia en su operación real: los datos de otros APIs vienen
  siempre del API que los tiene.
- **FR-049**: Por cada API (Usuarios, Clínicas y Pagos) MUST escribirse en `contracts/` un documento de
  pedidos que diga, por cada pedido: qué falta, para qué lo necesita esta API, la forma propuesta y qué
  bloquea; redactado para enviarse tal cual al equipo dueño del API. Los pedidos no son requisito para
  desarrollar y probar esta feature; solo bloquean la verificación contra los APIs reales y el
  despliegue.
- **FR-050**: Cuando un API entregue lo que se le pidió, MUST cambiar solo la integración con ese API, sin
  cambiar el contrato publicado de esta API. Mientras no lo entregue, las operaciones MUST fallar cerradas
  (403 o 503) en lugar de devolver datos inventados.

**Verificación**

- **FR-051**: Las pruebas automatizadas MUST cubrir, con reloj fijo y simulaciones: los ejemplos de
  referencia; el inicio, la prueba, la fecha de corte y `trial_days` = 0; los cuatro estados y los límites
  del tiempo; el redondeo de los días; la creación única del registro con peticiones simultáneas; el
  importe del catálogo (con decimales) y su conversión a la unidad mínima; el inicio del pago y su
  idempotencia (incluido el reintento tras un cobro cerrado y el cambio de importe); la aplicación de un
  pago exactamente una vez (también con consultas simultáneas), a tiempo, en prueba y vencido, mensual y
  anual y con fin de mes; los pagos rechazados, cancelados, inconsistentes, ajenos y reembolsados; los
  cambios de plan; el acceso (401, 403, 404, 422 y su orden) y la degradación de cada API (503 y consulta
  degradada) sin revelar datos de los otros APIs.
- **FR-052**: MUST añadirse una colección de Postman nueva e independiente en `tests/postman/`, de punta a
  punta y automática (contra el servicio real con simulaciones de Usuarios, Clínicas y Pagos), con los
  recorridos y los errores clave: consulta de una organización nueva, inicio del pago, pago aprobado y
  fecha movida, y los errores 401, 403, 404, 409 y 503. MUST NOT repetir lo que cubren las pruebas
  automatizadas ni modificar las colecciones existentes, y no contiene secretos.
- **FR-053**: La matriz «operación → permiso» y su prueba de cobertura MUST actualizarse con las dos
  operaciones, y las pruebas existentes MUST seguir pasando sin cambiar ninguna de sus comprobaciones de
  comportamiento. Solo MAY ajustarse, para reconocer lo nuevo y sin debilitarse: (a) las comprobaciones
  que verifican el conjunto completo de operaciones de la API, el conjunto completo de códigos de error o
  la versión publicada; (b) el montaje de las pruebas que arrancan el servicio, para que definan las
  variables obligatorias nuevas (FR-039, FR-040); y (c) la comprobación que fija el contenido exacto del
  script `e2e:all` de Newman, para que incluya la colección nueva. El plan enumera cada ajuste.
- **FR-054**: El README y `.env.example` MUST documentar las variables nuevas y las operaciones nuevas.

### Contratos consumidos y pedidos a otros APIs

Resumen de lo que esta API consume de cada API y de lo que le pide (Principio IX). El detalle —forma
exacta de las respuestas, errores esperados y el texto de cada pedido— se escribe en `contracts/` (FR-047,
FR-049). Lo que dice «existe» se verificó leyendo esos servicios en solo lectura; no se modificó ninguno.

**Usuarios — identidad y permisos (Principio VIII)**

| Qué | Estado | Para qué | Qué bloquea |
|---|---|---|---|
| `GET /api/v1/authorization/check?permission=…` con el token reenviado | Existe | Decidir el 401 y el 403 de cada operación | — |
| Permisos `subscription_periods:read` y `subscription_periods:write` (con su módulo), asignados al Dueño | Falta (propuesta) | Que el Dueño pueda consultar y pagar | Todo, en el entorno real: sin ellos, toda petición recibe 403 |
| Permisos `payments:read` y `payments:write` asignados al Dueño | Falta (no existen en su catálogo) | Su token se reenvía a Pagos | Iniciar el pago y verificar cobros |
| `tenant_id` en `GET /api/v1/authorization/me` | Falta (no lo publica) | Pagos lo exige para aislar los pagos por organización | Iniciar el pago y verificar cobros |

**Clínicas — organización, plan vigente y periodo de cobro**

| Qué | Estado | Para qué | Qué bloquea |
|---|---|---|---|
| `GET /api/v1/organizations/{id}` con el token del Dueño (solo lee la suya; otra responde 404): `subscription_id` (plan vigente) y `created_at` (alta) | Existe | Comprobar al Dueño, conocer el plan vigente y la fecha de alta | — |
| `billing_period` (`monthly` o `annual`) en esa lectura | Falta (lo guarda, pero ninguna lectura lo expone) | Calcular el importe y el periodo que cubre un cobro | Consultar e iniciar el pago en el entorno real (sin él la respuesta es inesperada: 503) |
| `GET /api/v1/clinics` («mis clínicas»), con `organization_id` | Existe; lo usa la aplicación, no esta API | Que la aplicación obtenga el identificador de la organización de la persona | — |

**Pagos — pagos genéricos (Mercado Pago)**

| Qué | Estado | Para qué | Qué bloquea |
|---|---|---|---|
| `POST /api/v1/payments` (`Idempotency-Key`; devuelve `checkout_url`) | Existe | Crear el cobro | Nada por sí mismo (ver los permisos y `tenant_id` de Usuarios) |
| `GET /api/v1/payments/{id}` (estatus, importe en unidad mínima, moneda, referencia, `updated_at`) | Existe | Verificar los cobros sin resolver | Nada por sí mismo |
| Dirección a la que regresa la persona tras el checkout | Falta (no se puede indicar) | Que la persona vuelva a la aplicación al pagar | No bloquea: sin ella la persona vuelve por su cuenta y la siguiente consulta aplica el pago |
| Aviso cuando un pago cambia de estatus | No se pide | — | Esta API consulta, no espera avisos |
| Fecha de aprobación propia del pago | Sugerido (hoy solo hay `updated_at`) | Decidir con exactitud si el pago llegó a tiempo (FR-029, FR-031) | No bloquea: se usa `updated_at` |

### Key Entities *(include if feature involves data)*

- **Periodo de suscripción** *(dato propio; uno por organización; se crea en el primer contacto)*: el
  control de una organización. Guarda solo el identificador de la organización (como referencia), el inicio
  de su primer periodo, el fin de su prueba (vacío si su plan no tenía prueba) y hasta cuándo está pagada
  (vacío mientras no se aplique ningún pago). **Se derivan, no se guardan**: la fecha del siguiente pago, el
  estado y los días que faltan.
- **Cobro** *(dato propio; uno por pago que esta API inicia)*: identificador del pago en Pagos,
  organización, importe (decimal exacto, en pesos), moneda, duración del periodo de cobro (mensual o
  anual), fecha de pago que salda, periodo cubierto (se fija al aplicarlo), resultado propio (pendiente,
  aplicado o cerrado) y, si se cerró, el motivo (rechazado, cancelado, inconsistente o reembolsado antes de
  aplicarse); cuándo se inició y cuándo se resolvió. No guarda el estatus del pago ni su checkout.
- **Estado de la suscripción de la organización** *(respuesta de la consulta; no se guarda)*: campos
  propuestos —nombres en inglés, Principio VII—: `state` (`trial`, `current`, `overdue` o `no_charge`),
  `trial_ends_at`, `payment_due_at`, `days_remaining`, `subscription` (`id` y `name` del plan),
  `billing_period` (`monthly` o `annual`), `amount` (texto con dos decimales), `currency` (`MXN`) y
  `payment_in_progress` (`true`, `false` o `null` si no se pudo verificar).
- **Inicio de pago** *(respuesta de iniciar el pago; no se guarda)*: campos propuestos `checkout_url`,
  `amount`, `currency` y `billing_period`.
- **Plan del catálogo** *(existente, de esta API; solo se lee)*: nombre, estatus, `trial_days`,
  `monthly_price` y `annual_price`.
- **Fecha de corte** *(configuración)*: el instante antes del cual ningún primer periodo puede empezar.
- **Organización, plan vigente, periodo de cobro, fecha de alta** *(externos, de Clínicas)*, **Pago**
  *(externo, de Pagos)* y **Persona y permisos** *(externos, de Usuarios)*: se piden en cada uso y no se
  guardan.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El estado de una organización aparece en pantalla en menos de 3 segundos en el 95 % de las
  consultas en condiciones normales, también cuando tiene hasta cinco cobros sin resolver.
- **SC-002**: El 100 % de las peticiones sin token, con token inválido, sin el permiso, sobre una
  organización que no es de la persona o con Usuarios o Clínicas inaccesibles se rechaza sin devolver ni
  cambiar ningún dato (401, 403, 404 o 503), y una verificación automática que recorre todas las rutas
  confirma que las dos operaciones nuevas declaran su permiso.
- **SC-003**: Un bloqueo, un cambio de roles o un permiso quitado en el API de usuarios surte efecto en la
  siguiente petición de esa persona (0 peticiones posteriores aceptadas por permisos ya revocados).
- **SC-004**: El 100 % de las filas de los ejemplos de referencia se reproduce exactamente con reloj fijo
  (fechas, estado y días), incluidos los límites del tiempo, el redondeo, los meses cortos y el año
  bisiesto.
- **SC-005**: En una prueba con 20 consultas simultáneas, la primera crea un solo registro y, después de un
  pago aprobado, la fecha del siguiente pago se mueve exactamente una vez, en el 100 % de las ejecuciones.
- **SC-006**: 0 pagos que esta API no inició, y 0 pagos cuyo importe o moneda no coinciden con lo
  registrado, mueven alguna fecha.
- **SC-007**: El importe cobrado coincide con el precio del catálogo del plan y el periodo de cobro vigentes
  hasta el centavo en el 100 % de los casos probados (incluidos precios con decimales), y el cliente no
  puede alterarlo (0 casos).
- **SC-008**: Iniciar el pago dos veces para el mismo periodo deja un solo cobro en el 100 % de los casos
  probados.
- **SC-009**: Con Pagos inaccesible, el 100 % de las consultas con cobros sin resolver responde 200 con
  fechas, estado e importe y `payment_in_progress` en `null`, y el 100 % de los inicios de pago responde 503
  sin registrar un cobro; con Clínicas inaccesible, el 100 % responde 503.
- **SC-010**: 0 respuestas con fechas o importes inventados cuando un API ajeno falla o no ofrece todavía lo
  pedido, y 0 respuestas que revelen direcciones, cuerpos de error o credenciales de otro API.
- **SC-011**: Tras pagar, la siguiente consulta muestra la fecha nueva en el 100 % de los casos con Pagos
  disponible, y la persona obtiene la dirección del checkout con una sola petición.
- **SC-012**: Las pruebas de las demás operaciones siguen en verde sin cambiar ninguna de sus comprobaciones
  de comportamiento (0 comprobaciones de comportamiento modificadas), y la colección de Postman nueva se
  ejecuta en verde de punta a punta con las simulaciones.
- **SC-013**: Existen los tres documentos de pedidos (Usuarios, Clínicas y Pagos) y el 100 % de sus pedidos
  trae las cuatro partes: qué falta, para qué, forma propuesta y qué bloquea.

## Assumptions

- **Actor y consumidor**: la operación es para el Dueño de la organización, desde el frontend de las
  clínicas. Las lecturas y escrituras para roles de Sistema (Backoffice) quedan fuera de alcance.
- **La organización se indica en la petición**: las dos operaciones se dirigen a una organización por su
  identificador, que la aplicación toma de la lista «mis clínicas» (`organization_id`). La ruta exacta,
  los nombres de campo y los códigos de error nuevos se fijan en el contrato del plan; los nombres de
  «Key Entities» son los que propone esta especificación.
- **Quién es el Dueño lo decide Clínicas**: esta API no conoce roles ni pertenencias; confía en que
  Clínicas solo deja que un rol de clínica lea la organización de la que es Dueño y en que el permiso
  `subscription_periods:*` solo se asigna al Dueño. Los dos filtros juntos —el permiso (Usuarios) y la
  lectura de la organización (Clínicas)— son el control de acceso: un rol de Sistema, que en Clínicas sí
  puede leer cualquier organización, no llega a esta API porque no tiene el permiso (sus lecturas son otra
  feature).
- **Primer contacto**: el registro se crea en la primera consulta; se crea también si el primer contacto
  fuera iniciar el pago (la aplicación consulta primero, pero la API no puede suponerlo).
- **La consulta aplica cobros aprobados**: el `GET` de consulta tiene un efecto acotado y determinista
  (crear el registro y aplicar o cerrar cobros ya decididos en Pagos). Basta el permiso de lectura porque
  solo refleja pagos que la propia API inició; la persona no controla qué se aplica ni cuándo.
- **Periodo de cobro ausente**: si Clínicas responde 200 sin `billing_period`, la respuesta se trata como
  inesperada (503); no se asume «mensual». Por eso, contra el API real tal como está hoy, la feature no
  funciona hasta que Clínicas lo publique; mientras tanto se desarrolla y se prueba con la simulación
  (historia 8).
- **Sin fuente ficticia dentro del servicio**: a diferencia del dashboard (spec 003), donde no existía
  ninguna fuente real, aquí los clientes reales de los tres APIs existen desde el primer día y una
  fuente ficticia dentro del servicio habría podido conceder acceso a una organización que no es de quien
  llama. El «avance sin esperar» se logra con simulaciones en las pruebas y en la pila aislada de punta a
  punta; el aviso al arrancar que sí aplica es el de la dirección de Pagos sin cifrar (FR-040).
- **Fecha de alta**: se toma la `created_at` de la organización que expone Clínicas, en UTC (decisión D5).
- **Fecha de aprobación**: Pagos no publica una; se usa la de la última actualización del pago, que
  mientras el pago siga aprobado y sin reembolsos coincide con su aprobación o la sigue de cerca (una
  notificación repetida del proveedor la puede adelantar unos minutos). Se pide a Pagos una fecha de
  aprobación propia para exactitud, sin bloquear.
- **Meses**: un periodo mensual parte del fin del anterior y conserva la hora y el día del mes, acortado al
  último día del mes cuando no existe (FR-030). Una organización cuyo día de pago es 29, 30 o 31 puede
  quedar fijada en un día menor tras un mes corto; se acepta por sencillez (no se guarda un día ancla).
- **Cobros con condiciones distintas**: cuando un cambio de plan modifica el importe de un cobro pendiente
  se crea uno nuevo y el anterior queda pendiente, porque Pagos no ofrece cancelar; si se pagan ambos, se
  aplican ambos. Se interpreta así la combinación de «el siguiente cobro usa el plan vigente» y «no crear
  dos cobros para el mismo periodo».
- **Estatus del plan**: el estatus de un plan en el catálogo no afecta al cobro; la organización paga el
  precio del plan que Clínicas informa, aunque ya no admita altas nuevas.
- **Moneda**: solo pesos mexicanos (`MXN`); un pago aprobado en otra moneda no coincide con lo registrado y
  no se aplica.
- **Dependencias externas**: los permisos nuevos de Usuarios, `payments:*` para el Dueño, `tenant_id`, el
  periodo de cobro de Clínicas y la dirección de regreso de Pagos no los crea esta feature; se piden
  (FR-049). Hasta que existan, las pruebas usan las simulaciones, que deben poder conceder y denegar cada
  permiso y reproducir cada falla.
- **Constitución**: no hace falta enmendarla. El «Constitution Check» del plan confirmará, en particular,
  que guardar el identificador de la organización solo como referencia de los datos propios no contradice
  el Principio IX.
- **Condiciones normales (SC-001)**: cada API ajeno responde en menos de 500 ms y el 95 % se mide sobre una
  serie de consultas seguidas.
- **Zona horaria e idioma**: todo en UTC; convertir a la zona horaria de la clínica le toca a la
  aplicación. Los campos, parámetros y códigos están en inglés; los mensajes, la documentación publicada y
  este documento, en español (Principio VII).

### Fuera de alcance

- Bloquear o suspender el acceso al vencer: esta API solo informa.
- Correos o avisos a las personas.
- Facturas (CFDI).
- Prorrateo al cambiar de plan.
- El efecto de reembolsos y contracargos sobre un periodo ya aplicado (decisión D3).
- Cobros recurrentes automáticos: la persona inicia cada pago.
- Lecturas o escrituras para roles de Sistema.
- Ampliar, acortar o reiniciar una prueba a mano.
- Consultar el historial o la lista de cobros (no se pidió).
- Tareas programadas o procesos en segundo plano.
- Las pantallas del frontend y del Backoffice, incluida la forma en que la aplicación recibe de vuelta a la
  persona tras el checkout.

## Decisiones de negocio (resueltas por defecto)

Estas cinco decisiones estaban abiertas en la descripción original. Se cerraron el 2026-11-18 con su valor
por defecto (ver «Clarifications»). La columna «Resolución» es lo que las historias, los requisitos y los
ejemplos dan por hecho; la última dice qué habría que tocar si la persona responsable las cambia después.

| # | Decisión | Resolución | Razón y alternativa considerada | Qué cambiaría |
|---|---|---|---|---|
| D1 | Periodo de gracia después de vencer | Ninguno: `overdue` desde que el reloj alcanza la fecha del siguiente pago; solo se informan el estado y los días de atraso. | Esta API solo informa; qué hacer con una organización vencida (avisar, restringir) es otra decisión y allí puede aplicarse un margen sin tocar este contrato. Alternativa: un margen de N días antes de `overdue`. | El límite de `overdue` (FR-013), los días de atraso (FR-014) y los ejemplos 5, 6, 13 y 14. |
| D2 | Fecha de corte para las organizaciones existentes | Obligatoria y sin valor por omisión; en el primer despliegue vale el instante del despliegue: las existentes empiezan su primer periodo ahí y reciben los días de prueba completos de su plan desde ese instante. | Sin la variable, un despliegue dejaría vencidas a todas de golpe. Consecuencia aceptada: una organización existente con un plan sin prueba (`trial_days` = 0) vence ese mismo día (ejemplo 14); quien opera puede fijar una fecha posterior al despliegue si quiere darles margen. | FR-039, FR-008 y los ejemplos 12, 14 y 15. |
| D3 | Si un reembolso revoca el periodo | No. Un cobro aplicado nunca se revierte; un cobro aún no aplicado cuyo pago ya aparece reembolsado se cierra sin aplicarse. | Pagos no avisa de los cambios: revocar obligaría a revisar en cada consulta todos los cobros ya aplicados y a definir qué pasa con un reembolso parcial. Se atiende en una especificación aparte. | FR-028 (filas de reembolso), FR-032 y «Fuera de alcance». |
| D4 | Si el importe cobrado suma IVA (los precios del catálogo son sin IVA y la tasa la define quien lleva la contabilidad) | No: el importe es el precio del catálogo tal cual, sin IVA sumado ni desglose. | La tasa todavía no existe y no se inventa una política de impuestos. Alternativa recomendada, para añadir después: precio más IVA con una tasa configurable y obligatoria (0 válido) y la respuesta con el desglose (subtotal, impuesto y total), de modo que lo cobrado coincida con lo que luego se factura. | FR-016 a FR-019, la respuesta (campos nuevos, aditivos), el redondeo al centavo y las pruebas de importe. |
| D5 | Fecha de alta de la organización | La `created_at` de la organización, que es lo único que expone Clínicas. | Es lo único que existe y, en un alta normal, la diferencia con el momento en que el Dueño ya puede entrar es de minutos. Alternativa, si el alta del Dueño suele tardar o reintentarse: pedir a Clínicas la fecha en que el alta se completó. | FR-008 y un pedido más a Clínicas. |
