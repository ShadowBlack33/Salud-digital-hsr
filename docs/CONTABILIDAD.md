# Módulo de contabilidad (R09)

Implementa el contrato de `docs/CONTRATO_FACTURACION.md` sobre **MongoDB**. Código: `app/services/contabilidad.py` (lógica) y `app/api/contabilidad.py` (rutas).

> **Aviso importante.** El valor que genera este módulo es una **referencia interna de cobro**. **No es una factura electrónica DIAN ni un reporte RIPS**, y no tiene validez fiscal ni se envía a ninguna entidad. Sirve para llevar el control de cuánto se cobra por cada servicio y quién lo paga.

## Rutas

Prefijo `/contabilidad`. Requieren el permiso `facturacion:read` **y** rol `contable` o `admin`; cualquier otro rol recibe 403 y el intento queda en la auditoría. (No existe un permiso `facturacion:write` en la base; por eso la escritura se restringe por rol.)

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/contabilidad/facturas` | Lista. Filtros: `tipo`, `estado`, `entidad`, `q` (nombre/cédula), `desde`, `hasta`. Sin `pagina`/`por_pagina` devuelve la lista completa; con ellos, `{"facturas", "total"}` |
| POST | `/contabilidad/facturas` | Crea. 201 si es nueva; **200 con la misma factura** si ese `reporte_id` ya estaba facturado |
| PATCH | `/contabilidad/facturas/{id}/pagar` | Pasa a `pagada` (desde pendiente, radicada o glosada) |
| PATCH | `/contabilidad/facturas/{id}/anular` | Anula con `motivo` (mín. 5 caracteres). Una factura pagada no se anula: 409 |
| GET | `/contabilidad/tarifario` | Tarifario (40 servicios, el mismo del front) |

## Colecciones y índices

- `facturas`: una por cobro. Id legible `F-250001…` generado con un contador atómico (`contadores`).
- `tarifario`: se siembra una sola vez con `$setOnInsert`.
- Índices: `uq_id` (único), **`uq_reporte_id` (único parcial, solo donde `reporte_id` existe)**, fecha, tipo+estado+fecha, entidad+estado, paciente+fecha, `nombre_bidx`.

## Factura automática idempotente

Cuando se aprueba un reporte de IA se factura el análisis (`analisis_ia`, código `IA0001`) con `facturar_reporte(...)`. El índice único sobre `reporte_id` garantiza **una sola factura por reporte**, aunque el evento llegue dos veces o dos peticiones corran a la vez: la segunda pierde la carrera (`DuplicateKeyError`), el código lo captura y devuelve la factura ya existente (`creada = False`).

Enganche para `app/services/reactores.py` (archivo de José David):

```python
from app.services import contabilidad

def al_aprobar_reporte(db, reporte) -> None:
    try:
        datos = contabilidad.datos_para_factura(db, reporte.paciente_id)
        contabilidad.facturar_reporte(reporte.id, reporte.paciente_id, usuario_id=getattr(reporte, "aprobado_por", None), **datos)  # ajustar al nombre real del campo
    except Exception:
        log.exception("No se pudo facturar el reporte %s", reporte.id)  # nunca debe tumbar la aprobación
```

## Datos personales

- El nombre del paciente se guarda **cifrado** (AES-256-GCM, AAD `facturas.paciente_nombre`); para buscar se usa un índice ciego por palabra.
- La cédula **nunca** se guarda en claro: solo enmascarada (`******6591`).

## Reparto del valor

Mismas reglas que el front (`repartir()`): particular paga todo; SOAT y especial, 0; prepagada, mínimo entre el valor y 35.000; consulta/urgencias con cuota moderadora (4.700 contributivo, 0 subsidiado); el resto, copago de 11,5 % / 10 %.

## Limitaciones (para decirlas con honestidad en la sustentación)

- Es una referencia interna: ni DIAN ni RIPS.
- No hay nota crédito: una factura pagada no se puede anular.
- MongoDB queda fuera de la transacción de PostgreSQL: si la aprobación del reporte se revierte después de facturar, la factura queda (por eso el reactor es "mejor esfuerzo" y la factura es idempotente).
- Sin permiso `facturacion:write` en la base: el control de escritura es por rol en la API.
- Si Mongo está caído, las rutas responden 503 (no tumban el resto de la API).

## Pruebas

```powershell
pip install mongomock fastapi httpx
python scripts/test_contabilidad.py                       # Mongo simulado, 57 verificaciones
$env:MONGO_URL_PRUEBA="mongodb://hsr:CLAVE@127.0.0.1:27017/?authSource=admin"
python scripts/test_contabilidad.py                       # con Mongo real: además prueba la concurrencia
```

Tras copiar los archivos hay que reconstruir la imagen (se agregó `pymongo`): `docker compose up -d --build api`.

## Clusters (R07)

`GET /analitica/clusters` se explica en `docs/DATASETS.md` y `docs/INFORME_CLUSTERS.md`.
