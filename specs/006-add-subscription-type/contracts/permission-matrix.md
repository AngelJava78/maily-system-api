# Contrato: matriz operación → permiso (delta sobre `004-correct-subscriptions-api`)

**Sin cambios** en las 6 operaciones propias de esta API ni en sus 4 permisos: ver
[specs/001-subscriptions-api/contracts/permission-matrix.md](../../001-subscriptions-api/contracts/permission-matrix.md).
Esta feature no añade, quita ni renombra ninguna operación ni ningún permiso de `subscriptions:*`;
`subscription_type_id` se valida con el mismo permiso que ya exigía cada operación
(`subscriptions:write` al crear, `subscriptions:update` al intentar modificarlo).

**El catálogo `subscription_types` no tiene ninguna operación ni permiso propio** (Clarifications
2026-10-26, FR-001): se administra a mano, igual que `subscription_statuses`; esta API no publica
ningún endpoint para leerlo, crearlo ni modificarlo por separado. Que sea una tabla en vez de una
columna con `CHECK` no cambia esto.

## El script de reconciliación de tipos (FR-009, FR-010) no es una operación de esta API

`src/scripts/backfill_subscription_types.py` (ver [plan.md](../plan.md), [data-model.md](../data-model.md)
y [quickstart.md](../quickstart.md)) no expone ningún endpoint ni declara `x-required-permission`: es
un paso manual de despliegue, como `docker compose run --rm migrate`. Para leer los conteos de
clínicas necesita un token de acceso con el mismo permiso que ya exigía la API de clínicas para esa
consulta (`clinics-api-integration.md` de `001-subscriptions-api`); no introduce ningún permiso ni
credencial nueva, ni un permiso propio de `subscriptions:*`.

| Quién ejecuta el script | Token que debe pasarle |
|---|---|
| La persona que despliega esta feature | Uno vigente, de alguien con el permiso que la API de clínicas ya exige para leer conteos (igual que cualquier otra llamada a `get_counts`) |

La prueba `tests/contract/test_permission_coverage.py` sigue sin cambios: las 6 rutas y sus 4
permisos propios no se tocan (el script no es una ruta de esta API).
