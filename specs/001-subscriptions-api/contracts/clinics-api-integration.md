# Contrato consumido: API de clínicas (FR-008, FR-009, FR-017, Principio IX)

> **Estado: propuesta de este repositorio.** El API de clínicas no está especificado aquí (la spec
> delegó su contrato a la planificación). Este documento fija lo que **este servicio necesita** de él;
> debe acordarse con quien lo mantenga (ver «Puntos a confirmar»). Hasta entonces, las pruebas usan su
> simulación ([e2e-stubs.md](e2e-stubs.md)) y, sin el API, el conteo sale como «no disponible».

El número de clínicas de una suscripción es un dato **ajeno**: se consulta en cada lectura y **no se
guarda** aquí.

## Operación consumida

```http
GET {CLINICS_API_BASE_URL}/api/v1/clinics/subscription-counts
GET {CLINICS_API_BASE_URL}/api/v1/clinics/subscription-counts?subscription_id=1&subscription_id=2
Authorization: Bearer <el token de la persona, tal como llegó>
Accept: application/json
```

- Sin `subscription_id` devuelve el conteo de **todas** las suscripciones que tienen al menos una clínica;
  con uno o varios, solo el de esas.
- `200`:

```json
{
  "items": [
    { "subscription_id": 1, "clinics_count": 2 },
    { "subscription_id": 6, "clinics_count": 14 }
  ]
}
```

- Solo aparecen las suscripciones con `clinics_count >= 1`. **Una suscripción que no aparece tiene 0
  clínicas** (el API respondió, así que el cero es verdadero). `subscription_id` es el identificador de
  esta API; `clinics_count` es un entero ≥ 1. «Clínicas de una suscripción» = las que la tienen asignada,
  con la definición que aplique el API de clínicas.

## Uso y degradación

| Operación de este servicio | Consulta | Si falla (tiempo, red, 4xx/5xx, cuerpo inesperado, 401/403) |
|---|---|---|
| `list_subscriptions` | Sin filtro, **en paralelo** con la base de datos | Todas devuelven `clinics_count: null`; el listado es `200` |
| `get_subscription`, `update_subscription`, `change_subscription_status` | `subscription_id=<id>`, tras leer/escribir la base de datos | `clinics_count: null`; la operación es exitosa |
| `create_subscription` | **Ninguna**: una suscripción nueva no puede tener clínicas | — (`clinics_count: 0`) |
| `delete_subscription` | `subscription_id=<id>`, tras comprobar que existe | `503 clinics_check_unavailable`; no se elimina |
| `delete_subscription` con `clinics_count >= 1` | idem | `409 subscription_has_clinics`; no se elimina |

«Falla» incluye cualquier respuesta que no sea `200` con el cuerpo descrito (por ejemplo `items` con un
`subscription_id` que no se pidió, un `clinics_count` no entero o negativo, o dos elementos con el mismo
`subscription_id`): se trata como **no disponible**, nunca como cero.

## Reglas de la integración

- **Autenticación**: se reenvía el token de la persona. No hay credenciales de servicio, secretos
  nuevos ni comunicación con Auth0 (Principio VIII). Consecuencia: el API de clínicas decide si esa
  persona puede leer los conteos (p. ej. con un permiso `clinics:read` de su catálogo); una respuesta
  `401` o `403` es «no disponible» aquí.
- **Tiempo máximo total** de `CLINICS_API_TIMEOUT_SECONDS` (por defecto 5 s); **sin reintentos**.
- **Sin caché** del conteo.
- **Errores**: ni el cuerpo ni la dirección del API de clínicas llegan al cliente; las fallas se registran
  (en inglés) con la operación y el estado, sin el token ni el cuerpo.
- **Capas**: `src/integrations/clinics_api.py` (`ClinicsApiClient`) solo habla HTTP, valida la forma de
  la respuesta y lanza `ClinicsApiUnavailable`; el Service decide cómo degradar (Principio I).

## Puntos a confirmar con quien mantenga el API de clínicas

1. Nombre y ruta de la operación (esta propuesta: `GET /api/v1/clinics/subscription-counts`).
2. Que acepte el token de la persona y el permiso que exige.
3. Que **no asigne** suscripciones Eliminadas (consulta de estatus) para cerrar la carrera entre la
   comprobación de clínicas y la baja (research R7).
4. Si el conteo incluye clínicas inactivas o bloqueadas (hoy se muestra lo que el API devuelva).
