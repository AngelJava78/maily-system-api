# Feature Specification: Dashboard de Plataforma («Panel de Maily»)

**Feature Branch**: `003-platform-dashboard`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "Agregar a la MailySoft System API un endpoint de consulta (solo
lectura) para el dashboard de plataforma de Maily («Panel de Maily»), que alimenta la pantalla de
resumen general del administrador de plataforma. En una sola consulta devuelve el total de
clínicas, las clínicas activas, las clínicas con periodo de prueba, el total de doctores, de
pacientes y de usuarios, y las clínicas más recientes (identificador, nombre, fecha de creación y
estatus). La cantidad de clínicas recientes se elige con el parámetro opcional `limit` (de 1 a 10;
más de 10 devuelve 10; inválido, 422) o, si no se envía, con un valor por defecto configurable
(`DASHBOARD_RECENT_CLINICS_LIMIT`: 3, 5 o 10; 5 si no se configura). Exige token y el permiso
`dashboard:read`, comprobado antes de validar `limit`. En la Fase 1 los datos son ficticios,
deterministas y no se guardan en la base de datos del servicio; el contrato debe ser estable para
cuando existan los APIs reales y, si una fuente falla en el futuro, el indicador afectado se
devuelve como `null` sin inventar un cero. Incluye pruebas, una colección de Postman y la
actualización de la cobertura de permisos, sin tocar la API de suscripciones."

## Clarifications

### Session 2026-10-18

- Q: Cuando falle la fuente de las clínicas, ¿la lista de clínicas recientes llega como `null` o como
  `[]`? → A: `null`. El `[]` queda reservado para cuando la fuente respondió que no hay clínicas; el
  contrato declara la lista como «lista o `null`» desde la Fase 1.
- Q: ¿El total de usuarios incluye a los doctores? → A: Sí. Todo doctor es un usuario de la
  plataforma, así que el total de usuarios nunca es menor que el de doctores; los pacientes no son
  usuarios y no cuentan en ese total.
- Q: Además de que el servicio no reutilice resultados, ¿la respuesta debe indicar a navegadores y
  servidores intermedios que no la guarden en caché? → A: Sí. La respuesta 200 declara que no debe
  guardarse en caché (`Cache-Control: no-store`) y una prueba lo comprueba.
- Q: ¿La colección de Postman nueva es solo la automática de punta a punta o también se añade el
  dashboard a la colección manual existente? → A: Solo una colección nueva e independiente de punta a
  punta (automática, con las simulaciones de sus dependencias). La colección manual y la automática de
  suscripciones no se modifican; sus controles de cobertura se acotan a las suscripciones (FR-033).
- Q: Si fallan todas las fuentes de datos a la vez, ¿el dashboard responde 200 con todo en `null` o
  503? → A: 200 con todos los indicadores y la lista en `null`. Solo la falla del control de acceso
  impide responder (503).

## User Scenarios & Testing *(mandatory)*

El actor es **quien administra la plataforma de Maily** (una persona del equipo de MailySoft, desde
la pantalla de resumen general «Panel de Maily» de la aplicación de administración). No es una
clínica ni su personal: los paneles propios de cada clínica quedan fuera. Toda persona que use la API
se identifica con un token de acceso y solo puede hacer lo que sus permisos le autorizan; los
permisos los decide el API de usuarios, no este servicio. La operación es **solo de consulta**:
no hay nada que crear, cambiar ni borrar.

### User Story 1 - Ver el resumen general de la plataforma (Priority: P1)

Quien tiene permiso de consulta del dashboard obtiene, en una sola consulta, seis indicadores de la
plataforma —total de clínicas, clínicas activas, clínicas con periodo de prueba, total de doctores,
total de pacientes y total de usuarios— y la lista de las clínicas más recientes, cada una con su
identificador, nombre, fecha de creación y estatus. La respuesta solo trae datos agregados y los
datos básicos de esas clínicas: ninguna información personal de pacientes, doctores ni usuarios.

**Why this priority**: Es la pantalla de inicio del administrador de plataforma y la razón de ser de
la feature; sin esta consulta el «Panel de Maily» no tiene qué mostrar.

**Independent Test**: Con una persona que tiene el permiso, consultar el dashboard sin ningún
parámetro y comprobar que llegan los seis enteros y exactamente tantas clínicas recientes como el
valor por defecto del servicio (5 si no se configuró otro), de la más nueva a la más antigua, cada
una con UUID, nombre, fecha en UTC y estatus con identificador y nombre; repetir la consulta y
comprobar que la respuesta es idéntica.

**Acceptance Scenarios**:

1. **Given** una persona con el permiso `dashboard:read`, **When** consulta el dashboard sin
   `limit`, **Then** recibe el total de clínicas, las activas, las de periodo de prueba, el total de
   doctores, el de pacientes y el de usuarios (enteros mayores o iguales a cero) y las clínicas
   recientes en la cantidad por defecto del servicio.
2. **Given** la respuesta del dashboard, **When** se revisa cada clínica reciente, **Then** trae su
   identificador (UUID), su nombre, su fecha de creación en ISO 8601 con zona horaria UTC y su
   estatus como objeto con identificador y nombre.
3. **Given** la respuesta del dashboard, **When** se revisan los indicadores de clínicas, **Then** las
   activas y las de periodo de prueba no se solapan, su suma no supera el total, y el estatus de cada
   clínica reciente es coherente con esos conteos; además, el total de usuarios no es menor que el de
   doctores.
4. **Given** la respuesta del dashboard, **When** se examina su contenido, **Then** solo hay conteos y
   los datos básicos de las clínicas recientes; no hay nombres, contactos ni otros datos personales de
   pacientes, doctores o usuarios.
5. **Given** los datos ficticios de la Fase 1, **When** se consulta el dashboard dos veces seguidas,
   **Then** las dos respuestas son idénticas (mismos valores y mismo orden).
6. **Given** una consulta que devuelve el dashboard (200), **When** se examinan las cabeceras de la
   respuesta, **Then** indican que no debe guardarse en caché (`Cache-Control: no-store`).

---

### User Story 2 - Solo quien tiene el permiso puede consultar el dashboard (Priority: P1)

La consulta exige que la persona esté autenticada y tenga el permiso `dashboard:read`. Si no está
autenticada se le pide iniciar sesión; si lo está pero no tiene el permiso, se le niega; si no se
puede comprobar su permiso, se le niega también (falla cerrada). La comprobación se hace en cada
petición con los datos vigentes del API de usuarios y **antes** de validar el parámetro `limit`: una
persona sin permiso recibe la negativa aunque haya enviado un `limit` inválido.

**Why this priority**: El dashboard muestra la situación global de la plataforma; consultarlo sin
control sería una fuga de información de negocio. Es indispensable desde la primera versión.

**Independent Test**: Probar la consulta con (a) sin token, (b) token inválido o vencido, (c) persona
autenticada sin el permiso, (d) persona con el permiso y (e) el API de usuarios caído; comprobar que
solo (d) devuelve el dashboard. Repetir (a), (b), (c) y (e) con un `limit` inválido y comprobar que
el rechazo sigue siendo por acceso y no por validación.

**Acceptance Scenarios**:

1. **Given** una petición sin token, **When** se consulta el dashboard, **Then** se rechaza indicando
   que debe iniciar sesión (401) y no se devuelve ningún dato.
2. **Given** un token inválido o vencido, **When** se consulta el dashboard, **Then** se rechaza (401)
   y no se devuelve ningún dato.
3. **Given** una persona autenticada que no tiene `dashboard:read`, **When** consulta el dashboard,
   **Then** se rechaza indicando que no tiene permiso (403) y el mensaje nombra el permiso requerido.
4. **Given** una persona que tiene permisos de suscripciones pero no `dashboard:read`, **When** consulta
   el dashboard, **Then** se rechaza (403): cada permiso autoriza solo su operación.
5. **Given** una persona a la que acaban de quitar el permiso en el API de usuarios, **When** hace su
   siguiente consulta, **Then** se le niega, sin esperar a que caduque su token.
6. **Given** el API de usuarios no responde, agota el tiempo o responde algo inesperado, **When** se
   consulta el dashboard, **Then** se rechaza indicando que el servicio no está disponible por el
   momento (503) y no se devuelve ningún dato.
7. **Given** una petición sin permiso (o sin token, o con el API de usuarios caído) que además trae
   un `limit` inválido, **When** se consulta, **Then** el rechazo es por acceso (403, 401 o 503), no
   por `limit` (422).
8. **Given** una persona con el permiso que envía un `limit` inválido, **When** consulta, **Then** se
   rechaza por validación (422): el permiso se comprueba primero, la validación después.
9. **Given** la documentación publicada de la API, **When** cualquiera la abre, **Then** se muestra
   sin pedir token e indica el permiso que exige la consulta del dashboard.

---

### User Story 3 - Elegir cuántas clínicas recientes ver (Priority: P2)

Quien consulta puede indicar con el parámetro opcional `limit` cuántas clínicas recientes quiere:
cualquier entero de 1 a 10. Si pide más de 10 no recibe un error: recibe 10, que es el máximo. Si no
envía `limit`, recibe la cantidad por defecto del servicio. Si envía algo que no es un entero válido
(menor que 1, texto o vacío), se le rechaza con un mensaje en español. La lista nunca se pagina y
siempre llega ordenada de la clínica más nueva a la más antigua.

**Why this priority**: La pantalla puede mostrar listas de distinto tamaño según el espacio; es
secundaria frente a ver el resumen y proteger el acceso, pero define el contrato de la lista.

**Independent Test**: Consultar con `limit` = 1, 3 y 10 y comprobar que llegan 1, 3 y 10 clínicas; con
11 y con 1000 y comprobar que llegan 10 y no hay error; sin `limit` y comprobar que llega la cantidad
por defecto; con 0, -1, `abc`, `5.5` y vacío y comprobar el 422; y comprobar el orden, incluido el
desempate cuando dos clínicas tienen la misma fecha de creación.

**Acceptance Scenarios**:

1. **Given** hay al menos 10 clínicas, **When** se consulta con `limit` entre 1 y 10, **Then** llegan
   exactamente esa cantidad de clínicas, las más recientes.
2. **Given** hay al menos 10 clínicas, **When** se consulta con `limit` mayor que 10 (por ejemplo 11
   o 1000), **Then** llegan 10 clínicas y no hay error.
3. **Given** no se envía `limit`, **When** se consulta, **Then** llega la cantidad por defecto de la
   configuración del servicio.
4. **Given** se envía `limit` menor que 1 (0 o negativo), no numérico (`abc`), decimal (`5.5`) o vacío,
   **When** una persona con permiso consulta, **Then** se rechaza con 422, con el formato de error
   uniforme del servicio y un mensaje en español que no repite el valor recibido, y no se devuelve
   ningún dato del dashboard.
5. **Given** existen menos clínicas que la cantidad pedida (por ejemplo 4 y `limit` = 10), **When** se
   consulta, **Then** llegan las 4, sin error y sin rellenar.
6. **Given** no existe ninguna clínica, **When** se consulta, **Then** las clínicas recientes llegan
   como lista vacía (nunca nula) y los seis conteos llegan en 0.
7. **Given** hay clínicas con fechas de creación distintas, **When** se consulta, **Then** llegan de la
   más nueva a la más antigua.
8. **Given** dos clínicas con exactamente la misma fecha de creación, **When** se consulta, **Then**
   se ordenan entre sí por identificador ascendente, y el orden es el mismo en toda consulta.

---

### User Story 4 - Fijar la cantidad por defecto de clínicas recientes (Priority: P2)

Quien opera el servicio puede fijar con una variable de entorno opcional (`DASHBOARD_RECENT_CLINICS_LIMIT`)
cuántas clínicas recientes se devuelven cuando la persona no envía `limit`. Solo admite 3, 5 o 10; si
no se configura, son 5. Un valor distinto impide que el servicio arranque y el error dice qué
variable es inválida, sin mostrar secretos. Un cambio de valor surte efecto al reiniciar el servicio.

**Why this priority**: Permite ajustar el panel a cada despliegue sin tocar el código; el valor por
defecto razonable (5) hace que la mayoría de los despliegues no necesiten configurarla.

**Independent Test**: Arrancar el servicio sin la variable y comprobar que el valor por defecto es 5;
arrancarlo con 3, con 5 y con 10 y comprobar que cada uno rige cuando no se envía `limit`; arrancarlo
con 4, 0, 11 y `abc` y comprobar que no arranca, que el error nombra la variable y que no muestra el
valor; comprobar que `.env.example` documenta la variable.

**Acceptance Scenarios**:

1. **Given** la variable no está configurada, **When** se consulta sin `limit`, **Then** llegan 5
   clínicas recientes.
2. **Given** la variable vale 3, 5 o 10, **When** se consulta sin `limit`, **Then** llega esa cantidad.
3. **Given** la variable vale 3, **When** se consulta con `limit` = 7, **Then** llegan 7: el `limit`
   enviado prevalece sobre el valor por defecto.
4. **Given** la variable tiene un valor que no es 3, 5 ni 10 (por ejemplo 4, 0, 11, -5 o `abc`),
   **When** se intenta arrancar el servicio, **Then** no arranca y el mensaje indica que
   `DASHBOARD_RECENT_CLINICS_LIMIT` no es válida, sin mostrar su valor ni ningún secreto.
5. **Given** el servicio ya está en marcha, **When** cambia el valor de la variable en el entorno,
   **Then** el servicio sigue usando el valor con el que arrancó hasta que se reinicie.
6. **Given** el archivo `.env.example`, **When** se consulta, **Then** documenta la variable con sus
   valores admitidos (3, 5 y 10) y su valor por defecto (5).

---

### User Story 5 - Datos ficticios y avisados en la Fase 1 (Priority: P2)

Los datos de clínicas, doctores, pacientes y usuarios pertenecen a otros APIs de MailySoft que aún
no existen. Mientras tanto, el dashboard devuelve datos ficticios pero coherentes, que no se guardan
en la base de datos de este servicio. Al arrancar, el servicio registra un aviso claro de que el
dashboard usa datos ficticios, para que nadie lo lleve a producción sin darse cuenta.

**Why this priority**: Permite construir y probar la pantalla ya, sin esperar a los demás APIs; el
aviso evita que los datos ficticios se tomen por reales.

**Independent Test**: Arrancar el servicio y comprobar que registra el aviso; aplicar las migraciones
y comprobar que el esquema de la base de datos no cambió por esta feature; consultar el dashboard con
`limit` = 10 y comprobar que llegan 10 clínicas con UUID válidos; reiniciar el servicio y comprobar que
la respuesta es idéntica a la anterior.

**Acceptance Scenarios**:

1. **Given** el servicio arranca con la configuración válida, **When** termina de iniciar, **Then**
   queda registrado un aviso de que el dashboard usa datos ficticios, sin secretos, y el arranque no
   se impide.
2. **Given** esta feature desplegada, **When** se revisa la base de datos del servicio, **Then** no
   tiene tablas ni migraciones nuevas ni guarda datos del dashboard.
3. **Given** el conjunto de datos ficticios, **When** se consulta con `limit` = 10, **Then** llegan 10
   clínicas, todas con UUID válido.
4. **Given** el servicio se reinicia, **When** se vuelve a consultar con los mismos parámetros,
   **Then** la respuesta es idéntica a la de antes del reinicio.
5. **Given** el conjunto de datos ficticios, **When** se consulta con `limit` = 10, **Then** entre las
   clínicas recibidas hay al menos una «Activa» y una «En prueba», y al menos dos con la misma fecha
   de creación (para comprobar el estatus y el desempate de punta a punta).

---

### User Story 6 - Un contrato estable que sobrevive a las fuentes reales (Priority: P3)

Cuando existan los APIs reales de clínicas, doctores, pacientes y usuarios, el dashboard cambiará
solo de dónde saca los datos; los campos, sus tipos y su significado no cambian, y la pantalla del
«Panel de Maily» sigue funcionando sin tocarla. Además, si una de esas fuentes falla, el indicador
que depende de ella llega como `null` (nunca como un cero inventado) y el resto del dashboard se
sigue devolviendo.

**Why this priority**: No tiene efecto visible en la Fase 1 (los datos ficticios no fallan), pero
fija desde ahora la forma de la respuesta y la degradación, que son caras de cambiar después, cuando
ya haya consumidores.

**Independent Test**: Con fuentes simuladas (no reales) que fallan una por una, comprobar que solo los
indicadores afectados llegan en `null`, que el resto conserva sus valores y que la respuesta es 200;
comprobar que una fuente que responde «no hay nada» produce `0` y `[]`, no `null`; comprobar que el
esquema publicado de la respuesta declara cada indicador como entero o `null`.

**Acceptance Scenarios**:

1. **Given** las fuentes reales conectadas en el futuro, **When** se consulta el dashboard, **Then** la
   respuesta tiene los mismos campos, tipos y significado que en la Fase 1.
2. **Given** la fuente de los doctores falla, **When** se consulta el dashboard, **Then** el total de
   doctores llega como `null` (no como 0) y los demás indicadores y la lista de clínicas recientes se
   devuelven con sus valores, con 200.
3. **Given** la fuente de las clínicas falla, **When** se consulta el dashboard, **Then** los
   indicadores que dependen de ella y la lista de clínicas recientes llegan como `null` (la lista no
   llega como `[]`), y los totales de doctores, pacientes y usuarios se devuelven con sus valores.
4. **Given** una fuente responde que no hay datos, **When** se consulta el dashboard, **Then** los
   conteos son `0` y la lista es `[]`: son valores verdaderos, no una falla.
5. **Given** una fuente falla, **When** se consulta el dashboard, **Then** la respuesta no revela
   direcciones, cuerpos de error ni credenciales de esa fuente.
6. **Given** una fuente de datos falla, **When** se consulta el dashboard, **Then** el control de
   acceso no se relaja: sigue exigiendo token y permiso, y sigue fallando cerrado.

---

### Edge Cases

- **`limit` en los bordes**: 1 y 10 son válidos e inclusivos; 0 y negativos se rechazan; 11, 1000 y
  cualquier entero mayor que 10, por grande que sea, devuelven 10 sin error.
- **`limit` que no es un entero válido**: texto (`abc`), decimal o con notación científica (`5.5`,
  `1e1`), vacío (`limit=`) o con solo espacios se rechazan con 422. A diferencia de la variable de
  entorno (donde un valor vacío equivale a no configurarla), un `limit` presente y vacío es inválido.
- **`limit` repetido** (`limit=3&limit=5`): se rechaza con 422, para no adivinar cuál de los valores
  se quiso usar.
- **Parámetros de consulta desconocidos** (por ejemplo `page`, `offset` o filtros): no existen en esta
  operación; se ignoran sin ningún efecto y no cambian el resultado.
- **Acceso y `limit` inválido a la vez**: gana el acceso. Sin token → 401; sin permiso → 403; API de
  usuarios caído → 503; solo con acceso concedido se evalúa `limit` (422).
- **Menos clínicas que la cantidad pedida**: se devuelven todas las que haya, sin error y sin
  rellenar con clínicas inventadas.
- **Ninguna clínica**: la lista llega como `[]`, nunca como `null`, y los seis conteos llegan en 0.
- **Clínicas con la misma fecha de creación**: se ordenan entre sí por identificador ascendente; el
  orden no cambia entre consultas.
- **Clínicas en otros estatus**: cuentan en el total de clínicas, pero no en las activas ni en las de
  periodo de prueba; por eso el total puede ser mayor que la suma de esas dos.
- **Valor por defecto configurado y `limit` enviado**: el `limit` válido enviado prevalece (con
  la variable en 3, un `limit` de 7 devuelve 7); el valor por defecto solo rige cuando no se envía
  `limit`.
- **Variable de entorno vacía**: se trata como no configurada (vale 5), igual que las demás variables
  opcionales del servicio.
- **Variable de entorno con un valor no admitido** (4, 0, 11, -5, `abc`, 5.5…): el servicio no
  arranca; el mensaje nombra `DASHBOARD_RECENT_CLINICS_LIMIT` y no muestra el valor.
- **Cambio de la variable con el servicio en marcha**: no tiene efecto hasta reiniciar.
- **Una fuente de datos falla en el futuro**: el indicador afectado llega como `null`; el resto se
  sigue devolviendo con 200. Un cero o una lista vacía solo significan que la fuente respondió que no
  hay datos.
- **Fallan todas las fuentes en el futuro**: la respuesta sigue siendo 200 con todos los indicadores
  y la lista en `null`; lo único que impide responder es el control de acceso (503).
- **El API de usuarios no responde**: no se devuelve ningún dato y se indica que el servicio no está
  disponible por el momento. La documentación publicada sigue disponible.
- **Persona autenticada pero bloqueada o sin roles en el API de usuarios**: no tiene el permiso, así
  que se le niega la consulta.

## Requirements *(mandatory)*

### Functional Requirements

**Control de acceso**

- **FR-001**: La consulta del dashboard MUST exigir un token de acceso válido y el permiso
  `dashboard:read`. Solo la documentación publicada de la API MUST seguir disponible sin token. El
  servicio MUST NOT verificar el token por sí mismo: MUST reenviarlo, sin modificarlo, al API de
  usuarios y aceptar su respuesta como única autoridad sobre la identidad y el permiso (Principio
  VIII de la constitución).
- **FR-002**: Sin token (o con una cabecera que no usa el esquema Bearer) o con un token rechazado o
  vencido, el servicio MUST responder 401. Con un token válido pero sin el permiso `dashboard:read`,
  MUST responder 403 (cada permiso autoriza solo su operación: tener permisos de suscripciones no
  basta). Si el API de usuarios no responde, agota el tiempo de espera o contesta algo inesperado,
  MUST responder 503 y fallar cerrado. En ninguno de estos casos MUST devolverse dato alguno del
  dashboard.
- **FR-003**: La comprobación de acceso MUST hacerse en cada petición con los datos vigentes del API de
  usuarios, sin conservar decisiones anteriores, y MUST ocurrir antes de validar `limit`: una
  petición sin identidad válida o sin permiso recibe 401, 403 o 503 aunque su `limit` sea inválido.
  Solo cuando el acceso se concede se valida `limit` (422).
- **FR-004**: La operación MUST declarar en el contrato publicado de la API el permiso que exige
  (`dashboard:read`) y el esquema de seguridad Bearer, y MUST añadirse a la matriz «operación →
  permiso» sin alterar ninguna de las filas existentes (las seis de suscripciones). Ampliar la matriz
  no exige enmendar la constitución.

**Resumen de la plataforma**

- **FR-005**: El servicio MUST devolver, en una sola consulta: el total de clínicas, las clínicas
  activas, las clínicas con periodo de prueba, el total de doctores, el total de pacientes y el total
  de usuarios (cada uno un entero mayor o igual a cero) y la lista de clínicas recientes (FR-010 a
  FR-016).
- **FR-006**: «Clínicas activas» y «clínicas con periodo de prueba» MUST ser conjuntos que no se
  solapan (una clínica tiene un solo estatus) y su suma MUST NOT superar el total de clínicas. El
  total MAY ser mayor que esa suma porque incluye las clínicas en otros estatus.
- **FR-007**: Los totales de doctores, pacientes y usuarios MUST ser conteos de toda la plataforma
  (todas las clínicas), no de una clínica en particular. Todo doctor es un usuario de la plataforma:
  el total de usuarios incluye a los doctores y por tanto MUST NOT ser menor que el total de doctores.
  Los pacientes no son usuarios: MUST NOT contarse en el total de usuarios.
- **FR-008**: La respuesta MUST contener únicamente datos agregados y los datos básicos de las
  clínicas recientes. MUST NOT exponer información personal de pacientes, doctores ni usuarios
  (nombres, contactos, documentos u otros datos de personas).
- **FR-009**: Cada clínica reciente MUST mostrar: identificador (UUID), nombre, fecha de creación y
  estatus como objeto con identificador y nombre. La fecha de creación MUST devolverse en ISO 8601
  con zona horaria UTC explícita (por ejemplo, `2026-09-30T14:25:00Z`).

**Clínicas recientes y parámetro `limit`**

- **FR-010**: La consulta MUST aceptar el parámetro de consulta opcional `limit` (entero) que fija
  cuántas clínicas recientes se devuelven. Con un entero entre 1 y 10, MUST devolverse esa cantidad
  de clínicas (o todas las que haya, si son menos; ver FR-014).
- **FR-011**: Con un `limit` entero mayor que 10, el servicio MUST NOT rechazar la petición: MUST
  devolver el máximo de 10 clínicas, sin error. El máximo de 10 MUST ser fijo y NO configurable.
- **FR-012**: Sin `limit`, el servicio MUST usar el valor por defecto de su configuración (FR-017).
- **FR-013**: Con un `limit` menor que 1, no entero (texto, decimal o notación científica), vacío o
  en blanco, o repetido, el servicio MUST rechazar la petición con 422, usando el formato de error
  uniforme del servicio (`validation_error`, con un elemento para el campo `limit`) y un mensaje en
  español que MUST NOT repetir el valor recibido. MUST NOT devolverse ningún dato del dashboard.
- **FR-014**: Si existen menos clínicas que la cantidad efectiva pedida, el servicio MUST devolver
  todas las que haya, sin error y sin rellenar. Si no existe ninguna, MUST devolver la lista vacía
  `[]` (nunca `null`) y los seis conteos en 0.
- **FR-015**: Las clínicas recientes MUST ordenarse de la más nueva a la más antigua por fecha de
  creación y, a igualdad de fecha, por identificador en orden ascendente. El orden MUST ser el mismo
  en consultas repetidas con los mismos datos.
- **FR-016**: Se declara expresamente, solo para esta operación, la excepción de paginación del
  Principio IV: la lista de clínicas recientes está acotada por diseño a un máximo fijo de 10
  elementos, tiene el orden determinista de FR-015 y MUST NOT paginarse. Esta excepción no cambia la
  regla general de paginación de los demás listados.

**Configuración**

- **FR-017**: El valor por defecto de la cantidad de clínicas recientes MUST definirse con la
  variable de entorno opcional `DASHBOARD_RECENT_CLINICS_LIMIT`, que solo admite los valores 3, 5 o
  10. Si no se configura (o está vacía), el valor por defecto MUST ser 5.
- **FR-018**: Si el valor configurado no es 3, 5 ni 10, el servicio MUST NOT arrancar y MUST indicar
  qué variable es inválida, sin mostrar su valor ni secretos.
- **FR-019**: La variable MUST documentarse en `.env.example` con sus valores admitidos y su valor por
  defecto, y MUST validarse al arrancar como el resto de la configuración del servicio. Un cambio de
  valor MUST requerir reiniciar el servicio: el servicio en marcha no relee la variable.

**Datos ficticios de la Fase 1**

- **FR-020**: En la Fase 1, los datos de clínicas, doctores, pacientes y usuarios MUST ser ficticios
  pero coherentes, porque pertenecen a otros APIs de MailySoft que aún no existen. MUST NOT guardarse
  en la base de datos de este servicio: esta feature no añade tablas, migraciones ni cambios al
  esquema de datos.
- **FR-021**: Los datos ficticios MUST ser deterministas: los mismos valores en cada llamada y tras
  cada reinicio, sin depender del reloj, del azar ni del orden de las consultas. Todos los
  identificadores MUST ser UUID válidos.
- **FR-022**: Los datos ficticios MUST cumplir estas invariantes: la suma de clínicas activas y en
  prueba no supera el total de clínicas; el número de clínicas recientes devueltas no supera el total;
  el total de usuarios no es menor que el total de doctores (FR-007); y, para cada estatus, el número
  de clínicas recientes devueltas con ese estatus no supera el conteo correspondiente (las «Activa»
  devueltas no superan las clínicas activas; las «En prueba», las clínicas con periodo de prueba).
- **FR-023**: El conjunto de clínicas ficticias MUST tener al menos 10 clínicas, para poder devolver
  cualquier cantidad hasta el máximo. Entre las 10 más recientes MUST haber clínicas «Activa» y
  «En prueba» y al menos dos con exactamente la misma fecha de creación.
- **FR-024**: Al arrancar, el servicio MUST registrar un aviso de que el dashboard usa datos ficticios,
  para que no pase a producción sin que nadie lo note. El aviso MUST NOT impedir el arranque ni
  incluir secretos.

**Contrato estable y degradación futura**

- **FR-025**: El contrato de respuesta MUST ser estable: cuando existan los APIs reales, solo MUST
  cambiar el origen de los datos, sin cambiar los campos, sus tipos ni su significado y sin afectar a
  los consumidores. Todo cambio incompatible posterior MUST versionarse (Principio IV).
- **FR-026**: El contrato publicado MUST reservar desde esta versión que cada indicador sea un entero
  o `null` y que la lista de clínicas recientes sea una lista o `null`, para que activar la
  degradación futura no sea un cambio incompatible. En la Fase 1 ningún valor es `null`.
- **FR-027**: Cuando una fuente de datos falle (no responda, agote el tiempo de espera o conteste algo
  inesperado), el indicador que depende de ella MUST devolverse como `null` y MUST NOT inventarse un
  cero; la lista de clínicas recientes, si depende de esa fuente, MUST devolverse como `null` y no
  como `[]`. El resto del dashboard MUST seguir devolviéndose con 200, incluso si fallan todas las
  fuentes (todo en `null`): solo la falla del control de acceso impide responder. Un `0` o un `[]`
  MUST significar únicamente que la fuente respondió que no hay datos. La respuesta MUST NOT revelar
  direcciones, cuerpos de error ni credenciales de la fuente que falló.
- **FR-028**: La falla de una fuente de datos MUST NOT afectar al control de acceso, que sigue
  fallando cerrado (FR-002).

**Calidad de la API y alcance**

- **FR-029**: La operación MUST ser de solo lectura: esta feature MUST NOT incluir operaciones de
  escritura y ningún dato devuelto puede modificarse mediante esta API. No hay caché: cada consulta
  MUST reflejar el estado vigente de los datos, sin reutilizar resultados de consultas anteriores, y
  la respuesta 200 MUST indicar a navegadores y servidores intermedios que no debe guardarse en caché
  (`Cache-Control: no-store`).
- **FR-030**: Los errores MUST usar el formato uniforme y los códigos del catálogo de errores vigente
  (401, 403, 503 y 422 con los códigos que ya existen), con mensajes en español que no revelen el
  token, secretos ni detalles internos de otros servicios. Esta feature MUST NOT modificar el
  catálogo de errores existente.
- **FR-031**: La operación MUST documentarse en el contrato publicado de la API, en español: su
  resumen y descripción, su etiqueta propia, el permiso que exige, el parámetro `limit` (rango de 1 a
  10, tope de 10 y valor por defecto configurable) y las respuestas 200 (indicando que no se guarda en
  caché), 401, 403, 422 y 503 con ejemplos.
- **FR-032**: Esta feature MUST NOT modificar el comportamiento ni el contrato de la API de
  suscripciones ni de ninguna operación existente. Las pruebas existentes de esas operaciones MUST
  seguir pasando sin cambiar ninguna de sus comprobaciones de comportamiento.
- **FR-033**: Únicas excepciones a FR-032: (a) las comprobaciones que verifican el **conjunto
  completo** de operaciones de la API (la cobertura de permisos, el contrato publicado y la
  cobertura y la prueba de desfase de las colecciones de Postman) MAY ajustarse únicamente para
  reconocer la operación nueva, ampliándose o acotando su alcance al recurso que vigilan, sin
  debilitarse y sin cambiar sus filas ni sus comprobaciones sobre las suscripciones; y (b) la
  aserción de que el arranque no registra ningún aviso MAY limitarse a los avisos propios de lo que
  verifica (los de direcciones inseguras), porque FR-024 añade un aviso de arranque nuevo. El plan
  MUST enumerar cada ajuste y justificarlo.

**Verificación**

- **FR-034**: Las pruebas automatizadas MUST NOT llamar a APIs reales: el API de usuarios se sustituye
  por una simulación que reproduce su contrato y sus fallos, y las fuentes de datos del dashboard son
  los datos ficticios o simulaciones.
- **FR-035**: Las pruebas automatizadas del servicio MUST cubrir: sin `limit` (valor por defecto);
  `limit` válido; `limit` mayor que 10 (devuelve 10); `limit` inválido (422, incluidos 0, negativo,
  texto, decimal, vacío y repetido); menos clínicas que el límite; ninguna clínica (`[]` y conteos
  en 0); el orden y el desempate; el valor configurado válido (3, 5, 10 y ausente) e inválido (el
  servicio no arranca y nombra la variable sin mostrar su valor); el aviso de datos ficticios al
  arrancar; las invariantes y el determinismo de los datos ficticios; que la respuesta no contiene
  datos personales; que la respuesta 200 declara que no se guarde en caché; los errores 401, 403 y
  503; que el permiso se comprueba antes que `limit`; y la degradación de FR-027 con fuentes
  simuladas que fallan.
- **FR-036**: MUST añadirse una colección de Postman nueva e independiente, en `tests/postman/`, de
  punta a punta y automática (se ejecuta contra el servicio real con las simulaciones de sus
  dependencias, como la de suscripciones), con los recorridos y los errores clave de esta operación:
  sin `limit`, `limit` válido, `limit` mayor que 10 (devuelve 10), `limit` inválido (422), el orden y
  el desempate, y los errores 401, 403 y 503. MUST NOT repetir lo que ya cubren las pruebas
  automatizadas del servicio y MUST NOT modificar ninguna de las dos colecciones existentes (la
  automática de suscripciones y la manual); no se añade el dashboard a la manual. Sin secretos, según
  las reglas de la constitución para las colecciones.
- **FR-037**: La cobertura de permisos MUST actualizarse según el flujo de la constitución: la matriz
  «operación → permiso» incluye la operación nueva con `dashboard:read`, y la prueba de cobertura de
  permisos falla si la ruta del dashboard carece de permiso declarado o no coincide con la matriz,
  sin modificar lo que ya existe (FR-004, FR-033).

### Key Entities

- **Resumen del dashboard («Panel de Maily»)**: la vista de solo lectura que se devuelve en una
  consulta. Reúne seis indicadores y la lista de clínicas recientes. No se guarda: se compone en cada
  consulta. Campos propuestos (nombres en inglés, Principio VII): `total_clinics`, `active_clinics`,
  `trial_clinics`, `total_doctors`, `total_patients`, `total_users` y `recent_clinics`.
- **Indicador**: un conteo entero mayor o igual a cero. El contrato reserva `null` para «no
  disponible» (fuente fallida); nunca se usa 0 para eso.
- **Clínica reciente**: resumen básico de una clínica: identificador (UUID), nombre, fecha de creación
  (ISO 8601, UTC) y estatus. Campos propuestos: `id`, `name`, `created_at` y `status`.
- **Estatus de clínica**: objeto con identificador y nombre, propio del dominio de clínicas. En la
  Fase 1 se usan «Activa» y «En prueba»; existen otros estatus que el panel no desglosa y que solo
  cuentan en el total.
- **Cantidad por defecto de clínicas recientes**: valor de configuración (3, 5 o 10; 5 si no se
  configura) que rige cuando la persona no envía `limit`.
- **Persona autenticada y permiso `dashboard:read`** *(externos, del API de usuarios)*: quien consulta
  y el permiso que el API de usuarios le reconoce. Este servicio no los guarda.
- **Fuentes de datos** *(externas y futuras)*: los APIs de MailySoft que aportarán clínicas, doctores,
  pacientes y usuarios. En la Fase 1 no existen y se sustituyen por datos ficticios.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El resumen completo —los seis indicadores y hasta 10 clínicas recientes— se obtiene en
  una sola consulta y aparece en pantalla en menos de 2 segundos en el 95 % de las consultas en
  condiciones normales.
- **SC-002**: El 100 % de las consultas sin token, con token inválido, sin el permiso `dashboard:read`
  o con el API de usuarios inaccesible se rechaza sin devolver ningún dato, y una verificación
  automática que recorre todas las rutas confirma que la del dashboard declara su permiso.
- **SC-003**: Un bloqueo o un cambio de permisos hecho en el API de usuarios surte efecto en la
  siguiente consulta de esa persona (0 consultas posteriores aceptadas por permisos ya revocados).
- **SC-004**: En el 100 % de las combinaciones de acceso fallido (sin token, sin permiso, API de
  usuarios caído) con un `limit` inválido, la respuesta es la del acceso (401, 403 o 503) y nunca la
  de validación (422).
- **SC-005**: Para cualquier `limit` entero válido, la cantidad de clínicas devueltas es la menor entre
  `limit`, 10 y las clínicas existentes (100 % de los casos probados); para todo `limit` menor que 1,
  no entero, vacío o repetido, la respuesta es 422 (100 %).
- **SC-006**: Dos consultas seguidas con los mismos datos, incluso con un reinicio del servicio entre
  ambas, devuelven respuestas idénticas en valores y en orden (100 %), y las invariantes de
  coherencia (activas + prueba ≤ total; recientes ≤ total; estatus de las recientes ≤ conteos;
  doctores ≤ usuarios) se cumplen en el 100 % de las respuestas.
- **SC-007**: Ninguna respuesta del dashboard contiene datos personales de pacientes, doctores ni
  usuarios (0 casos): solo los campos del contrato publicado.
- **SC-008**: El servicio arranca con la variable de configuración ausente, con 3, con 5 y con 10, y
  rechaza el arranque con cualquier otro valor en el 100 % de los casos probados; el mensaje nombra la
  variable y nunca muestra su valor.
- **SC-009**: El 100 % de los arranques con datos ficticios registra el aviso correspondiente, y la
  base de datos del servicio queda sin ningún cambio de esquema por esta feature (0 tablas y 0
  migraciones nuevas).
- **SC-010**: Con fuentes simuladas que fallan una por una, el 100 % de las respuestas conserva el
  resto del dashboard con 200 y deja en `null` solo los indicadores afectados (0 ceros inventados), y
  el contrato publicado de la respuesta no cambia entre los datos ficticios y las fuentes simuladas.
- **SC-011**: Las pruebas de la API de suscripciones y de las demás operaciones existentes siguen en
  verde sin cambiar ninguna de sus comprobaciones de comportamiento (0 comprobaciones de
  comportamiento modificadas).
- **SC-012**: La colección de Postman de esta operación se ejecuta en verde de punta a punta contra el
  servicio real con las simulaciones de sus dependencias, y cubre todos los casos que FR-036 enumera.

## Assumptions

- **Actor y alcance**: la consulta es para el administrador de plataforma de Maily (personal de
  MailySoft), no para las clínicas. Los dashboards propios de cada clínica, la gestión o suspensión de
  suscripciones, la alerta de clínicas con prueba o periodo vencido, los filtros, la paginación y
  cualquier operación de escritura quedan **fuera de alcance**.
- **Nombres del contrato**: los nombres de campo en inglés de «Key Entities» son los que propone esta
  especificación y se fijan en el contrato publicado del plan, junto con la ruta de la operación (bajo
  el prefijo versionado `/api/v1`) y su identificador de operación. El nombre del permiso
  (`dashboard:read`) sigue la convención `recurso:acción` de la constitución.
- **Tipo del identificador de estatus de clínica**: se asume entero, como el estatus de las
  suscripciones (un catálogo con identificador y nombre). Cuando exista el API de clínicas, deberá
  respetar ese tipo para no romper el contrato (FR-025); si publicara otro, se resolvería en la
  especificación que lo conecte.
- **Orden de desempate**: la especificación no fijaba el sentido del desempate por identificador; se
  elige ascendente (coherente con el desempate del catálogo de suscripciones, que también ordena por
  identificador).
- **La lista de clínicas recientes y el Principio IV**: es un fragmento acotado del resumen (máximo
  fijo de 10), no un listado paginable. Por prudencia se declara aquí la excepción que el Principio IV
  prevé (FR-016), con su máximo y su orden; se asume, como indicó la persona responsable, que no hace
  falta enmendar la constitución. El «Constitution Check» del plan lo confirmará.
- **Degradación (confirmada en la sesión de aclaraciones 2026-10-18)**: la solicitud decía que el
  indicador afectado se devuelve como `null`; la persona responsable confirmó que la misma regla rige
  para la lista de clínicas recientes, porque un `[]` afirmaría «no hay clínicas», un dato inventado
  igual que un cero, y que si fallan todas las fuentes la respuesta sigue siendo 200 con todo en
  `null`, porque la única falla que debe impedir responder es la del control de acceso (Principios
  VIII y IX).
- **Qué es una «fuente»**: cada indicador depende de la fuente que lo aporta (clínicas, doctores,
  pacientes, usuarios). Qué API concreto aporta cada una, y su contrato consumido, se documentarán en
  la especificación que lo conecte (Principio IX); esta feature no define ni consume ningún API nuevo.
  En la Fase 1 la degradación no puede ocurrir con los datos ficticios: queda definida, declarada en el
  contrato y comprobada con fuentes simuladas (FR-027, FR-035).
- **Los datos ficticios no son una copia de datos ajenos**: viven en el código del servicio y no
  almacenan datos reales de otro sistema, por lo que no contradicen el Principio IX; son
  provisionales y se sustituirán por las fuentes reales.
- **Dependencia del API de usuarios**: el permiso `dashboard:read` MUST estar dado de alta en su
  catálogo (su dueño) y asociado al rol de administración de plataforma antes de integrar; este
  servicio no lo crea. Hasta entonces se prueba con la simulación del API de usuarios, que debe poder
  conceder y denegar ese permiso.
- **Ajuste de las pruebas que vigilan el conjunto completo de la API (FR-033)**: la solicitud pide
  que no cambien las pruebas de las operaciones existentes y, a la vez, que se actualice la cobertura
  de permisos. Varias comprobaciones actuales dan por hecho que la API tiene **exactamente** seis
  operaciones (cobertura de permisos, contrato publicado, y cobertura y prueba de desfase de las
  colecciones de Postman), por lo que cualquier operación nueva las haría fallar. Se interpreta que
  esas comprobaciones —y solo ellas— se amplían o acotan para reconocer la operación nueva, sin
  debilitarse ni tocar lo que verifican sobre las suscripciones; la colección de Postman nueva es
  independiente y no se añade a las existentes. El plan enumera cada ajuste. *Hallazgo de la
  planificación (2026-10-18)*: una prueba del arranque exige que no se registre **ningún** aviso con
  direcciones válidas, y el aviso de datos ficticios (FR-024) la haría fallar; por eso FR-033(b) permite
  limitar esa aserción a los avisos de direcciones inseguras, que es lo que la prueba quiere verificar.
- **Reparto de las pruebas**: los casos «menos clínicas que el límite», «ninguna clínica», «valor
  configurado válido e inválido» y la degradación se verifican con las pruebas automatizadas del
  servicio, porque la colección de Postman corre contra el servicio real con los datos ficticios fijos
  y no puede cambiar su configuración ni su conjunto de datos; la colección cubre los recorridos de
  punta a punta y los errores clave (Principio V). La pila aislada de punta a punta sustituye al API de usuarios por su
  simulación.
- **Condiciones normales (SC-001)**: el API de usuarios responde en menos de 500 ms y el 95 % se mide
  sobre una serie de consultas seguidas. En la Fase 1 los datos ficticios no añaden espera; cuando
  existan las fuentes reales, se revisará el criterio en la especificación que las conecte.
- **Zona horaria**: las fechas de creación se devuelven siempre en UTC; mostrarlas en la hora local de
  la persona es responsabilidad de la aplicación que consume la API.
- **Idioma**: los campos, parámetros y códigos están en inglés; los mensajes, la documentación
  publicada y este documento, en español (Principio VII).
- **Documentación de uso**: el README del proyecto se mantiene al día con la nueva operación y la nueva
  variable de configuración; el detalle lo fija el plan.
