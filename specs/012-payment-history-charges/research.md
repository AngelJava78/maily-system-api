# Research: Historial paginado de cobros de la suscripción (012-payment-history-charges)

## R1: Reutilizar el patrón de `clinic-subscriptions`, con el ajuste que ya pide el Frontend

**Decision**: la operación nueva (`GET /{organization_id}/charges`) copia la forma de
`list_clinic_subscription_charges` (Router → Service → Repository, paginación por `offset`/`limit` con un
`SELECT count(*)` aparte), con dos cambios deliberados: los parámetros de consulta son `page`/`page_size`
(no `page`/`limit`) y la paginación (`total`, `total_pages`) va en el **cuerpo** de la respuesta, no en el
encabezado `X-Total-Count`.

**Rationale**: el pedido del Frontend (`pedido-system-api-charges.md`) ya decidió ambos cambios: su
`HttpClient` compartido (`src/shared/api/httpClient.ts` de ese repositorio) nunca expone encabezados de
respuesta a quien llama, solo el cuerpo validado; y `page`/`page_size` es la convención que ese mismo
Frontend ya usa para los demás listados paginados que consume (Pacientes). No hay ninguna razón de este
lado para divergir del pedido: es exactamente lo que se le pidió a quien mantiene este API.

**Alternatives considered**: mantener `page`/`limit` y el encabezado, igual que `clinic-subscriptions` —
rechazado porque obligaría al Frontend a cambiar su cliente HTTP compartido para este único listado, algo
que el pedido explícitamente descartó.

## R2: Sin reconciliación en esta lectura

**Decision**: `list_charges` del Service solo hace la comprobación de que la persona es el Dueño (la misma
de `get_status`); no llama a `_prepare()` completo (que también crea el registro del periodo si falta y
reconcilia los cobros pendientes con Pagos).

**Rationale**: la reconciliación ya ocurre en cada lectura del periodo completo, que el Frontend siempre
pide en la misma pantalla (`/payment`) junto con este historial. Repetirla aquí sería una llamada más a
Pagos, con el mismo token de la persona, sin ningún cobro nuevo que aplicar que la otra lectura no vaya a
aplicar ya. Un historial de solo lectura no necesita ese costo; el pedido tampoco lo exige (sus criterios
de aceptación no piden que un cobro pendiente cambie de estado al leer el historial).

**Alternatives considered**: reconciliar también aquí, para que el historial muestre siempre el estado más
reciente — rechazada por el costo (otra llamada a Pagos en cada apertura de la pantalla) sin beneficio
medible, dado que la otra lectura de la misma pantalla ya lo hace.

## R3: Sin crear el registro del periodo si no existe

**Decision**: a diferencia de `get_status`/`start_payment` (que crean el periodo en su primera consulta,
FR-007 de la spec 010), `list_charges` no lo crea: si el periodo no existe todavía, la organización
simplemente no tiene cobros (`items: []`, `total: 0`), lo cual ya es la respuesta correcta.

**Rationale**: crear el periodo es una decisión de negocio de cuándo empieza la prueba de una
organización (spec 010, FR-007); el historial de cobros no necesita tomar esa decisión para responder
«no hay nada que mostrar todavía». No crearlo evita un efecto secundario de una operación de solo lectura.

## R4: El modelo de datos no cambia

**Decision**: ninguna migración de Alembic nueva. La tabla `subscription_charges` (migración 0008) ya
tiene todas las columnas que el pedido pide publicar.

**Rationale**: confirmado leyendo `src/models/subscription_charge.py` y la migración 0008 antes de
planear: `status`, `closed_reason`, `amount`, `currency`, `billing_period`, `period_starts_at`,
`period_ends_at` y `created_at` ya existen, con las mismas restricciones (`CheckConstraint`) que ya
garantizan, a nivel de base de datos, que `closed_reason` y las fechas del periodo solo acompañan al
estado que les corresponde (FR-003, FR-004): el DTO de esta feature no necesita repetir esa validación
porque nunca puede recibir una combinación inválida del Repository.

## R5: Sin permiso nuevo

**Decision**: la operación exige `subscription_periods:read`, el mismo permiso que ya exige
`GET /{organization_id}`; no se da de alta ningún permiso en el catálogo del API de usuarios.

**Rationale**: es la misma persona (el Dueño) viendo datos de la misma organización; el pedido lo pide así
explícitamente («mismo permiso que ya exige el periodo completo»), y la constitución (Principio VIII)
permite reutilizar un permiso existente sin enmienda, solo con la fila nueva en la matriz
«operación → permiso» de esta feature ([contracts/permission-matrix.md](contracts/permission-matrix.md)).

## R6: Tamaño de página por omisión y máximo

**Decision**: `page` por omisión 1; `page_size` por omisión 10, de 1 a 100.

**Rationale**: 10 es `SUBSCRIPTION_CHARGES_PAGE_SIZE` ya fijado del lado del Frontend
(`mailySoft-frontend/specs/030-payment-history/src/features/subscription/hooks/useSubscriptionCharges.ts`),
así que pedir sin parámetros da lo mismo que ese Frontend ya pide por omisión. 100 es la misma cota que ya
usa `LimitQuery` del listado de cobros de clínicas (`src/routers/clinic_subscriptions.py`): no hay ninguna
razón para una cota distinta en un listado con la misma forma.

## R7: Puertas de calidad antes de integrar a `main`

**Decision**: igual que toda feature de este repositorio (constitución, Principio V y «Flujo de Desarrollo
y Puertas de Calidad»): el ciclo activo (`/speckit-implement`) se limita a `uv run pytest` (nivel rápido,
sin PostgreSQL real); antes de integrar a `main` se exige la suite completa
(`uv run pytest -m ""`, con PostgreSQL 17 real), el esquema OpenAPI generado sin errores, la prueba de
cobertura de permisos y las colecciones de Postman/Newman actualizadas y en verde. Como no existe todavía
un pipeline de CI/despliegue, quien integra el cambio (esta sesión, por instrucción de la persona
responsable) corre esa puerta a mano.
