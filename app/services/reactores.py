"""
Reactores del sistema activo (R19, R20).

ESQUELETO DE CONTRATO. Jose David es el dueño de este archivo: las firmas ya
quedan fijadas para que los demás módulos las llamen desde hoy, y él rellena
el cuerpo con notificar() y el canal en vivo (ver el PDF de reparto, sección
5.2). Mientras tanto cada función no hace nada y nunca lanza: un aviso que
falla no debe tumbar la acción de negocio que lo originó.

Regla de uso: se llaman DESPUÉS de guardar el hecho, dentro de la misma
sesión de base de datos del endpoint (antes del commit), para que el aviso
y el hecho se confirmen juntos.
"""
from __future__ import annotations

import logging

log = logging.getLogger("hsr.reactores")


def al_remitir(db, remision) -> None:
    """El médico remitió un paciente: avisar al especialista destinatario."""
    log.debug("al_remitir(%s) pendiente de implementar", getattr(remision, "id", None))


def al_aceptar(db, remision) -> None:
    """El especialista aceptó la remisión: avisar al médico remitente."""
    log.debug("al_aceptar(%s) pendiente de implementar", getattr(remision, "id", None))


def al_aprobar_reporte(db, reporte) -> None:
    """Se aprobó un reporte de IA: crear la factura automática (reporte_id) y avisar al contable."""
    log.debug("al_aprobar_reporte(%s) pendiente de implementar", getattr(reporte, "id", None))


def al_bloquear(db, usuario) -> None:
    """Una cuenta quedó bloqueada por 3 intentos fallidos: avisar al admin con el usuario afectado."""
    log.debug("al_bloquear(%s) pendiente de implementar", getattr(usuario, "username", None))


def al_alerta_critica(db, alerta) -> None:
    """El modelo marcó un caso crítico: avisar al clínico responsable por el canal en vivo."""
    log.debug("al_alerta_critica(%s) pendiente de implementar", getattr(alerta, "id", None))
