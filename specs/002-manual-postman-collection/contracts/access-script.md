# Contrato: script de acceso (pre-request de la colección)

**Ubicación**: `event[listen=prerequest]` de la colección manual (único; ver [research.md](../research.md) M14) |
**Spec**: FR-009 a FR-012, FR-004, FR-014, FR-017 | **Evidencia**: prototipo en Newman 6.2.3, 25 escenarios
(M2 a M8)

El script corre antes de **cada** petición de la colección y decide una cosa: **sale o se omite**
(`pm.execution.skipRequest()`). Nunca lanza errores para parar (M2) y no usa `await` (M4).

## Contrato con el exterior

| Entrada | De dónde |
|---|---|
| `baseUrl`, `auth0Domain`, `auth0Audience`, `auth0ClientId`, `auth0ClientSecret`, `plainClientId`, `plainClientSecret` | entorno activo (`pm.environment`) |
| Autenticación efectiva, método, URL y cuerpo en bruto de la petición | `pm.request` |
| Token, vencimiento y clave de cada identidad; datos de la sesión | variables de colección ([data-model.md](../data-model.md)) |

| Salida | Efecto |
|---|---|
| Petición lista | no hace nada más; borra `accessProblem` |
| Petición omitida | `console.error("[Colección manual] <mensaje>")`, `accessProblem = <mensaje>` y `skipRequest()` |
| Token nuevo | escribe `…Token`, `…TokenExpiresAt`, `…TokenKey` en variables de colección |
| Contacto externo | `POST https://{auth0Domain}/oauth/token` y, antes de modificar, `GET {baseUrl}/api/v1/subscriptions/{id}`. **Nada más** (FR-012) |

## Algoritmo (orden fijo)

1. **Datos de otra API**: si `sessionApi` ≠ `baseUrl`, se borran `subscriptionId`, `subscriptionName`,
   `otherSubscriptionId`, `otherSubscriptionName`, `deletedSubscriptionId` y se guarda `sessionApi = baseUrl`.
2. **Identidad** de la petición según `pm.request.auth` (M7): hereda → `accessToken`; `noauth` → ninguna;
   Bearer `{{plainToken}}` → `plainToken`; Bearer `{{badToken}}` → inventado; cualquier otra → ninguna.
3. **Variables sin valor**: antes, si la URL o el cuerpo usan `{{newSuffix}}`, se genera uno nuevo y se guarda
   (la petición no necesita un pre-request propio: correría después de este script). Después, toda `{{variable}}` (nombres `\w+`; las dinámicas `{{$…}}` no cuentan) de la **URL y del
   cuerpo en bruto** debe tener valor; si no → omitir con A-09.
4. **Token** (solo `accessToken` y `plainToken`):
   - `plainToken` sin `plainClientId`/`plainClientSecret` → omitir con A-08 (opcional, no es fallo).
   - Faltan `auth0Domain`, `auth0Audience`, el cliente o su secreto → A-01. Dominio con esquema o barras → A-02.
   - Si la clave `dominio|audience|clientId` coincide y quedan **más de 60 s** → se reutiliza.
   - Si no, se pide a Auth0 (M6) y se traduce el resultado (A-03 a A-07). Éxito → se guardan los tres valores.
   - `badToken`: se genera `invalid-<aleatorio>`, sin llamar a Auth0.
5. **Propiedad** (M8.2): si el método es `PATCH`, `PUT` o `DELETE` y la URL usa `{{subscriptionId}}` o
   `{{otherSubscriptionId}}`, se hace `GET` de esa suscripción con el token principal y se exige: existe (A-10), se pudo
   comprobar (A-11), hay un nombre guardado (A-12) y es el mismo (A-13). Si no, se omite.
6. **Salir**: sin problema → `accessProblem` se borra y la petición sale.

## Catálogo de mensajes (español, sin secretos ni tokens)

Prefijo común en consola: `[Colección manual] `. Los textos son los del prototipo salvo A-12, que es nuevo.

| Id | Cuándo | Mensaje |
|---|---|---|
| A-01 | faltan valores | `No se pudo obtener el token: faltan valores en el entorno activo (<nombres>). Rellénalos; el secreto solo en tu copia local de la variable, nunca en un valor que se sincronice.` |
| A-02 | dominio con esquema/barras | `auth0Domain debe ir sin «https://» ni barras (por ejemplo, mi-tenant.us.auth0.com).` |
| A-03 | Auth0 no responde | `No se pudo obtener el token: Auth0 no respondió. Revisa auth0Domain («<dominio>») y tu conexión a internet.` |
| A-04 | 401 | `No se pudo obtener el token: Auth0 rechazó las credenciales de <la aplicación de acceso>. Revisa <idVar> y <secretVar>.` |
| A-05 | 403 | `No se pudo obtener el token: Auth0 no autoriza a <la aplicación> para el destinatario «<audience>». Revisa auth0Audience (debe ser idéntico al identificador de la API de usuarios, incluida la barra final) y que la aplicación esté autorizada para esa API en Auth0.` |
| A-06 | 429 | `No se pudo obtener el token: Auth0 limitó las solicitudes. Espera un minuto y vuelve a enviar.` |
| A-07 | otra respuesta | `No se pudo obtener el token: Auth0 respondió algo inesperado (HTTP <estatus>). Revisa auth0Domain y auth0Audience.` |
| A-08 | segunda app sin configurar | `No se envió la petición (opcional): para usarla configura plainClientId y plainClientSecret en el entorno con la segunda aplicación de acceso (sin permisos). Consulta el README, apartado «Persona sin permisos».` |
| A-09 | variable sin valor | `No se envió la petición: la variable «<nombre>» no tiene valor. <pista>` (pistas: `subscriptionId`, `otherSubscriptionId`, `deletedSubscriptionId`, `baseUrl`, `clinicsStubUrl`; por defecto «Revisa el entorno activo y las peticiones anteriores de la carpeta.») |
| A-10 | la guardada no existe | `No se envió la petición: la suscripción <id> ya no existe en este entorno. Envía «<petición que la crea>» para crear otra.` |
| A-11 | no se pudo comprobar | `No se envió la petición: no se pudo comprobar la suscripción <id> (HTTP <estatus>). Revisa que la persona de acceso tenga el permiso subscriptions:read.` (si la API no respondió: `…(la API no respondió).`) |
| A-12 | sin nombre guardado | `No se envió la petición: no hay un nombre guardado para la suscripción <id>, así que no se puede asegurar que la creó la colección. Envía «<petición que la crea>».` |
| A-13 | otro nombre | `No se envió la petición: la suscripción <id> ya no es la que creó la colección (otro nombre). Para no tocar datos ajenos, envía «<petición que la crea>» y vuelve a intentarlo.` |

Las peticiones citadas (fragmentos `<operationId>: …` del script: el `creator` de `OWNED` y las citas de las pistas) **deben existir** con ese nombre exacto (regla D8 de la prueba de desfase).

## Invariantes (cada una tiene una regla en la prueba o un escenario en el quickstart)

- **I1 — Sin fugas**: el script no escribe en la consola el secreto ni el token (solo nombres de variables y el
  mensaje). La Consola de Postman registra además la petición a Auth0, cuerpo incluido: es local y se advierte.
- **I2 — Fail-closed**: toda petición que exige token sale **solo** con uno vigente de su identidad; si no, se
  omite. Las excepciones son las que no llevan autenticación (`noauth`) o llevan `badToken`.
- **I3 — Nada ajeno se modifica**: `PATCH`/`PUT`/`DELETE` salen solo tras comprobar propiedad (paso 5).
- **I4 — Una sola salida por ejecución**: o termina sin problema o con exactamente un mensaje.
- **I5 — Sin estado oculto**: todo el estado está en variables de colección visibles para la persona.
- **I6 — Portable**: *callbacks*, sin `await` de nivel superior; sin librerías externas (`require`).
