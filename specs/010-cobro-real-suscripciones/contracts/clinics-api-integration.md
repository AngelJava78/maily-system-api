# Contrato consumido: API de clínicas — ampliación (FR-002, FR-003, FR-016, FR-017; research R6)

> **Estado: propuesta de este repositorio, igual que `specs/001-subscriptions-api/contracts/
> clinics-api-integration.md`.** El API de clínicas **no existe todavía como servicio real** (a
> diferencia de `mailySoft-usuarios`, que sí existe y solo le falta un permiso): esta operación es
> una propuesta de lo que `maily-system-api` necesita, a acordar con quien construya ese servicio.
> Hasta entonces, el desarrollo y las pruebas usan su simulación (`contracts/e2e-stubs.md`).

Amplía el contrato ya consumido de la spec 001 (`GET /api/v1/clinics/subscription-counts`, que no
cambia). Esta operación nueva es la pieza central del rediseño de esta spec (2026-11-11, Principio
IX): qué clínica tiene qué plan y con qué ciclo **es un dato de Clínicas**; `maily-system-api` lo
consulta en el momento de cobrar y no lo guarda.

## Operación consumida

```http
GET {CLINICS_API_BASE_URL}/api/v1/clinics/clinic-subscriptions/{clinic_subscription_id}
Authorization: Bearer <el token de quien disparó el cobro, tal como llegó>
Accept: application/json
```

- `clinic_subscription_id`: el identificador de Clínicas (propuesta: UUID), opaco para
  `maily-system-api` (igual que un `resource_id` de Pagos — nunca se interpreta, solo se reenvía).
- `200` esperado:

  ```json
  {
    "tenant_id": "3f1b1e2a-7c9d-4e2a-9c3e-1a2b3c4d5e6f",
    "subscription_id": 2,
    "billing_cycle": "monthly"
  }
  ```

  - `tenant_id`: la clínica, UUID.
  - `subscription_id`: el plan **del catálogo de `maily-system-api`** (`subscriptions`, spec 001) —
    Clínicas guarda esta referencia, pero el catálogo de planes y su precio siguen siendo propiedad
    de este servicio.
  - `billing_cycle`: `"monthly"` o `"annual"`.
  - Clínicas responde esto solo cuando la suscripción existe, no está cancelada y **pertenece a la
    organización de quien llama** (el token reenviado) — la misma regla de «solo mi organización»
    que ya sigue `mailySoft-usuarios` (spec 019) para la consulta de otro usuario.
- `404`: la suscripción no existe, está cancelada, o es de otra organización (los tres casos
  **indistinguibles** desde esta respuesta — Clínicas no revela cuál, igual que `mailySoft-usuarios`
  con `user_not_found`).

## Traducción de la respuesta (`ClinicsApiClient.get_clinic_subscription`)

| Respuesta de Clínicas | Resultado aquí |
|---|---|
| `200` con `tenant_id` (UUID), `subscription_id` (entero ≥ 1) y `billing_cycle` (`monthly`/`annual`) | Se devuelve `ClinicSubscriptionInfo(tenant_id, subscription_id, billing_cycle)` |
| `404` | `ClinicsApiNotFound` → el Service responde `404 clinic_subscription_not_found` (FR-003) |
| `401`/`403` | `ClinicsApiUnavailable` (igual que hoy: no hay credencial de servicio, se reenvía el token de la persona; un rechazo del lado de Clínicas no es un «no existe») |
| `200` con cuerpo que no es JSON, sin alguno de los tres campos, o con un tipo inesperado (`subscription_id` no entero, `billing_cycle` fuera de las dos opciones) | `ClinicsApiUnavailable` |
| `503`, cualquier otro `5xx`, `429`, `3xx` (no se sigue), tiempo agotado, error de red/TLS | `ClinicsApiUnavailable` |

`ClinicsApiUnavailable` (ya existente, reutilizada) → el Service responde `503` (FR-004): a
diferencia de `clinics_count` (un dato complementario de una lectura, que se degrada a `null`), esta
consulta es el núcleo de una escritura (el cobro) y **falla cerrada**, igual que Usuarios o Pagos.

## Reglas de la integración (iguales a las del contrato de `clinics_count`, no se repiten)

- Se reenvía el token de quien disparó el cobro; sin credenciales de servicio propias.
- `CLINICS_API_TIMEOUT_SECONDS` (la misma variable ya existente) acota también esta llamada; sin
  reintentos, sin caché, sin seguir redirecciones.
- Ni el cuerpo ni la dirección de Clínicas llegan al cliente de esta API; las fallas se registran (en
  inglés) sin el token ni el cuerpo.
- **Capas**: sigue viviendo en `src/integrations/clinics_api.py` (`ClinicsApiClient`, ya existente);
  el Service (`ClinicSubscriptionService`) decide cómo reaccionar a cada excepción (Principio I).

## Puntos a confirmar con quien construya el API de clínicas

1. Nombre y ruta de la operación (esta propuesta: `GET /api/v1/clinics/clinic-subscriptions/{id}`).
2. Que el `subscription_id` que guarda sea, de verdad, un identificador del catálogo de
   `maily-system-api` (no uno propio de Clínicas) — es la referencia cruzada que hace que esta
   especificación pueda calcular el precio.
3. Que no revele, en el `404`, si la suscripción existe en otra organización.
4. Cómo (y si) Clínicas necesitará enterarse del resultado de un cobro (Assumptions de la spec: fuera
   de alcance de esta entrega) — probablemente una pieza de la propia especificación de Clínicas.
