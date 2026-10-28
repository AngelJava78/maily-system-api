# Feature Specification: Guardar los módulos de la suscripción en su propia tabla

**Feature Branch**: `008-subscription-modules-table`

**Created**: 2026-10-27

**Status**: Draft

**Input**: User description: "Debemos hacer una corrección en las operaciones CRUD de las
suscripciones. Actualmente se pasa una lista de módulos (`module_keys`) guardada en una sola
columna de la suscripción. Me parece más adecuado que se guarde en una tabla que relacione las
suscripciones con los módulos (por ejemplo: `subscription_modules`, en inglés). Al crear o
modificar suscripciones se debe seguir validando que la lista de módulos exista en la lista de
módulos activos; esa lista no es responsabilidad de este microservicio, sino del microservicio
`users-api` (`GET /api/v1/modules`)."

## User Scenarios & Testing *(mandatory)*

Los actores son **quien administra los planes de MailySoft** (crea y actualiza suscripciones desde
el Backoffice, elige qué módulos incluye cada plan) y **quienes consumen el catálogo de
suscripciones**, que ya reciben los módulos incluidos de cada plan. Ninguno de los dos actores nota
este cambio en su forma de trabajar: lo que cambia es cómo este servicio guarda esa relación por
dentro, no lo que cualquiera de ellos envía o recibe.

### User Story 1 - Crear o actualizar los módulos de una suscripción sin que cambie nada para quien la administra (Priority: P1)

Quien administra los planes sigue indicando, al crear o actualizar una suscripción, el conjunto
completo de módulos que tendrá (una lista de claves), y sigue recibiendo exactamente las mismas
respuestas y los mismos rechazos que hoy: «patients» siempre incluido, cada módulo validado contra
el catálogo de módulos de clínica activos que reporta `users-api`, y las dependencias entre módulos
propias de este servicio (por ejemplo, Recordatorios exige Agenda y citas) exigidas igual que
siempre.

**Why this priority**: Es la base de toda la especificación: el único propósito de guardar los
módulos en su propia tabla es mejorar cómo se almacenan internamente, nunca cambiar lo que ya
funciona para quien crea o actualiza una suscripción. Si este comportamiento cambiara aunque sea en
un caso, la corrección habría introducido una regresión en vez de resolver nada.

**Independent Test**: Repetir, contra el servicio ya corregido, cada escenario de validación de
módulos ya cubierto hoy (módulo reconocido, módulo no reconocido, módulo sin su prerrequisito,
`users-api` sin responder, «patients» omitido en la solicitud) y comprobar que cada uno se resuelve
exactamente igual que antes de la corrección.

**Acceptance Scenarios**:

1. **Given** una solicitud de creación con una lista de módulos válida y reconocida por `users-api`,
   **When** se crea la suscripción, **Then** se crea con exactamente esos módulos más «patients», en
   la misma forma de respuesta que hoy (lista de claves ordenada alfabéticamente).
2. **Given** una solicitud que incluye una clave de módulo que `users-api` no reconoce como módulo de
   clínica activo, **When** se envía (al crear o al actualizar), **Then** se rechaza indicando esa
   clave, y no se guarda ni se modifica ningún módulo.
3. **Given** una solicitud que incluye un módulo sin su prerrequisito (por ejemplo, Recetas sin
   Expediente clínico), **When** se envía, **Then** se rechaza indicando ambos módulos, igual que
   hoy.
4. **Given** una actualización que envía un nuevo conjunto completo de módulos para una suscripción
   que ya tenía otros, **When** se aplica, **Then** la suscripción queda con exactamente el conjunto
   nuevo: ningún módulo anterior que ya no está en la lista permanece, y todos los módulos nuevos
   quedan presentes.
5. **Given** `users-api` no responde al validar los módulos de una solicitud de creación o de
   actualización, **When** se envía, **Then** se rechaza con el mismo error ya existente, sin dejar
   guardado ningún módulo de esa solicitud.

---

### User Story 2 - Conservar los módulos de las suscripciones que ya existen (Priority: P1)

Al aplicar esta corrección sobre una base de datos que ya tiene suscripciones con módulos
guardados, cada una conserva exactamente el mismo conjunto de módulos que tenía antes, sin que nadie
tenga que revisarlas ni corregirlas a mano.

**Why this priority**: Una migración de almacenamiento que pierda o altere los módulos de una
suscripción ya vigente sería más grave que el problema que esta especificación busca resolver: una
clínica podría perder acceso a un módulo que ya pagaba, o quedarse con uno que no le corresponde.

**Independent Test**: Con varias suscripciones ya existentes con distintos conjuntos de módulos
(incluida alguna con solo «patients» y alguna con varios), aplicar la corrección y comprobar que,
al consultar cada una después, muestra exactamente el mismo conjunto de módulos que mostraba antes.

**Acceptance Scenarios**:

1. **Given** una suscripción que ya existe con un conjunto de módulos determinado, **When** se
   aplica esta corrección, **Then** al consultarla después muestra exactamente ese mismo conjunto,
   ni un módulo más ni uno menos.
2. **Given** varias suscripciones existentes con conjuntos de módulos distintos entre sí, **When**
   se aplica esta corrección, **Then** ninguna termina con los módulos de otra ni con un conjunto
   vacío que no tenía.

---

### User Story 3 - Ningún módulo puede quedar duplicado ni huérfano en la base de datos (Priority: P2)

A diferencia de hoy —donde nada impide, a nivel de base de datos, que una lista de módulos
contuviera una clave repetida o quedara asociada a una suscripción que ya no existe—, la nueva
relación garantiza esas reglas por diseño: ni la base de datos admite dos filas del mismo módulo
para la misma suscripción, ni puede quedar una fila de módulo sin la suscripción a la que
pertenece.

**Why this priority**: Es la razón de fondo de esta corrección (más allá de que el comportamiento
externo no cambie): una relación propia entre suscripciones y módulos permite, a futuro, consultas
como «qué suscripciones usan el módulo X» sin recorrer listas, y deja que la propia base de datos —
no solo el código del servicio— impida datos inconsistentes.

**Independent Test**: Intentar, a nivel de los datos, que una suscripción quede con el mismo módulo
repetido o que una fila de módulo quede sin la suscripción que la originó, y comprobar que la base
de datos lo impide en ambos casos, no solo el código de la aplicación.

**Acceptance Scenarios**:

1. **Given** una suscripción ya guardada con un módulo determinado, **When** se intenta que la
   misma combinación de suscripción y módulo quede guardada dos veces, **Then** la base de datos lo
   rechaza.
2. **Given** una suscripción se elimina (baja lógica, ya existente), **When** se intenta razonar
   sobre sus módulos después, **Then** siguen asociados a esa suscripción (no se borran ni se
   sueltan), igual que el resto de sus datos tras una baja lógica.

---

### Edge Cases

- Se envía la misma clave de módulo repetida dentro de una sola solicitud de creación o
  actualización: se trata como si se hubiera enviado una sola vez (igual que hoy), sin que eso
  produzca dos filas iguales.
- Se actualiza una suscripción para dejarla solo con «patients» (quitando todos los demás módulos
  que tenía): después de la actualización no queda ninguna fila de módulo salvo la de «patients».
- Se actualiza una suscripción sin incluir el campo de módulos en la solicitud: su conjunto de
  módulos permanece exactamente igual, sin ninguna escritura sobre esa relación.
- Falla la escritura a mitad de camino al reemplazar el conjunto completo de módulos de una
  suscripción (por ejemplo, un error de la base de datos): la suscripción MUST NOT quedar con una
  mezcla del conjunto anterior y el nuevo; o se aplica el conjunto nuevo completo, o se conserva el
  anterior completo.
- Una suscripción nunca llegó a tener ningún módulo además de «patients» (el caso más simple, hoy
  ya el valor por defecto): sigue representándose igual después de la corrección, con una sola fila
  (la de «patients»).
- Se agrega en el futuro un módulo nuevo al catálogo de `users-api` que esta especificación no
  conocía: se acepta igual que hoy, salvo que sea un módulo con prerrequisito sin incluirlo (004,
  FR-018), que no se ve afectado por esta corrección.

## Requirements *(mandatory)*

### Functional Requirements

**Almacenamiento de los módulos**

- **FR-001**: Los módulos que incluye cada suscripción MUST guardarse como una relación propia entre
  la suscripción y cada clave de módulo que incluye (una fila por cada módulo), en vez de como un
  solo valor compuesto dentro de una columna de la suscripción.
- **FR-002**: Esa relación MUST impedir, a nivel de los datos, que la misma suscripción quede
  asociada dos veces al mismo módulo, y MUST impedir que una fila de módulo exista sin la
  suscripción a la que pertenece.
- **FR-003**: Al desplegar esta corrección, toda suscripción que ya exista MUST conservar
  exactamente el mismo conjunto de módulos que tenía antes, sin perder ninguno ni ganar uno que no
  tenía.

**Comportamiento que no cambia (validado contra lo ya vigente desde 004)**

- **FR-004**: El contrato publicado para los módulos de una suscripción (una lista de claves, que
  siempre incluye «patients» y se muestra ordenada alfabéticamente, tanto al crear y actualizar como
  al consultar) MUST seguir siendo exactamente el mismo: esta corrección MUST NOT requerir ningún
  cambio en lo que envía o recibe quien consume la API.
- **FR-005**: Al crear una suscripción o al reemplazar el conjunto completo de módulos de una ya
  existente, cada clave de módulo MUST seguir validándose contra el catálogo de módulos de clínica
  activos que reporta `users-api`; una clave que ese catálogo no reconozca MUST seguir
  rechazándose, igual que hoy (004, FR-015 y FR-019). Esta especificación MUST NOT trasladar esa
  validación, ni total ni parcialmente, a este servicio.
- **FR-006**: El módulo «patients» MUST seguir incluido siempre en toda suscripción, se envíe o no
  en la solicitud, igual que hoy (004, FR-017).
- **FR-007**: Las reglas de dependencia entre módulos propias de este servicio (004, FR-018, p. ej.
  Recordatorios exige Agenda y citas) MUST seguir aplicándose sin cambios, tanto al crear como al
  actualizar.
- **FR-008**: Si `users-api` no responde al validar los módulos de una solicitud, esa solicitud MUST
  seguir rechazándose con el mismo error ya existente, sin dejar escrita ninguna fila de módulo de
  esa solicitud (004, FR-020).
- **FR-009**: Al reemplazar el conjunto completo de módulos de una suscripción en una actualización,
  el resultado MUST ser, de forma atómica, exactamente ese conjunto nuevo: ningún módulo que ya no
  forma parte de él MUST permanecer, y todos los módulos nuevos MUST quedar presentes; si la
  operación no puede completarse por completo, MUST NOT quedar ningún cambio parcial (ni el
  conjunto anterior con algunas filas nuevas, ni el conjunto nuevo con algunas filas viejas).
- **FR-010**: La baja lógica de una suscripción (ya existente) MUST NOT eliminar ni modificar sus
  filas de módulo: se conservan igual que el resto de los datos de una suscripción eliminada.

### Key Entities

- **Suscripción (plan)**: entidad ya existente (nombre, descripción, tipo, precios, días de prueba,
  autoconsumo, límites, otras funcionalidades, estatus, número de clínicas y fechas, sin cambios en
  esta especificación). Deja de llevar sus módulos en un campo propio: a partir de esta
  especificación, su conjunto de módulos se obtiene de la nueva relación con la entidad siguiente.
- **Módulo incluido en una suscripción** *(nueva, relación)*: asocia una suscripción con una clave
  de un módulo de clínica. La clave identifica un módulo de un catálogo externo que esta API no
  administra ni copia (propiedad de `users-api`, ver Assumptions e igual que ya establecía 004); lo
  único que esta entidad guarda es qué claves eligió cada suscripción. Cada combinación de
  suscripción y módulo aparece como máximo una vez.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los escenarios de validación de módulos ya cubiertos hoy (módulo
  reconocido, no reconocido, sin prerrequisito, `users-api` sin responder, «patients» implícito)
  se resuelve, después de esta corrección, exactamente igual que antes: mismo resultado, mismo
  código de error cuando aplica.
- **SC-002**: El 100% de las suscripciones que ya existían antes de desplegar esta corrección
  conserva, después de desplegarla, exactamente el mismo conjunto de módulos que tenía (0 casos de
  pérdida o de módulos de más).
- **SC-003**: Es imposible, a nivel de los datos, que una suscripción quede con el mismo módulo
  repetido o con una fila de módulo sin la suscripción a la que pertenece (0 casos posibles, no solo
  0 casos observados).
- **SC-004**: El 100% de las suscripciones puede seguir reemplazando su conjunto completo de módulos
  mediante la operación de actualización ya existente, sin pasos ni campos adicionales respecto a
  hoy.

## Assumptions

- Esta especificación es una corrección interna de almacenamiento (Principios I, II y VI): no
  cambia el contrato publicado de la API para los módulos de una suscripción (la lista de claves que
  se envía al crear o actualizar, y la que se devuelve al consultar), por lo que quien consume la
  API no necesita ningún ajuste.
- La validación contra el catálogo de módulos de clínica activos de `users-api`
  (`GET /api/v1/modules`), las reglas de dependencia entre módulos y la obligatoriedad de «patients»
  ya están vigentes desde `004-correct-subscriptions-api` y esta especificación no las modifica: solo
  cambia cómo se guardan internamente los módulos ya validados.
- El catálogo de módulos sigue siendo propiedad del microservicio de usuarios
  (`mailySoft-usuarios`); esta especificación no copia ni cachea ese catálogo aquí, solo registra, en
  la nueva relación, qué claves eligió cada suscripción (igual que hoy, Principio IX).
- El nombre de ejemplo mencionado para la nueva relación (`subscription_modules`, en inglés como
  exige el Principio VII para el código) es una propuesta de quien administra el proyecto; el nombre
  exacto de la tabla, sus columnas y la migración de Alembic que la crea se deciden en el plan
  técnico de esta especificación (`/speckit-plan`), no en este documento.
- No se requiere ningún permiso nuevo: crear o reemplazar los módulos de una suscripción sigue
  exigiendo `subscriptions:write` o `subscriptions:update` según la operación, igual que hoy.
- Las suscripciones que ya existen conservan sus módulos actuales al aplicar esta corrección sin
  intervención manual (FR-003, SC-002); no se requiere que alguien revise o corrija datos a mano.
