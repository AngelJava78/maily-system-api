# Feature Specification: Corrección del modelo de datos de la API de Suscripciones

**Feature Branch**: `004-correct-subscriptions-api`

**Created**: 2026-10-23

**Status**: Draft

**Input**: User description: "Te comparto un Mockup para que se corrija la API de suscripciones.
Ignora la parte de registrar clínica (esa no va en esta API). Actualmente la API contiene datos
mínimos o datos que no están o no deben ir. Analiza mi archivo adjunto y genera la spec para crear,
actualizar, eliminar (lógicamente) y listar las suscripciones." Se adjuntó un mockup del Backoffice
de MailySoft (pantallas «Nueva suscripción» y «Suscripciones» —listado y comparativo—) con los datos
que debe tener cada plan: nombre, descripción, precio mensual, precio anual, días de prueba, si se
ofrece en autoconsumo desde el portal de MailySoft, los módulos de clínica que habilita (de un
catálogo de 9, con dependencias entre varios), los límites de crecimiento de la clínica
(consultorios, doctores, asistentes y pacientes nuevos al año) y otras funcionalidades que no son
módulos (soporte, capacitación…). El mockup también incluye la pantalla «Registrar clínica», que
queda fuera de esta API por instrucción explícita del responsable del proyecto.

## Clarifications

### Session 2026-10-23

- Q: ¿El precio anual de un plan debe guardarse siempre como una proporción fija del precio
  mensual (por ejemplo, 10 meses de precio = 2 meses gratis), o debe ser un valor totalmente
  independiente que la persona administradora decide libremente? → A: Precio anual independiente,
  sin proporción obligatoria con el mensual; la API no calcula ni exige ninguna relación entre
  ambos precios.
- Q: ¿El catálogo de los módulos de clínica debe administrarse en esta API de Suscripciones, o debe
  pedirse a otra API? → A: Vive en la API de usuarios (`mailySoft-usuarios`), como módulos de tipo
  «Clínica». Esta API de Suscripciones no lo administra: lo solicita a la API de usuarios y valida
  contra ella los identificadores de módulo que recibe.
- Q: Como la API de usuarios no modela dependencias entre módulos ni un «siempre incluido», ¿quién
  valida esas reglas (que Recordatorios exija Agenda y citas, que Pacientes esté siempre incluido,
  etc.)? → A: Esta API de Suscripciones sigue validando las dependencias y el «siempre incluido»
  con sus propias reglas, referenciando los módulos por el identificador que reconoce la API de
  usuarios.
- Q: Ya que el nombre y la descripción de cada módulo viven en la API de usuarios, ¿la respuesta de
  esta API de Suscripciones debe incluir el nombre y la descripción de cada módulo incluido, o solo
  su identificador? → A: Solo el identificador de cada módulo incluido; quien consulta obtiene el
  nombre y la descripción directamente de la API de usuarios. El listado de suscripciones no hace
  ninguna llamada adicional a la API de usuarios para resolver nombres de módulo.
- Q: Si no se envía el campo de autoconsumo al crear una suscripción, ¿nace sin autoconsumo o con
  autoconsumo activado por defecto? → A: Nace sin autoconsumo (falso) si no se envía; hay que
  activarlo a propósito, para que un plan nunca quede público por accidente.

## User Scenarios & Testing *(mandatory)*

Los actores son **quien administra los planes de MailySoft** (una persona, desde el Backoffice) y
**los sistemas consumidores** (otros servicios que leen el catálogo de suscripciones, incluida la
pantalla de registrar clínica, que queda fuera de esta API). Toda persona que use la API se
identifica con un token de acceso y solo puede hacer lo que sus permisos le autorizan.

### User Story 1 - Consultar el catálogo de planes con su información completa (Priority: P1)

Quien tiene permiso de lectura obtiene, en una sola consulta, todas las suscripciones vigentes
—Activas, Inactivas y Bloqueadas—, cada una con su estatus, sus dos precios (mensual y anual), sus
días de prueba, si está en autoconsumo, los módulos de clínica que incluye, sus cuatro límites de la
clínica, sus otras funcionalidades y el número de clínicas que la tienen. No hay páginas: la lista
llega completa y en un orden estable. Las suscripciones eliminadas no aparecen.

**Why this priority**: Es la pantalla que hoy muestra el Backoffice (listado y comparativo de
planes) y el dato base que consumen los demás sistemas, incluida la pantalla de registrar clínica
(fuera de esta API); sin un plan completo no se puede comparar ni asignar.

**Independent Test**: Con el plan «Profesional» del mockup (precio mensual $1,299, precio anual
$12,990, 14 días de prueba, autoconsumo activado, 6 módulos —Pacientes, Agenda y citas,
Recordatorios, Expediente clínico, Plantillas de expediente y Recetas—, límites 2 consultorios / 3
doctores / 2 asistentes / 15,000 pacientes nuevos al año, y las funcionalidades «Soporte por correo
y WhatsApp» y «Capacitación inicial en línea»), consultar el catálogo y comprobar que todos esos
datos llegan completos; repetir con el catálogo vacío y comprobar que devuelve una lista vacía, no
un error.

**Acceptance Scenarios**:

1. **Given** hay suscripciones Activas, Inactivas y Bloqueadas, **When** una persona con permiso de
   lectura consulta el catálogo, **Then** recibe todas, cada una con su estatus, sus dos precios,
   sus días de prueba, su autoconsumo, sus módulos, sus cuatro límites, sus otras funcionalidades,
   el número de clínicas y sus fechas de creación y de última modificación.
2. **Given** existe una suscripción Eliminada, **When** se consulta el catálogo, **Then** no
   aparece.
3. **Given** el API de clínicas no responde, **When** se consulta el catálogo, **Then** las
   suscripciones se devuelven igualmente, con el número de clínicas indicado como «no disponible»
   (nunca como cero) y con el resto de sus datos completo.
4. **Given** el catálogo está vacío, **When** se consulta, **Then** se devuelve una lista vacía.
5. **Given** la suscripción «Avanzado» del mockup (8 de 9 módulos: todos salvo Facturación),
   **When** se consulta, **Then** la lista de módulos incluidos no contiene Facturación aunque sí
   contiene Finanzas (su prerrequisito), confirmando que excluir un módulo no obliga a excluir los
   que dependen de él.

---

### User Story 2 - Solo quien tiene el permiso puede operar (Priority: P1)

Cada operación exige que la persona esté autenticada y tenga el permiso correspondiente: leer,
crear, actualizar o eliminar. Si no está autenticada se le pide iniciar sesión; si lo está pero no
tiene el permiso, se le niega la operación y no cambia nada. La comprobación se hace en cada
petición con los datos vigentes del API de usuarios.

**Why this priority**: Las suscripciones determinan qué puede usar cada clínica y cuánto paga; una
operación sin control es un riesgo de negocio.

**Independent Test**: Para cada operación, probar con (a) sin token, (b) token inválido, (c)
persona sin el permiso, (d) persona con el permiso, y (e) el API de usuarios caído; comprobar que
solo (d) ejecuta la operación.

**Acceptance Scenarios**:

1. **Given** una petición sin token, **When** se invoca cualquier operación, **Then** se rechaza
   indicando que debe iniciar sesión y no se ejecuta nada.
2. **Given** una persona autenticada sin el permiso de la operación, **When** la invoca, **Then**
   se rechaza indicando que no tiene permiso y no se crea ni se modifica nada.
3. **Given** a una persona le acaban de quitar el permiso en el API de usuarios, **When** hace su
   siguiente petición, **Then** se le niega, sin esperar a que caduque su token.
4. **Given** el API de usuarios no responde, **When** se invoca cualquier operación, **Then** se
   rechaza indicando que el servicio no está disponible por el momento.
5. **Given** una petición con permiso denegado y datos además inválidos (por ejemplo, un precio
   anual negativo), **When** se invoca, **Then** el rechazo es por falta de permiso: la
   comprobación ocurre antes de validar los datos.

---

### User Story 3 - Crear una suscripción con su información completa (Priority: P2)

Quien tiene permiso de escritura registra un plan nuevo con su nombre, descripción opcional, precio
mensual, precio anual, días de prueba, si está en autoconsumo, los módulos de clínica que incluye,
sus cuatro límites de la clínica y sus otras funcionalidades. La suscripción nace Activa y aparece
de inmediato en el catálogo. No puede haber dos suscripciones vigentes con el mismo nombre.

**Why this priority**: Es el botón «Nueva suscripción» del Backoffice; sin crear con el modelo
completo, el resto de las pantallas (listado, comparativo y la asignación a clínicas, fuera de esta
API) no tienen de dónde leer los módulos y los límites.

**Independent Test**: Crear «Profesional» con precio mensual 1299, precio anual 12990, 14 días de
prueba, autoconsumo activado, los módulos Pacientes, Agenda y citas, Recordatorios, Expediente
clínico, Plantillas de expediente y Recetas, límites 2/3/2/15000 y las funcionalidades «Soporte por
correo y WhatsApp» y «Capacitación inicial en línea»; verificar que la respuesta trae todo eso más
su identificador, estatus Activa, 0 clínicas y sus fechas. Intentar crear con Recetas pero sin
Expediente clínico y comprobar que se rechaza. Intentar crear sin los límites y comprobar que se
rechaza.

**Acceptance Scenarios**:

1. **Given** una persona con permiso de escritura, **When** crea una suscripción con datos válidos
   (incluidos sus módulos y sus cuatro límites), **Then** se crea con estatus Activa, se devuelve
   completa y aparece en el catálogo.
2. **Given** ya existe una suscripción vigente llamada «Profesional», **When** se intenta crear
   otra llamada «profesional» (otra capitalización), **Then** se rechaza indicando que el nombre
   ya está en uso.
3. **Given** una solicitud que incluye el módulo Recetas sin incluir Expediente clínico, **When**
   se envía, **Then** se rechaza indicando que Recetas exige Expediente clínico.
4. **Given** una solicitud que no incluye el módulo Pacientes, **When** se envía, **Then** se crea
   de todas formas con Pacientes incluido.
5. **Given** una solicitud sin alguno de los cuatro límites de la clínica, **When** se envía,
   **Then** se rechaza indicando que falta un dato obligatorio.
6. **Given** una solicitud sin precio anual, **When** se envía, **Then** se rechaza indicando que
   el precio anual es obligatorio.
7. **Given** una solicitud sin días de prueba ni autoconsumo, **When** se envía, **Then** se crea
   con 0 días de prueba y sin autoconsumo.
8. **Given** la solicitud trae un dato no reconocido (por ejemplo, un identificador o un estatus),
   **When** se envía, **Then** se rechaza completa indicando qué campo no está permitido.
9. **Given** la API de usuarios no responde al validar los módulos de la solicitud, **When** se
   envía, **Then** se rechaza indicando que no se pudo comprobar, y no se crea nada.

---

### User Story 4 - Consultar una suscripción por su identificador (Priority: P2)

Quien tiene permiso de lectura consulta una suscripción por su identificador y obtiene el mismo
detalle completo que en el catálogo.

**Why this priority**: El formulario de edición del Backoffice necesita leer un plan concreto (con
sus módulos ya marcados y sus límites) sin traer todo el catálogo.

**Independent Test**: Consultar una suscripción Activa, una Inactiva y una Bloqueada y comprobar
que se devuelven con su detalle completo; consultar una Eliminada y una que no existe y comprobar
que ambas se reportan como «no se encuentra».

**Acceptance Scenarios**:

1. **Given** una suscripción Activa, Inactiva o Bloqueada, **When** se consulta por su
   identificador, **Then** se devuelve completa, con sus módulos marcados y sus límites.
2. **Given** una suscripción Eliminada o un identificador inexistente, **When** se consulta,
   **Then** se responde que no se encuentra.

---

### User Story 5 - Actualizar los datos de una suscripción (Priority: P2)

Quien tiene permiso de actualización cambia el nombre, la descripción, el precio mensual, el precio
anual, los días de prueba, el autoconsumo, los módulos incluidos, los cuatro límites de la clínica o
las otras funcionalidades de una suscripción. Puede enviar solo los datos que cambian; el resto se
conserva. El estatus no se cambia por aquí (ver historia 6).

**Why this priority**: Los precios, los módulos y los límites de un plan cambian con el tiempo; es
el lápiz de edición de cada tarjeta del Backoffice.

**Independent Test**: Cambiar solo el precio anual de una suscripción y comprobar que lo demás
queda igual; intentar quitar el módulo Expediente clínico dejando Recetas incluida y comprobar que
se rechaza; bajar el límite de doctores de 3 a 1 y comprobar que se acepta; intentar actualizar una
Eliminada y comprobar que no se encuentra.

**Acceptance Scenarios**:

1. **Given** una suscripción vigente, **When** se actualiza solo su precio anual con un valor
   válido, **Then** cambia solo ese dato, el resto se conserva y se actualiza su fecha de
   modificación.
2. **Given** una suscripción que incluye Expediente clínico, Plantillas de expediente y Recetas,
   **When** se envía una nueva lista de módulos que quita Expediente clínico pero conserva Recetas,
   **Then** se rechaza indicando que Recetas exige Expediente clínico, y no cambia nada.
3. **Given** una suscripción con el límite de doctores en 3, **When** se actualiza a 1, **Then** se
   acepta, sin importar cuántas clínicas con ese plan ya tengan más de 1 doctor.
4. **Given** otra suscripción vigente ya tiene el nombre deseado, **When** se intenta usarlo,
   **Then** se rechaza indicando que el nombre ya está en uso.
5. **Given** la solicitud intenta cambiar el estatus, el identificador, las fechas o el número de
   clínicas, **When** se envía, **Then** se rechaza completa indicando qué campo no está permitido.
6. **Given** una suscripción Eliminada, **When** se intenta actualizar, **Then** se responde que no
   se encuentra.
7. **Given** la solicitud cambia los módulos y la API de usuarios no responde al validarlos,
   **When** se envía, **Then** se rechaza indicando que no se pudo comprobar, y no cambia nada.

---

### User Story 6 - Cambiar el estatus de una suscripción (Priority: P2)

Quien tiene permiso de actualización cambia el estatus de una suscripción entre Activa, Inactiva y
Bloqueada.

**Why this priority**: Es el modo de retirar un plan de la oferta o de suspenderlo sin perder su
historial (precios, módulos y límites).

**Independent Test**: Pasar una suscripción Activa a Inactiva, a Bloqueada y de vuelta a Activa;
pedir el estatus que ya tiene y comprobar que se rechaza; pedir «Eliminada» y comprobar que se
rechaza.

**Acceptance Scenarios**:

1. **Given** una suscripción Activa, **When** se cambia a Inactiva o a Bloqueada, **Then** su
   estatus cambia y conserva el resto de sus datos (precios, módulos, límites).
2. **Given** una suscripción Inactiva o Bloqueada, **When** se cambia a Activa, **Then** vuelve a
   estar Activa.
3. **Given** una suscripción que ya tiene el estatus pedido, **When** se pide ese mismo estatus,
   **Then** se rechaza indicando que ya lo tiene.
4. **Given** se pide «Eliminada» por esta vía, **When** se envía, **Then** se rechaza: eliminar
   tiene su propia operación.
5. **Given** una suscripción con clínicas asignadas, **When** se cambia a Inactiva o a Bloqueada,
   **Then** el cambio se permite.

---

### User Story 7 - Eliminar una suscripción (Priority: P3)

Quien tiene permiso de eliminación da de baja una suscripción. La baja es lógica: la suscripción se
conserva con el estatus Eliminada, deja de aparecer en el catálogo y de poder consultarse, y su
nombre queda libre para otra.

**Why this priority**: Evita que planes descontinuados ensucien el catálogo sin perder su
historial; es menos frecuente que las demás operaciones.

**Independent Test**: Eliminar una suscripción sin clínicas y comprobar que ya no aparece en el
catálogo ni puede consultarse; intentar eliminar una con clínicas asignadas y comprobar que se
rechaza; repetir con el API de clínicas inaccesible y comprobar que también se rechaza.

**Acceptance Scenarios**:

1. **Given** una suscripción vigente sin clínicas, **When** se elimina, **Then** pasa a Eliminada,
   no aparece en el catálogo y su nombre queda libre.
2. **Given** una suscripción Eliminada o inexistente, **When** se intenta eliminar, **Then** se
   responde que no se encuentra.
3. **Given** una suscripción con clínicas asignadas, **When** se intenta eliminar, **Then** se
   rechaza indicando que tiene clínicas asignadas, y no cambia nada.
4. **Given** el API de clínicas no responde, **When** se intenta eliminar una suscripción, **Then**
   se rechaza indicando que no se pudo comprobar si tiene clínicas, y no cambia nada.

---

### Edge Cases

- **El API de usuarios no responde**: ninguna operación se ejecuta; se indica que el servicio no
  está disponible por el momento.
- **El API de clínicas no responde**: el catálogo y el detalle siguen funcionando sin el número de
  clínicas (nunca un cero inventado); eliminar se rechaza por no poder comprobarse.
- **Persona autenticada pero bloqueada o sin roles**: se le niegan todas las operaciones.
- **Dos personas crean a la vez una suscripción con el mismo nombre**: solo una se crea.
- **Dos personas editan a la vez la misma suscripción**: gana el último cambio por campo; los
  campos distintos que cada una cambió se conservan ambos.
- **Nombre con distinta capitalización o con espacios al inicio o al final**: se consideran el
  mismo nombre; se guarda recortado.
- **Precio mensual o anual en cero**: válido (por ejemplo, un plan histórico o de cortesía).
- **Precio mensual o anual negativo, con más de dos decimales o desmesurado**: se rechaza.
- **Precio anual menor, igual o mayor que doce veces el precio mensual**: los tres casos se
  aceptan; esta API no valida la proporción entre ambos precios.
- **Días de prueba en cero**: válido, sin periodo de prueba.
- **Días de prueba negativo o no entero**: se rechaza.
- **Se intenta excluir el módulo Pacientes** (omitiéndolo de la lista o pidiendo quitarlo): no
  tiene efecto, sigue incluido.
- **Se incluye un módulo que exige un prerrequisito no incluido** (por ejemplo, Recetas sin
  Expediente clínico, o Facturación sin Finanzas): se rechaza indicando ambos módulos.
- **Se incluye un identificador de módulo que la API de usuarios no reconoce como módulo de tipo
  Clínica vigente**: se rechaza toda la solicitud.
- **La API de usuarios no responde al validar los módulos de una solicitud de creación o de
  actualización**: se rechaza indicando que no se pudo comprobar; las suscripciones ya existentes
  siguen pudiendo consultarse con los módulos que ya tienen.
- **Un límite de la clínica en cero** (por ejemplo, 0 asistentes): válido.
- **Un límite negativo o no entero**: se rechaza.
- **Se baja un límite por debajo de lo que alguna clínica ya tiene de alta** (por ejemplo, 2
  doctores cuando una clínica con ese plan ya tiene 3): se permite; las consecuencias para esa
  clínica las aplica el sistema que administra las clínicas, no esta API.
- **Identificador mal formado o inexistente**: se responde que no se encuentra o que el dato no es
  válido, nunca un error interno.
- **Datos no reconocidos en la solicitud**: se rechaza toda la solicitud y no se cambia nada.
- **Cuerpo que no es JSON legible**: se rechaza como datos no válidos aunque falte el permiso o la
  persona no se haya identificado (única excepción al orden normal de comprobación).
- **Catálogo vacío**: lista vacía, no error.
- **Catálogo que crece más allá de lo previsto**: ver FR-006; pasar a paginar es un cambio
  incompatible que se versiona.

## Requirements *(mandatory)*

### Functional Requirements

**Control de acceso**

- **FR-001**: Toda operación sobre las suscripciones MUST exigir un token de acceso válido y el
  permiso que le corresponde; solo la documentación publicada de la API queda exenta.
- **FR-002**: El servicio MUST reenviar el token recibido, sin modificarlo, al API de usuarios y
  MUST aceptar su respuesta como única autoridad sobre la identidad y el permiso de la persona;
  MUST NOT verificarlo por sí mismo.
- **FR-003**: Los permisos MUST seguir siendo cuatro: `subscriptions:read` (listar y consultar),
  `subscriptions:write` (crear), `subscriptions:update` (actualizar datos y cambiar estatus) y
  `subscriptions:delete` (eliminar).
- **FR-004**: La comprobación del permiso MUST ocurrir en cada petición, con los datos vigentes del
  API de usuarios, y MUST ocurrir antes de validar los datos de la solicitud o de buscar la
  suscripción.
- **FR-005**: Cuando no pueda decidirse el acceso (sin token, permiso denegado o API de usuarios
  sin respuesta), el servicio MUST rechazar la operación sin ejecutarla, distinguiendo en el
  mensaje entre «debe iniciar sesión», «no tiene permiso» y «servicio no disponible por el
  momento».

**Catálogo y consulta**

- **FR-006**: El servicio MUST devolver en una sola consulta, sin paginar, todas las suscripciones
  que no estén Eliminadas, en un orden determinista (fecha de creación ascendente y, a igualdad,
  identificador ascendente). El catálogo esperado no supera 100 suscripciones y su máximo para
  devolverse completo es 500; superarlo exige paginar, lo que es un cambio incompatible que se
  versiona.
- **FR-007**: Las suscripciones Eliminadas MUST NOT aparecer en el catálogo y MUST tratarse como
  inexistentes en cualquier otra operación (consulta, actualización, cambio de estatus).
- **FR-008**: Cada suscripción, en el catálogo y en su consulta individual, MUST mostrar: su
  identificador; su nombre; su descripción (si tiene); su precio mensual; su precio anual; sus días
  de prueba; si está en autoconsumo; los identificadores de los módulos de clínica que incluye
  (sin su nombre ni su descripción, que se consultan en la API de usuarios); sus cuatro límites de
  la clínica; sus otras funcionalidades; su estatus (identificador y nombre); el número de clínicas
  que la tienen; y sus fechas de creación y de última modificación. **Esta es la corrección central
  de esta especificación**: hoy la API no expone precio anual, días de prueba, autoconsumo, módulos
  estructurados ni límites, y mezcla módulos y límites dentro de una sola lista de texto libre.
- **FR-009**: El número de clínicas MUST obtenerse del API de clínicas en cada lectura y MUST NOT
  guardarse en este servicio; si no está disponible, la suscripción MUST devolverse igual con el
  número marcado como no disponible, nunca como cero.
- **FR-010**: El servicio MUST permitir consultar una suscripción por su identificador con el mismo
  detalle que el catálogo.

**Precio y condiciones comerciales**

- **FR-011**: El precio mensual MUST ser un importe en pesos mexicanos (sin IVA), mayor o igual a
  cero, con hasta dos decimales, y MUST ser obligatorio al crear.
- **FR-012**: El precio anual MUST seguir las mismas reglas que el mensual (pesos mexicanos sin
  IVA, mayor o igual a cero, hasta dos decimales) y MUST ser obligatorio al crear. Es un importe
  independiente: el servicio MUST NOT exigir que guarde ninguna proporción fija con el precio
  mensual. El ahorro o el equivalente mensual que se muestre a quien consulta es un cálculo de
  quien consume la API a partir de ambos precios, no un dato que este servicio calcule o guarde.
- **FR-013**: Los días de prueba MUST ser un entero entre 0 y 3650; 0 significa que el plan no
  tiene periodo de prueba. Si no se envían al crear, MUST tomar el valor 0.
- **FR-014**: El servicio MUST guardar si la suscripción está en autoconsumo (visible y contratable
  por su cuenta desde el portal de MailySoft) como un valor de verdadero o falso. Si no se envía al
  crear, MUST tomar el valor falso. Este servicio solo guarda y expone el valor; que el portal de
  MailySoft lo respete es responsabilidad de ese sistema.

**Módulos incluidos**

- **FR-015**: El catálogo de los módulos de clínica que una suscripción puede incluir MUST NOT
  administrarse en este servicio: es propiedad de la API de usuarios, como módulos de tipo
  «Clínica» (uno de los tipos de módulo que esa API reconoce). Este servicio MUST validar contra la
  API de usuarios que cada módulo que se intente incluir en una suscripción existe, está vigente y
  es de tipo Clínica, identificándolo por el identificador estable que esa API le asigna (no por su
  nombre).
- **FR-016**: Para aplicar las reglas de las FR-017 y FR-018, esta especificación asume un catálogo
  de al menos estos nueve módulos de tipo Clínica dados de alta en la API de usuarios: Pacientes,
  Agenda y citas, Recordatorios, Expediente clínico, Plantillas de expediente, Recetas, Finanzas,
  Reportes y Facturación. Que existan allí, con esos nombres y antes de integrar esta API, es una
  dependencia externa de esta especificación (ver Assumptions).
- **FR-017**: El módulo Pacientes MUST estar siempre incluido en toda suscripción, se envíe o no
  explícitamente en la solicitud; ninguna operación MUST poder excluirlo.
- **FR-018**: Los siguientes módulos MUST exigir que su prerrequisito esté también incluido en la
  misma suscripción: Recordatorios exige Agenda y citas; Plantillas de expediente exige Expediente
  clínico; Recetas exige Expediente clínico; Facturación exige Finanzas. Este servicio MUST aplicar
  esta regla por su cuenta, porque la API de usuarios no modela dependencias entre módulos. Crear o
  actualizar una suscripción con un módulo sin su prerrequisito MUST rechazarse, indicando ambos
  módulos.
- **FR-019**: Al crear una suscripción o al actualizar sus módulos, la solicitud MUST indicar el
  conjunto completo de módulos que tendrá (sustituye al anterior, igual que «otras
  funcionalidades»); un identificador de módulo que la API de usuarios no reconozca como módulo de
  tipo Clínica vigente MUST rechazar toda la solicitud.
- **FR-020**: Si la API de usuarios no responde al validar los módulos de una solicitud de creación
  o de actualización, esa operación MUST rechazarse indicando que no se pudo comprobar; no se
  ejecuta «por si acaso». Las suscripciones ya existentes MUST seguir pudiendo consultarse con los
  módulos que ya tienen.

**Límites de la clínica**

- **FR-021**: Toda suscripción MUST definir cuatro límites de la clínica —consultorios, doctores,
  asistentes y pacientes nuevos al año—, cada uno un entero no negativo; los cuatro MUST ser
  obligatorios al crear.
- **FR-022**: Los límites MUST tratarse como techos informativos de este servicio: no representan
  un conteo de uso real y este servicio MUST NOT validarlos contra las clínicas que ya tiene
  asignadas una suscripción. Bajar un límite en una actualización MUST permitirse siempre, incluso
  por debajo de lo que alguna clínica ya tenga de alta (aplicar esa consecuencia a las clínicas
  existentes es responsabilidad del sistema que las administra, fuera de esta API).
- **FR-023**: Los cuatro límites MUST poder modificarse mediante la operación de actualización,
  individualmente o en conjunto, igual que el resto de los datos generales.

**Otras funcionalidades**

- **FR-024**: Cada suscripción MUST poder describir, además de sus módulos, una lista ordenada de
  hasta 20 funcionalidades en texto libre que no son módulos del sistema (por ejemplo, soporte o
  capacitación); cada texto de 1 a 150 caracteres. Al actualizarla, la solicitud MUST enviar la
  lista completa (sustituye a la anterior); puede enviarse vacía.

**Creación y actualización general**

- **FR-025**: El nombre de una suscripción MUST ser obligatorio (1 a 100 caracteres) y único, sin
  distinguir mayúsculas, entre las suscripciones no eliminadas; el nombre de una Eliminada MUST
  quedar libre. La suscripción MUST nacer con estatus Activa.
- **FR-026**: La operación de actualización MUST permitir modificar, enviando solo lo que cambia:
  nombre, descripción, precio mensual, precio anual, días de prueba, autoconsumo, módulos
  incluidos, los cuatro límites y las otras funcionalidades. MUST NOT permitir cambiar por esta vía
  el identificador, el estatus, las fechas ni el número de clínicas.
- **FR-027**: El servicio MUST permitir cambiar el estatus de una suscripción vigente entre Activa,
  Inactiva y Bloqueada, en cualquier dirección, tenga o no clínicas asignadas. Pedir el estatus que
  ya tiene MUST rechazarse; pedir «Eliminada» por esta vía MUST rechazarse (eliminar tiene su
  propia operación).

**Eliminación**

- **FR-028**: El servicio MUST permitir eliminar una suscripción de forma lógica (pasa a Eliminada,
  se conserva, deja de aparecer en el catálogo, su nombre queda libre). MUST rechazarse si tiene al
  menos una clínica asignada, y también MUST rechazarse si no puede comprobarse porque el API de
  clínicas no responde; en ambos casos no cambia nada.
- **FR-029**: Una suscripción Eliminada MUST NOT poder reactivarse, actualizarse ni cambiar de
  estatus con esta API.

**Calidad de la API**

- **FR-030**: El servicio MUST rechazar toda solicitud que traiga datos no reconocidos (campos mal
  escritos, no permitidos o que pertenecen a otra operación, como el estatus en la creación),
  indicando qué campo no está permitido, sin crear ni modificar nada.
- **FR-031**: Los textos recibidos (nombre, descripción, otras funcionalidades) MUST guardarse sin
  espacios al inicio ni al final.
- **FR-032**: Los mensajes dirigidos a personas MUST estar en español y todos los errores MUST
  tener el mismo formato, que distingue al menos: no autenticado, sin permiso, no se encuentra,
  conflicto (nombre en uso, estatus repetido, suscripción con clínicas, módulo sin su
  prerrequisito), datos no válidos y dependencia no disponible (incluida la API de usuarios al
  validar módulos).
- **FR-033**: Los estatus MUST salir del catálogo de estatus de suscripción (Activa, Inactiva,
  Bloqueada y Eliminada), administrado a mano; quien consuma la API MUST basarse en el
  identificador del estatus, no en su nombre.
- **FR-034**: Cada operación MUST documentar en el contrato publicado de la API el permiso que
  exige y sus respuestas posibles, incluidas las nuevas reglas de módulos y de límites.

### Key Entities

- **Suscripción (plan)**: oferta comercial que se asigna a las clínicas. Tiene nombre único entre
  las vigentes, descripción opcional, precio mensual, precio anual, días de prueba, si está en
  autoconsumo, los identificadores de los módulos de clínica que incluye, sus cuatro límites de la
  clínica (consultorios, doctores, asistentes, pacientes nuevos al año), una lista ordenada de
  otras funcionalidades, un estatus, el número de clínicas (dato ajeno, solo lectura) y fechas de
  creación y de última modificación.
- **Módulo (de clínica)** *(externo, del API de usuarios)*: función del sistema que una suscripción
  puede habilitar para las clínicas que la tienen. Su catálogo (identificador, nombre, descripción)
  es propiedad de la API de usuarios, como módulos de tipo «Clínica»; este servicio no lo
  administra ni lo guarda, solo referencia sus identificadores. Si está siempre incluido (como
  Pacientes) y de qué otro módulo depende son reglas de esta especificación (FR-017 y FR-018), no
  de la API de usuarios.
- **Estatus de suscripción**: catálogo con Activa (disponible y ofrecida), Inactiva (retirada de la
  oferta), Bloqueada (suspendida) y Eliminada (baja lógica, fuera de toda consulta); administrado a
  mano.
- **Persona autenticada y permiso** *(externos, del API de usuarios)*: quien invoca la API y los
  permisos `subscriptions:*` que el API de usuarios le reconoce. Este servicio no los guarda.
- **Clínica** *(externa, del API de clínicas)*: cliente que tiene asignada una suscripción. Este
  servicio solo conoce cuántas tiene cada una.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El catálogo completo (hasta 100 suscripciones) se obtiene en una sola consulta y
  aparece en pantalla en menos de 2 segundos en el 95 % de las consultas en condiciones normales.
- **SC-002**: El 100 % de las operaciones sin token válido, sin permiso o con el API de usuarios
  inaccesible se rechaza sin cambiar ningún dato.
- **SC-003**: Un bloqueo o un cambio de permisos en el API de usuarios surte efecto en la siguiente
  petición de esa persona (0 peticiones posteriores aceptadas por permisos ya revocados).
- **SC-004**: El 100 % de las suscripciones devueltas (en el catálogo o en el detalle) incluye su
  precio mensual, su precio anual, sus días de prueba, su autoconsumo, sus módulos, sus cuatro
  límites, sus otras funcionalidades y su estatus; las Eliminadas no aparecen en ninguna consulta.
- **SC-005**: Con el API de clínicas inaccesible, el 100 % de las consultas del catálogo y del
  detalle sigue devolviendo las suscripciones, sin el número de clínicas.
- **SC-006**: Ante 50 intentos simultáneos de crear una suscripción con el mismo nombre, exactamente
  uno tiene éxito.
- **SC-007**: Quien administra puede crear un plan completo (precios, prueba, autoconsumo, módulos y
  límites) y verlo en el catálogo en menos de 3 minutos, sin conocimientos técnicos.
- **SC-008**: El 100 % de los mensajes de error está en español y sigue el mismo formato.
- **SC-009**: Ninguna suscripción con clínicas asignadas llega a eliminarse, ni siquiera cuando no
  puede comprobarse si las tiene (0 casos).
- **SC-010**: El 100 % de los intentos de guardar un módulo sin su prerrequisito se rechaza; ninguna
  suscripción queda guardada con una combinación de módulos inconsistente (0 casos).
- **SC-011**: El 100 % de las suscripciones del catálogo tiene sus cuatro límites de la clínica
  definidos; ningún sistema que las consuma recibe un plan sin saber hasta dónde puede crecer la
  clínica que lo tiene.

## Assumptions

- **Esta especificación corrige y sustituye el modelo de datos de `001-subscriptions-api`** para
  las mismas cuatro operaciones (crear, actualizar —incluido el cambio de estatus—, eliminar
  lógicamente y listar/consultar). El control de acceso, el reenvío del token, el CORS y las demás
  reglas de seguridad ya validadas en esa especificación siguen vigentes sin cambios y no se repiten
  aquí en detalle.
- **Alcance excluido explícitamente**: la pantalla «Registrar clínica» del mockup (alta de una
  clínica, su propietario/administrador y la asignación de una suscripción) no es parte de esta
  API, por instrucción del responsable del proyecto; esa pantalla solo consume el listado de
  suscripciones que esta especificación ya cubre.
- **Catálogo de módulos, en la API de usuarios**: a la fecha de esta especificación (2026-10-23),
  esa API tiene en desarrollo (feature `013-modules-permissions-catalogs` de
  `mailySoft-usuarios`, **todavía sin comprometer a control de versiones**, no desplegada) un
  recurso de módulos con tipos administrados a mano («Sistema» y «Clínica»), identificados por
  `id`/`key`, con operaciones de listar, crear, consultar, actualizar, bloquear/desbloquear y
  eliminar. Es una **dependencia externa que esta especificación da por hecha, no por garantizada**:
  antes de integrar, esa feature debe quedar terminada, comprometida y desplegada, y alguien debe
  dar de alta en ella, con `type_id` de Clínica, los nueve módulos que exige la FR-016 (hoy esa API
  no tiene sembrado ninguno; solo cuatro módulos de tipo Sistema protegidos: `users`, `roles`,
  `permissions`, `modules`). El contrato de referencia es
  `specs/013-modules-permissions-catalogs/contracts/openapi-modules.yaml` de ese repositorio
  (`GET /api/v1/modules`, permiso `modules:read`, con filtro `type_id`); su DTO de módulo no incluye
  dependencias ni un «siempre incluido», por lo que esas dos reglas (FR-017, FR-018) las valida esta
  API de Suscripciones, no la de usuarios.
- **Límites sin tope superior fijado por el mockup**: se asume un máximo técnico razonable
  (1,000,000) para evitar valores absurdos; el mockup no lo especifica. Tampoco se exige un mínimo
  mayor que cero: un plan podría, por ejemplo, definir 0 asistentes.
- **Días de prueba sin tope fijado por el mockup**: se asume un máximo técnico razonable (3650 días)
  por la misma razón.
- **«Otras funcionalidades» hasta 150 caracteres por elemento**: el mockup fija el máximo de 20
  elementos, pero no un máximo de caracteres por elemento; se conserva el límite de 150 ya usado
  por este mismo campo en `001-subscriptions-api` (ahí se llamaba «lo que incluye»).
- **Planes de ejemplo**: Esencial, Profesional, Avanzado y Empresarial (con los precios, módulos y
  límites del mockup) ilustran la información que debe poder guardar la API; no son datos
  iniciales obligatorios. El catálogo no necesita sembrarse con ellos; si se necesitan cargados de
  origen, se pedirá en una especificación aparte.
- **Datos existentes**: se asume que el catálogo de suscripciones aún no tiene información real en
  producción con el modelo de `001-subscriptions-api` que deba migrarse; si ya existiera, el plan
  de migración de esos datos se definirá en la fase de planificación (`/speckit-plan`), no en esta
  especificación.
- **Consecuencias sobre clínicas existentes**: qué pasa con una clínica que ya supera un límite que
  se bajó, o que ya usa un módulo que se quitó del plan, lo decide y lo aplica el sistema que
  administra las clínicas, no esta API; mismo criterio que ya usa `001-subscriptions-api` para las
  consecuencias de Inactiva o Bloqueada.
- **Moneda e impuestos**: los precios (mensual y anual) son en pesos mexicanos y no incluyen IVA
  («Precios simulados en pesos mexicanos, antes de IVA», según el mockup); calcular o mostrar el
  IVA es responsabilidad de quien consume la API.
