# Contrato: salud de Maily v1 (lo que este servicio implementa y lo que consume)

Común a mailySoft-usuarios 016, mailySoft-pacientes 008 y esta spec. Cualquier cambio de rutas, campos o
códigos se hace en las tres a la vez y se avisa al Backoffice (spec, «Dependencias»). El estado público
`GET /health/status` **no** forma parte de v1: solo lo ofrece este servicio
([openapi-health.yaml](openapi-health.yaml)). El contrato consumido de cada servicio queda documentado aquí,
como pide el Principio IX.

## 1. Rutas del contrato (en la raíz, fuera de `/api/v1`, sin token)

Reglas comunes: responden con `Cache-Control: no-store`; campos en inglés; fechas ISO 8601 UTC con `Z`; sin
secretos, nombres de host, direcciones, cadenas de conexión, mensajes de excepción ni trazas; en este
servicio, con las cabeceras CORS de la API para los orígenes de `CORS_ALLOWED_ORIGINS` (FR-050).

### `GET /health/live`

- **200** `{"status":"ok"}` mientras el proceso atienda HTTP, sin consultar ninguna dependencia, en menos de
  100 ms. Sirve también como *startup probe*.

### `GET /health/ready`

- Comprueba **solo** la base de datos con una consulta trivial (`SELECT 1`), con un límite total de
  `HEALTH_READY_TIMEOUT_SECONDS` (2 s por defecto). No consulta otros servicios HTTP ni tiene en cuenta el
  horario de la base de datos.
- **200** si responde y **503** si no, con el mismo cuerpo:

  ```json
  {"status": "ok", "checks": [{"name": "database", "status": "ok", "latency_ms": 12, "error": null}]}
  {"status": "unavailable", "checks": [{"name": "database", "status": "error", "latency_ms": 2001, "error": "timeout"}]}
  ```

- `latency_ms`: entero ≥ 0, la duración del chequeo, también cuando falla.
- `error`: `null`, `timeout`, `connection_error`, `not_configured` o `unexpected_error`. `not_configured` es
  para los servicios que pueden arrancar sin base de datos configurada (pacientes 008); este servicio no lo
  emite. Una falla inesperada es `unexpected_error` con 503, nunca un 500.

### `GET /info`

- **200** `{"service":"maily-system-api","version":"2.0.0","commit":"<sha>"|"unknown","build_date":"<ISO 8601 UTC>"|"unknown","environment":"<nombre>"|"unknown"}`.
- `version`: la de `src.VERSION`, igual al OpenAPI y a `pyproject.toml`. `commit`, `build_date` y
  `environment` salen de `APP_COMMIT_SHA`, `APP_BUILD_DATE` (inyectadas al construir la imagen) y
  `APP_ENVIRONMENT` (al desplegar); sin ellas, `unknown`.

## 2. Cómo interpreta el agregador a los demás servicios (`kind` `service`)

Llamadas: `GET {base_url}{live_path}`, `GET {base_url}{ready_path}` y `GET {base_url}{info_path}` en
paralelo, cada una con un límite total de `HEALTH_CHECK_TIMEOUT_SECONDS` (3 s por defecto; incluye DNS,
conexión y lectura), sin reintentos, sin seguir redirecciones, leyendo a lo más 64 KiB, con
`Accept-Encoding: identity`, sin el token de la persona ni ninguna cabecera de la petición original, sin
cookies y con verificación TLS. El host de cada dirección es siempre el de `base_url` y debe estar en
`HEALTH_ALLOWED_HOSTS`.

| Respuesta observada | Interpretación |
|---|---|
| `live` 200 con objeto JSON y `status` `ok` | Vivo |
| `live` con otro código (incluido un 3xx) | `down`, `unexpected_status` |
| `live` 200 con HTML, texto u objeto sin `status` `ok` | `down`, `invalid_response` |
| `live` sin respuesta en el límite / conexión / DNS / > 64 KiB | `down`, `timeout` / `connection_error` / `dns_error` / `response_too_large` |
| Vivo y `ready` 200 con `status` `ok` y `checks` | `up` |
| Vivo y `ready` 503 con `status` `unavailable` y `checks` | `degraded`, `not_ready` y sus `checks` depurados |
| Vivo y `ready` con otro código o cuerpo, o falla de red | `degraded` con el código de esa falla |
| `info` 200 con objeto JSON | `version`, `commit`, `build_date` y `environment` depurados (cada campo inválido → `unknown`) |
| `info` con cualquier otra cosa | Los cuatro en `unknown`; el estado no cambia |

Depuración (FR-013): solo campos conocidos; textos sin caracteres de control y cortados a 64 caracteres;
`build_date` válida con zona y normalizada a UTC; a lo más 20 chequeos; chequeos sin `name` de texto o con
otro `status` se descartan; un `error` fuera de la lista de arriba → `unexpected_error`. Nunca se devuelve
el cuerpo crudo.

## 3. Frontends (`kind` `frontend`)

- `GET {base_url}{live_path}`: solo cuenta el código de estado; el cuerpo no se lee. 2xx → `up`; cualquier
  otro (incluido un 3xx) → `down` con `unexpected_status`; falla de red → `down` con su código.
- La ruta de salud debe existir de verdad: con una ruta inexistente, un *catch-all* que responde 200 con
  `index.html` haría parecer sano al frontend. Para MailySoft (servido por Maily360) es `/healthz/`, **con**
  barra final: `/healthz` puede redirigir y dejaría el frontend `down`.
- `info_path` es opcional y solo cuenta si responde el JSON de `/info`; MailySoft no tiene: su versión es
  `unknown` (decisión 4 de la spec).

## 4. Coordinación entre servicios

- **Tiempos**: el `HEALTH_READY_TIMEOUT_SECONDS` de cada servicio (2 s) debe ser menor que el
  `HEALTH_CHECK_TIMEOUT_SECONDS` del agregador (3 s): así el agregador recibe el 503 con el detalle en vez de
  agotar su tiempo y marcar el servicio `down`. Quien opera conserva esa relación.
- **Nombres de variables**: iguales en los tres servicios (`HEALTH_READY_TIMEOUT_SECONDS`, `APP_COMMIT_SHA`,
  `APP_BUILD_DATE`, `APP_ENVIRONMENT`). Las reglas de valores pueden variar por servicio (pacientes 008
  acepta decimales y no se niega a arrancar con un valor inválido).
- **Base de datos compartida detenida**: los servicios que dependen de ella responden `ready` 503 y
  aparecen `degraded` (siguen vivos), mientras que el componente `database` aparece `stopped`.
- **Registro**: para monitorear un microservicio nuevo basta con que cumpla este contrato, que su host esté
  en `HEALTH_ALLOWED_HOSTS` y registrarlo desde el Backoffice; no hace falta redesplegar este servicio.

## 5. Simulaciones para las pruebas

`tests/stubs/components/app.py` imita, por prefijo de ruta, cada comportamiento de las tablas anteriores
(sano, `ready` 503, 200 con HTML, cuerpo que no es JSON, redirección, lento, respuesta de más de 64 KiB,
`info` incompleto, frontend) y registra las cabeceras recibidas para comprobar que nunca llega un token. Las
fallas de DNS y de conexión las produce un transporte de pruebas ([research R20](../research.md#r20-pruebas-principio-v-fr-041-fr-049)).
Detalle de la pila de punta a punta: [e2e-collection.md](e2e-collection.md).
