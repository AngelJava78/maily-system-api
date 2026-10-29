# Modelo de datos: quitar dependencias entre módulos

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

## Sin cambios de esquema

Esta feature **no cambia ninguna tabla, columna, índice, restricción ni migración**. El esquema
vigente sigue siendo exactamente el que dejó `008-subscription-modules-table`
(`subscription_modules`, con su clave primaria compuesta `(subscription_id, module_key)` y su
`FOREIGN KEY` a `subscriptions.id`; ver
[specs/008-subscription-modules-table/data-model.md](../008-subscription-modules-table/data-model.md)).

Por eso:

- No hay migración de Alembic nueva.
- `project-definition/DATA_SCHEMA.md` y `project-definition/create_database.sql` no se tocan.
- Los `module_keys` ya guardados en suscripciones existentes no se modifican ni se revalidan (fuera
  de alcance de `spec.md`): si alguna fila quedó con un módulo que dependía de la regla que se
  retira, sigue ahí tal cual, porque esta feature no es una migración de datos.

## Lo que sí cambia (no es un cambio de datos, sino de código)

`CLINIC_MODULE_KEYS` (un `frozenset` de claves fijas) y `MODULE_DEPENDENCIES` (un `dict` de pares
dependiente → prerrequisito) en `src/clinic_modules.py` **no son datos de la base**: son constantes
de Python en memoria, nunca columnas ni filas. Quitarlas (FR-004) es una operación sobre el código,
documentada en [plan.md](plan.md) y en [research.md](research.md), no sobre el modelo de datos.

El único módulo cuya clave sigue conocida de antemano por esta API, en código, es `PATIENTS_KEY`
(`"patients"`) — y eso tampoco cambia.
