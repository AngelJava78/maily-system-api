# Pedido a mailySoft-clinicas: exponer el periodo de cobro de la organización

**De**: quien mantiene maily-system-api. **Para**: quien mantiene mailySoft-clinicas. **Fecha**: 2026-11-18.

Texto listo para enviar. Pide **un campo** en una lectura de **mailySoft-clinicas**. Lo necesita la feature
010 de maily-system-api («Periodos de suscripción»). **No bloquea el código de maily-system-api**: en sus
pruebas, Clínicas se simula con el contrato que propongo abajo. Sí bloquea las pruebas con servicios reales
y el despliegue: **sin el campo, las dos operaciones nuevas responden 503**.

---

## 1. Qué pide el negocio

maily-system-api va a decirle al Dueño de cada organización cuánto tiempo le queda de prueba y cuándo toca
pagar, y a cobrarle. El importe depende del **plan** de la organización y de su **periodo de cobro**
(mensual o anual). Del plan ya te pregunto lo que necesito (`subscription_id`); el periodo de cobro lo
guardas tú (`organizations.billing_period`, feature 010 de Clínicas, autoservicio de alta) pero **ninguna
lectura lo publica**. maily-system-api no puede guardar una copia (Principio IX: lo que es de otro API se le
pide en cada uso), así que necesita leerlo de ti.

## 2. Lo que te pido

### 2.1 `billing_period` en la lectura de una organización

Añadir a `OrganizationRead` (la respuesta de `GET /api/v1/organizations/{id}`) el campo:

```json
{
  "id": "0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b",
  "subscription_id": 3,
  "billing_period": "monthly",
  "created_at": "2026-11-20T15:30:00Z"
}
```

- `billing_period`: `"monthly"` o `"annual"` (los valores que ya guardas, con su `CHECK`).
- Siempre presente, nunca `null` (la columna es `NOT NULL`).
- Es un campo **aditivo**: no cambia nada de lo que ya devuelve la operación.
- Mismo permiso (`organizations:read`) y mismas reglas de acceso: el Owner solo lee su organización; otra,
  `404 not_found`.

### 2.2 (Opcional, no bloquea) Una fecha de alta más fiable

Hoy tomo `created_at` de la organización como «la fecha de alta» (cuándo empieza su primera prueba). Si el
alta del Dueño suele tardar o reintentarse (`pending_owner`), la prueba contaría desde antes de que la
persona pueda entrar. Si te parece útil, expón la fecha en que el alta se completó (por ejemplo
`onboarding.completed_at`) y, cuando exista, la uso en lugar de `created_at`. **No lo necesito para salir**;
es solo para que lo tengas presente.

## 3. Cómo lo usa maily-system-api

Una llamada por petición del Dueño, con **su token reenviado**:

```http
GET {CLINICS_API_BASE_URL}/api/v1/organizations/{organization_id}
Authorization: Bearer <token del Dueño>
```

- `200`: uso `id`, `subscription_id`, `billing_period` y `created_at`. Valido la forma con rigor: sin
  `billing_period` (o con un valor distinto de `monthly`/`annual`) la respuesta me parece inesperada y
  respondo 503 (no supongo «mensual»).
- `404` con `{"code": "not_found"}`: respondo 404 a la persona, sin decir si la organización existe.
- Cualquier otra cosa (sin respuesta, 401, 403, 5xx…): respondo 503 y no hago nada.

No uso `GET /api/v1/clinics` («mis clínicas»); es la aplicación la que toma de ahí el `organization_id`.

## 4. Criterios de aceptación, para tus pruebas

1. `GET /api/v1/organizations/{id}` con el token del Dueño de esa organización devuelve `billing_period` igual
   al guardado (`monthly` o `annual`).
2. Con el token del Dueño de **otra** organización, `404 not_found` (igual que hoy), sin `billing_period`.
3. Con un rol de Sistema con `organizations:read`, también devuelve `billing_period`.
4. Una organización dada de alta por el autoservicio con `billing_period: "annual"` lo devuelve como
   `"annual"`; una anterior a esa feature (migrada con el valor por defecto) lo devuelve como `"monthly"`.
5. Los demás campos de la respuesta no cambian.
6. El esquema OpenAPI de `OrganizationRead` lo declara como obligatorio, con sus dos valores.

## 5. Preguntas para ti

1. ¿Te acomoda el nombre `billing_period` también en la respuesta (es el mismo del alta y de la columna)?
2. Las organizaciones anteriores a tu feature 010 quedaron con `monthly` por el valor por defecto de la
   migración: ¿es el valor correcto para cobrarles o hay que revisarlo antes de que maily-system-api empiece a
   cobrar? (Yo lo leeré tal cual.)
3. (Opcional) ¿Puedes exponer la fecha en que se completó el alta? (sección 2.2)

## 6. Qué bloquea

| Pedido | Bloquea |
|---|---|
| 2.1 `billing_period` en `GET /api/v1/organizations/{id}` | Las dos operaciones nuevas contra servicios reales (consultar el estado e iniciar el pago): sin él, 503 `organization_check_unavailable` |
| 2.2 Fecha de alta completada | Nada (mejora opcional) |

Nada de esto bloquea el desarrollo ni las pruebas automatizadas de maily-system-api, que usan una
simulación de Clínicas con el campo ya incluido.
