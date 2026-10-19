# Specification Quality Checklist: Dashboard de Plataforma («Panel de Maily»)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-18
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

- La descripción de la feature ya traía resueltas casi todas las decisiones de negocio (rango de
  `limit`, tope de 10 sin error, valores de la variable de configuración, orden de comprobación
  403 → 422, datos ficticios, degradación con `null`), por eso no hay marcadores
  [NEEDS CLARIFICATION]. Lo que la descripción dejaba abierto se resolvió con un valor por defecto y
  está en «Assumptions» para que la persona responsable lo confirme o lo corrija (ver abajo).
- Nombrar `limit`, `DASHBOARD_RECENT_CLINICS_LIMIT`, `dashboard:read`, `.env.example`, Postman, UUID,
  ISO 8601 y los códigos HTTP es parte del contrato que se pidió (qué ve y configura quien consume y
  opera la API), no una elección de tecnología de implementación; igual que en las especificaciones
  001 y 002. No hay rutas de archivos de código, clases, bibliotecas ni consultas: eso va al plan.
  Los nombres de campo de la respuesta se proponen en «Key Entities» y el plan los fija en el contrato.

### Decisiones por defecto que conviene confirmar (ver «Assumptions»)

1. **Pruebas existentes que vigilan «todas las operaciones» (FR-033)**. La solicitud pide a la vez no
   tocar las pruebas de las operaciones existentes y actualizar la cobertura de permisos. Hay
   comprobaciones que dan por hecho que la API tiene *exactamente* seis operaciones
   (`tests/contract/test_permission_coverage.py`, `test_openapi_contract.py` y la cobertura y la
   prueba de desfase de las colecciones de Postman), así que añadir una operación las rompe sin
   remedio. Se interpretó que solo esas comprobaciones se amplían o acotan para reconocer la
   operación nueva, sin debilitarlas ni cambiar nada de lo que verifican sobre las suscripciones; la
   colección de Postman nueva es independiente y no se añade a las existentes.
2. **Lista de clínicas recientes cuando su fuente falla**: `null`, no `[]` (un `[]` diría «no hay
   clínicas», un dato inventado igual que un cero). Contradice solo en apariencia el «nunca nula» de la
   solicitud, que se refiere al caso en que la fuente sí respondió y no hay clínicas.
3. **Si fallan todas las fuentes**: 200 con todo en `null`; solo el control de acceso puede impedir
   responder.
4. **Desempate por identificador**: ascendente (la solicitud no fijaba el sentido).
5. **Tipo del identificador de estatus de clínica**: entero, como el estatus de las suscripciones.
6. **Parámetros**: `limit` repetido → 422; parámetros desconocidos (p. ej. `page`) → se ignoran;
   variable de entorno vacía → como no configurada (5), igual que las demás opcionales.
7. **Reparto de pruebas**: «menos clínicas que el límite», «ninguna clínica», «valor configurado
   válido e inválido» y la degradación se verifican con las pruebas automatizadas del servicio, no con
   Postman, porque la colección no puede cambiar la configuración ni los datos del servicio real.

### Para el plan

- El «Constitution Check» debe confirmar que la excepción de paginación del Principio IV (FR-016) no
  exige enmienda, como indicó la persona responsable.
- El permiso `dashboard:read` debe darse de alta en el catálogo del API de usuarios antes de integrar;
  la simulación del API de usuarios (pila de punta a punta) debe poder concederlo y denegarlo.
- Garantizar que el permiso se comprueba antes de validar `limit` (FR-003) y reutilizar los códigos de
  error existentes (`validation_error`, 401, 403, 503) sin tocar el catálogo (FR-030).
