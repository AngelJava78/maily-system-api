# Contrato consumido: API de clínicas (FR-003, FR-047, FR-050; Principio IX)

> **Estado**: la operación **existe hoy**; lo que falta es **un campo** (`billing_period`), que se pide en
> [pedidos-clinicas.md](pedidos-clinicas.md). Hasta que Clínicas lo publique, esta API responde 503 contra el
> servicio real; las pruebas usan la simulación (`tests/stubs/clinics_api`), que ya lo trae.

La organización, su plan vigente, su periodo de cobro y su fecha de alta son datos **ajenos**: se leen en
cada uso y **no se guardan** (FR-042). Esta API guarda solo el identificador de la organización, como llave
de sus datos propios.

## Operación consumida

```http
GET {CLINICS_API_BASE_URL}/api/v1/organizations/{organization_id}
Authorization: Bearer <el token de la persona, tal como llegó>
Accept: application/json
```

- **Quién puede leer** (evidencia: `mailySoft-clinicas/src/routers/organizations.py` y
  `services/organization_queries_service.py`): exige el permiso `organizations:read`; un rol de sistema lee
  cualquier organización; **un rol de clínica solo la organización cuyo Owner es el usuario del token**, y
  cualquier otra responde `404`. Por eso un `200` a este token prueba que la persona es el Dueño (FR-003).
- `200` con un objeto JSON. Esta API usa **solo** estos campos (el resto se ignora):

```json
{
  "id": "0f4e2b9a-6d1c-4f7e-9a3b-5c8d7e6f1a2b",
  "subscription_id": 3,
  "billing_period": "monthly",
  "created_at": "2026-11-20T15:30:00Z"
}
```

| Campo | Qué es | Estado | Validación estricta de esta API |
|---|---|---|---|
| `id` | La organización | Existe | UUID **igual** al pedido |
| `subscription_id` | El plan vigente (id del catálogo de esta API) | Existe | Entero ≥ 1, no booleano |
| `created_at` | La fecha de alta | Existe | ISO 8601 **con zona** (se normaliza a UTC) |
| `billing_period` | El periodo de cobro elegido | **Falta** (Clínicas lo guarda en `organizations` pero ninguna lectura lo expone) | `monthly` o `annual`; cualquier otro valor o su ausencia → «no disponible» |

- `404` con cuerpo `{"code": "not_found", ...}`: la organización no existe o no es de la persona → esta API
  responde `404 organization_not_found`.

## Uso y degradación (FR-003, FR-035)

| Resultado de la llamada | Respuesta de esta API |
|---|---|
| `200` válido | Continúa |
| `404` con `code: "not_found"` | `404 organization_not_found` |
| Sin respuesta, tiempo agotado, error de red | `503 organization_check_unavailable` |
| `401`, `403`, `5xx`, cualquier otro estado, redirección (`3xx`, **no se sigue**) | `503 organization_check_unavailable` |
| `404` con otro código o sin cuerpo JSON (por ejemplo, una ruta que su versión no tiene) | `503 organization_check_unavailable` |
| `200` con un cuerpo ilegible, sin alguno de los cuatro campos o con un valor inválido (**incluido el `billing_period` ausente**) | `503 organization_check_unavailable` |

«Falla» nunca se convierte en un dato inventado: no se supone un periodo de cobro por omisión (FR-037) y el
acceso falla cerrado.

## Reglas de la integración

- **Autenticación**: se reenvía el token de la persona. No hay credenciales de servicio, secretos nuevos ni
  comunicación con Auth0 (Principio VIII; FR-005). Todo lo que se pide se obtiene con el token de un Dueño.
- **Tiempo máximo total** de `CLINICS_API_TIMEOUT_SECONDS` (5 s por defecto); **sin reintentos**; **sin
  caché**.
- **Sin redirecciones**: el cliente HTTP compartido no las sigue; el token jamás viaja a otra dirección.
- **Errores**: el cuerpo, la dirección y el token de Clínicas nunca llegan al cliente ni a los registros;
  solo se registra el tipo de falla y el estado.
- **Capas**: `ClinicsApiClient.get_organization` (en `src/integrations/clinics_api.py`) solo habla HTTP,
  valida la forma de la respuesta y devuelve un `OrganizationRecord` o lanza `OrganizationNotFound` /
  `ClinicsApiUnavailable`; el Service decide qué error devolver.

## Lo que la aplicación hace con «mis clínicas»

`GET /api/v1/clinics` (permisos `clinics:read` u `organizations:read`) devuelve, para un rol de clínica, las
clínicas a las que pertenece, cada una con su `organization_id`. **Esta API no lo consume**: es la aplicación
la que lo usa para obtener el identificador de la organización que envía a esta API.

## Puntos a confirmar con quien mantenga el API de clínicas

1. Que `GET /api/v1/organizations/{id}` exponga `billing_period` (pedido principal).
2. Que el 404 de «no es tuya» siga siendo idéntico al de «no existe» (hoy lo es).
3. (Opcional, D5) La fecha en que el alta de la organización se completó, si el alta del Dueño suele tardar.
