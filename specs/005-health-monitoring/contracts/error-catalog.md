# Contrato: catálogo de errores (FR-018, FR-030, FR-037)

Dos catálogos distintos que no se mezclan:

1. **Errores de la API** (cuerpo uniforme `ErrorResponse`: `code`, `message` y, en las validaciones,
   `errors`). La feature añade **2 códigos**: el enumerado `ErrorCode` pasa de 15 a **17**. Los 15 vigentes
   (catálogo de la [spec 004](../../004-correct-subscriptions-api/contracts/error-catalog.md)) no cambian.
2. **Códigos de error de componente** (campo `error` de cada componente del resultado de salud) y **de
   chequeo** (campo `error` de cada elemento de `checks`). No son errores de la API: la consulta de salud
   responde 200 y la degradación va por componente.

Los textos de este documento son **exactos**: `src/messages.py` los copia sin parafrasear y las pruebas los
comparan.

## 1. Errores de la API

### Códigos nuevos

| Código | HTTP | Cuándo | Mensaje |
|---|---|---|---|
| `monitored_component_not_found` | 404 | El componente no existe o está eliminado (consultar, modificar o eliminar) | «No se encontró el componente monitoreado con el identificador {component_id}.» |
| `monitored_component_code_already_exists` | 409 | Otro componente no eliminado usa el `code`, o es `maily-system-api` o `database` (reservados para los integrados) | «Ya existe un componente monitoreado con el código «{code}».» |

### Códigos vigentes que usan las operaciones nuevas

| Código | HTTP | En esta feature |
|---|---|---|
| `unauthenticated`, `token_expired`, `invalid_token` | 401 | Las seis operaciones protegidas (con `WWW-Authenticate`) |
| `permission_denied` | 403 | Ídem; el mensaje nombra el permiso (`health:read`, `health:write`, `health:update` o `health:delete`) |
| `authorization_unavailable` | 503 | Ídem (el API de usuarios no responde: falla cerrada) |
| `validation_error` | 422 | Las operaciones del registro (cuerpo, identificador, lista permitida, combinación resultante) |
| `internal_error` | 500 | Las operaciones del registro con la base de datos no disponible (FR-037), sin detalles; nada cambia |

Las cuatro rutas públicas no usan este catálogo: `/health/live`, `/info` y `/health/status` siempre
responden 200, y el 503 de `/health/ready` es la respuesta de disponibilidad del contrato v1
(`{"status":"unavailable","checks":[…]}`), no un error de la API. `GET /api/v1/health`, concedido el acceso,
siempre responde 200.

### Precedencia (FR-003, FR-030)

| Orden | Comprobación | Resultado |
|---|---|---|
| 0 | Cuerpo que no es JSON legible (alta y modificación) | 422 `validation_error` en `body`. **Excepción heredada de la spec 001**: FastAPI decodifica el cuerpo antes de las dependencias ([research R4](../research.md#r4-permiso-antes-de-validar-fr-003-fr-030-escenario-3-10)) |
| 1 | Identidad y permiso (API de usuarios) | 401 → 403 → 503 |
| 2 | Datos: identificador UUID, campos del DTO, campos desconocidos o no modificables, «al menos un dato», host de `base_url` en la lista permitida | 422 `validation_error` |
| 3 | Existencia (consultar, modificar, eliminar) | 404 `monitored_component_not_found` |
| 4 | Combinación resultante de una modificación (reglas por `kind`) | 422 `validation_error` |
| 5 | Código reservado o repetido entre los no eliminados (alta y modificación) | 409 `monitored_component_code_already_exists` |
| — | Base de datos no disponible, en cualquier paso que la use | 500 `internal_error`; nada cambia |

### Mensajes de validación del registro (recurso `monitored-components`)

Cada elemento de `errors` nombra el campo de la API; los mensajes no repiten el valor recibido (en
`base_url` podría traer credenciales) ni revelan la lista permitida.

| Campo | Problema | Mensaje |
|---|---|---|
| `code` | Ausente o vacío | «El código del componente es obligatorio.» |
| `code` | Formato o longitud | «El código debe tener de 2 a 50 caracteres entre minúsculas sin acentos, dígitos y guiones, empezar con una letra y no terminar en guion ni tener dos guiones seguidos.» |
| `name` | Ausente o vacío (tras recortar) | «El nombre del componente es obligatorio.» |
| `name` | Más de 100 caracteres | «El nombre del componente no puede tener más de 100 caracteres.» |
| `name` | No es texto | «El nombre del componente debe ser un texto.» |
| `kind` | Ausente | «El tipo del componente es obligatorio.» |
| `kind` | Otro valor (incluido `database`) | «El tipo del componente debe ser «service» o «frontend».» |
| `base_url` | Ausente o vacía | «La dirección base del componente es obligatoria.» |
| `base_url` | Formato (esquema, host, usuario o contraseña, `?`, `#`, longitud, caracteres) | «La dirección base debe ser una dirección http:// o https:// de hasta 255 caracteres, con un host válido y sin usuario, contraseña, consulta (?) ni fragmento (#).» |
| `base_url` | Host fuera de la lista permitida (o sin lista) | «El host de la dirección base no está entre los hosts permitidos por el servicio.» |
| `live_path`, `ready_path`, `info_path` | Formato | «La ruta debe empezar con una sola «/» y tener hasta 200 caracteres, sin segmentos «.» o «..» y sin «\», «?», «#», «%», espacios ni caracteres de control.» |
| `live_path`, `ready_path`, `info_path` | `null` en un `service` | «Un componente de tipo «service» necesita esta ruta: no puede ser nula.» |
| `live_path` | Ausente o `null` en un `frontend` | «Un componente de tipo «frontend» necesita su ruta de salud.» |
| `ready_path` | Con valor en un `frontend` | «Un componente de tipo «frontend» no lleva ruta de disponibilidad: envíela nula o no la envíe.» |
| `enabled` | No es booleano | ««enabled» debe ser verdadero o falso.» |
| `sort_order` | No es entero o fuera de 0–9999 | «El orden debe ser un número entero de 0 a 9999.» |
| `body` | Modificación sin ningún dato | «Hay que enviar al menos un dato para modificar.» (mismo texto que en suscripciones) |
| (cualquiera) | Campo no reconocido o no modificable (`id`, `created_at`, `updated_at`, `deleted_at`…) | «El campo «{field}» no está permitido.» (mensaje vigente) |
| `component_id` | No es un UUID | «El identificador del componente debe ser un UUID.» |
| `body` | Cuerpo ilegible | «El cuerpo de la solicitud no es válido.» (mensaje vigente) |

Implementación: las reglas de formato las lanzan los validadores de los DTOs como `ValueError` con el texto
en español (patrón vigente de `SubscriptionStatusChange`); el resto, `VALIDATION_MESSAGES["monitored-components"]`.
Los 422 que decide el Service (lista permitida y reglas por `kind`, en el alta y en el resultado de una
modificación) se lanzan como errores de dominio con el formato de Pydantic y los traduce el mismo
`translate_validation_errors`, así el cuerpo es idéntico al de la validación de FastAPI. El tipo de error `uuid_parsing` se añade a `_KINDS` (como `invalid`); hoy
ninguna operación recibe un UUID, así que no cambia ningún mensaje vigente.

## 2. Códigos de error de componente (campo `error` del resultado de salud, FR-018)

Lista cerrada, en inglés; el Backoffice los explica en español. Agregar un código es un cambio compatible
que se documenta; quitar o renombrar uno no lo es.

| Código | Significado | Aparece en | Estado del componente |
|---|---|---|---|
| `timeout` | No respondió dentro de `HEALTH_CHECK_TIMEOUT_SECONDS` | servicios, frontends, base de datos | `down` (en `live`), `degraded` (en `ready`), `down`/`stopped` (base) |
| `connection_error` | Conexión rechazada o cortada, error de TLS o certificado no válido | servicios, frontends, base de datos | Ídem |
| `dns_error` | El nombre del host no se pudo resolver | servicios, frontends | `down` (`live`) o `degraded` (`ready`) |
| `host_not_allowed` | Su host ya no está en la lista permitida; no se le llamó | servicios, frontends | `unknown` |
| `unexpected_status` | Código HTTP no previsto, incluidas las redirecciones (no se siguen) | servicios, frontends | `down` (`live` o frontend) o `degraded` (`ready`) |
| `invalid_response` | El cuerpo no es el del contrato v1 (no es JSON, por ejemplo HTML; le faltan campos o tienen otro tipo; o viene comprimido) | servicios | `down` (`live`) o `degraded` (`ready`) |
| `response_too_large` | La respuesta superó 64 KiB | servicios | `down` (`live`) o `degraded` (`ready`) |
| `not_ready` | Vivo, pero su `/health/ready` respondió 503 conforme al contrato (en `maily-system-api`: la base de datos no respondió) | servicios | `degraded` |
| `unexpected_error` | Cualquier otra falla del chequeo; si la falla es del propio agregador y no permite saber el estado | todos | `down`/`degraded` según la llamada, o `unknown` si es del agregador |

Un componente `up` tiene `error` `null`. La base de datos `stopped` conserva la causa observada (por
ejemplo, `connection_error`). Una falla de `/info` nunca produce un código: solo deja los datos de build en
`unknown`.

## 3. Códigos de error de chequeo (campo `error` de `checks`, contrato v1)

`null` (chequeo `ok`), `timeout`, `connection_error`, `not_configured` o `unexpected_error`. En su propio
`/health/ready` este servicio emite `timeout`, `connection_error` y `unexpected_error`; nunca
`not_configured` (no arranca sin `DATABASE_URL`). El agregador acepta los cinco en los chequeos de los demás y convierte cualquier otro valor
en `unexpected_error` (FR-013).
