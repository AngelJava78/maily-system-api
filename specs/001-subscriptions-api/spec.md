# Feature Specification: API REST de Suscripciones

**Feature Branch**: `001-subscriptions-api`

**Created**: 2026-10-17

**Status**: Draft

**Input**: User description: "Quiero construir una API como la de mailySoft-usuarios, con el mismo
stack y las mismas reglas, pero para gestionar suscripciones. Voy a recibir un token de Auth0 en las
peticiones y voy a invocar al API de usuarios para ver si la persona tiene el permiso que le permite
leer, crear, actualizar o eliminar la suscripción (la lista de operaciones puede ampliarse). Las
suscripciones pueden estar activas, inactivas o bloqueadas. Se deben devolver todas las
suscripciones con sus estatus; no es necesario paginar. Ejemplos de suscripciones (con los
pantallazos del Front): Básico $1,500/mes, Pro $4,500/mes, Premium $8,900/mes, Enterprise (precio a
cotizar, $0/mes), Solo $900/mes y Legacy full ($0/mes, plan histórico), cada una con su descripción,
el número de clínicas que la tienen y la lista de lo que incluye."

## Clarifications

### Session 2026-10-17

- Q: ¿Cómo se valida el token de Auth0 en este servicio? → A: No se valida aquí. El servicio reenvía
  el token recibido al API de usuarios, que es la única autoridad sobre la identidad y sobre el
  permiso de la persona; este servicio solo obedece su respuesta.
- Q: ¿Qué significa «eliminar» una suscripción, si los estatus son solo Activa, Inactiva y
  Bloqueada? → A: Baja lógica. El catálogo de estatus suma un cuarto estatus, «Eliminada»: la
  suscripción se conserva (hay clínicas que la referencian) pero deja de aparecer en el listado y de
  consultarse.
- Q: ¿De dónde sale el «N clínicas en este plan» que muestra el Front? → A: Del API de clínicas,
  consultado en cada lectura. Este servicio no guarda clínicas ni su asignación a los planes.
- Q: ¿Qué pasa si se intenta eliminar o bloquear una suscripción con clínicas asignadas? → A:
  Eliminar se rechaza si la suscripción tiene clínicas; bloquear e inactivar se permiten siempre. Como
  saber si tiene clínicas depende del API de clínicas, si ese API no responde la eliminación se
  rechaza por no poder comprobarlo.
- Q: ¿Cómo se describe lo que incluye un plan? → A: Solo como una lista de textos libres, tal como la
  muestra hoy el Front. No hay límites estructurados (de consultorios o de usuarios) que otros
  sistemas puedan aplicar de forma automática; si algún día se necesitan, se especificarán aparte.

## User Scenarios & Testing *(mandatory)*

Los actores son **quien administra los planes de MailySoft** (una persona, desde la pantalla
«Planes» de una aplicación de administración) y **los sistemas consumidores** (otros servicios que
leen el catálogo de suscripciones). Toda persona que use la API se identifica con un token de acceso
y solo puede hacer lo que sus permisos le autorizan; los permisos los decide el API de usuarios, no
este servicio.

### User Story 1 - Consultar el catálogo de suscripciones con su estatus (Priority: P1)

Quien tiene permiso de lectura obtiene, en una sola consulta, todas las suscripciones vigentes
—Activas, Inactivas y Bloqueadas— cada una con su estatus, su precio mensual, su descripción, lo que
incluye y el número de clínicas que la tienen. No hay páginas: la lista llega completa y en un orden
estable. Las suscripciones eliminadas no aparecen.

**Why this priority**: Es la pantalla que hoy muestra el Front (tarjetas de planes, con las
inactivas atenuadas) y el dato base que consumen los demás sistemas; sin él, el resto de las
operaciones no tiene dónde verse.

**Independent Test**: Con cuatro suscripciones —una Activa, una Inactiva, una Bloqueada y una
Eliminada— consultar el catálogo y comprobar que devuelve exactamente las tres primeras, cada una
con su estatus, el mismo orden en dos consultas seguidas y sin ninguna señal de paginación; repetir
con el catálogo vacío y comprobar que devuelve una lista vacía, no un error.

**Acceptance Scenarios**:

1. **Given** hay suscripciones Activas, Inactivas y Bloqueadas, **When** una persona con permiso de
   lectura consulta el catálogo, **Then** recibe todas, cada una con su estatus (identificador y
   nombre), su precio mensual, su descripción, lo que incluye, el número de clínicas y sus fechas de
   creación y de última modificación.
2. **Given** existe una suscripción Eliminada, **When** se consulta el catálogo, **Then** no aparece.
3. **Given** el API de clínicas no responde, **When** se consulta el catálogo, **Then** las
   suscripciones se devuelven igualmente, con el número de clínicas indicado como «no disponible»
   (nunca como cero).
4. **Given** el catálogo está vacío, **When** se consulta, **Then** se devuelve una lista vacía.

---

### User Story 2 - Solo quien tiene el permiso puede operar (Priority: P1)

Cada operación sobre las suscripciones exige que la persona esté autenticada y tenga el permiso
correspondiente: leer, crear, actualizar o eliminar. Si no está autenticada se le pide iniciar
sesión; si lo está pero no tiene el permiso, se le niega la operación y no cambia nada. La
comprobación se hace en cada petición con los datos vigentes del API de usuarios, de modo que bloquear
a una persona o quitarle un permiso surte efecto en su siguiente petición.

**Why this priority**: Las suscripciones determinan qué puede usar cada clínica y cuánto paga; una
operación sin control es un riesgo de negocio. Es indispensable desde la primera versión.

**Independent Test**: Para cada operación, probar con (a) sin token, (b) token inválido o vencido,
(c) persona autenticada sin el permiso, (d) persona con el permiso, y (e) el API de usuarios caído;
comprobar que solo (d) ejecuta la operación y que (a)–(c) y (e) no cambian nada.

**Acceptance Scenarios**:

1. **Given** una petición sin token, **When** se invoca cualquier operación de suscripciones,
   **Then** se rechaza indicando que debe iniciar sesión y no se ejecuta nada.
2. **Given** una persona autenticada que no tiene el permiso de la operación, **When** la invoca,
   **Then** se rechaza indicando que no tiene permiso y no se crea ni se modifica nada.
3. **Given** una persona con permiso de lectura pero no de actualización, **When** intenta cambiar
   una suscripción, **Then** se rechaza; sigue pudiendo consultar.
4. **Given** una persona a la que acaban de quitar el permiso en el API de usuarios, **When** hace su
   siguiente petición, **Then** se le niega, sin esperar a que caduque su token.
5. **Given** el API de usuarios no responde o responde algo inesperado, **When** se invoca cualquier
   operación, **Then** se rechaza indicando que el servicio no está disponible por el momento
   (nunca se ejecuta «por si acaso»).
6. **Given** una petición con permiso denegado y datos además inválidos, **When** se invoca,
   **Then** el rechazo es por falta de permiso: la comprobación ocurre antes de validar los datos o
   buscar la suscripción.
7. **Given** la documentación publicada de la API, **When** cualquiera la abre, **Then** se muestra
   sin pedir token.

---

### User Story 3 - Crear una suscripción (Priority: P2)

Quien tiene permiso de escritura registra un plan nuevo con su nombre, su descripción (opcional), su
precio mensual y lo que incluye. La suscripción nace Activa y aparece de inmediato en el catálogo.
No puede haber dos suscripciones vigentes con el mismo nombre.

**Why this priority**: Permite formar el catálogo que consumen las demás historias; es el botón
«Nuevo plan» de la pantalla.

**Independent Test**: Crear «Pro» con precio mensual 4,500 y verificar que la respuesta trae su
identificador, su estatus Activa, el número de clínicas y sus fechas, y que aparece en el
catálogo; intentar crear otra llamada «pro» (con otra capitalización) y comprobar que se rechaza;
intentar crear una sin nombre o con precio negativo y comprobar que se rechaza.

**Acceptance Scenarios**:

1. **Given** una persona con permiso de escritura, **When** crea una suscripción con datos válidos,
   **Then** se crea con estatus Activa, se devuelve completa y aparece en el catálogo.
2. **Given** ya existe una suscripción vigente con el nombre «Pro», **When** se intenta crear otra
   llamada «pro», **Then** se rechaza indicando que el nombre ya está en uso.
3. **Given** existe una suscripción Eliminada llamada «Solo», **When** se crea una nueva llamada
   «Solo», **Then** se crea sin conflicto (el nombre de una eliminada queda libre).
4. **Given** la solicitud trae un dato no reconocido (por ejemplo, un identificador o un estatus),
   **When** se envía, **Then** se rechaza completa indicando qué campo no está permitido.
5. **Given** una solicitud con nombre vacío, precio negativo o con más de dos decimales, **When** se
   envía, **Then** se rechaza con un mensaje por cada campo inválido.

---

### User Story 4 - Consultar una suscripción (Priority: P2)

Quien tiene permiso de lectura consulta una suscripción por su identificador y obtiene el mismo
detalle que en el catálogo, con su estatus y su número de clínicas.

**Why this priority**: Los sistemas consumidores y el formulario de edición necesitan leer un plan
concreto sin traer todo el catálogo.

**Independent Test**: Consultar una suscripción Activa, una Inactiva y una Bloqueada y comprobar que
se devuelven con su estatus; consultar una Eliminada y una que no existe y comprobar que ambas se
reportan como «no se encuentra».

**Acceptance Scenarios**:

1. **Given** una suscripción Activa, Inactiva o Bloqueada, **When** se consulta por su
   identificador, **Then** se devuelve completa con su estatus.
2. **Given** una suscripción Eliminada o un identificador inexistente, **When** se consulta,
   **Then** se responde que no se encuentra.

---

### User Story 5 - Actualizar una suscripción (Priority: P2)

Quien tiene permiso de actualización cambia el nombre, la descripción, el precio mensual o lo que
incluye una suscripción. Puede enviar solo los datos que cambian; el resto se conserva. El estatus no
se cambia por aquí (ver historia 6).

**Why this priority**: Los precios y las funciones de un plan cambian con el tiempo; es el lápiz de
edición de cada tarjeta de la pantalla.

**Independent Test**: Cambiar solo el precio de una suscripción y comprobar que lo demás queda
igual y que su fecha de última modificación cambia; intentar ponerle el nombre de otra suscripción
vigente y comprobar que se rechaza; intentar actualizar una Eliminada y comprobar que no se
encuentra.

**Acceptance Scenarios**:

1. **Given** una suscripción vigente, **When** se actualiza solo su precio con un valor válido,
   **Then** cambia el precio, el resto se conserva y se actualiza su fecha de modificación.
2. **Given** otra suscripción vigente ya tiene el nombre deseado, **When** se intenta usarlo,
   **Then** se rechaza indicando que el nombre ya está en uso.
3. **Given** la solicitud intenta cambiar el estatus, el identificador, las fechas o el número de
   clínicas, **When** se envía, **Then** se rechaza completa indicando qué campo no está permitido.
4. **Given** una suscripción Eliminada, **When** se intenta actualizar, **Then** se responde que no
   se encuentra.

---

### User Story 6 - Cambiar el estatus de una suscripción (Priority: P2)

Quien tiene permiso de actualización cambia el estatus de una suscripción entre Activa, Inactiva y
Bloqueada. El cambio queda reflejado en el catálogo y en el detalle de inmediato.

**Why this priority**: Es el modo de retirar un plan de la oferta (Inactiva, como «Solo» o «Legacy
full» en la pantalla) o de suspenderlo (Bloqueada) sin perder su historial.

**Independent Test**: Pasar una suscripción Activa a Inactiva, a Bloqueada y de vuelta a Activa,
comprobando cada vez su estatus en el catálogo; pedir el estatus que ya tiene y comprobar que se
rechaza; pedir un estatus que no existe o «Eliminada» y comprobar que se rechaza.

**Acceptance Scenarios**:

1. **Given** una suscripción Activa, **When** se cambia a Inactiva o a Bloqueada, **Then** su estatus
   cambia y el catálogo la sigue mostrando con el nuevo estatus.
2. **Given** una suscripción Inactiva o Bloqueada, **When** se cambia a Activa, **Then** vuelve a
   estar Activa.
3. **Given** una suscripción que ya tiene el estatus pedido, **When** se pide ese mismo estatus,
   **Then** se rechaza indicando que ya lo tiene.
4. **Given** se pide «Eliminada» o un estatus desconocido por esta vía, **When** se envía, **Then**
   se rechaza: eliminar se hace con su propia operación.
5. **Given** una suscripción con clínicas asignadas, **When** se cambia a Inactiva o a Bloqueada,
   **Then** el cambio se permite y las clínicas conservan su asignación.

---

### User Story 7 - Eliminar una suscripción (Priority: P3)

Quien tiene permiso de eliminación da de baja una suscripción. La baja es lógica: la suscripción se
conserva con el estatus Eliminada, deja de aparecer en el catálogo y de poder consultarse, y su
nombre queda libre para otra.

**Why this priority**: Evita que planes descontinuados ensucien el catálogo sin perder su historial;
es menos frecuente que las demás operaciones.

**Independent Test**: Eliminar una suscripción y comprobar que ya no aparece en el catálogo, que
consultarla responde «no se encuentra», que no puede actualizarse ni cambiar de estatus y que su
nombre puede usarse en una suscripción nueva; eliminar una inexistente y comprobar que no se
encuentra; intentar eliminar una con clínicas asignadas y comprobar que se rechaza y que sigue en el
catálogo; repetirlo con el API de clínicas inaccesible y comprobar que también se rechaza.

**Acceptance Scenarios**:

1. **Given** una suscripción vigente sin clínicas, **When** se elimina, **Then** pasa a Eliminada, no
   aparece en el catálogo y su nombre queda libre.
2. **Given** una suscripción Eliminada o inexistente, **When** se intenta eliminar, **Then** se
   responde que no se encuentra.
3. **Given** una suscripción con clínicas asignadas, **When** se intenta eliminar, **Then** se
   rechaza indicando que tiene clínicas asignadas, y no cambia nada.
4. **Given** el API de clínicas no responde, **When** se intenta eliminar una suscripción, **Then**
   se rechaza indicando que no se pudo comprobar si tiene clínicas, y no cambia nada.

---

### Edge Cases

- **El API de usuarios no responde** (caída, tiempo agotado o respuesta inesperada): ninguna
  operación se ejecuta y se indica que el servicio no está disponible por el momento. La
  documentación publicada sigue disponible.
- **El API de clínicas no responde**: el catálogo y el detalle siguen funcionando; solo falta el
  número de clínicas, marcado como no disponible. Nunca se muestra un cero inventado. La única
  operación que sí se rechaza en ese caso es eliminar, porque no puede comprobarse que la
  suscripción no tenga clínicas.
- **Persona autenticada pero bloqueada o sin roles en el API de usuarios**: no tiene permisos, así
  que se le niegan todas las operaciones.
- **Dos personas crean a la vez una suscripción con el mismo nombre**: solo una se crea; la otra
  recibe el rechazo de nombre en uso.
- **Nombre con distinta capitalización o con espacios al inicio o al final**: «Pro», «pro» y
  « Pro » se consideran el mismo nombre; los textos se guardan sin espacios sobrantes.
- **Precio cero**: es válido (planes de precio a cotizar o históricos); el motivo se explica en la
  descripción.
- **Precio negativo, con más de dos decimales o desmesurado**: se rechaza.
- **Identificador mal formado o inexistente**: se responde que no se encuentra o que el dato no es
  válido, nunca un error interno.
- **Datos no reconocidos en la solicitud** (campos mal escritos o que no se pueden enviar): se
  rechaza toda la solicitud y no se cambia nada.
- **Catálogo vacío**: lista vacía, no error.
- **Catálogo que crece más allá de lo previsto**: ver FR-006; pasar a paginar sería un cambio
  incompatible del contrato.

## Requirements *(mandatory)*

### Functional Requirements

**Control de acceso**

- **FR-001**: Toda operación sobre las suscripciones MUST exigir un token de acceso válido y el
  permiso que le corresponde. Solo la documentación publicada de la API MUST estar disponible sin
  token.
- **FR-002**: El servicio MUST NOT verificar el token por sí mismo: MUST reenviarlo, sin
  modificarlo, al API de usuarios y MUST aceptar su respuesta como única autoridad sobre la
  identidad y el permiso de la persona.
- **FR-003**: Los permisos de las suscripciones MUST ser cuatro: `subscriptions:read` (consultar el
  catálogo y una suscripción), `subscriptions:write` (crear), `subscriptions:update` (actualizar y
  cambiar el estatus) y `subscriptions:delete` (eliminar). La lista de operaciones y permisos MUST
  poder ampliarse sin rehacer las existentes.
- **FR-004**: La comprobación MUST hacerse en cada petición, con los datos vigentes del API de
  usuarios (sin conservar decisiones anteriores), y MUST ocurrir antes de validar los datos de la
  solicitud o de buscar la suscripción.
- **FR-005**: Cuando no pueda decidirse el acceso (token rechazado, permiso denegado, API de usuarios
  sin respuesta o con respuesta inesperada), el servicio MUST rechazar la operación sin ejecutarla,
  distinguiendo en el mensaje entre «debe iniciar sesión», «no tiene permiso» y «servicio no
  disponible por el momento».

**Catálogo y consulta**

- **FR-006**: El servicio MUST devolver en una sola consulta todas las suscripciones en estatus
  Activa, Inactiva y Bloqueada, sin paginar, cada una con su estatus, y en un orden determinista:
  por fecha de creación (la más antigua primero) y, a igualdad, por identificador. El catálogo
  esperado no supera 100 suscripciones y su máximo para devolverse completo es 500; si lo supera,
  el listado deberá paginarse, lo que es un cambio incompatible que se versiona.
- **FR-007**: Las suscripciones Eliminadas MUST NOT aparecer en el catálogo y MUST tratarse como
  inexistentes en cualquier otra operación.
- **FR-008**: Cada suscripción MUST mostrar: identificador, nombre, descripción (si tiene), precio
  mensual, lo que incluye (ver FR-012), estatus como objeto con identificador y nombre, número de
  clínicas y fechas de creación y de última modificación.
- **FR-009**: El número de clínicas de cada suscripción MUST obtenerse del API de clínicas en cada
  lectura y MUST NOT guardarse en este servicio. Si ese dato no está disponible, la suscripción MUST
  devolverse igualmente con el número marcado como no disponible, nunca como cero.
- **FR-010**: El servicio MUST permitir consultar una suscripción por su identificador (Activa,
  Inactiva o Bloqueada) con el mismo detalle que el catálogo.

**Creación y actualización**

- **FR-011**: El servicio MUST permitir crear una suscripción con nombre (obligatorio, de 1 a 100
  caracteres), descripción (opcional, hasta 500 caracteres), precio mensual y lo que incluye. La
  suscripción MUST nacer con estatus Activa.
- **FR-012**: Cada suscripción MUST describir lo que incluye mediante una lista ordenada de textos
  libres (por ejemplo, «Hasta 5 consultorios» o «Todo lo de Pro»), que puede estar vacía, con hasta
  20 elementos de 1 a 150 caracteres cada uno. El servicio MUST conservar y devolver la lista en el
  orden en que se envió y MUST NOT interpretar sus textos como límites aplicables.
- **FR-013**: El precio mensual MUST ser un importe en pesos mexicanos, mayor o igual a cero, con
  como máximo dos decimales, y MUST guardarse sin pérdida de precisión.
- **FR-014**: El nombre de una suscripción MUST ser único, sin distinguir mayúsculas, entre las
  suscripciones que no están Eliminadas (una Inactiva o Bloqueada sigue reservando su nombre; el de
  una Eliminada queda libre). La unicidad MUST cumplirse también con solicitudes simultáneas.
- **FR-015**: El servicio MUST permitir actualizar el nombre, la descripción, el precio mensual y lo
  que incluye de una suscripción vigente, enviando solo lo que cambia. MUST actualizar su fecha de
  última modificación y MUST NOT permitir cambiar por esta vía el identificador, el estatus, las
  fechas ni el número de clínicas.
- **FR-016**: El servicio MUST permitir cambiar el estatus de una suscripción vigente entre Activa,
  Inactiva y Bloqueada, en cualquier dirección. Pedir el estatus que ya tiene MUST rechazarse
  indicándolo, y pedir «Eliminada» por esta vía MUST rechazarse.

**Eliminación**

- **FR-017**: El servicio MUST permitir eliminar una suscripción de forma lógica (estatus
  Eliminada), conservando sus datos. Eliminar MUST rechazarse indicando que tiene clínicas asignadas
  si la suscripción tiene al menos una, y MUST rechazarse indicando que no pudo comprobarse si el
  API de clínicas no responde; en ambos casos no cambia nada. Bloquear e inactivar una suscripción
  MUST permitirse siempre, tenga o no clínicas.
- **FR-018**: Una suscripción Eliminada MUST NOT poder reactivarse, actualizarse ni cambiar de
  estatus con esta API en esta versión.

**Calidad de la API**

- **FR-019**: El servicio MUST rechazar toda solicitud que traiga datos no reconocidos (campos mal
  escritos o que no se pueden enviar), indicando qué campo no está permitido, sin crear ni
  modificar nada.
- **FR-020**: Los textos recibidos MUST guardarse sin espacios al inicio ni al final.
- **FR-021**: Los mensajes dirigidos a personas (validaciones, errores y confirmaciones) MUST estar
  en español y todos los errores MUST tener el mismo formato, que distingue al menos: no
  autenticado, sin permiso, no se encuentra, conflicto (nombre en uso, estatus repetido o
  suscripción con clínicas), datos no válidos y dependencia no disponible. Ningún mensaje MUST revelar el token, secretos ni detalles
  internos de otros servicios.
- **FR-022**: Los estatus MUST salir de un catálogo de estatus de suscripción —Activa, Inactiva,
  Bloqueada y Eliminada— que se administra a mano; quien consuma la API MUST basarse en el
  identificador del estatus, no en su nombre.
- **FR-023**: Cada operación MUST documentar en el contrato publicado de la API el permiso que
  exige y sus respuestas posibles.

### Key Entities

- **Suscripción (plan)**: oferta comercial que se asigna a las clínicas. Tiene nombre único entre
  las vigentes, descripción opcional, precio mensual, lo que incluye (lista ordenada de textos
  libres), un estatus, el número de
  clínicas (dato ajeno, solo lectura) y fechas de creación y de última modificación.
- **Estatus de suscripción**: catálogo con Activa (disponible y ofrecida), Inactiva (retirada de la
  oferta), Bloqueada (suspendida) y Eliminada (baja lógica, fuera de toda consulta).
- **Persona autenticada y permiso** *(externos, del API de usuarios)*: quien invoca la API y los
  permisos `subscriptions:*` que el API de usuarios le reconoce. Este servicio no los guarda.
- **Clínica** *(externa, del API de clínicas)*: cliente que tiene asignada una suscripción. Este
  servicio solo conoce cuántas tiene cada una.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El catálogo completo (hasta 100 suscripciones) se obtiene en una sola consulta y
  aparece en pantalla en menos de 2 segundos en el 95 % de las consultas en condiciones normales.
- **SC-002**: El 100 % de las operaciones sin token válido, sin permiso o con el API de usuarios
  inaccesible se rechaza sin cambiar ningún dato, y una verificación automática que recorre todas
  las operaciones confirma que ninguna carece de permiso declarado (salvo la documentación).
- **SC-003**: Un bloqueo o un cambio de permisos hecho en el API de usuarios surte efecto en la
  siguiente petición de esa persona (0 peticiones posteriores aceptadas por permisos ya revocados).
- **SC-004**: El 100 % de las suscripciones devueltas, en el catálogo o en el detalle, incluye su
  estatus; las Eliminadas no aparecen en ninguna consulta.
- **SC-005**: Con el API de clínicas inaccesible, el 100 % de las consultas del catálogo y del
  detalle sigue devolviendo las suscripciones, sin el número de clínicas.
- **SC-006**: Ante 50 intentos simultáneos de crear una suscripción con el mismo nombre, exactamente
  uno tiene éxito.
- **SC-007**: Quien administra puede crear una suscripción y verla en el catálogo en menos de 1
  minuto, sin conocimientos técnicos.
- **SC-008**: El 100 % de los mensajes de error está en español y sigue el mismo formato.
- **SC-009**: Ninguna suscripción con clínicas asignadas llega a eliminarse, ni siquiera cuando no
  puede comprobarse si las tiene (0 casos).

## Assumptions

- **Origen de los ejemplos**: los seis planes que se compartieron (Básico, Pro, Premium, Enterprise,
  Solo y Legacy full) ilustran la información que muestra el Front; **no** son datos iniciales
  obligatorios. El catálogo empieza vacío y se llena con la operación de crear. Si se necesitan
  cargados de origen, se pedirá en una especificación aparte.
- **Moneda y periodo**: los precios son mensuales y en pesos mexicanos (se infiere de la facturación
  CFDI de los planes). No hay otro periodo de cobro ni otra moneda en esta versión. Un precio de 0
  es válido; «precio a cotizar» y «plan histórico» se explican en la descripción.
- **Significado de los estatus**: **Activa** = disponible y ofrecida a clínicas nuevas. **Inactiva**
  = retirada de la oferta pero conservada, y las clínicas que ya la tienen siguen con ella (como
  «Solo» y «Legacy full» en la pantalla). **Bloqueada** = suspendida por la administración. Este
  servicio solo guarda y publica el estatus y valida sus propias reglas; aplicar sus consecuencias a
  las clínicas (por ejemplo, impedir asignar un plan Inactivo o Bloqueado) corresponde a los
  sistemas que lo consumen, y queda fuera de esta especificación. Las suscripciones Activa, Inactiva
  y Bloqueada pueden editarse.
- **Cambios de estatus**: se permiten de cualquier estatus vigente a cualquier otro. Una suscripción
  Eliminada no se recupera con esta API; si hiciera falta, se haría a mano en la base de datos.
- **Orden del catálogo**: por fecha de creación, la más antigua primero; el Front puede reordenar o
  agrupar (por ejemplo, las Inactivas al final).
- **Límites de los textos**: el nombre admite hasta 100 caracteres y la descripción hasta 500; lo
  que incluye admite hasta 20 elementos de hasta 150 caracteres.
- **Lo que incluye un plan es solo informativo**: es texto para mostrar, igual que en el Front. Los
  límites reales (consultorios, usuarios) los aplican los sistemas que consumen el catálogo; si
  necesitan leerlos como datos, se añadirán en una especificación futura.
- **Dependencia del API de usuarios**: se consulta su operación de verificación de los permisos de la
  persona autenticada (la prevista en su especificación 008); los permisos `subscriptions:*` MUST
  estar dados de alta en su catálogo antes de integrar. Si esa operación aún no está desplegada,
  se prueba con una simulación.
- **Dependencia del API de clínicas**: debe ofrecer el número de clínicas por suscripción; su
  contrato se define en la planificación. Mientras no exista, el número se marca como no disponible.
- **Fuera de alcance**: asignar suscripciones a las clínicas, facturación y cobro, historial de
  precios o de cambios («quién» cambió qué), avisos a las clínicas cuando cambia un plan, gestión de
  cuentas de acceso (Auth0) y varios idiomas (todo el contenido es en español).
- **Conservación**: los datos de las suscripciones eliminadas se conservan por auditoría; un borrado
  definitivo, si algún día se exige, queda fuera de esta API.
