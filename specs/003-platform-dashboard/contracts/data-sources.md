# Contrato interno: fuentes de datos del dashboard (FR-020 a FR-028)

El dashboard no tiene datos propios: los seis indicadores y la lista de clínicas recientes pertenecen a otros
APIs de MailySoft (clínicas, doctores, pacientes y usuarios) que aún no existen. Este documento fija la
**costura** entre el Service del dashboard y esas fuentes, de modo que cuando existan solo cambie quién cumple
este contrato (FR-025). No es un contrato HTTP: es una interfaz de Python que vive en `src/integrations/`
(Principio I). No se consume ningún API nuevo en esta feature (Principio IX): el contrato consumido de cada
API real lo documentará la especificación que lo conecte.

## El puerto `DashboardSource`

Archivo: `src/integrations/dashboard_source.py` (un `Protocol`; solo `dataclass` y biblioteca estándar, sin
`fastapi`, `src.dtos`, `src.models` ni `sqlalchemy`).

```text
class DashboardSource(Protocol):
    is_dummy: bool        # True solo para la fuente ficticia de la Fase 1 (activa el aviso de arranque)

    async def clinic_counts(self, token: str) -> ClinicCounts
    async def recent_clinics(self, token: str, limit: int) -> list[ClinicRecord]
    async def doctors_total(self, token: str) -> int
    async def patients_total(self, token: str) -> int
    async def users_total(self, token: str) -> int
```

Los registros (`ClinicCounts`, `ClinicRecord`, `ClinicStatusRecord`) están en
[data-model.md](../data-model.md), sección 1.

| Consulta | Debe devolver | Notas |
|---|---|---|
| `clinic_counts` | `total`, `active` y `trial`, enteros ≥ 0, de toda la plataforma | `active` y `trial` no se solapan y `active + trial ≤ total` |
| `recent_clinics` | **Como máximo** `limit` clínicas, de la más nueva a la más antigua por `created_at` y, a igualdad de fecha, por `id` ascendente | `limit` llega ya entre 1 y 10; la fuente hace el corte, así que el desempate decide qué clínica entra |
| `doctors_total`, `patients_total`, `users_total` | Un entero ≥ 0 de toda la plataforma | `users_total ≥ doctors_total`: todo doctor es un usuario y los pacientes no lo son |

`token` es el token de la persona tal como llegó. La fuente ficticia lo ignora; los clientes reales lo
reenviarán (Principio VIII) y **nunca** lo registrarán.

## Fallas

- Una fuente que no responde, agota su tiempo máximo, o contesta algo inesperado (cualquier `4xx`/`5xx`, un
  cuerpo ilegible, una redirección) MUST lanzar `DashboardSourceUnavailable`
  (`src/integrations/errors.py`, junto a `UsersApiUnavailable`). Su mensaje es genérico y **no incluye**
  direcciones, cuerpos de error ni credenciales (Principio IX).
- El Service solo captura esa excepción. Cualquier otra (un `KeyError`, un `TypeError`…) es un error de
  programación: no se convierte en `null` y responde `500 internal_error`.
- La consulta fallida deja en `null` **solo lo suyo** (tabla en [data-model.md](../data-model.md), sección 2).
  Las otras cuatro consultas se ejecutan igual y en paralelo.
- Una fuente que responde "no hay nada" devuelve `0` o `[]`: **no** es una falla.

## Qué hace el Service con lo que recibe

| Responsabilidad | Dónde |
|---|---|
| Cantidad efectiva (`min(limit, 10)` o el valor por defecto) | Service |
| Reordenar y cortar la lista (por si una fuente futura no cumple el orden) | Service |
| Convertir `DashboardSourceUnavailable` en `None` y registrar un aviso sin detalles | Service |
| Convertir los registros en DTOs (UTC, `null`) | Router + DTOs |
| Tiempo máximo de espera, reintentos (no hay: son lecturas pero no se reintenta), traducción de la respuesta del otro API | La fuente real (futura) |

## Implementación de la Fase 1: `DummyDashboardSource`

Archivo: `src/integrations/dummy_dashboard_source.py`.

- `is_dummy = True`: al arrancar, el servicio registra el aviso de datos ficticios (FR-024).
- Datos **literales** y deterministas: el conjunto de 12 clínicas, 37 doctores, 1 284 pacientes y 52 usuarios de
  [data-model.md](../data-model.md), sección 6. Sin reloj, sin azar, sin red, sin base de datos (FR-020,
  FR-021).
- `clinic_counts` se **calcula** sobre el conjunto de clínicas (total, las de estatus 1 y las de estatus 2), de
  modo que las invariantes de FR-022 se cumplen por construcción.
- `recent_clinics(token, limit)` devuelve el conjunto ordenado como pide el contrato y cortado a `limit`.
- Nunca lanza `DashboardSourceUnavailable`: sus datos no fallan.
- El constructor admite otro conjunto de clínicas y otros totales (para las pruebas: un conjunto de 4 clínicas,
  uno vacío con todo en cero, etc.).

## Cableado (`src/dependencies.py`)

| Pieza | Función |
|---|---|
| `build_dashboard_source()` | Devuelve la fuente que usa el servicio (hoy `DummyDashboardSource`). La usan `lifespan` (para decidir el aviso) y la dependencia siguiente |
| `get_dashboard_source()` | Dependencia de FastAPI: `build_dashboard_source()` |
| `get_dashboard_service()` | Dependencia de FastAPI: `DashboardService(fuente, get_dashboard_settings().dashboard_recent_clinics_limit)` |

Las pruebas sustituyen `get_dashboard_source` con `app.dependency_overrides` (un `FakeDashboardSource`
configurable); el resto del camino —seguridad, Router, Service, DTOs— es el real.

## Cómo se conecta una fuente real (guía para las especificaciones futuras)

1. Documentar su **contrato consumido** (operaciones, formato de respuesta y errores esperados) en su propia
   especificación, y su simulación en `tests/stubs/` (Principios V y IX).
2. Implementar una o varias de las cinco consultas en `src/integrations/` con `httpx`, tiempo máximo total
   desde una variable de entorno, sin seguir redirecciones y sin registrar el token.
3. Traducir **cualquier** respuesta no esperada a `DashboardSourceUnavailable`.
4. Componer las fuentes en `build_dashboard_source()` (una clase que delegue en cada cliente, o varias) con
   `is_dummy = False`: el aviso de arranque desaparece solo.
5. No cambiar: `DashboardService`, el Router, los DTOs, el OpenAPI, la matriz de permisos ni la colección de
   Postman de contrato. Si la fuente real obliga a cambiar alguno, es un cambio incompatible y se versiona
   (FR-025).
