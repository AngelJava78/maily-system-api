# Feature Specification: Tipo de suscripción (Individual o Empresarial)

**Feature Branch**: `006-add-subscription-type`

**Created**: 2026-10-26

**Status**: Draft

**Input**: User description: "Agregar a las suscripciones el tipo de suscripción (Individual o
Empresarial), que indica a quién va dirigida: Individual para médicos independientes (su
consultorio está asociado, sin que el médico lo sepa, a una clínica) y Empresarial para empresas
con varias clínicas y varios consultorios por clínica. El tipo es obligatorio al crear, se muestra
en la consulta y en el listado, y es inmutable (no puede cambiarse al actualizar). Una suscripción
Individual solo puede tener una clínica asociada; una Empresarial puede tener varias. Las
suscripciones que ya existen deben quedar como Individual, salvo las que ya tengan más de una
clínica asociada, que deben quedar como Empresarial. Quedan fuera de esta spec: cambios al nombre,
los módulos, los límites o las características ya existentes; la creación automática de la clínica
oculta para las suscripciones Individual; y el cambio de tipo de una suscripción."

## Clarifications

### Session 2026-10-26

- Q: Además del listado y de la consulta por identificador —que ya incluyen el tipo de
  suscripción—, ¿necesita el sistema que administra las clínicas algún contrato nuevo de esta API
  para aplicar el límite de una sola clínica en las suscripciones Individual? → A: No; el listado y
  la consulta por identificador (que ya exponen el tipo) son el único contrato que esta API ofrece
  para eso; no se agrega ningún endpoint ni operación nueva.
- Q: Si al asignar el tipo a las suscripciones existentes el sistema de clínicas no responde y no
  puede confirmarse el conteo de alguna, ¿el despliegue debe seguir reintentando sin límite, o debe
  asignar un tipo por defecto tras un número acotado de intentos y marcar esa suscripción para
  revisión manual? → A: Reintentar sin límite; el despliegue no se completa hasta confirmar el
  conteo real de cada suscripción, nunca se adivina un tipo.
- Q: ¿El tipo de suscripción debe administrarse como un catálogo propio (una tabla con `id` y
  `name`, igual que el estatus de la suscripción), al que se le puedan agregar tipos nuevos más
  adelante sin tocar código, o debe quedar fijo a los dos valores de hoy? → A: Catálogo propio,
  igual que el estatus (`subscription_statuses`): administrado a mano, ampliable insertando una
  fila nueva, sin necesidad de una migración que reescriba una restricción. Hoy solo tiene
  Individual y Empresarial, pero el mecanismo no los da por cerrados para siempre.

## User Scenarios & Testing *(mandatory)*

Los actores son **quien administra los planes de MailySoft** (crea y actualiza suscripciones desde
el Backoffice) y **los sistemas consumidores**, incluido el sistema que administra las clínicas:
ese sistema es quien de verdad asocia una clínica a una suscripción, y usa el tipo que esta API
expone para decidir si una suscripción Individual ya tiene su única clínica. Esa asociación en sí
no es una operación de esta API (ver Assumptions).

### User Story 1 - Crear una suscripción indicando su tipo (Priority: P1)

Quien tiene permiso de escritura, al crear una suscripción, indica si es Individual (para un médico
independiente) o Empresarial (para una empresa con varias clínicas). Sin un tipo válido, la
suscripción no se crea.

**Why this priority**: Es el cambio central de esta especificación: sin el tipo obligatorio desde
el origen, ninguna de las demás reglas (inmutabilidad, límite de clínicas, migración) tiene algo
sobre lo que apoyarse.

**Independent Test**: Crear una suscripción con tipo Individual y otra con tipo Empresarial y
comprobar que ambas se guardan con su tipo; intentar crear una sin el campo de tipo y comprobar que
se rechaza; intentar crear una con un valor que no sea Individual ni Empresarial (vacío, mal
escrito, otro idioma) y comprobar que también se rechaza.

**Acceptance Scenarios**:

1. **Given** una persona con permiso de escritura y datos válidos con tipo Individual, **When**
   crea la suscripción, **Then** se crea con tipo Individual y así aparece en la respuesta.
2. **Given** los mismos datos válidos pero con tipo Empresarial, **When** se crea, **Then** se crea
   con tipo Empresarial.
3. **Given** una solicitud de creación que no incluye el campo de tipo, **When** se envía, **Then**
   se rechaza indicando que el tipo es obligatorio, y no se crea nada.
4. **Given** una solicitud de creación cuyo tipo no es exactamente Individual ni Empresarial,
   **When** se envía, **Then** se rechaza indicando que el tipo no es válido, y no se crea nada.

---

### User Story 2 - Ver el tipo al consultar una suscripción (Priority: P1)

Quien tiene permiso de lectura ve el tipo de cada suscripción tanto al consultar el catálogo
completo como al consultar una suscripción por su identificador.

**Why this priority**: Sin ver el tipo en la respuesta, ni quien administra los planes ni los
sistemas que consumen el catálogo (incluido el que administra las clínicas) pueden distinguir una
suscripción Individual de una Empresarial ni decidir nada a partir de eso.

**Independent Test**: Con suscripciones de ambos tipos ya creadas, consultar el catálogo completo y
comprobar que cada una muestra su tipo; consultar una Individual y una Empresarial por su
identificador y comprobar que cada una trae el tipo correcto.

**Acceptance Scenarios**:

1. **Given** hay suscripciones Individual y Empresarial vigentes, **When** se consulta el catálogo
   completo, **Then** cada una muestra su propio tipo, sin mezclarse.
2. **Given** una suscripción Individual, **When** se consulta por su identificador, **Then** su
   tipo es Individual.
3. **Given** una suscripción Empresarial, **When** se consulta por su identificador, **Then** su
   tipo es Empresarial.

---

### User Story 3 - El tipo queda fijo después de creada (Priority: P2)

Quien tiene permiso de actualización sigue pudiendo cambiar el nombre, los precios, los módulos,
los límites y las demás funcionalidades de una suscripción, pero no puede cambiar su tipo. Cualquier
solicitud de actualización que lo incluya se rechaza por completo, cambie o no el valor.

**Why this priority**: El tipo acota cuántas clínicas puede tener una suscripción; permitir
cambiarlo después de creada abriría la puerta a dejar una suscripción con más clínicas de las que
su tipo permite, o a reglas inconsistentes entre esta API y el sistema que administra las clínicas.

**Independent Test**: Actualizar una suscripción enviando su tipo (igual o distinto al que ya tiene)
junto con otro campo válido, y comprobar que toda la solicitud se rechaza y nada cambia; actualizar
la misma suscripción sin incluir el tipo y comprobar que los demás campos cambian con normalidad.

**Acceptance Scenarios**:

1. **Given** una suscripción Individual, **When** se envía una actualización que intenta cambiar su
   tipo a Empresarial, **Then** se rechaza indicando que el tipo no puede modificarse, y no cambia
   ningún dato.
2. **Given** una suscripción Individual, **When** se envía una actualización que repite el mismo
   tipo (Individual) junto con, por ejemplo, un nuevo precio, **Then** también se rechaza por
   completo, incluido el precio: el tipo no es un campo que la actualización admita, con ningún
   valor.
3. **Given** una suscripción vigente de cualquier tipo, **When** se actualiza cualquier otro dato
   sin incluir el tipo en la solicitud, **Then** se actualiza con normalidad y su tipo permanece
   igual.

---

### Edge Cases

- Se crea una suscripción sin el campo de tipo: se rechaza indicando que es obligatorio.
- Se crea una suscripción con un valor de tipo que no es exactamente Individual ni Empresarial
  (vacío, mal escrito, en otro idioma, un número): se rechaza indicando que no es válido.
- Se intenta actualizar una suscripción enviando el tipo, aunque sea con el mismo valor que ya
  tiene: se rechaza toda la solicitud, sin cambiar ningún dato.
- Se intenta actualizar una suscripción enviando el tipo junto con otros campos válidos: se rechaza
  toda la solicitud, incluidos esos otros campos.
- Una suscripción Empresarial sin ninguna clínica asociada, o con varias: ambos casos son válidos;
  Empresarial no exige un mínimo.
- El sistema que administra las clínicas intenta asociar una segunda clínica a una suscripción
  Individual: esta API no participa en esa operación (no la tiene); el rechazo lo aplica ese otro
  sistema a partir del tipo que esta API le expone.
- Al asignar el tipo a las suscripciones que ya existen, no puede confirmarse cuántas clínicas tiene
  alguna de ellas (el sistema que las administra no responde en ese momento): no se le asigna un
  tipo adivinado; se reintenta hasta confirmar el conteo real antes de dar por terminada la
  asignación.
- Una suscripción que ya existía tenía, antes de esta funcionalidad, más de una clínica asociada:
  queda como Empresarial.
- Una suscripción que ya existía tenía, antes de esta funcionalidad, como máximo una clínica (o
  ninguna): queda como Individual.
- Se elimina (baja lógica) una suscripción, sea Individual o Empresarial: siguen aplicando las
  reglas ya vigentes (se rechaza si tiene clínicas asignadas o si no puede comprobarse); el tipo no
  cambia esa regla.

## Requirements *(mandatory)*

### Functional Requirements

**Tipo de suscripción**

- **FR-001**: Toda suscripción, nueva o ya existente, MUST tener siempre asignado un tipo; ninguna
  MUST quedar sin tipo en ningún momento. El tipo MUST salir de un catálogo administrado a mano,
  igual que el estatus de la suscripción (Clarifications 2026-10-26): hoy ese catálogo tiene
  exactamente dos valores, Individual y Empresarial, pero agregar uno nuevo en el futuro MUST
  poder hacerse insertando una fila en el catálogo, sin exigir una migración que reescriba una
  restricción fija ni un cambio de código. Esta especificación MUST NOT agregar a esta API ninguna
  operación propia para administrar el catálogo (igual que el estatus, se administra por fuera de
  las operaciones normales de la API).
- **FR-002**: Al crear una suscripción, el tipo MUST ser obligatorio. La solicitud MUST rechazarse
  por completo, sin crear nada, si el campo no se envía o si su valor no corresponde a uno de los
  tipos del catálogo vigente (hoy, Individual o Empresarial).
- **FR-003**: El tipo MUST mostrarse en la respuesta de toda suscripción, tanto en el listado
  completo como en la consulta por identificador, igual que sus demás datos.
- **FR-004**: Una vez creada una suscripción, su tipo MUST ser inmutable: ninguna operación de esta
  API MUST permitir cambiarlo. Toda solicitud de actualización que incluya el campo de tipo —con el
  mismo valor que ya tiene o con uno distinto— MUST rechazarse por completo, incluidos los demás
  campos que traiga esa misma solicitud, indicando que el tipo no puede modificarse; en ese caso no
  MUST cambiar ningún dato de la suscripción.
- **FR-005**: La operación de eliminación (baja lógica) y sus reglas ya vigentes (se rechaza si la
  suscripción tiene clínicas asignadas o si no puede comprobarse) MUST seguir aplicándose igual,
  sin que el tipo de la suscripción las modifique.

**Relación entre el tipo y las clínicas asociadas**

- **FR-006**: El tipo MUST acotar, como regla de negocio, cuántas clínicas puede tener asociadas
  una suscripción: como máximo una si es Individual; cualquier cantidad, incluida ninguna, si es
  Empresarial. Esta regla es propia de estos dos tipos; si en el futuro se agrega un tercero al
  catálogo (FR-001), su propia regla de clínicas no queda definida por esta especificación.
- **FR-007**: Esta API MUST NOT almacenar ni administrar por sí misma la asociación entre una
  clínica y una suscripción (no cambia respecto a lo ya vigente). Esa asociación la ejecuta el
  sistema que administra las clínicas, que MUST apoyarse en el tipo que esta API expone en el
  listado y en la consulta por identificador (FR-003) para decidir si corresponde rechazar una
  segunda clínica para una suscripción Individual. Esta especificación MUST NOT agregar a esta API
  ninguna operación nueva —ni un endpoint dedicado— para asociar, desasociar o comprobar la
  elegibilidad de una clínica: lo ya expuesto en esas dos lecturas es, por decisión confirmada, el
  único contrato que esta API ofrece para ese fin (ver Clarifications).

**Datos existentes**

- **FR-008**: Al desplegar esta funcionalidad, toda suscripción que ya exista en la base de datos
  MUST recibir un tipo: Individual, salvo lo que indica la FR-009.
- **FR-009**: Si, en el momento de asignar el tipo a una suscripción existente, el sistema que
  administra las clínicas indica que esa suscripción tiene más de una clínica asociada, esa
  suscripción MUST quedar con el tipo Empresarial en lugar de Individual.
- **FR-010**: Si no puede confirmarse cuántas clínicas tiene asociada una suscripción existente en
  el momento de asignarle el tipo, esa suscripción MUST NOT recibir un tipo adivinado; la
  asignación MUST reintentarse sin límite de intentos hasta poder confirmarse con el conteo real,
  antes de dar por terminada la puesta en marcha de esta funcionalidad, aunque eso retrase el
  despliegue (decisión confirmada, ver Clarifications).

**Calidad de la API**

- **FR-011**: Los mensajes de rechazo relacionados con el tipo (falta, valor no reconocido, intento
  de modificarlo) MUST estar en español y MUST seguir el mismo formato de error que ya usa el resto
  de la API.
- **FR-012**: El contrato publicado de la API MUST documentar el tipo como un dato obligatorio al
  crear y presente en toda lectura, y MUST documentar explícitamente que no forma parte de los
  datos que la operación de actualización admite.

### Key Entities

- **Suscripción (plan)**: entidad ya existente (nombre, descripción, precios, días de prueba,
  autoconsumo, módulos, límites, otras funcionalidades, estatus, número de clínicas y fechas, sin
  cambios en esta especificación). Se le agrega el tipo: Individual o Empresarial, obligatorio
  desde la creación y fijo para siempre.
- **Tipo de suscripción**: indica a quién va dirigida la suscripción. Es un catálogo administrado a
  mano y ampliable, igual que el estatus de la suscripción (Clarifications 2026-10-26): hoy tiene
  exactamente dos valores, pero se pueden agregar más adelante sin tocar código. Individual: para
  un médico independiente; internamente su consultorio se asocia a una sola clínica, de cuya
  existencia el médico no es consciente. Empresarial: para una empresa con varias clínicas y varios
  consultorios por clínica. Una vez asignado a una suscripción, el tipo no vuelve a cambiar (eso no
  depende de si el catálogo es ampliable o no).
- **Clínica** *(externa, del sistema que administra las clínicas; sin cambios de esta
  especificación)*: cliente que tiene asignada una suscripción. El tipo de la suscripción acota
  cuántas puede tener (una si es Individual, cualquier cantidad si es Empresarial), pero la
  asociación en sí sigue siendo propiedad de ese sistema, no de esta API.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los intentos de crear una suscripción sin un tipo válido (Individual o
  Empresarial) se rechaza; ninguna suscripción nueva queda guardada sin tipo (0 casos).
- **SC-002**: El 100% de las suscripciones devueltas, tanto en el listado completo como en la
  consulta por identificador, incluye su tipo.
- **SC-003**: El 100% de los intentos de modificar el tipo de una suscripción ya creada se rechaza
  sin cambiar ningún otro dato de esa solicitud; ninguna suscripción cambia de tipo después de
  creada (0 casos).
- **SC-004**: Al terminar de desplegar esta funcionalidad, el 100% de las suscripciones que ya
  existían tiene un tipo asignado conforme a la regla de migración (Individual, o Empresarial si ya
  tenía más de una clínica asociada); 0 suscripciones quedan sin tipo.
- **SC-005**: El sistema que administra las clínicas puede conocer el tipo de cualquier suscripción
  consultando únicamente esta API, sin pasos ni cálculos adicionales de su parte.
- **SC-006**: Quien administra los planes crea una suscripción nueva, incluido su tipo, en el mismo
  tiempo que hoy le toma crear una suscripción, sin pasos perceptibles adicionales ni conocimientos
  técnicos.

## Assumptions

- Esta especificación amplía el modelo ya vigente de `004-correct-subscriptions-api`: el control de
  acceso, el formato de error, la unicidad del nombre, los módulos, los límites y las demás reglas
  ya validadas siguen igual y no se repiten aquí; el tipo se agrega sin tocarlas.
- El tipo de suscripción es un catálogo administrado a mano y ampliable, igual que el estatus de la
  suscripción (`subscription_statuses`): confirmado en Clarifications (2026-10-26). Hoy tiene
  exactamente dos valores (Individual y Empresarial); agregar un tercero en el futuro es insertar
  una fila nueva en ese catálogo, no una migración que reescriba una restricción fija. Esta
  especificación no define ese tercer valor ni sus reglas propias (por ejemplo, cuántas clínicas
  podría tener): solo que el mecanismo para agregarlo, cuando haga falta, no exige cambiar código.
- Esta API no almacena ni administra la asociación entre clínicas y suscripciones; eso ya era así
  antes de esta especificación (el número de clínicas lo aporta, de solo lectura, el sistema que las
  administra). Por eso, el rechazo de una segunda clínica para una suscripción Individual lo aplica
  ese otro sistema, consultando el tipo que esta API ya expone en el listado y en la consulta por
  identificador; no se necesita ningún contrato nuevo de esta API para eso (confirmado con el
  responsable del proyecto, sesión de aclaraciones del 2026-10-26). Esta especificación no agrega
  una operación de "asociar clínica" ni ningún endpoint dedicado a esta API.
- La creación automática de la "clínica oculta" de una suscripción Individual (mencionada solo como
  contexto de por qué el médico no es consciente de su clínica) la ejecuta ese otro sistema y queda
  fuera de esta especificación, por instrucción explícita.
- El cambio de tipo de una suscripción ya creada queda fuera de alcance. Si en el futuro se necesita
  (por ejemplo, una Individual que crece a Empresarial), se define en una especificación aparte, que
  podría necesitar un proceso distinto de una simple actualización.
- La asignación de tipo a las suscripciones existentes ocurre una sola vez, al desplegar esta
  funcionalidad, usando el conteo de clínicas vigente en ese momento; no se vuelve a recalcular
  después, igual que para las suscripciones nuevas.
- Las suscripciones ya existentes que estén en estatus Eliminada también reciben un tipo al
  desplegar esta funcionalidad (para que ninguna fila quede sin tipo), siguiendo la misma regla de
  conteo de clínicas; al estar eliminadas, esto no tiene ningún efecto operativo visible.
