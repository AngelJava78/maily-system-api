# Specification Quality Checklist: Periodo de prueba y siguiente pago de cada organización («Periodos de suscripción»)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-18
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Validación (iteración 1 de 3): todos los elementos pasan. No hay marcadores [NEEDS CLARIFICATION]:
  la descripción traía resueltas casi todas las reglas de negocio (diez reglas de fechas, importe y
  cobros) y las cinco decisiones que dejaba abiertas para `/speckit-clarify` se cerraron el 2026-11-18
  con su valor por defecto, por indicación de la persona responsable (sección «Clarifications» y tabla
  «Decisiones de negocio»). En D1, D2, D3 y D5 el valor por defecto coincide con la recomendación; en
  **D4 (IVA) no**: se tomó «sin IVA» (lo que dice la regla de importe de la descripción) y la
  recomendación (precio más IVA con tasa configurable) quedó registrada como alternativa aditiva.
- Nombrar los permisos (`subscription_periods:read` y `:write`), las variables de entorno propuestas, las
  operaciones de los otros APIs, `resource_type`, UTC, ISO 8601 y los códigos HTTP es parte del contrato
  que pidió la descripción y que la constitución exige documentar en la especificación (Principios VIII y
  IX), no una elección de tecnología; igual que en las especificaciones 001 y 003. No hay rutas de
  archivos de código, clases, bibliotecas, tablas ni consultas: eso va al plan. Los nombres de campo se
  proponen en «Key Entities» y el plan los fija en el contrato.
- Los ejemplos de referencia (16 filas) se calcularon con un script aparte y se comprobaron fila por fila
  contra las reglas; son la base de SC-004.

### Interpretaciones por defecto que conviene confirmar (ver «Assumptions»)

1. **Sin fuente ficticia dentro del servicio.** La descripción cita la spec 003 («puerto, fuente ficticia y
   aviso al arrancar»), pero aquí los clientes reales existen desde el primer día y una fuente ficticia
   para la comprobación del Dueño podría conceder acceso a quien no debe. El avance sin esperar se logra
   con simulaciones en las pruebas y en la pila de punta a punta; el aviso al arrancar que sí aplica es el
   de la dirección de Pagos sin cifrar.
2. **`billing_period` ausente en la respuesta de Clínicas → 503**, no se supone «mensual» (regla «nunca
   inventes»). Consecuencia: contra el API real de hoy la feature no responde 200 hasta que Clínicas lo
   publique.
3. **Fecha de aprobación = `updated_at` del pago aprobado**, porque Pagos no publica una fecha de
   aprobación propia; se pide una, sin bloquear.
4. **Meses sin día ancla**: cada periodo parte del fin del anterior y un día 29–31 acortado por un mes
   corto no se recupera (se acepta por sencillez).
5. **Cobro pendiente cuyo importe cambió por un cambio de plan → cobro nuevo** (Pagos no permite cancelar
   el anterior). Combina «el siguiente cobro usa el plan vigente» con «no crear dos cobros para el mismo
   periodo».
6. **La organización va en la petición** (la aplicación la toma de «mis clínicas») y el Dueño se comprueba
   con la lectura de la organización en Clínicas; cualquier respuesta distinta de 200 y 404 es 503.
7. **El registro también se crea si el primer contacto es iniciar el pago**, y la consulta aplica cobros ya
   aprobados (efecto acotado y determinista bajo el permiso de lectura).
8. **Un cobro aún no aplicado cuyo pago ya aparece reembolsado se cierra sin aplicarse** (coherente con
   «Pagos lo reporta como aprobado» y con D3).

### Para el plan

- El «Constitution Check» debe confirmar que guardar el identificador de la organización solo como
  referencia (Principio IX), la excepción de no paginar (no hay listados) y un `GET` con efecto acotado
  (Principio IV) no exigen enmienda.
- Escribir en `contracts/` el contrato consumido de Usuarios, Clínicas y Pagos y los tres documentos de
  pedidos (FR-047 y FR-049); declarar el esquema nuevo en `data-model.md` y en `DATA_SCHEMA.md` (FR-043).
- Ampliar, sin debilitarlas, las comprobaciones que dan por hecho el conjunto completo de operaciones de la
  API (cobertura de permisos, contrato publicado, colecciones de Postman) y enumerar cada ajuste (FR-053).
