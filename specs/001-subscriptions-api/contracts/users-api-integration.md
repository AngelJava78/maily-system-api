# Contrato consumido: API de usuarios (FR-001 a FR-005, Principios VIII y IX)

Este servicio **no verifica tokens**: reenvía el token de la persona al API de usuarios y obedece su
respuesta. Este documento fija lo que este servicio espera de él y cómo traduce cada respuesta. La
fuente de verdad del contrato es la especificación 008 del repositorio `mailySoft-usuarios`
(`specs/008-auth0-access-control/contracts/openapi-access-control.yaml`, operación `check_permission`).

## Operación consumida

```http
GET {USERS_API_BASE_URL}/api/v1/authorization/check?permission=subscriptions:read
Authorization: Bearer <el token tal como llegó>
Accept: application/json
```

- Se llama **una vez por petición protegida**, con el permiso exacto de la operación (ver
  [permission-matrix.md](permission-matrix.md)). El API de usuarios solo responde por la persona dueña
  del token.
- Formato del permiso: `^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$`, hasta 100 caracteres (los cuatro permisos
  `subscriptions:*` lo cumplen).
- Respuesta `200`: `{ "permission": "subscriptions:read", "allowed": true | false }`. El API de usuarios
  evalúa el permiso con datos vigentes (usuario Activo, rol Activo, permiso Activo), no con lo que traiga
  el token.

## Traducción de las respuestas

| Respuesta del API de usuarios | Resultado aquí | Se ejecuta la operación |
|---|---|---|
| `200`, `allowed: true` y `permission` igual al pedido | Continúa | Sí |
| `200`, `allowed: false` | `403 permission_denied` | No |
| `401` con `code` = `unauthenticated` | `401 unauthenticated` | No |
| `401` con `code` = `token_expired` | `401 token_expired` | No |
| `401` con `code` = `invalid_token` | `401 invalid_token` | No |
| `401` con cuerpo ilegible o `code` desconocido | `401 invalid_token` | No |
| `200` con cuerpo que no es JSON, sin `allowed` booleano o con otro `permission` | `503 authorization_unavailable` | No |
| `503` (`authentication_unavailable`), cualquier otro `5xx`, `429` | `503 authorization_unavailable` | No |
| Cualquier otro `4xx` (`403`, `404`, `422`…) | `503 authorization_unavailable` (y un registro de error en inglés con el estado, para detectar un contrato roto) | No |
| Cualquier `3xx` (redirección: **no se sigue**) | `503 authorization_unavailable` | No |
| Tiempo máximo agotado, conexión rechazada, error de red o de TLS | `503 authorization_unavailable` | No |

**Falla cerrada**: cualquier caso no listado es `503 authorization_unavailable`. Nunca se ejecuta una
operación por duda.

## Reglas de la integración

- **Reenvío**: la cabecera `Authorization` se reenvía sin modificar; no se reenvía ninguna otra cabecera
  de la petición original.
- **Sin caché ni reintentos** (research R2): cada petición protegida produce exactamente una llamada.
- **Sin redirecciones** (FR-024): el cliente no sigue redirecciones; una respuesta `3xx` cuenta como «no disponible» y el token jamás se envía a otra dirección.
- **Transporte** (FR-024): si `USERS_API_BASE_URL` usa `http://` y el host no es `localhost`, `127.0.0.1`, `::1` ni un nombre sin punto, el arranque registra una advertencia que nombra la variable (nunca la dirección); no impide arrancar.
- **Tiempo máximo total** de `USERS_API_TIMEOUT_SECONDS` (por defecto 5 s) con `asyncio.timeout` además
  del `Timeout` de `httpx`.
- **Token**: nunca aparece en un registro, mensaje de error ni respuesta. Se rechaza localmente, sin
  llamar, una petición sin cabecera, con esquema distinto de `Bearer` (`unauthenticated`) o con un token
  de más de 8 192 bytes (`invalid_token`).
- **Capas**: `src/integrations/users_api.py` (`UsersApiClient`) solo habla HTTP y lanza excepciones
  propias (`UsersApiRejectedToken(code)`, `UsersApiUnavailable`); `AuthorizationService` las traduce a
  los errores de la aplicación; `src/security.py` aplica el resultado como dependencia.
- **Orden**: la comprobación ocurre antes de validar los datos de la solicitud y de consultar la base de
  datos (research R4).

## Qué debe estar listo en el API de usuarios

1. La operación `GET /api/v1/authorization/check` publicada (spec 008).
2. Los permisos `subscriptions:read`, `subscriptions:write`, `subscriptions:update` y
   `subscriptions:delete` en su catálogo y asociados a los roles que correspondan.
3. Una dirección accesible desde este servicio (`USERS_API_BASE_URL`; en la pila local, otro puerto que
   el 8000 si ambos corren en el mismo equipo).

Mientras no esté listo, el desarrollo y las pruebas usan la simulación
([e2e-stubs.md](e2e-stubs.md)); sin API de usuarios, el servicio rechaza todo con
`503 authorization_unavailable`, que es el comportamiento especificado.
