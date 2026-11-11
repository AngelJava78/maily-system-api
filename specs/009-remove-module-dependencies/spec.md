# Feature Specification: Quitar dependencias entre módulos

**Feature Branch**: `009-remove-module-dependencies`

**Created**: 2026-10-28

**Status**: Draft

**Input**: User description: "Quitar las dependencias entre módulos y validar los módulos de una suscripción solo contra la API de usuarios."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Crear o modificar una suscripción con cualquier combinación de módulos vigentes (Priority: P1)

Quien administra el catálogo de suscripciones de MailySoft crea o edita un plan e incluye cualquier
combinación de los módulos de clínica que la API de usuarios tiene activos. Hoy, algunas
combinaciones válidas (por ejemplo, incluir Recordatorios sin Agenda y citas, porque Agenda y citas
ya no existe como módulo) son rechazadas por una regla de dependencias que ya no corresponde al
catálogo real de módulos.

**Why this priority**: Es el defecto que bloquea operación real hoy mismo (el plan "Saturno" no se
puede crear con los 18 módulos activos) y el único cambio de comportamiento que esta especificación
introduce.

**Independent Test**: Se puede probar por completo creando una suscripción con cualquier
combinación de módulos del catálogo activo de la API de usuarios —incluyendo combinaciones que antes
se rechazaban por falta de un "prerrequisito"— y confirmando que la operación responde 201/200 sin
exigir ningún otro módulo adicional.

**Acceptance Scenarios**:

1. **Given** la API de usuarios tiene activos los 18 módulos de tipo Clínica (appointments,
   billing, clinics, consulting_rooms, expenses, finance, incomes, overview, patient_diagnoses,
   patients, prescriptions, reminders, reports, schedule, services, staff, templates,
   vital_signs), **When** se crea la suscripción "Saturno" con esos 18 módulos, **Then** la
   operación responde 201 y la suscripción queda con esos 18 módulos.
2. **Given** reminders y schedule están ambos activos en la API de usuarios, **When** se crea o
   actualiza una suscripción incluyendo reminders sin incluir schedule ni appointments,
   **Then** la operación se acepta (201/200) sin exigir schedule ni appointments.
3. **Given** billing y finance están ambos activos en la API de usuarios, **When** se crea o
   actualiza una suscripción incluyendo billing sin incluir finance, **Then** la operación se
   acepta (201/200) sin exigir finance.

---

### User Story 2 - Rechazar un módulo que no existe en el catálogo activo de la API de usuarios (Priority: P2)

Quien crea o modifica una suscripción incluye por error (o porque el módulo ya no existe o fue
desactivado) una clave que la API de usuarios no reconoce como módulo de clínica activo. La
operación se rechaza indicando exactamente qué clave no es válida, sin mencionar ninguna regla de
dependencia (porque esa regla ya no existe).

**Why this priority**: Preserva la única validación de módulos que sigue vigente (FR-015/FR-019 de
`specs/004-correct-subscriptions-api`) una vez eliminada la validación de dependencias; sin esta
historia, cualquier texto quedaría aceptado como módulo.

**Independent Test**: Se puede probar por completo enviando una clave que no está en el catálogo
activo de tipo Clínica (por ejemplo, una clave retirada como `scheduling`) y confirmando que la
operación se rechaza señalando esa clave como no encontrada.

**Acceptance Scenarios**:

1. **Given** `scheduling` ya no es un módulo de tipo Clínica activo en la API de usuarios,
   **When** se crea o actualiza una suscripción incluyendo `scheduling`, **Then** la operación se
   rechaza con un error que identifica `scheduling` como módulo no encontrado, y no se crea ni
   modifica ninguna suscripción.

---

### User Story 3 - Un módulo nuevo se puede usar sin cambiar código de este servicio (Priority: P3)

El equipo de la API de usuarios da de alta un módulo nuevo de tipo Clínica con estatus Activo.
Quien administra las suscripciones puede incluir ese módulo nuevo en cualquier plan de inmediato,
sin esperar ningún cambio de código ni despliegue de la API de Suscripciones.

**Why this priority**: Es la garantía de fondo de esta especificación (ningún catálogo ni regla de
módulos vive en código de este servicio), pero no bloquea nada operativo mientras las Historias 1 y
2 funcionen; por eso queda en tercer lugar.

**Independent Test**: Se puede probar por completo dando de alta en la API de usuarios un módulo de
tipo Clínica con estatus Activo que nunca existió antes, y confirmando que una suscripción puede
incluirlo sin que la API de Suscripciones necesite ningún cambio.

**Acceptance Scenarios**:

1. **Given** se da de alta en la API de usuarios un módulo nuevo de tipo Clínica con estatus
   Activo, **When** se crea o actualiza una suscripción incluyendo ese módulo nuevo, **Then** la
   operación se acepta sin requerir ningún cambio de código ni despliegue de la API de
   Suscripciones.

---

### Edge Cases

- ¿Qué pasa si la petición solo incluye `patients`? No se consulta la API de usuarios (igual que
  hoy): `patients` siempre es válido por sí mismo.
- ¿Qué pasa si la API de usuarios no responde o responde algo inesperado al consultar el catálogo de
  módulos? La operación se rechaza indicando que no se pudo verificar el catálogo de módulos,
  igual que hoy (FR-007).
- ¿Qué pasa si una suscripción ya guardada tiene un módulo que la API de usuarios desactivó
  después? No se revalida al leerla: sigue mostrándose como está guardada (FR-009); la validación
  solo ocurre al crear o al enviar `module_keys` en una actualización.
- ¿Qué pasa si una actualización no incluye `module_keys` en absoluto? No se valida ningún módulo
  en esa operación (FR-009), igual que hoy.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Al crear una suscripción, o al actualizarla enviando `module_keys`, el sistema MUST
  consultar el catálogo de módulos de tipo Clínica con estatus Activo de la API de usuarios, y
  MUST aceptar únicamente las claves que ese catálogo devuelva en ese momento.
- **FR-002**: Si la petición incluye una clave que no está en ese catálogo, el sistema MUST
  rechazar toda la operación indicando cuál clave no se encontró, sin crear ni modificar la
  suscripción.
- **FR-003**: El sistema MUST NOT exigir que un módulo incluido en una suscripción dependa de la
  presencia de ningún otro módulo. Cualquier combinación de claves del catálogo activo es una
  combinación válida.
- **FR-004**: El sistema MUST NOT mantener, en ninguna parte de su propio código, una lista fija de
  claves de módulos de clínica ni una lista de relaciones de dependencia entre módulos. La única
  clave de módulo que el sistema MUST seguir conociendo de antemano es la de Pacientes (`patients`,
  FR-006); el resto del catálogo se conoce exclusivamente consultando la API de usuarios en el
  momento de la operación.
- **FR-005**: El sistema MUST eliminar por completo el comportamiento y la documentación del error
  "falta un módulo prerrequisito" (hoy un 409): ya no existe ninguna combinación de módulos que se
  rechace por motivo de dependencia, en ningún punto de la API, su documentación de contrato, sus
  pruebas automatizadas ni sus colecciones de prueba manual.
- **FR-006**: El módulo Pacientes MUST seguir incluido siempre en toda suscripción, se envíe o no
  explícitamente en la petición; ninguna operación puede excluirlo (sin cambios respecto a la regla
  ya vigente de `specs/004-correct-subscriptions-api`, FR-017).
- **FR-007**: Si la API de usuarios no responde, o responde de forma inesperada, al consultar el
  catálogo de módulos activos, el sistema MUST rechazar la operación indicando que el catálogo de
  módulos no se pudo verificar (sin cambios respecto al comportamiento ya vigente).
- **FR-008**: Si la petición de creación o actualización solo incluye al módulo Pacientes, el
  sistema MUST NOT necesitar consultar la API de usuarios para esa operación (sin cambios respecto
  al comportamiento ya vigente).
- **FR-009**: Una actualización que no envía `module_keys` MUST NOT disparar ninguna validación de
  módulos. Las suscripciones ya guardadas MUST NOT revalidarse contra el catálogo de módulos al
  leerlas, aun si un módulo que tenían guardado deja de estar activo después en la API de usuarios.
- **FR-010**: Esta especificación reemplaza la FR-016 de `specs/004-correct-subscriptions-api` (que
  asumía un catálogo mínimo de nueve módulos fijos) y elimina por completo la FR-018 de esa misma
  especificación (la regla de dependencias entre módulos). Las demás reglas de esa especificación
  sobre módulos (FR-015, FR-017, FR-019) no cambian.

### Key Entities *(include if feature involves data)*

- **Módulo de clínica**: una clave que identifica una funcionalidad de clínica que una suscripción
  puede incluir. Su existencia, su nombre y si está activo son propiedad exclusiva de la API de
  usuarios; esta especificación no introduce ningún catálogo propio ni ninguna relación de
  dependencia entre módulos — solo preserva que Pacientes es siempre obligatorio.
- **Suscripción**: ya definida por especificaciones previas; esta especificación solo cambia qué
  combinaciones de módulos son válidas al crearla o modificar su lista de módulos, descrita en
  `module_keys`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una suscripción puede crearse con los 18 módulos de tipo Clínica hoy activos en la
  API de usuarios, en cualquier combinación entre ellos, sin que ninguna combinación se rechace por
  motivo de dependencia entre módulos.
- **SC-002**: Un módulo de tipo Clínica dado de alta como Activo en la API de usuarios después de
  esta entrega puede incluirse en una suscripción el mismo día, sin ningún cambio de código ni
  despliegue de la API de Suscripciones.
- **SC-003**: El 100% de las claves de módulo que la API de usuarios no reconoce como de tipo
  Clínica activo siguen siendo rechazadas, identificando la clave rechazada.
- **SC-004**: Cero referencias, en el código de este servicio o en sus pruebas automatizadas, a una
  clave de módulo de clínica concreta distinta de Pacientes.
- **SC-005**: Cero menciones del error "falta un módulo prerrequisito" en la documentación de
  contrato, en las pruebas automatizadas o en las colecciones de prueba manual de este servicio.

## Assumptions

- La API de usuarios sigue siendo la única fuente de verdad sobre qué módulos de tipo Clínica
  existen y cuáles están activos, consultada de la misma forma que ya usa este servicio; esta
  especificación no le pide ningún cambio.
- "Catálogo activo" significa, en el momento de la operación, los módulos que esa consulta devuelve
  en ese instante; no se congela ni se cachea entre una operación y otra.
- Las suscripciones que ya tienen guardados módulos que dependían de la regla eliminada (por
  ejemplo, Recordatorios sin Agenda y citas, si alguna vez se forzó a mano) no se tocan ni se
  revalidan: esta especificación no incluye ninguna migración de datos.
- El Backoffice u otros consumidores de esta API pueden necesitar su propio ajuste al dejar de ver
  el error 409 de prerrequisito, pero ese ajuste queda fuera de esta especificación (tendrá la suya
  propia).
