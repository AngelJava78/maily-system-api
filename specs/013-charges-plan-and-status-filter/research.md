# Research: plan de cada cobro y filtro por estado

## R1 — `plan` es una foto, no una referencia al catálogo

**Decision**: agregar una columna `plan` (texto, nullable) a `subscription_charges`, escrita una sola vez al
crear el cobro (`SubscriptionPeriodRepository.add_charge`), con el nombre que `SubscriptionPeriodService`
ya resuelve en ese instante (`context.plan.name`, el mismo valor que entra en la descripción del pago que
se manda a Pagos).

**Rationale**: la misma razón de diseño que ya decidió `amount`/`billing_period` como valores propios del
cobro (Principio IX del servicio: lo de otro sistema o catálogo se consulta en cada uso, pero lo que este
servicio ya pidió y registró no se vuelve a derivar). El plan de la organización cambia con el tiempo
(cambio de plan, FR de la spec 027 del Frontend) y su nombre en el catálogo también puede cambiar; un cobro
histórico debe seguir diciendo con qué plan se hizo, no con el que la organización tiene ahora.

**Alternatives considered**: guardar `plan_id` y resolver el nombre en cada lectura con un join al catálogo
— descartado porque reintroduce exactamente el problema que se quiere evitar (un rename, o una baja lógica
del plan, cambiaría lo que dice un cobro ya cerrado).

## R2 — Los cobros existentes no se reconstruyen

**Decision**: la migración agrega la columna como `NULL` por omisión y no la rellena; el historial de qué
plan tenía cada organización en cada fecha pasada no existe en ningún lado de este servicio (el catálogo no
versiona sus cambios), así que cualquier intento de reconstrucción sería una adivinanza presentada como un
dato cierto.

**Rationale**: mismo criterio que el resto de este servicio frente a datos que no se pueden saber con
certeza (p. ej. `payment_in_progress: null` cuando Pagos no responde): mejor `null` explícito que un valor
inventado.

**Alternatives considered**: ninguna — ver «Clarifications» de spec.md.

## R3 — El filtro de estado se resuelve en la capa de Repository, no en el Service

**Decision**: `SubscriptionPeriodRepository.list_charges` recibe `status: str | None` y lo agrega a su
`WHERE` (una condición más, junto a `organization_id`); el conteo (`total`) se calcula sobre las mismas
condiciones, así que ya refleja el filtro. El Service y el Router solo lo pasan a través, sin lógica propia.

**Rationale**: es exactamente el patrón ya usado por esta misma operación para `page`/`page_size` (spec
012): la paginación y ahora el filtro son asunto de la consulta SQL, no de post-procesar en memoria lo que
ya se leyó — así escala igual de bien con historiales largos.

**Alternatives considered**: filtrar en Python después de leer todos los cobros — descartado: rompe la
paginación (habría que leer de más para saber el `total` real del subconjunto) y no sigue el patrón ya
establecido.

## R4 — Un único valor de `status`, validado por FastAPI/Pydantic con el enum ya existente

**Decision**: el parámetro de consulta usa el mismo `Literal["pending", "applied", "closed"]`
(`ChargeStatusName`) que ya tiene el campo `status` de la respuesta, como `Annotated[ChargeStatusName | None,
Query(...)]`. FastAPI rechaza automáticamente cualquier otro valor con 422, sin código adicional.

**Rationale**: reutilizar el tipo ya declarado evita que el conjunto de estados válidos se desincronice
entre lo que la respuesta publica y lo que el filtro acepta.

**Alternatives considered**: aceptar una lista separada por comas (varios estados a la vez) — fuera de
alcance de esta spec (ver «Clarifications»).

## R5 — Sin migración de datos, sin permiso nuevo, sin cambio de contrato existente

**Decision**: la migración (0010) solo agrega una columna nullable; no se toca ninguna restricción, índice
ni disparador existente de `subscription_charges`. El permiso sigue siendo `subscription_periods:read`. Los
campos y el formato de paginación que ya publica esta operación (spec 012) no cambian: los dos agregados
(`plan` en cada cobro, `status` en la consulta) son estrictamente aditivos.

**Rationale**: esto es una ampliación de un contrato ya publicado, no una versión incompatible: no hace
falta otro prefijo de ruta ni avisar a nadie más que ya lo consuma (ningún consumidor real existe todavía
fuera de la simulación del Frontend, que se actualiza en su propia spec contra este mismo contrato).
