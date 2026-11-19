# Pedido a mailySoft-usuarios: permisos del cobro de la suscripción y `tenant_id` del Dueño

**De**: quien mantiene maily-system-api. **Para**: quien mantiene mailySoft-usuarios. **Fecha**: 2026-11-18.

Texto listo para enviar. Pide cambios en **mailySoft-usuarios**. Lo necesita la feature 010 de
maily-system-api («Periodos de suscripción»: el control del periodo de prueba y del siguiente pago de cada
organización). **No bloquea el código de maily-system-api**: en sus pruebas, Usuarios se simula con el
contrato de siempre (`GET /api/v1/authorization/check`). Sí bloquea las pruebas con servicios reales y el
despliegue: **sin los permisos, toda petición recibe 403**.

---

## 1. Qué pide el negocio

Hoy nadie registra cuándo termina la prueba de una organización ni hasta cuándo está pagada. El frontend ya
promete en el alta «El pago se solicita al terminar la prueba». maily-system-api pasa a ser el dueño de ese
control: le dice al **Dueño** (rol Owner) de cada organización cuánto tiempo le queda de prueba y cuándo toca
pagar, y lo lleva a pagar a través de Pagos (Mercado Pago). Todo con **el token del Dueño**: maily-system-api
no se comunica con Auth0 ni tiene credenciales de máquina, así que a Clínicas y a Pagos solo les reenvía el
token de quien llama.

## 2. Lo que te pido

### 2.1 Los permisos de maily-system-api (dos)

- **`subscription_periods:read`**: consultar el estado de su organización (`GET
  /api/v1/subscription-periods/{organization_id}`).
- **`subscription_periods:write`**: iniciar el pago (`POST
  /api/v1/subscription-periods/{organization_id}/payments`).

Un módulo nuevo `subscription_periods` de tipo **Sistema** (como `organizations` o `subscriptions`), con las
acciones `read` y `write` de tu catálogo, y los dos permisos **asignados al rol Owner**. Va de tipo Sistema
porque un rol de Clínica sí puede recibir permisos de un módulo de Sistema (par (2,1), spec 015) y porque
no es un módulo de los que incluye un plan en el menú del frontend. Los nombres son una propuesta; si
prefieres otros, dímelo y los cambio.

### 2.2 Los permisos de Pagos para el Dueño (dos)

- **`payments:read`** y **`payments:write`** asignados al rol Owner. Pagos ya los exige
  (`mailySoft-pagos`, spec 001) y no existen en tu catálogo. Son necesarios porque maily-system-api
  **reenvía el token del Dueño** a Pagos: para crear el pago (`payments:write`) y para ver si se aprobó
  (`payments:read`). Pagos aísla los pagos por organización, así que el Dueño solo ve los de la suya.

(Opcional: `payments:refund` no hace falta para esta feature y **no** se pide para el Owner.)

### 2.3 `tenant_id` en `GET /api/v1/authorization/me`

Pagos exige que esa respuesta traiga la organización a la que pertenece la persona y hoy no la publicas.
Forma que Pagos ya espera (clave de primer nivel, siempre presente):

```json
{
  "user": { "...": "..." },
  "roles": [ { "...": "..." } ],
  "tenant_id": "0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b",
  "password_change_required": false
}
```

- `tenant_id` es el **identificador de la organización** (el mismo `organization_id` de Clínicas) a la que
  pertenece la persona, o `null` si no pertenece a ninguna (los roles de Sistema).
- Pagos lo usa como llave de aislamiento: sin él responde 403 `organization_required` y no deja crear ni
  ver pagos.
- **Cómo lo obtienes lo decides tú.** Hoy Usuarios no conoce las organizaciones (la pertenencia vive en
  Clínicas). Una forma posible: que el alta del Owner (`POST /api/v1/owner-accounts`, que Clínicas llama en el
  alta de la organización) reciba la organización y la guardes en el usuario. Si ya planeas el módulo de
  Organizaciones, es el mismo dato.

## 3. Cómo lo usa maily-system-api

1. Cada petición del Dueño a maily-system-api pregunta `GET /api/v1/authorization/check?permission=
   subscription_periods:read` (o `:write`) con su token; sin caché.
2. maily-system-api lee la organización en Clínicas con ese mismo token (Clínicas solo deja al Dueño leer la
   suya; otra responde 404) y, si es suya, sigue.
3. Para crear y consultar el pago reenvía el token a Pagos, que a su vez lo reenvía a Usuarios
   (`/authorization/me`) y comprueba `payments:write` / `payments:read` y el `tenant_id`.

maily-system-api **no** llama a `/authorization/me` y no necesita `tenant_id` para sí misma; lo necesita Pagos.

## 4. Criterios de aceptación, para tus pruebas

1. Con un token del Dueño, `GET /api/v1/authorization/check?permission=subscription_periods:read` responde
   `allowed: true`; con `subscription_periods:write`, también.
2. Con un token de un rol sin esos permisos (por ejemplo ClinicAdmin, Doctor o un rol de Sistema),
   responde `allowed: false`.
3. Con un token del Dueño, `GET /api/v1/authorization/check?permission=payments:read` y `payments:write`
   responden `allowed: true`; `payments:refund`, `false`.
4. `GET /api/v1/authorization/me` con un token del Dueño trae `tenant_id` con el UUID de su organización; con
   un rol de Sistema, `tenant_id: null`.
5. Los permisos se pueden dar a un rol de tipo Clínica (el Owner) porque su módulo es de tipo Sistema.
6. Un permiso quitado al rol deja de concederse en la siguiente consulta (sin caché).

## 5. Preguntas para ti

1. ¿Te acomodan los nombres `subscription_periods:read` / `subscription_periods:write` y el módulo
   `subscription_periods`, o prefieres otros?
2. ¿Módulo de tipo Sistema (lo que propongo) o de Clínica?
3. ¿Cómo piensas obtener el `tenant_id` de una persona (ver 2.3) y para cuándo? Es lo más largo de los tres
   pedidos.
4. ¿Los permisos `payments:*` los das al Owner en el mismo cambio, o hay una razón para separarlos?

## 6. Qué bloquea

| Pedido | Bloquea |
|---|---|
| 2.1 Permisos `subscription_periods:*` asignados al Owner | **Todo** contra servicios reales: sin ellos, las dos operaciones responden 403 `permission_denied` |
| 2.2 Permisos `payments:read` y `payments:write` para el Owner | Iniciar el pago (503) y verificar los cobros (la consulta responde 200 con «no se pudo verificar un cobro en curso») |
| 2.3 `tenant_id` en `/authorization/me` | Lo mismo que 2.2: Pagos responde 403 `organization_required` y maily-system-api lo trata como Pagos no disponible |

Nada de esto bloquea el desarrollo ni las pruebas automatizadas de maily-system-api, que usan simulaciones.
