# Contrato: matriz operación → permiso (delta sobre `006-add-subscription-type`)

**Sin cambios.** Ver
[specs/001-subscriptions-api/contracts/permission-matrix.md](../../001-subscriptions-api/contracts/permission-matrix.md).
Esta feature no añade, quita ni renombra ninguna operación ni ningún permiso de `subscriptions:*`:
`clinics_limit` se valida con el mismo permiso que ya exigía cada operación (`subscriptions:write`
al crear, `subscriptions:update` al intentar modificarlo, igual si la solicitud se rechaza por ser
una suscripción Individual).

La prueba `tests/contract/test_permission_coverage.py` sigue sin cambios: las 6 rutas y sus 4
permisos propios no se tocan.
