# Modelo de datos (Fase 1): Colección de Postman para pruebas manuales

**Feature**: `002-manual-postman-collection` | **Spec**: [spec.md](spec.md) | **Investigación**: [research.md](research.md)

Esta feature **no toca la base de datos ni el esquema** (FR-024). Sus «datos» son archivos JSON versionados
y valores que Postman guarda en la máquina de cada persona. Aquí se fijan los nombres exactos, dónde vive
cada valor y cómo cambian, para que la colección, los entornos y la prueba de desfase hablen de lo mismo.

## Entidades

### 1. Colección manual

Archivo `tests/postman/collections/MailySoft-System-Manual.postman_collection.json` (formato v2.1).

| Campo | Regla |
|---|---|
| `info.name` | `MailySoft System API - Manual` |
| `info.schema` | `https://schema.getpostman.com/json/collection/v2.1.0/collection.json` |
| `info.description` | En español; abre con «si pulsas Enviar y no pasa nada, abre la Consola de Postman»; resume los pasos de arranque, los requisitos previos y la advertencia de bases de datos de pruebas |
| `auth` | Bearer con `{{accessToken}}` (solo referencia, nunca un token) |
| `event` | Un `prerequest` con el script de acceso ([contracts/access-script.md](contracts/access-script.md)); ningún `test` a nivel de colección |
| `variable` | Las de colección de la tabla «Variables de colección» |
| `item` | 4 carpetas ([contracts/collection-structure.md](contracts/collection-structure.md)) |

Cada carpeta y cada petición llevan `description` en español no vacía (FR-003) y cada petición lleva un evento
`test` (FR-005). Las peticiones se llaman `<operationId>: <descripción>` (igual que la colección de la spec 001);
las que no son operaciones de la API usan los prefijos `docs` o `sim`.

### 2. Entorno de uso

Dos archivos en `tests/postman/environments/`: `manual-local.postman_environment.json` y
`manual-deployed-test.postman_environment.json`. **Tienen exactamente las mismas claves** (regla D6).

| Clave | Tipo | Local | Desplegado de pruebas | Quién la rellena |
|---|---|---|---|---|
| `baseUrl` | `default` | `http://127.0.0.1:8010` | vacío | persona (desplegado) |
| `auth0Domain` | `default` | vacío | vacío | persona (p. ej. `mi-tenant.us.auth0.com`, sin `https://`) |
| `auth0Audience` | `default` | vacío | vacío | persona (idéntico al identificador de la API de usuarios) |
| `auth0ClientId` | `default` | vacío | vacío | persona |
| `auth0ClientSecret` | **`secret`** | **vacío** | **vacío** | persona, solo en su copia local |
| `plainClientId` | `default` | vacío | vacío | persona (opcional: caso 403) |
| `plainClientSecret` | **`secret`** | **vacío** | **vacío** | persona (opcional), solo en su copia local |
| `clinicsStubUrl` | `default` | `http://127.0.0.1:8001` | vacío | persona (solo local) |
| `testDatabaseNotice` | `default` | aviso en español | aviso en español (más enérgico) | nadie: es informativa |

Reglas (vigiladas por la prueba de desfase): ninguna variable de entorno comparte nombre con una de colección; toda
variable `secret` tiene `value: ""`; las variables de acceso tienen `value: ""`; el nombre del entorno incluye
«solo bases de datos de pruebas»; `_postman_variable_scope` es `environment`.

### 3. Credenciales de acceso

Las del entorno: `auth0ClientId` + `auth0ClientSecret` (aplicación principal, con los cuatro permisos) y
`plainClientId` + `plainClientSecret` (opcional, sin permisos). **Nunca** salen del equipo de la persona más
que hacia Auth0 (FR-012). El secreto no se copia a ninguna otra variable.

### 4. Token de sesión

Por identidad (`accessToken` y `plainToken`), en variables de colección:

| Variable | Contenido | Se escribe cuando |
|---|---|---|
| `accessToken` / `plainToken` | el token de acceso | Auth0 responde 200 con `access_token` |
| `accessTokenExpiresAt` / `plainTokenExpiresAt` | milisegundos desde la época del vencimiento | igual |
| `accessTokenKey` / `plainTokenKey` | `dominio\|audience\|clientId` con que se pidió | igual |

Estados: **sin token** → *(Auth0 200)* → **vigente** → *(quedan ≤ 60 s)* → **por vencer** → *(se pide otro)* →
**vigente**. Si cambia la clave (otro entorno, otro cliente) pasa de **vigente** a **sin token** (se descarta y
se pide otro). Si Auth0 falla, el token anterior **no se usa** cuando ya no sirve y la petición se omite.

### 5. Datos de la sesión

Lo que la colección creó en la API a la que apunta ahora, en variables de colección:

| Variable | Contenido | Quién la escribe |
|---|---|---|
| `sessionApi` | `baseUrl` con que se guardaron estos datos | el script de acceso |
| `subscriptionId`, `subscriptionName` | la suscripción de prueba actual | las pruebas de `create_subscription: crear la suscripción de prueba` y `…para los casos de error`; `update_subscription` renombrar actualiza el nombre |
| `otherSubscriptionId`, `otherSubscriptionName` | la segunda suscripción (choque de nombres) | `create_subscription: crear otra suscripción para el choque de nombres` |
| `deletedSubscriptionId` | la última suscripción que la colección eliminó con éxito | la prueba de `delete_subscription` al recibir 204 |
| `newSuffix` | sufijo único de la creación en curso | el script de acceso, cada vez que una petición lo usa |
| `nonexistentSubscriptionId` | constante `2147483647`, para el 404 | declarada en la colección |

Estados de una suscripción de prueba: **sin crear** → *(POST 201)* → **creada** (`subscriptionId` y nombre guardados)
→ *(PATCH)* **modificada** → *(DELETE 204)* → **eliminada** (`deletedSubscriptionId` guardado; el estatus en la
base es «Eliminada»). Si cambia `baseUrl`, todas pasan a **sin crear** (se descartan). Antes de cualquier
`PATCH`/`PUT`/`DELETE` sobre `subscriptionId` u `otherSubscriptionId`, el script exige que la
suscripción exista y se llame como se guardó; si no, la petición se omite.

### 6. Variables de apoyo del script

| Variable | Uso |
|---|---|
| `accessProblem` | último motivo por el que se omitió una petición; se borra cuando una petición sale |
| `badToken` | token inventado para el caso 401; se regenera en cada uso |

## Variables de colección declaradas (valor inicial)

Todas con valor inicial **vacío**, salvo `nonexistentSubscriptionId` = `2147483647`. Los tokens y sus
vencimientos pueden no declararse (se crean al guardarse); se declaran para que sean visibles y estén
documentadas. La prueba de desfase exige que **ninguna** variable de colección con nombre de token o secreto tenga
valor en el archivo (regla D5).

## Relaciones

- La **colección manual** usa un **entorno de uso** a la vez; su script lee de él las **credenciales** y escribe
  en variables de colección el **token** y los **datos de la sesión**.
- El **token** se invalida si cambia la clave `dominio|audience|clientId`; los **datos de la sesión** se
  invalidan si cambia `baseUrl`.
- La **simulación de clínicas** (spec 001) es ajena a este modelo: solo se invoca por HTTP desde una carpeta.
