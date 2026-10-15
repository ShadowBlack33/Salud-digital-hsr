"""
Reactores del sistema activo (R19, R20).

Cada acción de negocio (remitir, aceptar, aprobar, bloquear, alertar) llama a
su reactor DESPUÉS de guardar el hecho y ANTES del commit, dentro de la misma
sesión de base de datos del endpoint. Así el aviso y el hecho se confirman
juntos, y el evento en vivo solo sale cuando el commit ocurrió (ver
app/services/bandeja.py).

Un reactor nunca lanza. Corre dentro de un SAVEPOINT: si algo falla (la tabla
de notificaciones no existe, un destinatario inválido), se deshace solo lo del
reactor, se registra en el log, y la acción de negocio sigue su curso. Sin el
savepoint, un solo error de SQL dejaría abortada toda la transacción del
endpoint y el commit fallaría.

Los avisos NO llevan nombre, documento ni texto clínico libre: identifican al
paciente por su `paciente_id` (índice ciego) y el detalle se consulta en la
pantalla correspondiente, donde sí aplica el control de acceso por paciente.
"""
from __future__ import annotations

import functools
import logging

from sqlalchemy import text

from app.core.config import get_settings
from app.services import bandeja

log = logging.getLogger("hsr.reactores")
settings = get_settings()


def _g(obj, campo, defecto=None):
    """Lee un campo de un objeto o de un dict (las filas de remisiones son dicts)."""
    if isinstance(obj, dict):
        return obj.get(campo, defecto)
    return getattr(obj, campo, defecto)


def _seguro(fn):
    """Aísla el reactor: savepoint + sin excepciones + sin eventos fantasma."""
    @functools.wraps(fn)
    def envoltura(db, *args, **kwargs):
        cola = db.info.setdefault("eventos_pendientes", [])
        tareas = db.info.setdefault("tras_commit", [])
        marca = (len(cola), len(tareas))
        try:
            with db.begin_nested():
                return fn(db, *args, **kwargs)
        except Exception:  # noqa: BLE001
            del cola[marca[0]:]
            del tareas[marca[1]:]
            log.exception("El reactor %s falló; la acción de negocio continúa", fn.__name__)
            return None
    return envoltura


def _username(db, usuario_id) -> str:
    if usuario_id is None:
        return "un colega"
    fila = db.execute(text("SELECT username FROM usuarios WHERE id = :i"), {"i": usuario_id}).first()
    return fila[0] if fila else "un colega"


def _usuarios_de_personal(db, personal_id, rol: str | None = None) -> list[int]:
    """Cuentas activas ligadas a ese registro de personal."""
    if personal_id is None:
        return []
    filas = db.execute(text("""
        SELECT u.id FROM usuarios u JOIN roles r ON r.id = u.rol_id
        WHERE u.activo AND u.personal_id = :p AND (CAST(:r AS TEXT) IS NULL OR r.codigo = :r)
    """), {"p": personal_id, "r": rol}).all()
    return [f[0] for f in filas]


# --------------------------------------------------------------- remisiones
@_seguro
def al_remitir(db, remision) -> None:
    """El médico remitió un paciente: avisar al especialista destinatario."""
    rid = _g(remision, "id")
    destinatarios = _usuarios_de_personal(db, _g(remision, "especialista_id"), "especialista")
    remitente = _username(db, _g(remision, "remitido_por"))
    prioridad = _g(remision, "prioridad", "prioritaria")
    bandeja.notificar(
        db, destinatarios, "remision_nueva",
        f"Nueva remisión {prioridad} de {remitente}. Revísela en Remisiones.",
        paciente_id=_g(remision, "paciente_id"),
        datos={"remision_id": rid, "prioridad": prioridad})


@_seguro
def al_aceptar(db, remision) -> None:
    """El especialista aceptó la remisión: avisar al médico remitente."""
    rid = _g(remision, "id")
    quien = _username(db, _g(remision, "aceptada_por"))
    destinatarios = {_g(remision, "remitido_por"), *_usuarios_de_personal(db, _g(remision, "medico_id"))}
    destinatarios.discard(_g(remision, "aceptada_por"))
    bandeja.notificar(
        db, destinatarios, "remision_aceptada",
        f"{quien} aceptó su remisión n.º {rid}.",
        paciente_id=_g(remision, "paciente_id"),
        datos={"remision_id": rid})


@_seguro
def al_rechazar(db, remision) -> None:
    """El especialista rechazó la remisión: avisar al médico remitente."""
    rid = _g(remision, "id")
    quien = _username(db, _g(remision, "cerrada_por"))
    destinatarios = {_g(remision, "remitido_por"), *_usuarios_de_personal(db, _g(remision, "medico_id"))}
    destinatarios.discard(_g(remision, "cerrada_por"))
    bandeja.notificar(
        db, destinatarios, "remision_rechazada",
        f"{quien} rechazó su remisión n.º {rid}. El motivo está en Remisiones.",
        paciente_id=_g(remision, "paciente_id"),
        datos={"remision_id": rid})


# ------------------------------------------------------------------ IA
@_seguro
def al_reporte_pendiente(db, reporte) -> None:
    """
    El análisis de IA creó un reporte `pendiente`: avisar al clínico que lo pidió
    para que lo revise. Sube su contador `reportes_por_revisar`.
    Lo llama el módulo de IA justo después de guardar el reporte.
    """
    rid = _g(reporte, "id")
    bandeja.notificar(
        db, [_g(reporte, "creado_por")], "reporte_pendiente",
        f"El reporte de IA n.º {rid} está listo y espera su revisión.",
        paciente_id=_g(reporte, "paciente_id"),
        datos={"reporte_id": rid})


@_seguro
def al_aprobar_reporte(db, reporte) -> None:
    """
    Se aprobó un reporte de IA: crear la factura automática (con reporte_id) en
    MongoDB y avisar al contable. Lo llama el módulo de IA después de marcar el
    reporte `aprobado`.

    La factura se crea cuando el commit de la aprobación ya ocurrió: nunca se
    cobra un reporte cuya aprobación se revirtió. Es idempotente por reporte_id,
    así que un reintento o una doble aprobación no duplican el cobro. Si
    MongoDB no responde, no se pierde en silencio: queda en la auditoría y se
    avisa al contable y al admin (factura_fallida).
    """
    rid = _g(reporte, "id")
    pid = _g(reporte, "paciente_id")
    nombre = documento = None
    try:
        from app.core.crypto import descifrar, enmascarar
        from app.models import Paciente
        p = db.get(Paciente, pid) if pid else None
        if p is not None:
            nombre = f"{descifrar(p.nombre_cifrado, 'pacientes.nombre')} {descifrar(p.apellido_cifrado, 'pacientes.apellido')}"
            documento = enmascarar(descifrar(p.documento_cifrado, "pacientes.documento"))
    except Exception:  # noqa: BLE001 -- la factura sale igual, sin los datos de presentación
        log.warning("No se pudo leer el paciente para la factura del reporte %s", rid)

    def facturar() -> None:
        from app.core.deps import SessionLocal
        from app.services import facturacion_auto
        from app.services.auditoria import registrar
        try:
            factura = facturacion_auto.crear_por_reporte(
                rid, pid, paciente_nombre=nombre, paciente_documento=documento)
            error = None
        except Exception as e:  # noqa: BLE001
            factura, error = None, type(e).__name__
            log.exception("No se pudo crear la factura del reporte %s", rid)
        with SessionLocal() as s2:
            if factura is not None:
                registrar(s2, None, "factura", factura["id"], "create",
                          valor_nuevo={"reporte_id": rid, "paciente_id": pid, "origen": "automatica",
                                       "servicio": "analisis_ia", "valor": factura.get("valor")})
                bandeja.notificar(
                    s2, bandeja.usuarios_con_rol(s2, "contable"), "factura_creada",
                    f"Factura automática {factura['id']} creada al aprobar el reporte de IA n.º {rid}.",
                    paciente_id=pid, datos={"reporte_id": rid, "factura_id": factura["id"]})
            else:
                registrar(s2, None, "factura", f"F-IA-{rid}", "create", resultado="error",
                          valor_nuevo={"reporte_id": rid, "paciente_id": pid, "motivo": error})
                bandeja.notificar(
                    s2, bandeja.usuarios_con_rol(s2, "contable") + bandeja.usuarios_con_rol(s2, "admin"),
                    "factura_fallida",
                    f"No se pudo crear la factura del reporte de IA n.º {rid}: el servicio de facturación no respondió.",
                    paciente_id=pid, datos={"reporte_id": rid})
            s2.commit()

    bandeja.tras_commit(db, facturar)


# ------------------------------------------------------------------ acceso
@_seguro
def al_bloquear(db, usuario) -> None:
    """Una cuenta quedó bloqueada por 3 intentos fallidos: avisar al admin con el usuario afectado."""
    nombre = _g(usuario, "username")
    bandeja.notificar(
        db, bandeja.usuarios_con_rol(db, "admin", excepto=_g(usuario, "id")), "cuenta_bloqueada",
        f"La cuenta {nombre} quedó bloqueada tras {settings.max_intentos_login} intentos fallidos. "
        "Puede desbloquearla en Administración.",
        datos={"usuario_afectado": nombre, "usuario_id": _g(usuario, "id")})


# ------------------------------------------------------------------ alertas
@_seguro
def al_alerta_critica(db, alerta) -> None:
    """
    El modelo marcó un caso crítico: avisar al clínico responsable por el canal
    en vivo. Lo llama el módulo de IA después de insertar la fila en `alertas_criticas`
    (con su `usuario_id`, el clínico responsable). La alerta sigue activa, y
    visible, hasta que se reconozca; si pasan ESCALAMIENTO_MINUTOS sin
    reconocerla, app/services/escalamiento.py avisa al admin.
    """
    aid = _g(alerta, "id")
    mensaje = _g(alerta, "mensaje") or "Un paciente fue clasificado como crítico. Revíselo de inmediato."
    bandeja.notificar(
        db, [_g(alerta, "usuario_id")], "alerta_critica", mensaje,
        paciente_id=_g(alerta, "paciente_id"),
        datos={"alerta_id": aid, "nivel": _g(alerta, "nivel", "critico")})
