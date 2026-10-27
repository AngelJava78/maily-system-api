# Feature Specification: Límite de clínicas por suscripción

**Feature Branch**: `007-add-clinics-limit`

**Created**: 2026-10-26

**Status**: Draft

**Input**: User description: "Quiero agregar un limite de clínicas a las suscripciones. Similar al
campo: consulting_rooms_limit. Hay una sola regla: Si subscription_type_id == "Individual",
entonces el límite de clínicas es igual a 1 y no se puede cambiar. Si subscription_type_id !=
"Individual", entonces el límite de clínicas es mayor que 0 y menor o igual a 100."

## User Scenarios & Testing *(mandatory)*

Los actores son **quien administra los planes de MailySoft** (crea y actualiza suscripciones desde
el Backoffice) y **quienes consumen el catálogo de suscripciones**, incluido el sistema que
administra las clínicas, que ya usa el tipo de cada suscripción (Individual o Empresarial) para
decidir cuántas clínicas puede tener asociadas.

### User Story 1 - Crear una suscripción con el límite de clínicas correcto para su tipo (Priority: P1)

Quien tiene permiso de escritura, al crear una suscripción, indica su límite de clínicas. Si el
tipo elegido es Individual, el único valor aceptado es 1; si es cualquier otro tipo (hoy,
Empresarial), el valor debe estar entre 1 y 100. Fuera de esas reglas, la suscripción no se crea.

**Why this priority**: Es la regla central de esta especificación: sin ella aplicada desde la
creación, no hay nada que proteger después con la inmutabilidad de la Historia 3.

**Independent Test**: Crear una suscripción Individual con límite de clínicas 1 y comprobar que se
guarda; intentar crear una Individual con un límite distinto de 1 (0, 2, 100) y comprobar que se
rechaza; crear una Empresarial con un límite dentro de 1 a 100 y comprobar que se guarda; intentar
crear una Empresarial con un límite fuera de ese rango (0, 101, negativo) y comprobar que se
rechaza; intentar crear cualquier suscripción sin enviar el límite y comprobar que se rechaza.

**Acceptance Scenarios**:

1. **Given** una persona con permiso de escritura y datos válidos con tipo Individual y límite de
   clínicas 1, **When** crea la suscripción, **Then** se crea con límite de clínicas 1.
2. **Given** los mismos datos pero con tipo Individual y límite de clínicas distinto de 1, **When**
   se envía, **Then** se rechaza indicando que el límite no es válido para ese tipo, y no se crea
   nada.
3. **Given** datos válidos con tipo Empresarial y límite de clínicas dentro de 1 a 100 (por ejemplo,
   25), **When** crea la suscripción, **Then** se crea con ese límite.
4. **Given** los mismos datos pero con tipo Empresarial y límite de clínicas fuera de 1 a 100 (por
   ejemplo, 0 o 101), **When** se envía, **Then** se rechaza indicando que el límite no es válido
   para ese tipo, y no se crea nada.
5. **Given** una solicitud de creación que no incluye el límite de clínicas, **When** se envía,
   **Then** se rechaza indicando que es obligatorio, y no se crea nada.

---

### User Story 2 - Ver el límite de clínicas al consultar una suscripción (Priority: P1)

Quien tiene permiso de lectura ve el límite de clínicas de cada suscripción tanto al consultar el
catálogo completo como al consultar una suscripción por su identificador, igual que los otros
cuatro límites ya existentes (consultorios, doctores, asistentes y pacientes nuevos al año).

**Why this priority**: Sin verlo expuesto, ni quien administra los planes ni los sistemas que
consumen el catálogo (incluido el que administra las clínicas) pueden conocer ni usar ese techo.

**Independent Test**: Con una suscripción Individual y una Empresarial ya creadas, consultar el
catálogo completo y comprobar que cada una muestra su propio límite de clínicas; consultar cada una
por su identificador y comprobar lo mismo.

**Acceptance Scenarios**:

1. **Given** hay suscripciones vigentes de ambos tipos, **When** se consulta el catálogo completo,
   **Then** cada una muestra su propio límite de clínicas.
2. **Given** una suscripción cualquiera, **When** se consulta por su identificador, **Then** su
   límite de clínicas aparece junto con los otros cuatro límites.

---

### User Story 3 - El límite de clínicas se comporta según el tipo al actualizar (Priority: P2)

Quien tiene permiso de actualización puede ajustar el límite de clínicas de una suscripción
Empresarial (o de cualquier tipo que no sea Individual) a cualquier valor entre 1 y 100, igual que
ya puede ajustar los otros cuatro límites. En cambio, si la suscripción es Individual, el límite de
clínicas queda fijo en 1 para siempre: cualquier intento de modificarlo, cambie o no el valor, se
rechaza por completo, igual que ya ocurre con el tipo de la suscripción.

**Why this priority**: El límite de clínicas de una suscripción Individual sostiene la regla ya
vigente de que ese tipo representa a una sola persona con una sola clínica asociada; permitir
cambiarlo rompería esa regla. Las Empresariales, en cambio, necesitan poder crecer o reducir su
techo de clínicas con el tiempo.

**Independent Test**: Actualizar una suscripción Individual enviando su límite de clínicas (igual o
distinto al que ya tiene) junto con otro campo válido, y comprobar que toda la solicitud se rechaza
y nada cambia; actualizar la misma suscripción sin incluir el límite y comprobar que los demás
campos cambian con normalidad; actualizar una suscripción Empresarial con un nuevo límite dentro de
1 a 100 y comprobar que se guarda; intentar lo mismo con un valor fuera de ese rango y comprobar que
se rechaza.

**Acceptance Scenarios**:

1. **Given** una suscripción Individual (límite de clínicas 1), **When** se envía una actualización
   que intenta cambiar su límite de clínicas a otro valor, **Then** se rechaza indicando que no
   puede modificarse, y no cambia ningún dato.
2. **Given** una suscripción Individual, **When** se envía una actualización que repite el mismo
   límite (1) junto con, por ejemplo, un nuevo precio, **Then** también se rechaza por completo,
   incluido el precio.
3. **Given** una suscripción Empresarial con límite de clínicas 10, **When** se envía una
   actualización que lo cambia a 50, **Then** se guarda el nuevo límite.
4. **Given** una suscripción Empresarial, **When** se envía una actualización que lleva su límite
   fuera de 1 a 100, **Then** se rechaza indicando que el valor no es válido.
5. **Given** una suscripción vigente de cualquier tipo, **When** se actualiza cualquier otro dato
   sin incluir el límite de clínicas, **Then** se actualiza con normalidad y su límite permanece
   igual.

---

### Edge Cases

- Se crea una suscripción sin el campo del límite de clínicas: se rechaza indicando que es
  obligatorio, igual que los otros cuatro límites.
- Se crea una suscripción Individual con límite de clínicas no entero, negativo, cero o mayor que 1:
  se rechaza en todos los casos (el único valor aceptado para Individual es 1).
- Se crea una suscripción no Individual con límite de clínicas igual a los límites del rango (1 o
  100): se acepta en ambos casos (son los bordes válidos).
- Se crea una suscripción no Individual con límite de clínicas igual a 0 o igual a 101: se rechaza
  en ambos casos (son los bordes inválidos).
- Se intenta actualizar una suscripción Individual enviando su límite de clínicas, aunque sea con el
  valor que ya tiene (1): se rechaza toda la solicitud, sin cambiar ningún dato.
- Se intenta actualizar una suscripción Individual enviando su límite de clínicas junto con otros
  campos válidos: se rechaza toda la solicitud, incluidos esos otros campos.
- Se intenta actualizar una suscripción no Individual con un límite de clínicas fuera de 1 a 100: se
  rechaza esa solicitud, sin cambiar el límite ya guardado.
- Una suscripción no Individual tiene hoy, según el sistema que administra las clínicas, más
  clínicas asociadas que su límite de clínicas (o menos): ambos casos son válidos para esta API, que
  no compara el límite contra el uso real (ver Assumptions e igual que ya ocurre con los otros
  cuatro límites, 004 FR-022).
- Se agrega en el futuro un tercer tipo al catálogo de tipos de suscripción (006): mientras esa
  especificación futura no diga lo contrario, ese tipo nuevo cae en la regla de "no Individual" (1 a
  100, modificable), igual que Empresarial.

## Requirements *(mandatory)*

### Functional Requirements

**Límite de clínicas**

- **FR-001**: Toda suscripción, nueva o ya existente, MUST tener siempre un límite de clínicas: un
  entero obligatorio al crearse, igual que los otros cuatro límites de la clínica (consultorios,
  doctores, asistentes y pacientes nuevos al año) ya vigentes.
- **FR-002**: Si el tipo de la suscripción es Individual, su límite de clínicas MUST ser exactamente
  1. Toda solicitud de creación de una suscripción Individual cuyo límite de clínicas no sea 1 MUST
  rechazarse por completo, sin crear nada.
- **FR-003**: Si el tipo de la suscripción no es Individual (hoy, Empresarial; cualquier tipo que se
  agregue más adelante al catálogo de tipos), su límite de clínicas MUST ser un entero mayor que 0 y
  menor o igual a 100. Toda solicitud de creación fuera de ese rango MUST rechazarse por completo,
  sin crear nada.
- **FR-004**: El límite de clínicas MUST mostrarse en la respuesta de toda suscripción, tanto en el
  listado completo como en la consulta por identificador, igual que los otros cuatro límites.
- **FR-005**: Una vez creada una suscripción de tipo Individual, su límite de clínicas MUST quedar
  fijo en 1 para siempre: ninguna operación de actualización MUST permitir cambiarlo. Toda solicitud
  de actualización sobre una suscripción Individual que incluya el campo del límite de clínicas —con
  el mismo valor que ya tiene o con uno distinto— MUST rechazarse por completo, incluidos los demás
  campos que traiga esa misma solicitud, indicando que el límite no puede modificarse; en ese caso no
  MUST cambiar ningún dato de la suscripción.
- **FR-006**: En una suscripción que no sea Individual, el límite de clínicas MUST poder modificarse
  mediante la operación de actualización, individualmente o junto con otros campos, siempre a un
  entero mayor que 0 y menor o igual a 100; un valor fuera de ese rango MUST rechazarse indicando el
  error.
- **FR-007**: Al desplegar esta funcionalidad, toda suscripción que ya exista en la base de datos
  MUST recibir un límite de clínicas válido para su propio tipo (1 si es Individual; un valor entre
  1 y 100 si no lo es). Ninguna fila MUST quedar sin límite de clínicas.
- **FR-008**: Los mensajes de rechazo relacionados con el límite de clínicas (falta, fuera de rango
  para su tipo, intento de modificarlo en una suscripción Individual) MUST estar en español y MUST
  seguir el mismo formato de error que ya usa el resto de la API.
- **FR-009**: El contrato publicado de la API MUST documentar el límite de clínicas, su rango según
  el tipo de la suscripción, y que es inmutable específicamente en las suscripciones de tipo
  Individual.
- **FR-010**: El límite de clínicas MUST tratarse como un techo informativo de este servicio, igual
  que los otros cuatro límites: no representa un conteo real de clínicas y este servicio MUST NOT
  validarlo contra las clínicas que ya tenga asociadas una suscripción; esa responsabilidad, si
  aplica, sigue siendo del sistema que administra las clínicas.

### Key Entities

- **Suscripción (plan)**: entidad ya existente (nombre, descripción, tipo, precios, días de prueba,
  autoconsumo, módulos, límites, otras funcionalidades, estatus, número de clínicas y fechas, sin
  cambios en esta especificación salvo lo indicado aquí). Se le agrega el límite de clínicas: un
  quinto techo informativo, junto a los de consultorios, doctores, asistentes y pacientes nuevos al
  año, cuyo rango permitido depende de su tipo: exactamente 1 y fijo para siempre si es Individual;
  de 1 a 100 y modificable si no lo es.
- **Tipo de suscripción**: catálogo ya existente (006), fijo para siempre una vez asignado a una
  suscripción. Esta especificación no le agrega ni le quita valores: solo lee el tipo vigente de
  cada suscripción para decidir qué regla de límite de clínicas le aplica.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los intentos de crear una suscripción Individual con un límite de clínicas
  distinto de 1 se rechaza; ninguna suscripción Individual queda guardada con un límite distinto de
  1 (0 casos).
- **SC-002**: El 100% de los intentos de crear una suscripción no Individual con un límite de
  clínicas fuera de 1 a 100 se rechaza; ninguna suscripción no Individual queda guardada con un
  límite fuera de ese rango (0 casos).
- **SC-003**: El 100% de las suscripciones devueltas, en el listado completo y en la consulta por
  identificador, incluye su límite de clínicas.
- **SC-004**: El 100% de los intentos de modificar el límite de clínicas de una suscripción
  Individual se rechaza sin cambiar ningún otro dato de esa solicitud; ninguna suscripción Individual
  cambia su límite después de creada (0 casos).
- **SC-005**: El 100% de las suscripciones no Individuales puede ajustar su límite de clínicas
  dentro de 1 a 100 mediante la operación de actualización ya existente, sin pasos adicionales.
- **SC-006**: Al terminar de desplegar esta funcionalidad, el 100% de las suscripciones que ya
  existían tiene un límite de clínicas válido para su propio tipo; 0 quedan sin límite o con un valor
  fuera de rango.

## Assumptions

- Esta especificación amplía el modelo ya vigente de `004-correct-subscriptions-api` (los otros
  cuatro límites) y de `006-add-subscription-type` (el tipo de suscripción, ya fijo para siempre);
  no repite ni modifica sus reglas salvo lo indicado aquí.
- El límite de clínicas es, igual que los otros cuatro, un techo informativo: este servicio no lo
  valida contra las clínicas reales que tenga asociadas una suscripción. Esa comprobación, si
  aplica, sigue siendo responsabilidad del sistema que administra las clínicas, igual que 006 ya
  estableció para el máximo de una clínica en las suscripciones Individual.
- El límite de clínicas es distinto del número de clínicas (`clinics_count`) ya existente: ese es un
  dato de solo lectura que aporta el API de clínicas en cada consulta (cuántas clínicas usan hoy esa
  suscripción); el límite de clínicas de esta especificación es un techo que esta API guarda y
  expone, sin relación de validación entre ambos.
- "No Individual" incluye hoy solo a Empresarial, pero la regla de 1 a 100 (modificable) se aplica
  por igual a cualquier tipo que se agregue más adelante al catálogo de tipos (006), salvo que una
  especificación futura defina una regla propia para ese tipo nuevo.
- Como el tipo de una suscripción es fijo para siempre (006), el rango que le aplica a su límite de
  clínicas (exactamente 1, o de 1 a 100) también queda decidido para siempre desde la creación.
- Al desplegar esta funcionalidad, las suscripciones no Individuales que ya existan reciben 1 como
  límite de clínicas inicial (el valor más bajo del rango permitido, siempre válido y sin relación
  con cuántas clínicas tengan hoy asociadas); quien administra los planes puede ajustarlo después con
  la operación de actualización ya existente.
- El límite de clínicas requiere el mismo permiso que los demás datos generales de la suscripción
  (`subscriptions:write` al crear, `subscriptions:update` al actualizar); esta especificación no
  agrega permisos nuevos.
