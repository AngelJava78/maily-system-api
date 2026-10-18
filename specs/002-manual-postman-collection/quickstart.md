# Guía de validación (Fase 1): Colección de Postman para pruebas manuales

**Feature**: `002-manual-postman-collection` | **Spec**: [spec.md](spec.md) | **Contratos**: [contracts/](contracts/)

Cómo comprobar que la feature funciona, de lo más barato a lo que exige la aplicación de Postman. Los niveles
V1 y V9 los ejecuta quien implementa; V2 a V8 son verificación manual que **solo se puede hacer en la
aplicación de escritorio** (no hay forma de ejecutarla desde aquí) y deben hacerse una vez antes de dar la feature
por terminada.

## Requisitos previos (fuera de la colección, FR-023)

1. **Auth0**: una aplicación *Machine to Machine* autorizada para el *audience* de la API de usuarios.
   Su `sub` termina en `@clients`.
2. **API de usuarios** (`mailySoft-usuarios`): ese `sub` registrado como usuario y con un rol que tenga los
   cuatro permisos `subscriptions:read`, `subscriptions:write`, `subscriptions:update` y `subscriptions:delete`.
   El catálogo ya los trae, pero `project-definition/bootstrap_admin.sql` de ese repositorio solo asocia al
   *Administrator* los 12 de usuarios, roles y permisos: hay que asociar los cuatro al rol de la aplicación.
3. **Opcional (caso 403)**: una segunda aplicación M2M autorizada para el mismo *audience*, registrada en el API de
   usuarios **sin** permisos de suscripciones.
4. **Local**: API de usuarios en `http://localhost:8000`; esta API en `http://127.0.0.1:8010` (con
   `USERS_API_BASE_URL` y `CLINICS_API_BASE_URL` en su `.env`), conectada a una base **dedicada a las pruebas
   manuales** (`maily_system_manual`; ver el README): `docker compose exec db psql -U postgres -c "CREATE DATABASE maily_system_manual"`,
   luego, en la misma terminal que la API, `$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5434/maily_system_manual"` y `uv run alembic upgrade head`.
   Nunca la de desarrollo ni la de pytest.

## V1 — Pruebas automáticas (sin Postman, Node, ni servicio)

```powershell
uv run pytest tests/contract/test_manual_postman_collection.py tests/contract/test_postman_collection.py -q
uv run pytest -q                       # la suite completa sigue en verde
```

Esperado: todo en verde. **Comprobación de que la guarda muerde** (se hace una vez y se revierte): quitar de la
colección manual **todas** las peticiones `delete_subscription: …` → D1 falla nombrando `delete_subscription`;
escribir un valor en `auth0ClientSecret` del entorno local → D5 falla nombrando el archivo y la variable. El
detector además se prueba a sí mismo con copias en memoria ([contracts/drift-test.md](contracts/drift-test.md)).

## V2 — Importar y enviar la primera petición (SC-001, historia 1)

1. En Postman: *Import* → `tests/postman/collections/MailySoft-System-Manual.postman_collection.json` y
   `tests/postman/environments/manual-local.postman_environment.json`. **No hace falta iniciar sesión.**
2. Elegir el entorno «MailySoft System API - Manual - local (solo bases de datos de pruebas)».
3. Rellenar, en el entorno, `auth0Domain` (sin `https://`), `auth0Audience`, `auth0ClientId` y `auth0ClientSecret`
   (**solo el valor local**, no el inicial).
4. Abrir `0. Empezar` → `list_subscriptions: comprobar el acceso y ver el catálogo` → *Send*.

Esperado: 200 y un arreglo, **sin haber pegado ningún token**. Menos de 10 minutos desde el paso 1. Repetir *Send*:
no hay segunda llamada a Auth0 (se ve en la Consola de Postman: una sola petición a `/oauth/token`).

## V3 — Fallos de acceso: cada uno se explica y no envía (SC-005)

Con la Consola de Postman abierta (Ver → Mostrar Consola de Postman). Para cada fila, provocar el fallo, enviar
`list_subscriptions: comprobar el acceso…` y comprobar que **no hay respuesta**, que aparece el mensaje y que
**ninguna petición llegó a la API** (en la Consola solo se ve, a lo sumo, la llamada a Auth0):

| Provocar | Mensaje esperado (id de [access-script.md](contracts/access-script.md)) |
|---|---|
| Vaciar `auth0Audience` | A-01 nombrando `auth0Audience` |
| Poner `https://` al dominio | A-02 |
| Dominio inexistente | A-03 |
| Secreto equivocado | A-04 |
| *Audience* distinto del autorizado (o sin la barra final) | A-05 |
| Vaciar `auth0ClientSecret` | A-01 nombrando `auth0ClientSecret` y recordando que el secreto va solo en la copia local |

Esperado además: la Consola **no muestra el secreto ni el token** en ningún mensaje del script. (Postman sí registra
la petición a Auth0, cuerpo incluido: es local; no compartas capturas de la Consola.) También: la petición omitida
aparece **sin respuesta** y, en el *Collection Runner*, como omitida, no como fallida.

## V4 — Ciclo de vida (SC-004, historias 2 y 4)

`1. Ciclo de vida…`, petición a petición (o *Run folder*): todas en verde, sin editar URL ni cuerpo. `1.9` puede dar
**503** si no hay API de clínicas ni simulación: es lo esperado y el título lo explica (la `1.10` lo contempla).
Repetir la carpeta: crea otro nombre y no choca con el anterior.

Y la prueba de seguridad de datos: **antes de crear nada** (variables de sesión vacías), enviar
`update_subscription: cambiar el precio y las funciones`: no sale y dice que primero se cree la de prueba (A-09).

## V5 — Casos de error (SC-003)

`2. Casos de error`: 2.1 y 2.2 preparan; 2.3 a 2.18 provocan 401, 403, 404, 409, 422 y 503 con su código y mensaje
en español; 2.19 limpia. **Sin** segunda aplicación configurada, 2.5 y 2.6 se omiten explicando cómo configurarla
(A-08) y no cuentan como fallo; **con** ella, responden 403. 2.8 se omite si aún no hay una suscripción eliminada.

## V6 — Simulación de clínicas, solo local (historia 5)

```powershell
uv run uvicorn app:app --app-dir tests/stubs/clinics_api --port 8001
```

La carpeta `3.`, completa: 3.1 a 3.12 en verde (conteo 3 → 409 al eliminar → fallo provocado: conteo `null` y 503 →
sin clínicas: 204). **Sin** la simulación levantada: `get_subscription` muestra `clinics_count: null` y eliminar 503
(FR-018). Con `clinicsStubUrl` vacío (entorno desplegado): cada petición de la carpeta se omite con su mensaje.

## V7 — Entorno desplegado de pruebas (SC-007, historia 4)

Importar `manual-deployed-test.postman_environment.json`; rellenar `baseUrl` y los valores de acceso; recorrer
`0.` y `1.` sin editar ninguna petición (0 ediciones). Comprobar que **ninguna suscripción preexistente** cambió
(el nombre de todas las que cambian empieza por `Prueba manual`). El nombre del entorno y `testDatabaseNotice`
advierten de bases de datos de pruebas.

## V8 — Cambiar de entorno y de base (casos límite)

- Con una suscripción creada en local, cambiar al desplegado y enviar una modificación: no sale (A-09; los datos de
  la sesión se descartaron) y no se reutiliza el token del otro entorno (la Consola muestra una llamada nueva a Auth0).
- Reiniciar la base local (`docker compose down -v` + `up`), crear desde otra herramienta una suscripción con el mismo
  `id` guardado y enviar un `DELETE` de la colección: no sale y dice que ya no es la que creó la colección (A-13).

## V9 — Verificación desechable con Newman (quien implementa; no se versiona)

Para no entregar 44 peticiones sin ejecutarlas: la pila de la spec 001 (API real, base desechable y simulación de usuarios)
+ un Auth0 simulado con TLS que entrega un token registrado en esa simulación con los cuatro permisos (y otro sin
permisos) + `newman run … --insecure --env-var …`. Esperado: 0 pruebas fallidas; las peticiones omitidas (carpeta 3 sin
simulación, 2.5/2.6 sin segunda aplicación) aparecen como omitidas. El script, el Auth0 simulado y los
resultados se quedan fuera del repositorio y se **informan** al terminar.

## Mapa historia → dónde se prueba

| Historia | Prueba automática | Verificación |
|---|---|---|
| 1. Entrar sin pegar tokens | D4, D5, D5b | V2, V3, V9 |
| 2. Recorrer las operaciones | D1, D3, D11 | V4, V9 |
| 3. Errores clave | D2, D3 | V5, V9 |
| 4. Entorno desplegado | D6 | V7, V8 |
| 5. Simulación de clínicas | D7 (las `sim`) | V6, V9 |
| 6. Desfase y secretos | D0 a D11 | V1 |
| 7. Documentación | — | un revisor ajeno sigue solo el README (SC-009) |
