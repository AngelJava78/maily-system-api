# Specification Quality Checklist: Cobro Real de Suscripciones de Clínicas

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-10
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

- **`/speckit-clarify` (2026-11-10), 3 preguntas, 3 respondidas**: (1) quien administra la plataforma
  gestiona la suscripción de clínica con `tenant_id` explícito en el cuerpo (FR-006); (2) solo una
  persona de la propia clínica puede disparar el cobro, con un permiso nuevo
  (`clinic_subscriptions:charge`) asignable a un rol de Clínica, nunca a quien administra la
  plataforma (FR-012, FR-030, FR-031); (3) el historial de cobros se guarda completo, una fila por
  intento (`clinic_subscription_charges`). Las tres se integraron en «Clarifications», en los actores,
  en las historias 1, 2, 4 y 5, en FR-006/FR-012/FR-024/FR-030/FR-031 y en «Key Entities» y
  «Assumptions»; ningún marcador queda pendiente.
- **Sobre «sin detalles de implementación»**: nombrar rutas, campos, códigos HTTP y permisos es el
  contrato entre servicios que las specs de este repositorio ya fijan en la especificación (patrón de
  las specs 001, 003 y 005); las menciones a `POST /api/v1/payments` y `GET /api/v1/payments/{id}` de
  mailySoft-pagos son el contrato consumido (lo mismo que ya hace esta spec con `subscriptions` y con
  el API de clínicas), no una decisión de diseño interno de este servicio.
- **Para el plan**:
  - FR-030 amplía la integración con `mailySoft-usuarios` para usar también
    `GET /api/v1/authorization/me` (hoy este servicio solo usa `GET /api/v1/authorization/check`,
    FR-031): el plan debe diseñar esa ampliación del cliente existente (`UsersApiClient`) sin romper
    el uso que ya hace de `check` el resto de la API.
  - El permiso `clinic_subscriptions:charge` debe poder asignarse a un rol de tipo Clínica (p. ej.
    Owner) en el catálogo simulado de `mailySoft-usuarios`, a diferencia de
    `clinic_subscriptions:write/update/delete`, que son de un rol de Sistema (Administrator): la
    simulación de pruebas debe modelar ambos tipos de persona que llama.
  - Queda documentado como limitación conocida y fuera de alcance (no una contradicción a resolver):
    quien administra la plataforma asigna un plan a una clínica pero no puede cobrarlo; alguien de
    esa clínica debe enterarse y disparar el cobro por su cuenta.
