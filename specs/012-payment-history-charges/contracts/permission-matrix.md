# Contrato: fila nueva de la matriz operación → permiso (FR-006)

Esta feature **añade una fila** a la matriz «operación → permiso» de la API (spec 010,
`contracts/permission-matrix.md`, que no se modifica: sigue siendo el historial hasta su propia feature).
Reutiliza un permiso que ya existe; no se da de alta ninguno nuevo.

## Fila nueva (feature 012)

| Operación (`operationId`) | Método y ruta | Permiso |
|---|---|---|
| `list_subscription_charges` | `GET /api/v1/subscription-periods/{organization_id}/charges` | `subscription_periods:read` |

## Reglas

1. **Mismo permiso que consultar el periodo completo**: quien puede ver el periodo vigente de la
   organización puede ver su historial de cobros; no hay un permiso separado para el historial.
2. **El permiso solo no basta**: además la persona debe ser el Dueño de la organización indicada, lo que
   decide Clínicas (404 si no lo es) — el mismo control de acceso de `get_subscription_period`, no uno
   nuevo.
3. **La prueba de cobertura** `tests/contract/test_permission_coverage.py` sigue siendo global: su ajuste
   para esta feature es agregar `list_subscription_charges` a `EXPECTED_PERMISSIONS` y a `REQUESTS`
   (`GET {PERIODS_URL}/{ORGANIZATION_ID}/charges`); ninguna aserción existente cambia.
4. **Alta en el API de usuarios**: no aplica — el permiso ya existe y ya está asignado al rol Owner desde
   la spec 010.
