"""
Sistema activo: canal en vivo, bandeja y trabajo pendiente (R17, R18).

  GET  /eventos/stream            canal Server-Sent Events (text/event-stream)
  GET  /notificaciones            la bandeja del usuario (persistente)
  POST /notificaciones/{id}/leer  marcar una como leída (solo su dueña)
  POST /notificaciones/leer-todas
  GET  /pendientes                contadores de trabajo pendiente del usuario

Los cinco roles tienen bandeja: no exigen un permiso de recurso, solo estar
autenticado, y cada consulta se limita a las filas del propio usuario.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import ContextoAcceso, SessionLocal, get_db, get_token_payload, get_usuario_actual
from app.core.security import decodificar_token, tiene_permiso
from app.models import Sesion, Usuario
from app.services import bandeja, eventos

log = logging.getLogger("hsr.eventos")
router = APIRouter(tags=["Tiempo real"])

LATIDO_SEGUNDOS = 15          # un comentario SSE mantiene viva la conexión a través del túnel
REVALIDAR_SEGUNDOS = 60       # cada cuánto se confirma que la sesión sigue vigente


# ------------------------------------------------------------ canal SSE (R17)
def _validar_token(token: str | None) -> dict:
    """
    Autentica la conexión del canal. EventSource no puede mandar cabeceras, por
    eso se admite el token como ?token=. Se aplican las mismas reglas que a
    cualquier ruta: token de acceso vigente, usuario activo, sesión no cerrada
    y cuenta no bloqueada. Devuelve {usuario_id, rol, exp, sid}.
    """
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Se requiere autenticación",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decodificar_token(token)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Se requiere un token de acceso")
    with SessionLocal() as db:
        _sesion_vigente(db, payload)
    return {"usuario_id": int(payload["sub"]), "rol": payload.get("rol"),
            "exp": payload.get("exp"), "sid": payload.get("sid")}


def _sesion_vigente(db: Session, payload: dict) -> None:
    """Lanza 401/423 si el usuario o su sesión ya no valen (misma lógica que get_usuario_actual)."""
    from datetime import datetime, timezone
    usuario = db.query(Usuario).filter(Usuario.id == int(payload["sub"]), Usuario.activo.is_(True)).first()
    if usuario is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inexistente o desactivado")
    if payload.get("sid") is not None:
        s = db.get(Sesion, payload["sid"])
        if s is None or s.revocado_at is not None or s.usuario_id != usuario.id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La sesión fue cerrada. Inicia sesión de nuevo.")
    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_423_LOCKED, "Cuenta bloqueada temporalmente")


def _formatear(evento: dict) -> str:
    cuerpo = json.dumps(evento, ensure_ascii=False, default=str)
    cabecera = f"id: {evento['id']}\n" if evento.get("id") is not None else ""
    return f"{cabecera}data: {cuerpo}\n\n"


async def _flujo(request: Request, con: eventos.Conexion, auth: dict):
    yield "retry: 3000\n\n"
    yield ": conectado\n\n"
    ultima_revision = time.monotonic()
    try:
        while not con.cerrada:
            try:
                await asyncio.wait_for(con.senal.wait(), timeout=LATIDO_SEGUNDOS)
            except asyncio.TimeoutError:
                pass
            con.senal.clear()
            if await request.is_disconnected():
                break
            enviados = 0
            while con.pendientes:
                yield _formatear(con.pendientes.popleft())
                enviados += 1
            if con.cerrada:
                break
            # El token de acceso dura 15 min: al vencer se cierra el canal y el
            # front lo reabre con el token renovado.
            if auth["exp"] and time.time() >= auth["exp"]:
                break
            if time.monotonic() - ultima_revision >= REVALIDAR_SEGUNDOS:
                ultima_revision = time.monotonic()
                try:
                    await run_in_threadpool(_revalidar, auth)
                except HTTPException:
                    break   # cerró sesión, la bloquearon o la desactivaron
            if not enviados:
                yield ": ping\n\n"
    finally:
        eventos.cerrar(con)


def _revalidar(auth: dict) -> None:
    with SessionLocal() as db:
        _sesion_vigente(db, {"sub": auth["usuario_id"], "sid": auth["sid"]})


@router.get("/eventos/stream", summary="Canal de eventos en vivo (SSE)")
async def stream(request: Request, token: str | None = None):
    """
    Cada evento es un JSON con `tipo`, `mensaje`, `fecha` y, cuando aplica,
    `paciente_id`. Cada usuario recibe solo los que van dirigidos a él. El token
    puede ir en `?token=` (EventSource no envía cabeceras) o en Authorization.
    """
    if token is None:
        cabecera = request.headers.get("authorization", "")
        if cabecera.lower().startswith("bearer "):
            token = cabecera.split(" ", 1)[1].strip()
    auth = await run_in_threadpool(_validar_token, token)
    con = eventos.abrir(auth["usuario_id"], auth["rol"])
    return StreamingResponse(
        _flujo(request, con, auth), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"})


# ------------------------------------------------------------- bandeja (R18)
@router.get("/notificaciones", summary="Mi bandeja de notificaciones")
def mis_notificaciones(solo_no_leidas: bool = False, limite: int = 100,
                       usuario: Usuario = Depends(get_usuario_actual), db: Session = Depends(get_db)):
    limite = max(1, min(limite, 200))
    filas = db.execute(text("""
        SELECT id, tipo, mensaje, leida, fecha, paciente_id, datos FROM notificaciones
        WHERE usuario_id = :u AND (NOT :solo OR NOT leida)
        ORDER BY fecha DESC, id DESC LIMIT :l
    """), {"u": usuario.id, "solo": solo_no_leidas, "l": limite}).mappings().all()
    return [bandeja.vista(f) for f in filas]


@router.post("/notificaciones/leer-todas", summary="Marcar toda mi bandeja como leída")
def leer_todas(usuario: Usuario = Depends(get_usuario_actual), db: Session = Depends(get_db)):
    n = db.execute(text("""
        UPDATE notificaciones SET leida = TRUE, leida_at = NOW() WHERE usuario_id = :u AND NOT leida
    """), {"u": usuario.id}).rowcount
    db.commit()
    return {"marcadas": n}


@router.post("/notificaciones/{notificacion_id}/leer", summary="Marcar una notificación como leída")
def leer(notificacion_id: int, usuario: Usuario = Depends(get_usuario_actual), db: Session = Depends(get_db)):
    # El filtro por dueño va en el propio UPDATE: la de otro usuario responde
    # 404, igual que una que no existe (no se revela cuáles hay).
    fila = db.execute(text("""
        UPDATE notificaciones SET leida = TRUE, leida_at = COALESCE(leida_at, NOW())
        WHERE id = :i AND usuario_id = :u
        RETURNING id, tipo, mensaje, leida, fecha, paciente_id, datos
    """), {"i": notificacion_id, "u": usuario.id}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificación no encontrada")
    db.commit()
    return bandeja.vista(fila)


# ---------------------------------------------------- trabajo pendiente (R18)
# Tabla de reportes de IA (módulo de Esteban): se cuentan los `pendiente` de los
# pacientes del clínico. Si la tabla todavía no existe, el contador es 0.
TABLA_REPORTES_IA = "ia_reportes"


def _contar(db: Session, sql: str, params: dict) -> int:
    """Cuenta dentro de un savepoint: una tabla que aún no existe da 0, no un error."""
    try:
        with db.begin_nested():
            return int(db.execute(text(sql), params).scalar() or 0)
    except Exception:  # noqa: BLE001
        return 0


@router.get("/pendientes", summary="Mi trabajo pendiente")
def pendientes(payload: dict = Depends(get_token_payload), usuario: Usuario = Depends(get_usuario_actual),
               db: Session = Depends(get_db)):
    """
    Los tres contadores suben cuando nace el trabajo y bajan cuando se resuelve:
    se calculan sobre el estado real, no se acumulan aparte.
    """
    rol = usuario.rol.codigo
    clinico = rol in ("medico", "especialista")
    remisiones = _contar(db, "SELECT COUNT(*) FROM remisiones WHERE especialista_id = :p AND estado = 'pendiente'",
                         {"p": usuario.personal_id}) if usuario.personal_id is not None else 0

    reportes = 0
    if clinico:
        ctx = ContextoAcceso(usuario, payload, tiene_permiso(payload.get("permisos", []), "paciente", "read"),
                             "paciente", "read", db, None)
        if ctx.alcance == "assigned":
            sub = ctx.pacientes_asignados_subq()
            from sqlalchemy import String, column, func, select, table
            rep = table(TABLA_REPORTES_IA, column("paciente_id", String), column("estado"))
            consulta = select(func.count()).select_from(rep).where(
                rep.c.estado == "pendiente", rep.c.paciente_id.in_(sub.select()))
            try:
                with db.begin_nested():
                    reportes = int(db.execute(consulta).scalar() or 0)
            except Exception:  # noqa: BLE001 -- la tabla de IA aún no existe
                reportes = 0

    alertas = 0
    if clinico:
        alertas = _contar(db, "SELECT COUNT(*) FROM alertas_criticas WHERE usuario_id = :u AND estado = 'activa'",
                          {"u": usuario.id})
    elif rol == "admin":
        alertas = _contar(db, "SELECT COUNT(*) FROM alertas_criticas WHERE estado = 'activa' AND escalada_at IS NOT NULL", {})

    return {"reportes_por_revisar": reportes, "remisiones_recibidas": remisiones, "alertas_activas": alertas}
