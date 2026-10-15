# Eventos del módulo de IA (R19, R20) — para `docs/EVENTOS.md`

> Sección de Esteban. **Jose David:** pégala en `docs/EVENTOS.md` (el catálogo único de
> eventos del sistema) y borra este archivo. Está aparte solo para que las dos ramas no
> choquen al unirse.

## Catálogo

| Evento (`tipo`) | Quién lo dispara | A quién llega | Reacción automática | Auditoría |
|---|---|---|---|---|
| `alerta_critica` | `POST /ia/analizar`, cuando el modelo responde `critico: true` | El clínico (`medico` o `especialista`) que pidió el análisis. **No** llega a `paciente` ni a `contable` | Se crea una fila en `alertas` con `estado = 'activa'` y se llama a `reactores.al_alerta_critica`, que la empuja por el canal en vivo y la deja en la bandeja. El front la muestra como aviso persistente hasta que se reconoce | `alerta_critica` (entidad `alerta`) |
| `alerta_escalada` | Tarea de fondo de la API (`app/api/alertas.py`), cada 30 s | Todos los `admin` activos y **otro clínico** del paciente (el médico responsable de un encuentro activo, distinto del destinatario original) | Marca `alertas.escalada_at` y llama a `reactores.al_alerta_escalada(db, alerta)`; la alerta trae `destinatarios` con los ids de usuario | `alerta_escalada` (entidad `alerta`) |
| `reporte_aprobado` | `POST /ia/reportes/{id}/aprobar` (solo `medico` o `especialista`) | `contable` | `reactores.al_aprobar_reporte` crea la factura automática en MongoDB con `reporte_id` (R19) | `aprobar` (entidad `reporte_ia`) |

Eventos que **solo se auditan**, sin aviso a nadie:

| Acción | Auditoría |
|---|---|
| Ejecutar el análisis (`POST /ia/analizar`) | `ia_analisis` |
| Rechazar un reporte | `rechazar` (el reporte no se borra: queda como evidencia) |
| Reconocer una alerta (`POST /alertas/{id}/reconocer`, con nota obligatoria) | `reconocer` |
| Consultar el payload enviado al modelo | `read` con `vista: payload` |

## Escalamiento de alertas críticas (R20)

- **Regla:** una alerta `activa` que nadie reconoce en **N = 5 minutos** se escala una sola
  vez. Se configura con `ALERTA_ESCALAMIENTO_MINUTOS` en el `.env`; el front usa
  `VITE_MINUTOS_ESCALAMIENTO` para la cuenta regresiva y debe tener el mismo valor.
- **Mecanismo:** la API arranca una tarea `asyncio` que cada 30 s busca alertas activas, sin
  `escalada_at` y más viejas que N minutos (`FOR UPDATE SKIP LOCKED`, para no escalar dos
  veces). Una alerta se escala, en el peor caso, a los N minutos más 30 s.
- **Justificación de N = 5:**
  - Una alerta crítica de este modelo anticipa la necesidad de **cama de UCI**. Si el
    clínico responsable no la atiende, otra persona debe enterarse a tiempo para
    reservar la cama antes de que el paciente salga de cirugía.
  - 5 minutos permite mostrar el escalamiento completo dentro de la demostración de 5
    minutos de la sustentación.
  - En operación real el valor se ajustaría a la política institucional de comunicación de
    valores críticos. El escalamiento es un respaldo, no el canal principal.
- **Reconocer después de escalada:** cualquier clínico que tenga al paciente a su cargo
  puede reconocerla, no solo el destinatario original.

## Lo que falta para que el aviso llegue en vivo

`reactores.al_alerta_critica` y `reactores.al_alerta_escalada` (Jose David) son las que
publican por el canal en vivo (`/eventos/stream`). La alerta y el escalamiento ya quedan en
la base y en la auditoría aunque esas funciones no existan; sin ellas el front solo los ve
al recargar la página.
