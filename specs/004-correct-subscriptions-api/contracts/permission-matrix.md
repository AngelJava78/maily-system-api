# Contrato: matriz operación → permiso (delta sobre `001-subscriptions-api`)

**Sin cambios** en las 6 operaciones propias de esta API ni en sus 4 permisos: ver
[specs/001-subscriptions-api/contracts/permission-matrix.md](../../001-subscriptions-api/contracts/permission-matrix.md).
Esta feature no añade, quita ni renombra ninguna operación ni ningún permiso de
`subscriptions:*`.

## Permiso externo adicional que esta feature pasa a necesitar (no es un permiso propio)

`create_subscription` y `update_subscription` reenvían el token de la persona a la API de usuarios
para validar los módulos (`GET /api/v1/modules`, research R4), que exige el permiso `modules:read` de
**esa** API. No es un permiso de `subscriptions:*` ni algo que esta API declare con
`x-required-permission`: es un requisito operativo del lado de la API de usuarios.

| Quién necesita `modules:read` | Por qué |
|---|---|
| El rol con `subscriptions:write` | Para poder crear una suscripción que pida algún módulo además de `patients` |
| El rol con `subscriptions:update` | Para poder actualizar los módulos de una suscripción |

Si ese rol no tiene `modules:read`, la API de usuarios responde `403` a la consulta de módulos, que
esta API traduce como `503 module_check_unavailable` (research, contracts/users-api-integration.md):
**no** se puede distinguir, desde aquí, entre «la API de usuarios no respondió» y «el rol no tiene el
permiso», porque ambos casos deben fallar cerrado de la misma forma (Principio VIII). Confirmar este
permiso es uno de los «Puntos a confirmar fuera de este repositorio» de [plan.md](../plan.md).

La prueba `tests/contract/test_permission_coverage.py` sigue sin cambios: las 6 rutas y sus 4
permisos propios no se tocan.
