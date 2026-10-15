"""
Canal de eventos en vivo (R17).

Un broker en memoria: cada pestaña que abre /eventos/stream registra una
Conexion, y publicar() le entrega el evento a las conexiones de los usuarios
destinatarios. Con una sola réplica de la API no hace falta un broker externo
(Redis pub/sub solo si se escala a varias réplicas; ver docs/EVENTOS.md).

El broker NO decide quién debe enterarse: eso lo decide el reactor que publica
(app/services/reactores.py), que elige destinatarios por usuario. Aquí solo se
entrega, y por eso un evento clínico no puede llegar por el canal de un
usuario que no es destinatario.

Hilos: los endpoints sincrónicos de FastAPI corren en un pool de hilos y el
canal SSE en el bucle de asyncio. publicar() es seguro de llamar desde
cualquiera de los dos: entrega con call_soon_threadsafe en el bucle de cada
conexión.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from typing import Iterable

log = logging.getLogger("hsr.eventos")

# Eventos en espera por conexión. Si un cliente no los consume (red caída sin
# cerrar el socket), se cierra la conexión en vez de acumular memoria: al
# reconectar, el front vuelve a leer su bandeja, que es la fuente de verdad.
MAX_PENDIENTES = 200
# Pestañas abiertas por usuario. La más antigua se cierra al pasar el límite.
MAX_CONEXIONES_POR_USUARIO = 10


class Conexion:
    """Una pestaña conectada al canal."""

    def __init__(self, usuario_id: int, rol: str):
        self.usuario_id = usuario_id
        self.rol = rol
        self.loop = asyncio.get_running_loop()
        self.pendientes: deque[dict] = deque()
        self.senal = asyncio.Event()
        self.cerrada = False

    # Estos dos métodos corren siempre dentro del bucle de la conexión.
    def _poner(self, evento: dict) -> None:
        if len(self.pendientes) >= MAX_PENDIENTES:
            self.cerrada = True
        else:
            self.pendientes.append(evento)
        self.senal.set()

    def _cerrar(self) -> None:
        self.cerrada = True
        self.senal.set()


_conexiones: dict[int, list[Conexion]] = {}
_candado = threading.Lock()


def abrir(usuario_id: int, rol: str) -> Conexion:
    """Registra una conexión nueva (llamar desde el bucle de asyncio)."""
    con = Conexion(usuario_id, rol)
    sobrantes: list[Conexion] = []
    with _candado:
        lista = _conexiones.setdefault(usuario_id, [])
        lista.append(con)
        while len(lista) > MAX_CONEXIONES_POR_USUARIO:
            sobrantes.append(lista.pop(0))
    for c in sobrantes:
        c._cerrar()
    return con


def cerrar(con: Conexion) -> None:
    with _candado:
        lista = _conexiones.get(con.usuario_id, [])
        if con in lista:
            lista.remove(con)
        if not lista:
            _conexiones.pop(con.usuario_id, None)


def publicar(destinatarios: Iterable[int], evento: dict) -> int:
    """
    Entrega `evento` a todas las pestañas abiertas de esos usuarios.
    Devuelve cuántas conexiones lo recibieron. Nunca lanza: un aviso que falla
    no debe tumbar la acción de negocio que lo originó.
    """
    ids = set(destinatarios)
    with _candado:
        objetivo = [c for uid in ids for c in _conexiones.get(uid, [])]
    entregadas = 0
    for con in objetivo:
        try:
            con.loop.call_soon_threadsafe(con._poner, evento)
            entregadas += 1
        except RuntimeError:   # el bucle de esa conexión ya se cerró
            cerrar(con)
        except Exception:      # noqa: BLE001
            log.exception("No se pudo entregar el evento a la conexión de %s", con.usuario_id)
    return entregadas


def conectados() -> int:
    """Cantidad de conexiones abiertas (para el estado de servicios)."""
    with _candado:
        return sum(len(v) for v in _conexiones.values())


def usuarios_conectados() -> set[int]:
    with _candado:
        return set(_conexiones)
