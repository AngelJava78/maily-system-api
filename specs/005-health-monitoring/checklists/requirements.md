# Specification Quality Checklist: Monitoreo de salud de los servicios de Maily

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-24
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

- **Sin marcadores [NEEDS CLARIFICATION]**: el contexto común de las cuatro specs ya fijaba las decisiones
  de negocio (agregador, registro, horario, SSRF, permisos y contrato v1), y el estado público lo decidió la
  persona responsable (2026-10-24). Lo que dejaban abierto se resolvió con valores por defecto, anotados en
  «Assumptions» como «Decisiones tomadas sin preguntar (revisables con /speckit-clarify)»: 7 del contexto y
  22 propias de esta spec.
- **Sobre «sin detalles de implementación»**: nombrar rutas, campos, códigos HTTP, permisos, variables de
  entorno y códigos de error es el acuerdo entre servicios que se pidió fijar en la spec (lo consumen
  maily-backoffice 016, mailySoft-usuarios 016 y mailySoft-pacientes 008), igual que en las specs 001, 003 y
  004. Las únicas menciones de archivos o herramientas (`src/main.py` y `pyproject.toml` como origen actual
  de la versión, `PUBLIC_ROUTES` y `test_permission_coverage`, `ARG`/`ENV` del Dockerfile, Alembic, httpx,
  `zoneinfo`, APScheduler, Postman) son restricciones de la constitución y de la solicitud (qué hay hoy, qué
  pruebas se ajustan y qué tecnología no se añade), no decisiones de diseño: no hay clases, módulos,
  consultas ni estructuras de código. Eso va al plan. La actualización del estado público no añadió
  ninguna mención nueva de ese tipo.
- **Actualización del 2026-10-24: estado público** (decisión de la persona responsable):
  - Añadido: historia 6 (P2); FR-044 a FR-049, al final de la lista y sin renumerar; SC-013 a SC-016; tres
    casos límite (próximo encendido después de un fin de semana o cerca de un cambio de horario, falla
    dentro del horario y petición pública justo al vencer la caché); y las decisiones 25 a 29.
  - Ajustado: actores; historias 1, 2 y 4 (`next_start_at` y la excepción de `/health/status`); los casos
    límite de caché en 0, límite del horario, usuarios sin poder autorizar, usuarios caído y varias réplicas;
    FR-001 (tabla y conteos: 13 operaciones protegidas y 8 rutas públicas), FR-002, FR-012, FR-020 (y el caso
    «Caché en 0», acotados a la consulta autenticada para no contradecir el periodo mínimo de 15 s de la ruta
    pública), FR-035, FR-039 y FR-042; las entidades; «Dependencias»; «Limitación conocida»; y «Otros
    supuestos».
  - Ejemplos de `next_start_at` comprobados con las reglas de zona de la IANA: viernes 23 de octubre de 2026
    a las 21:15 en la Ciudad de México → `2026-10-26T14:00:00Z`; viernes 30 de octubre de 2026 a las 21:00 en
    `America/Tijuana` (con horario de verano) → `2026-11-02T16:00:00Z`.
- **Iteraciones de validación: 2 en la versión inicial y 2 en la actualización.**
  1. Primera pasada: se corrigieron (a) FR-043, que describía cómo repartir el código entre capas (detalle
     de diseño), y ahora solo exige cumplir los principios; (b) ambigüedades: qué pasa con un chequeo mal
     formado (FR-013), entradas inválidas de la lista permitida e IP exactas (FR-027), espacios en
     `DATABASE_SCHEDULE_DAYS` (FR-033) y el texto del valor por defecto de `HEALTH_ALLOWED_HOSTS` (FR-038);
     (c) faltaban el 500 de las operaciones del registro con la base caída (tabla de FR-001, coherente con
     FR-037 y con cómo documentan el 500 las suscripciones), la actualización conjunta de matriz y colección
     del flujo de la constitución (FR-042) y una línea explícita de «Fuera de alcance».
  2. Segunda pasada: comprobaciones mecánicas (0 marcadores, 0 restos de la plantilla, FR-001 a FR-043 sin
     huecos ni referencias rotas, tablas con columnas coherentes) y relectura; solo se ajustó redacción.
  3. Actualización, primera pasada: comprobaciones mecánicas (0 marcadores; FR-001 a FR-049 y SC-001 a
     SC-016 sin huecos ni duplicados; las historias 1 a 6 y las decisiones 1 a 29 sin huecos; todas las
     referencias a FR, SC, historias y decisiones existen; la tabla de FR-001 con 10 operaciones y 4 columnas)
     y relectura. Se corrigieron: (a) la historia 6 decía que el API de usuarios no recibía «ninguna
     consulta», falso si usuarios está registrado como componente: ahora, «ninguna consulta de permisos»;
     (b) FR-048 no decía qué hace la ruta pública cuando todavía no hay ningún resultado (al arrancar o con
     la caché invalidada); (c) la lista de reglas de FR-046 podía leerse como exhaustiva; (d) la prueba
     independiente de la historia 6 no acotaba las 100 peticiones al periodo mínimo.
  4. Actualización, segunda pasada: comprobaciones mecánicas repetidas y relectura; solo se corrigió el
     ancho de una línea de FR-048.
- **Para el plan y para /speckit-clarify**:
  - **Limitación conocida (mitigada)**: el panel autenticado sigue dependiendo de mailySoft-usuarios, que
    no puede autorizar mientras la base de datos está detenida por horario; el estado público
    `/health/status` lo mitiga sin token. Conviene confirmar con la persona responsable los dos huecos que
    quedan: un proceso reiniciado con la base detenida solo muestra los integrados, y si este servicio no
    responde tampoco hay estado público.
  - El ejemplo del contrato del estado público traía `"name":"maily-system-api"` para el componente
    integrado; la spec conserva «MailySoft System API» (FR-016), porque el estado público usa los mismos
    datos que `GET /api/v1/health`.
  - La spec de maily-backoffice 016 dice hoy que «Detenida por horario» no podrá verse con el diseño actual:
    hay que alinearla con la historia 6, `/health/status` y `next_start_at`.
  - La desviación del principio IX (direcciones desde el registro y no desde variables de entorno) debe
    justificarse en el «Constitution Check» o resolverse con una enmienda (FR-022).
  - `zoneinfo` necesita los datos de zonas horarias: en Windows y en imágenes que no los traen hace falta el
    paquete `tzdata`, que hoy no está en `uv.lock`.
  - Alinear con mailySoft-usuarios 016 y mailySoft-pacientes 008 el nombre de `HEALTH_READY_TIMEOUT_SECONDS`
    y la validación de `APP_*`; y confirmar con maily-backoffice 016 la lista de códigos de error de
    componente (FR-018) y que `"unknown"` significa «no disponible».
