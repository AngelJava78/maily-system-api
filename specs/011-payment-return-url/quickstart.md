# Quickstart: Dirección de regreso del pago (011-payment-return-url)

Guía para comprobar que la feature funciona. Los detalles están en [spec.md](spec.md) (tabla «Direcciones
de referencia»), [data-model.md](data-model.md) y
[contracts/payments-api-integration.md](contracts/payments-api-integration.md).

## Requisitos

- `uv` y Python 3.14 o superior; las dependencias del proyecto (`uv sync`).
- Para el nivel lento: `TEST_DATABASE_URL` en `.env`, apuntando a una base PostgreSQL 17 exclusiva de pruebas
  (su nombre termina en `_test`).
- Para las colecciones de Postman: Docker y Node.js con npm (solo para Newman).

## 1. Nivel rápido (el ciclo de `/speckit-implement`)

```powershell
uv run pytest
```

Esperado: todo en verde, incluidas las pruebas nuevas de la configuración (la tabla de direcciones), del
arranque, del cliente de Pagos, de la clave de idempotencia y del Service.

## 2. Suite completa (puerta antes de integrar a `main`)

```powershell
uv run pytest -m ""
```

Esperado: todo en verde, incluidas las pruebas de contrato nuevas (`test_subscription_periods_return_url.py`)
y las de siempre (migraciones desde cero, cobertura de permisos, OpenAPI, capas).

## 3. Arranque con una dirección inválida

```powershell
$env:PAYMENTS_RETURN_URL = "http://app.mailysoft.com/payment"; uv run uvicorn src.main:app --port 8001
```

Esperado: no arranca; el registro dice «La variable de entorno PAYMENTS_RETURN_URL no es válida.» y no
contiene la dirección. Con `https://app.mailysoft.com/payment` arranca. Al terminar:
`Remove-Item Env:PAYMENTS_RETURN_URL`.

## 4. El contrato publicado no cambia

Generar `/openapi.json` en `main` y en la rama y compararlos: deben ser idénticos (FR-013).

```powershell
uv run python -c "import json; from src.main import create_app; print(json.dumps(create_app().openapi(), sort_keys=True))" > $env:TEMP\openapi-branch.json
```

(La misma orden con `main` en otro árbol de trabajo da el archivo de comparación.)

## 5. Colecciones de Postman (pila aislada)

Las mismas órdenes del README («Pruebas de punta a punta»): levantar la pila `maily-system-e2e`, correr
`npm run e2e:all --prefix tests/postman` y bajarla. Esperado: las cuatro colecciones en verde, sin cambios
(la pila corre sin la variable, como el desarrollo local).

## 6. Opcional: regreso real con Mercado Pago (pruebas)

Solo si se quiere ver el regreso automático de punta a punta con los servicios reales:

1. Exponer el frontend con una dirección `https` pública (por ejemplo, un túnel) y usar su pantalla
   `/payment` como `PAYMENTS_RETURN_URL` de este servicio.
2. Agregar ese origen a `CHECKOUT_RETURN_ALLOWED_ORIGINS` de mailySoft-pagos y reiniciarlo.
3. Como Dueño, pagar la suscripción con una tarjeta de pruebas aprobada.

Esperado: al aprobarse el pago, Mercado Pago regresa a la persona a `/payment` (con sus parámetros en la
dirección) y la pantalla muestra la nueva fecha de pago en su primera o segunda lectura (SC-001). Sin el
origen permitido en Pagos, iniciar el pago responde 503 y el registro de este servicio pide revisar ese
origen.
