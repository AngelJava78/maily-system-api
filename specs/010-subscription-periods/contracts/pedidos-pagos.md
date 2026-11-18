# Pedido a mailySoft-pagos: regreso del checkout a la aplicación y fecha de aprobación

**De**: quien mantiene maily-system-api. **Para**: quien mantiene mailySoft-pagos. **Fecha**: 2026-11-18.

Texto listo para enviar. Pide **dos mejoras** en **mailySoft-pagos**. Las necesita la feature 010 de
maily-system-api («Periodos de suscripción»), que será el primer consumidor real de Pagos
(`resource_type: "system-api:subscription"`). **Ninguna bloquea el código ni la salida** de
maily-system-api: sin ellas funciona, con una incomodidad de experiencia y una imprecisión menor que
describo abajo. Lo que **sí** bloquea el uso real está en Usuarios (los permisos `payments:*` del Dueño y su
`tenant_id`; ver `pedidos-usuarios.md`), no en ti.

---

## 1. Qué pide el negocio

El Dueño de una organización paga la suscripción de su clínica con Mercado Pago a través de Pagos.
maily-system-api crea el pago con su token y lo lleva al `checkout_url`. Para que la experiencia sea
completa, la persona debería **volver a la aplicación** al terminar de pagar, y maily-system-api debería
saber **cuándo se aprobó** el pago para decidir con exactitud si llegó a tiempo.

## 2. Lo que te pido

### 2.1 Dirección de regreso tras el checkout (`redirect_urls`)

Hoy `POST /api/v1/payments` no deja indicar a dónde regresa la persona tras el checkout (el adaptador omite
`back_urls` y Mercado Pago no redirige: `contracts/mercado-pago-integration.md`). Te pido aceptar un campo
opcional en `PaymentCreate`:

```json
"redirect_urls": {
  "success": "https://app.mailysoft.com/billing/result?status=success",
  "failure": "https://app.mailysoft.com/billing/result?status=failure",
  "pending": "https://app.mailysoft.com/billing/result?status=pending"
}
```

- Opcional y aditivo: sin él todo funciona como hoy.
- Tú decides si validas las direcciones contra una lista de orígenes permitidos (conviene: evita redirecciones
  abiertas); si lo haces, dime la variable y se la configuro a maily-system-api.
- Si el proveedor lo permite, `auto_return: "approved"` para volver sin que la persona pulse nada.

**Cómo lo usará maily-system-api**: cuando exista, enviará la dirección de la aplicación (la forma exacta —de
dónde sale y cómo se valida— la acordamos contigo). Mientras no exista, la persona vuelve a la aplicación por
su cuenta y la **siguiente consulta aplica el pago** (maily-system-api revisa en Pagos los cobros pendientes
antes de responder).

### 2.2 Fecha de aprobación del pago

`PaymentRead` trae `created_at` y `updated_at`, pero no cuándo se aprobó. maily-system-api necesita esa
fecha para decidir si el pago llegó **a tiempo** (el periodo pagado empieza donde terminaba el anterior) o si
la organización ya estaba **vencida** (empieza en la fecha de aprobación). Te pido publicar:

```json
"approved_at": "2026-12-01T10:00:00Z"
```

- `approved_at`: instante en que el pago pasó a `approved` (UTC, ISO 8601); `null` si nunca se aprobó. Se
  conserva aunque después haya un reembolso.
- Aditivo: no cambia nada de lo que ya devuelves.

**Mientras no exista**, maily-system-api usa `updated_at` de un pago aprobado, que coincide con la
aprobación o la sigue de cerca (una notificación repetida del proveedor puede adelantarlo unos minutos).

## 3. Cómo lo usa maily-system-api hoy (para que lo tengas presente)

- `POST /api/v1/payments` con `Idempotency-Key` determinista (65 caracteres), `provider: "mercado_pago"`,
  `amount` en centavos, `currency: "MXN"`, `resource_type: "system-api:subscription"` y `resource_id` el UUID
  de la organización. Espera `201` (o `200` con una clave repetida) y `checkout_url`.
- `GET /api/v1/payments/{id}` para cada pago pendiente que ella inició, **en paralelo**, en cada consulta y
  en cada inicio de pago. Ninguna otra consulta. No espera avisos de cambio de estatus.
- Aplica un pago solo si lo inició ella, `status` es `approved` y coinciden `amount`, `currency`,
  `resource_type` y `resource_id`. Un pago creado directamente en Pagos con la misma referencia **no** mueve
  fechas.
- Todas las llamadas llevan el token del Dueño reenviado, con tiempo máximo total y sin reintentos.
- Le importa que la misma `Idempotency-Key` con el mismo cuerpo devuelva siempre el mismo pago aunque ya haya
  cambiado de estatus (si se pierde una respuesta, el reintento debe encontrar el mismo pago).

## 4. Criterios de aceptación, para tus pruebas

1. `POST /api/v1/payments` con `redirect_urls` válidas crea la preferencia con esas `back_urls`; sin el
   campo, igual que hoy.
2. Un `redirect_urls` con una dirección fuera de la lista permitida (si la implementas) responde 422.
3. Un pago aprobado trae `approved_at` con la fecha de la transición a `approved`; uno pendiente o rechazado,
   `null`.
4. Un reembolso posterior no cambia `approved_at`.
5. La misma `Idempotency-Key` con el mismo cuerpo devuelve el mismo pago con su estatus actual.

## 5. Preguntas para ti

1. ¿Prefieres `redirect_urls` con `success`/`failure`/`pending` (como `back_urls` de Mercado Pago) o una sola
   dirección?
2. ¿Validas las direcciones contra una lista de orígenes? ¿Con qué variable?
3. ¿`approved_at` es viable sin cambiar tu tabla (`payment_events` ya registra la transición) o necesita una
   columna?

## 6. Qué bloquea

| Pedido | Bloquea |
|---|---|
| 2.1 `redirect_urls` | Nada. Sin él, la persona regresa a la aplicación por su cuenta tras pagar y la siguiente consulta aplica el pago |
| 2.2 `approved_at` | Nada. Sin él se usa `updated_at`; la diferencia solo importa si el pago se aprobó antes de la fecha de vencimiento y nadie consulta hasta mucho después |

Para que maily-system-api use Pagos de verdad, Usuarios debe dar al Dueño los permisos `payments:read` y
`payments:write` y publicar su `tenant_id` (ver `pedidos-usuarios.md`); es algo que ya sabías (tu
`ESTADO.md`, sección 2.4).
