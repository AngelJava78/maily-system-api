# Data Model: Dirección de regreso del pago (011-payment-return-url)

Esta feature **no cambia la base de datos**: no hay tablas, columnas, índices ni migraciones nuevas, y
`DATA_SCHEMA.md` no cambia (FR-013). Lo que sí tiene forma es una configuración, un campo que viaja a Pagos
y las condiciones de la clave de idempotencia.

## Dirección de regreso (configuración)

| Atributo | Valor |
|---|---|
| Variable | `PAYMENTS_RETURN_URL` (opcional) |
| Dónde se lee | `PaymentsSettings.payments_return_url` (`src/config.py`), una vez al arrancar |
| Sin definir o vacía | `None`: no se envía nada a Pagos (FR-002, FR-007) |
| Valor guardado | El texto configurado sin los espacios del principio y del final (FR-005) |
| Alcance | Un valor por ambiente, para todas las organizaciones; solo el pago de los periodos de suscripción |

**Reglas de validación** (FR-003; en este orden, la primera que falla invalida la variable):

1. Después de quitar los espacios externos, no está vacía.
2. Sin espacios ni caracteres de control en su interior.
3. A lo más 2048 caracteres.
4. Sin el carácter `#` (sin fragmento).
5. `urlsplit` la entiende y su puerto, si lo hay, está entre 0 y 65535.
6. Esquema `https`.
7. Equipo (host) presente.
8. Sin usuario ni contraseña (tampoco una `@` sin usuario).
9. Equipo que no es local ni privado: no es `localhost` ni termina en `.localhost`; si es una dirección IP,
   no es de bucle local, privada, de enlace local, no especificada, reservada ni de multidifusión; si es un
   nombre, tiene al menos un punto.

**Al fallar**: el arranque se detiene con «Configuración incompleta o no válida. La variable de entorno
PAYMENTS_RETURN_URL no es válida.» (más las demás variables que fallen), sin el valor en el mensaje ni en el
registro (FR-004).

## Campo que viaja a Pagos

Solo en `POST /api/v1/payments` del pago de un periodo de suscripción y solo con la dirección configurada
(FR-006):

```json
"redirect_urls": { "success": "<PAYMENTS_RETURN_URL tal como se configuró>" }
```

Sin la dirección, el cuerpo no tiene la clave `redirect_urls` (FR-007). El cobro de clínicas nunca la
envía (FR-011). El detalle del contrato está en
[contracts/payments-api-integration.md](contracts/payments-api-integration.md).

## Condiciones de la clave de idempotencia

| Caso | Texto que se resume con SHA-256 (los primeros 24 dígitos hexadecimales) | Clave |
|---|---|---|
| Sin dirección | `<fecha que salda en UTC ISO 8601>\|<periodo>\|<importe en centavos>\|<intento>\|<descripción>` (el de la spec 010, sin cambios) | `sub-<organización>-<resumen>`, idéntica a la de la spec 010 |
| Con dirección | `json.dumps([<el texto de arriba>, <dirección>])` | `sub-<organización>-<resumen>`, distinta por cada dirección |

La clave sigue teniendo 65 caracteres ASCII (Pagos admite de 1 a 100). Ningún registro guardado cambia: los
cobros ya registrados no vuelven a crearse (se leen con su identificador de pago).

## Estados

Ninguno nuevo. Los cobros siguen el ciclo de la spec 010 (pendiente → aplicado o cerrado) y solo la
conciliación con Pagos los mueve (FR-012).
