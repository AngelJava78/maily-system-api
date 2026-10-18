# Feature Specification: Colección de Postman para Probar a Mano la API de Sistema

**Feature Branch**: `002-manual-postman-collection`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "Colección de Postman para probar a mano la API de sistema (MailySoft
System API) desde la aplicación de Postman. Colección nueva e independiente, solo manual, que no
depende de las simulaciones ni de Newman y que no toca la colección de punta a punta de la spec
001. Se usa contra un entorno local y contra un segundo entorno desplegado de pruebas (base de
datos de pruebas, nunca real). Cubre las 6 operaciones de suscripciones y la documentación
pública, con datos de ejemplo, descripciones en español y casos de error clave. Un script previo
pide y renueva solo el token de Auth0 con client credentials (aplicación Machine to Machine); el
secreto del cliente solo vive en el valor actual local de Postman. Una carpeta opcional permite
manejar la simulación local del API de clínicas. Incluye una prueba de desfase y documentación en
el README."

## Clarifications

### Session 2026-10-18

- Q: ¿La colección manual es nueva e independiente o la de punta a punta debe funcionar también en
  modo manual? → A: Nueva e independiente, solo manual. La colección de la spec 001 (para Newman y
  las simulaciones) no se toca; la prueba de desfase pasa a vigilar las dos.
- Q: ¿Cómo se obtiene el token de Auth0 dentro de Postman? → A: Con un script previo de la
  colección que pide y renueva solo el token con *client credentials* (aplicación Machine to
  Machine, cuyo `sub` termina en `@clients`). El dominio, el *audience* y el *client id* son
  variables del entorno; el *client secret* es una variable secreta que solo vive en la copia local
  de Postman (el valor actual), nunca en los archivos.
- Q: ¿Contra qué entornos se usa? → A: Contra el local (API local, API de usuarios local y una base
  de datos dedicada a las pruebas manuales, distinta de la de desarrollo y de la que usa pytest) y
  contra un segundo entorno desplegado de pruebas cuya base de datos es de pruebas, nunca real: dos
  archivos de entorno. La constitución exige que las colecciones apunten a una base de datos
  dedicada a pruebas y prohíbe apuntarlas a datos reales.
- Q: Sin API de clínicas real, ¿cómo se prueba a mano el borrado y el conteo de clínicas? → A: Se
  documenta cómo levantar localmente la simulación del API de clínicas en el puerto 8001 y la
  colección trae una carpeta opcional «Simulación de clínicas (solo local)» para fijar conteos y
  provocar fallos.

## User Scenarios & Testing *(mandatory)*

El actor es **quien prueba la API** (una persona del equipo que desarrolla o revisa, desde la
aplicación de escritorio de Postman). No necesita escribir URLs, cuerpos ni cabeceras: importa la
colección y un entorno, configura sus valores de acceso una sola vez y envía peticiones con datos de
ejemplo ya preparados. La colección es para **uso manual**; la verificación automática de punta a
punta sigue siendo la de la spec 001.

### User Story 1 - Entrar sin pegar tokens (Priority: P1)

Quien prueba rellena una sola vez, en su entorno, los datos de su aplicación de acceso (dominio,
destinatario del token e identificador del cliente) y su secreto. A partir de ahí, la colección
pide sola el token de Auth0 antes de la primera petición, lo reutiliza mientras sirve y lo renueva
poco antes de que venza, sin que la persona lo copie ni lo pegue nunca. Si el token no puede
obtenerse, la colección dice por qué en español en lugar de enviar una petición sin credenciales.

**Why this priority**: Toda operación de la API exige token y permiso; sin esto no se puede probar
nada y el token vence cada pocas horas, lo que haría tediosa cualquier sesión de pruebas.

**Independent Test**: Con la aplicación de acceso ya preparada, importar la colección y el entorno
local, rellenar los valores de acceso y enviar la primera petición de lectura: responde 200 sin que
la persona haya pegado ningún token. Dejar vacío un valor o poner un secreto equivocado y repetir:
la petición no sale y aparece una explicación en español.

**Acceptance Scenarios**:

1. **Given** los valores de acceso completos y ningún token guardado, **When** se envía cualquier
   petición que exige token, **Then** la colección lo pide, lo guarda en la copia local de la persona
   y la petición sale con él.
2. **Given** un token guardado que todavía sirve, **When** se envían más peticiones, **Then** se
   reutiliza sin pedir otro.
3. **Given** un token a punto de vencer o vencido, **When** se envía una petición, **Then** se pide
   uno nuevo antes de enviarla.
4. **Given** que falta algún valor de acceso, **When** se envía una petición, **Then** no se envía y
   la colección nombra, en español, el valor que falta y dónde se rellena.
5. **Given** que Auth0 rechaza las credenciales, no responde o la aplicación no está autorizada para
   el destinatario indicado, **When** se envía una petición, **Then** no se envía y la colección
   explica la causa probable y qué revisar, sin mostrar el secreto ni el token.
6. **Given** que se cambia de entorno (por ejemplo, de local a desplegado), **When** se envía una
   petición, **Then** no se reutiliza el token del otro entorno: se pide uno nuevo.

---

### User Story 2 - Recorrer las operaciones con datos de ejemplo (Priority: P1)

Quien prueba recorre, petición a petición, el ciclo de vida de una suscripción: crear, consultar,
listar, actualizar, cambiar el estatus a Inactiva, Bloqueada y de nuevo Activa, eliminar y comprobar
que ya no aparece. Cada petición trae datos de ejemplo válidos y una descripción en español que dice
qué hace, qué permiso necesita y qué respuestas esperar. Las peticiones de creación guardan el
identificador y el nombre único que necesitan las siguientes; las que cambian o eliminan solo actúan
sobre lo que creó la propia colección.

**Why this priority**: Es el uso principal: ver la API en acción, enseñarla y reproducir un problema
sin escribir nada a mano.

**Independent Test**: Importar la colección con el entorno local, enviar «Crear suscripción» y luego
«Consultar suscripción» sin editar nada: la segunda usa el identificador devuelto por la primera.
Enviar «Eliminar» antes de haber creado nada: no afecta a ningún dato existente.

**Acceptance Scenarios**:

1. **Given** la colección y el entorno importados y el acceso configurado, **When** se envía
   cualquier petición con sus datos de ejemplo, **Then** llega a la API sin editar la dirección ni
   el cuerpo.
2. **Given** una petición de creación, **When** se envía, **Then** crea una suscripción con un
   nombre único en cada ejecución y guarda su identificador y su nombre para las siguientes
   peticiones.
3. **Given** una suscripción creada por la colección, **When** se recorren consultar, actualizar,
   cambiar el estatus y eliminar, **Then** cada una actúa sobre esa suscripción y su respuesta se
   comprueba en pantalla (estatus esperado y datos clave, con títulos en español).
4. **Given** una petición de actualizar, cambiar el estatus o eliminar enviada antes de crear nada,
   **When** se envía, **Then** no afecta a ninguna suscripción existente y la colección explica que
   primero hay que crear la de prueba.
5. **Given** la API sin API de clínicas, **When** se envía «Eliminar», **Then** la respuesta
   esperada es el rechazo por no poder comprobar las clínicas, y la colección lo explica en lugar
   de darlo por un fallo.
6. **Given** cualquier petición, **When** se consulta su descripción, **Then** explica en español qué
   hace, qué permiso requiere y qué respuestas esperar.
7. **Given** la documentación pública de la API, **When** se envían sus dos peticiones (contrato y
   documentación interactiva), **Then** responden sin token.

---

### User Story 3 - Provocar y entender los errores clave (Priority: P2)

Quien prueba dispone de casos preparados que provocan a propósito los errores que más importan a
quien consume la API, con una descripción que explica por qué ocurren y cómo se arreglan: sin token y
con un token inválido (401), sin permiso (403), suscripción inexistente o eliminada (404), nombre o
estatus repetidos (409), datos no válidos (422) y eliminación que no puede comprobarse (503). Cada
caso comprueba el estatus, el código de error y el mensaje en español.

**Why this priority**: Quien programa contra la API depende de esos códigos y mensajes; verlos y
entenderlos a mano evita sorpresas y ayuda a diagnosticar cuando algo falla en un entorno.

**Independent Test**: Enviar cada caso de la carpeta de errores: cada uno provoca su error y la
comprobación confirma estatus, código y mensaje.

**Acceptance Scenarios**:

1. **Given** una petición sin token y otra con un token inventado, **When** se envían, **Then** ambas
   responden 401 con el código correspondiente.
2. **Given** una segunda aplicación de acceso opcional sin permisos, ya configurada, **When** se envía
   el caso de «persona sin permiso», **Then** responde 403 nombrando el permiso que falta.
3. **Given** que esa segunda aplicación no está configurada, **When** se envía el caso, **Then** no
   se envía y la colección explica cómo configurarla, sin contarlo como fallo.
4. **Given** un identificador inexistente y el de una suscripción ya eliminada, **When** se
   consultan, **Then** responden 404 con el mensaje en español.
5. **Given** un nombre ya usado y un cambio de estatus al que ya tiene, **When** se envían, **Then**
   responden 409 con su código.
6. **Given** datos no válidos (nombre ausente, precio negativo o con tres decimales, campo no
   permitido, estatus no permitido, lista de funciones nula), **When** se envían, **Then** responden
   422 con `errors` indicando el campo y el mensaje en español.
7. **Given** una suscripción creada y sin forma de comprobar sus clínicas, **When** se envía
   «Eliminar», **Then** responde 503 con el código de «no se pudo comprobar» y no se elimina nada.
8. **Given** las descripciones de la colección, **When** se leen, **Then** explican qué significa un
   503 por permiso no verificable (el API de usuarios no responde) y qué revisar cuando todo responde
   403 (la persona no está registrada o su rol no tiene los permisos), sin que la colección los
   provoque.

---

### User Story 4 - Usar la colección en un entorno desplegado de pruebas (Priority: P2)

Quien prueba cambia al segundo entorno, el desplegado de pruebas, rellena sus valores de acceso y
usa la misma colección sin tocar ninguna petición. La documentación y el propio entorno advierten de
que debe apuntar a una base de datos de pruebas y nunca a datos reales; la colección nunca modifica
ni elimina datos que no haya creado ella misma.

**Why this priority**: Probar solo en local no detecta problemas de despliegue (direcciones, acceso,
configuración de los otros APIs); un segundo entorno de pruebas lo cubre con el mismo material.

**Independent Test**: Seleccionar el entorno desplegado, rellenar sus valores y enviar la primera
lectura: responde 200 sin editar ninguna petición. Recorrer el ciclo de vida: solo toca la
suscripción que creó la colección.

**Acceptance Scenarios**:

1. **Given** el entorno desplegado y sus valores de acceso, **When** se envían las peticiones,
   **Then** funcionan igual que en local sin editar ninguna URL ni cuerpo.
2. **Given** un entorno que ya contiene suscripciones de otras personas, **When** se recorre el
   ciclo de vida, **Then** ninguna suscripción preexistente se modifica ni se elimina.
3. **Given** el entorno desplegado, **When** se lee su descripción, **Then** advierte de que debe
   apuntar a una base de datos de pruebas, nunca a datos reales.

---

### User Story 5 - Probar las clínicas con la simulación local (Priority: P3)

Quien prueba, en local, levanta la simulación del API de clínicas siguiendo la documentación y usa
una carpeta opcional de la colección para fijar cuántas clínicas tiene una suscripción, provocar los
fallos del API de clínicas y reiniciar la simulación. Así puede ver el conteo real, el conteo
«no disponible», el rechazo de eliminar una suscripción con clínicas y su eliminación cuando ya no las
tiene.

**Why this priority**: Sin API de clínicas real, es la única forma de ver a mano el comportamiento
que depende de ella. Es opcional: el resto de la colección funciona sin la simulación.

**Independent Test**: Con la simulación levantada, fijar 3 clínicas a una suscripción de prueba,
consultarla (conteo 3), intentar eliminarla (rechazo), fijar 0 y eliminarla (204).

**Acceptance Scenarios**:

1. **Given** la simulación levantada en local, **When** se fija el conteo de una suscripción y se
   consulta, **Then** la respuesta muestra ese conteo.
2. **Given** una suscripción con clínicas en la simulación, **When** se intenta eliminar, **Then** se
   rechaza (409) y sigue existiendo.
3. **Given** la simulación con un fallo provocado, **When** se consulta una suscripción, **Then** el
   conteo sale «no disponible» (`null`) y la consulta sigue funcionando; y al intentar eliminar se
   rechaza (503).
4. **Given** el entorno desplegado (sin simulación), **When** se envía una petición de esa carpeta,
   **Then** no se envía nada y la colección lo advierte sin contarlo como fallo.
5. **Given** que no hay simulación ni API de clínicas, **When** se consulta una suscripción, **Then**
   el conteo sale «no disponible» y la colección explica que es lo esperado.

---

### User Story 6 - Detectar que la colección se quedó atrás de la API (Priority: P3)

Una prueba automática de la suite normal compara las operaciones que publica la API con las de la
colección manual y falla, nombrando las que falten o sobren. También comprueba que los archivos de la
colección y los entornos no contienen secretos ni tokens y que los dos entornos definen las mismas
variables.

**Why this priority**: Sin esta guarda, la colección se desactualiza en silencio cada vez que crece la
API o alguien pega un secreto por error en un archivo; es barata y protege el valor de las demás
historias.

**Independent Test**: Quitar una petición de la colección manual (o añadir una operación a la API): la
prueba falla y nombra la operación; restaurarla hace que pase. Escribir un secreto en un archivo de
entorno: la prueba falla.

**Acceptance Scenarios**:

1. **Given** que cada operación de la API tiene su petición en la colección manual, **When** corre la
   prueba, **Then** pasa.
2. **Given** una operación de la API sin petición, o una petición que ya no corresponde a ninguna
   operación, **When** corre la prueba, **Then** falla y la nombra.
3. **Given** un secreto, un token o un valor no vacío en una variable secreta de un archivo, **When**
   corre la prueba, **Then** falla indicando el archivo y la variable.
4. **Given** un equipo sin servicio levantado, sin Node.js y sin Postman, **When** se ejecuta la
   suite, **Then** esta prueba corre igualmente, porque solo lee archivos del repositorio.

---

### User Story 7 - Ponerse en marcha siguiendo solo la documentación (Priority: P3)

Cualquier persona del equipo, sin conocer el proyecto, puede importar la colección, preparar su
acceso, levantar lo necesario en local y enviar su primera petición leyendo el README y las
descripciones de la propia colección.

**Why this priority**: Una colección que solo sabe usar quien la creó no sirve como práctica del
equipo; los requisitos previos de Auth0 y del API de usuarios son lo que más se tropieza.

**Independent Test**: Una persona que no participó en la feature sigue el README desde cero y obtiene
una respuesta 200 del catálogo sin pedir ayuda.

**Acceptance Scenarios**:

1. **Given** una persona con una aplicación de acceso de Auth0 sin preparar, **When** sigue la
   documentación, **Then** sabe qué debe configurar en Auth0 y en el API de usuarios (autorizar la
   aplicación para el destinatario, registrar su `sub` como usuario y darle un rol con los cuatro
   permisos de suscripciones) antes de enviar peticiones.
2. **Given** que todas las respuestas son 403, **When** consulta la documentación, **Then** encuentra
   la causa probable y cómo resolverla.
3. **Given** una persona que va a usar la colección, **When** lee las instrucciones, **Then** queda
   advertida de no apuntarla a datos reales y de escribir el secreto solo en su copia local.

---

### Edge Cases

- **Falta un valor de acceso o está vacío**: la petición no sale; se nombra el valor que falta.
- **Credenciales rechazadas, aplicación no autorizada para el destinatario, Auth0 sin respuesta o
  respuesta inesperada**: la petición no sale; se explica la causa probable. Nunca se envía una
  petición que exige token sin token.
- **Todo responde 403**: la persona no está registrada en el API de usuarios o su rol no tiene los
  permisos de suscripciones; la documentación lo explica. (El script de arranque del API de usuarios
  solo concede al Administrator los permisos de usuarios, roles y permisos, no los de suscripciones.)
- **El API de usuarios no responde**: todo responde 503 por permiso no verificable; está explicado,
  no se provoca desde la colección.
- **Sin API de clínicas ni simulación**: las lecturas muestran el conteo «no disponible» y eliminar
  responde 503; es el comportamiento esperado, no un fallo de la colección.
- **Cambio de entorno a mitad de una sesión**: no se reutiliza el token del otro entorno ni los
  identificadores guardados de la suscripción de prueba (que no existen allí).
- **Peticiones de actualizar, cambiar el estatus o eliminar sin haber creado nada**: no afectan a
  ningún dato existente.
- **Repetir el recorrido**: cada creación usa un nombre único, así que repetir no choca con lo que
  dejó la ejecución anterior (las suscripciones eliminadas quedan con estatus «Eliminada»).
- **Persona con sesión iniciada en Postman**: en algunas versiones los valores iniciales se
  sincronizan con la nube de Postman y los actuales no; por eso el secreto se escribe solo en la copia
  local (el valor actual). La colección no puede impedir que alguien lo escriba en un valor que se
  sincronice: la documentación lo advierte y la prueba de archivos detecta el caso del repositorio.
- **Entorno desplegado sin simulación de clínicas**: la carpeta opcional no envía nada y lo
  advierte.
- **Dos personas probando a la vez el mismo entorno**: cada una crea nombres únicos; no hay totales
  globales que comprobar.
- **El token se vence entre dos peticiones**: la siguiente petición pide uno nuevo antes de salir.

## Requirements *(mandatory)*

### Functional Requirements

**Cobertura y estructura**

- **FR-001**: El proyecto MUST incluir una colección de Postman **nueva e independiente**, de uso
  manual, que cubra las 6 operaciones de suscripciones (listar, consultar, crear, actualizar,
  cambiar el estatus y eliminar) y las dos peticiones de documentación pública (contrato y
  documentación interactiva). MUST NOT modificar la colección de punta a punta de la spec 001 ni
  depender de sus simulaciones, de Newman ni de sus peticiones auxiliares.
- **FR-002**: La colección MUST organizarse en carpetas por propósito: empezar y comprobar el
  acceso, ciclo de vida de una suscripción, casos de error y la carpeta opcional de simulación de
  clínicas. Dentro de cada carpeta, las peticiones MUST ir en un orden que funcione de principio a
  fin.
- **FR-003**: Cada petición MUST llevar datos de ejemplo válidos y una descripción en español que
  diga qué hace, qué permiso requiere y qué respuestas esperar. Cada carpeta y la propia colección
  MUST llevar una descripción general.
- **FR-004**: Las peticiones de creación MUST usar un nombre único en cada ejecución y MUST guardar el
  identificador y el nombre generados para las siguientes. Las peticiones que actualizan, cambian el
  estatus o eliminan MUST actuar solo sobre datos creados por la propia colección y MUST NOT afectar
  a datos preexistentes del entorno, aunque se envíen antes de haber creado nada (en ese caso MUST
  explicar que primero hay que crear). Antes de modificar o eliminar, MUST comprobar que la
  suscripción guardada sigue existiendo y conserva el nombre con que la creó la colección (el
  identificador podría haber pasado a ser de otra persona si la base de pruebas se reinició); si no,
  MUST no enviarla y explicarlo. Los identificadores y nombres guardados MUST descartarse si cambia
  la dirección de la API a la que apunta el entorno.
- **FR-005**: Cada petición MUST comprobar su respuesta de forma visible en Postman (estatus esperado
  y datos clave), con títulos en español, apoyándose solo en datos estables (estatus, códigos de
  error, campos clave y los mensajes que fija el contrato). MUST NOT repetir las pruebas de pytest.
  La petición de eliminar MUST aceptar como esperados tanto la eliminación (204) como el rechazo por
  no poder comprobar las clínicas (503), explicando cada caso.

**Entornos**

- **FR-006**: El proyecto MUST incluir dos archivos de entorno: **local** (API local; dirección por
  defecto `http://127.0.0.1:8010`) y **desplegado de pruebas**. La colección MUST funcionar con
  cualquiera de los dos sin editar ninguna URL ni cuerpo; cambiar de entorno solo exige elegirlo y
  rellenar sus valores.
- **FR-007**: Cada entorno MUST definir las variables de acceso: dominio de Auth0, destinatario
  (*audience*) del token —el del API de usuarios, que es quien lo verifica—, identificador del
  cliente y el secreto del cliente (variable secreta), más, opcionales, el identificador y el secreto
  de una segunda aplicación sin permisos y la dirección de la simulación de clínicas (solo local).
- **FR-008**: Los entornos MUST advertir de que deben apuntar a una base de datos de pruebas, nunca a
  datos reales (el formato de entorno no tiene campo de descripción: la advertencia va en el nombre del
  entorno y en una variable informativa); el entorno desplegado MUST documentarlo expresamente.

**Acceso y secretos**

- **FR-009**: La colección MUST pedir el token de Auth0 con *client credentials* mediante un script
  previo, usando las variables del entorno; MUST guardarlo, junto con su vencimiento, en variables de
  colección de la copia local de la persona (nunca en los archivos); MUST reutilizarlo mientras no esté
  por vencer y MUST renovarlo automáticamente poco antes de que venza. MUST descartar el token guardado si cambian el dominio, el
  destinatario o el cliente (por ejemplo, al cambiar de entorno).
- **FR-010**: Si el token no puede obtenerse (falta un valor, credenciales rechazadas, aplicación no
  autorizada para el destinatario, Auth0 sin respuesta o respuesta inesperada), la colección MUST
  explicar en español la causa probable y qué revisar, y MUST NOT enviar a la API ninguna petición
  que exija token. Las excepciones son la documentación pública y los casos de error que
  deliberadamente no llevan token.
- **FR-011**: El secreto del cliente y los tokens MUST NOT aparecer en las descripciones, en los
  mensajes ni en los resultados, y los scripts MUST NOT escribirlos en la consola de Postman. (La propia
  aplicación registra en su consola la petición a Auth0, cuerpo incluido: es local, no se sincroniza y la
  documentación advierte de no compartir capturas de ella.) Los archivos de la colección y de los
  entornos MUST NOT contener secretos ni tokens; el valor de toda variable secreta en los archivos MUST
  ser vacío (el secreto vive solo en la copia local de la persona, nunca en un valor que se sincronice).
  La autenticación de las peticiones MUST limitarse a referenciar la variable del token.
- **FR-012**: La colección MUST funcionar sin iniciar sesión en Postman y MUST NOT enviar resultados
  ni datos a servicios externos distintos de Auth0 (para el token) y de la API probada.

**Errores**

- **FR-013**: La colección MUST traer casos preparados que provoquen y comprueben, con estatus,
  código de error y mensaje en español: sin token (401), token inválido (401), persona sin permiso
  (403, ver FR-014), suscripción inexistente y eliminada (404), nombre repetido y estatus repetido
  (409), datos no válidos (422: nombre ausente, precio negativo o con más de dos decimales, campo no
  permitido, estatus no permitido y lista de funciones nula) y eliminación que no puede comprobarse
  (503).
- **FR-014**: El caso de «persona sin permiso» MUST usar una segunda aplicación de acceso opcional sin
  permisos; si no está configurada, MUST no enviarse y explicar cómo configurarla, sin contarse como
  fallo.
- **FR-015**: Las descripciones MUST explicar, sin provocarlos, el 503 por permiso no verificable
  (el API de usuarios no responde) y la causa habitual de un 403 generalizado (persona no registrada
  o sin los permisos de suscripciones).

**Clínicas**

- **FR-016**: La colección MUST incluir una carpeta **opcional** «Simulación de clínicas (solo
  local)» con peticiones para fijar el conteo de clínicas de una suscripción, provocar los fallos
  de la simulación del API de clínicas y reiniciarla.
- **FR-017**: Esa carpeta MUST no enviar nada cuando la dirección de la simulación no está definida
  (por ejemplo, en el entorno desplegado) y MUST advertirlo, sin contarlo como fallo.
- **FR-018**: La documentación y la colección MUST explicar que, sin API de clínicas ni simulación,
  el comportamiento esperado es conteo «no disponible» (`null`) en las lecturas y rechazo (503) al
  eliminar.

**Mantenimiento**

- **FR-019**: El proyecto MUST incluir una prueba de pytest que compare las operaciones de la API
  (según su contrato publicado) con las de la colección manual, en ambos sentidos, y falle nombrando
  las que falten o sobren. MUST ejecutarse con la suite normal, sin servicio levantado, sin Node.js y
  sin Postman.
- **FR-020**: La suite MUST comprobar que los archivos de la colección manual y de sus entornos no
  contienen tokens ni secretos, que toda variable secreta tiene el valor vacío en los archivos y que
  los dos entornos definen las mismas variables.
- **FR-021**: La documentación MUST indicar que toda feature que añada, quite o cambie operaciones
  actualiza **las dos colecciones** (la de punta a punta y la manual) en el mismo cambio.

**Documentación y límites**

- **FR-022**: El README MUST explicar cómo importar la colección y los entornos, cómo rellenar los
  valores de acceso, cómo crear y migrar la base de datos dedicada a las pruebas manuales, cómo
  levantar la API y el API de usuarios en local, cómo levantar la simulación de clínicas en el
  puerto 8001, cómo usar el entorno desplegado de pruebas y qué hacer ante cada
  fallo de obtención del token. MUST advertir de no apuntar la colección a datos reales y de escribir
  el secreto solo en la copia local de Postman.
- **FR-023**: La documentación MUST enumerar los requisitos previos, que quedan fuera de la
  colección: la aplicación de Auth0 autorizada para el destinatario del API de usuarios; su `sub`
  (que termina en `@clients`) registrado como usuario en el API de usuarios; y un rol de esa persona
  con los cuatro permisos de suscripciones (`subscriptions:read`, `write`, `update` y `delete`), que
  el catálogo del API de usuarios ya incluye pero que su script de arranque no asocia al
  Administrator. Opcionalmente, una segunda aplicación sin permisos.
- **FR-024**: Esta feature MUST NOT modificar el código de la aplicación ni el esquema de datos.
  La colección y los entornos MUST residir en la ubicación que la constitución fija para las pruebas
  de Postman, en formato v2.1.
- **FR-025**: Los mensajes, los títulos de las comprobaciones y las descripciones MUST estar en
  español; los identificadores técnicos (variables, archivos y scripts) MUST estar en inglés.

### Key Entities

- **Colección manual**: Conjunto versionado de carpetas y peticiones con datos de ejemplo,
  descripciones, comprobaciones visibles y el script de acceso. Independiente de la colección de
  punta a punta.
- **Entorno de uso**: Valores que cambian según dónde se usa la colección (local o desplegado de
  pruebas): dirección de la API, datos de acceso a Auth0 y, en local, dirección de la simulación de
  clínicas. No contiene secretos en los archivos.
- **Credenciales de acceso**: Identificador y secreto del cliente de la aplicación de acceso (el
  secreto solo en la copia local) y, opcionalmente, los de una segunda aplicación sin permisos.
- **Token de sesión**: Token de acceso con su vencimiento, guardado solo en la copia local de la
  persona (nunca en los archivos); se renueva solo.
- **Datos de la sesión**: Identificador y nombre único de las suscripciones que crea la colección, y
  que usan las peticiones siguientes.
- **Simulación de clínicas** (solo contexto): Aplicación de la spec 001 que imita el API de clínicas;
  se levanta aparte y se maneja desde la carpeta opcional.
- **API de usuarios y Auth0** (solo contexto): Auth0 entrega el token; el API de usuarios lo verifica y
  decide los permisos. Esta feature los usa, no los modifica.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona con su aplicación de acceso ya preparada importa la colección y el entorno
  local, rellena sus valores de acceso y obtiene su primera respuesta correcta del catálogo en menos
  de 10 minutos, sin pegar ningún token.
- **SC-002**: Durante una sesión de pruebas de al menos 2 horas, la persona no copia, pega ni renueva
  un token a mano ni una sola vez.
- **SC-003**: El 100 % de las 6 operaciones tiene al menos una petición con datos de ejemplo válidos
  y descripción en español, y cada tipo de error del alcance (401, 403, 404, 409, 422 y 503) tiene al
  menos un caso preparado.
- **SC-004**: Con la API arriba, el ciclo de vida completo (crear, consultar, actualizar, cambiar el
  estatus, eliminar) se recorre petición a petición sin editar ninguna URL ni cuerpo, tanto en el
  entorno local como en el desplegado de pruebas.
- **SC-005**: En el 100 % de los casos probados de fallo de acceso (valor ausente, credenciales
  rechazadas, aplicación no autorizada, Auth0 sin respuesta) la colección muestra un mensaje en
  español con la causa probable y no se envía ninguna petición sin token.
- **SC-006**: En el 100 % de los recorridos probados, ninguna suscripción preexistente del entorno se
  modifica ni se elimina: solo cambian las creadas por la colección.
- **SC-007**: Cambiar de entorno exige únicamente elegir el otro y rellenar sus valores: 0 ediciones
  en las peticiones.
- **SC-008**: El 100 % de las operaciones añadidas a la API sin su petición en la colección manual
  hace fallar la prueba de desfase, que nombra la operación que falta; y el 100 % de los secretos o
  tokens escritos en los archivos de la colección o de los entornos la hace fallar.
- **SC-009**: Una persona que no participó en la feature sigue solo el README y obtiene una respuesta
  correcta del catálogo en menos de 30 minutos, incluida la preparación de su aplicación de acceso.

## Assumptions

- **Dependencias**: Se apoya en la API de la spec 001 (implementada), en un API de usuarios con la
  operación de consulta de permisos (ya disponible en su versión 2.0.0) y en un tenant de Auth0 con
  una aplicación Machine to Machine. Usa la aplicación de escritorio de Postman actual (con
  scripts y variables secretas).
- **Tipo de credencial**: Se usa *client credentials* (aplicación Machine to Machine, cuyo `sub`
  termina en `@clients`); no se incluye inicio de sesión de una persona real (PKCE) ni el flujo de
  contraseña.
- **Vigencia del token**: «Poco antes de vencer» se entiende como 60 segundos antes de su
  vencimiento.
- **Almacenamiento de secretos**: El secreto es una variable secreta de Postman cuyo valor en los
  archivos es siempre vacío; la persona lo escribe en su copia local. Según la versión de Postman, el
  «valor inicial» se sincroniza con la nube si la persona inicia sesión y el «valor actual» no, o todos
  los valores son locales salvo que se compartan; la regla no cambia: nada secreto en un valor que
  pueda sincronizarse ni en los archivos. La colección funciona sin iniciar sesión.
- **Constitución**: Sigue la constitución v1.0.0: colecciones v2.1 en `tests/postman/`, sin secretos
  en colecciones ni entornos (un bloque Bearer que solo referencia una variable no es un secreto),
  sin enviar resultados a servicios externos y apuntando solo a bases de datos de pruebas.
- **Bases de datos de pruebas**: La base local es una **base dedicada a las pruebas manuales**
  (`maily_system_manual`, distinta de la de desarrollo `maily_system` y de la que usa pytest, que se
  borra y recrea) y la del entorno desplegado es de pruebas; ambas son desechables. El borrado es
  siempre lógico, así que cada recorrido deja suscripciones «Eliminada». La colección no puede saber a
  qué base apunta una API; la protección es procedimental (documentación y descripción de los
  entornos).
- **Entorno desplegado**: La plataforma donde esté desplegado es indiferente: solo cambian la
  dirección de la API y los valores de acceso. No se aprovisiona desde esta feature.
- **Colección de punta a punta**: La de la spec 001 (Newman, simulaciones, pila aislada) sigue siendo
  la verificación automática y no cambia.
- **Simulación de clínicas**: Es la de la spec 001; se levanta aparte en local en el puerto 8001 (el
  de `CLINICS_API_BASE_URL` del `.env.example`). El API de usuarios real debe seguir siendo el local.
- **Comprobaciones visibles**: Las comprobaciones de cada petición son ligeras (estatus, código y
  campos clave) y sirven para ver verde o rojo en Postman; la puerta de calidad sigue siendo pytest.
- **Fuera de alcance**:
  - Ejecutar esta colección con Newman o en integración continua (es de uso manual).
  - Crear o configurar las aplicaciones de Auth0, registrar al usuario en el API de usuarios u
    otorgar permisos desde la colección (se documentan como requisitos previos).
  - Provocar desde la colección el 503 por permiso no verificable (requeriría apagar el API de
    usuarios).
  - Cargar planes de ejemplo o datos iniciales en el entorno.
  - Inicio de sesión de una persona real, pruebas de rendimiento, de carga o de seguridad, y Postman
    en la nube (espacios compartidos, monitores y servidores simulados).
  - Aprovisionar o gestionar el entorno desplegado de pruebas.
