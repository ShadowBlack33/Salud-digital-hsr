"""
Capa de seguridad de datos entre la API y el servicio de IA (R12).

Ley 1581 de 2012 (principios de finalidad y circulación restringida): al
modelo solo le llega lo que necesita para predecir. Nunca el nombre, el
documento, el correo, el teléfono ni la dirección.

Dos decisiones de diseño:

1. LISTA PERMITIDA, no lista prohibida. Solo viajan las variables de
   VARIABLES_LOINC más edad y sexo. Un campo nuevo que alguien agregue
   mañana al paciente NO se cuela por descuido: para que llegue al modelo
   hay que escribirlo aquí a propósito.

2. SEUDÓNIMO con HMAC-SHA256 del paciente_id y una clave propia
   (IA_SEUDONIMO_KEY, distinta de las demás). Es estable (el mismo paciente
   da siempre el mismo seudónimo, así se pueden cruzar sus análisis) pero
   no se puede revertir sin la clave. Se recorta a 16 caracteres hex.

Además, todo valor del payload es numérico: un texto (que podría ser un
nombre) no tiene por dónde pasar. El servicio ml repite el control y
rechaza con 422 cualquier llave que no conozca.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings

# variable del modelo -> códigos LOINC que la alimentan (el primero es el preferido)
VARIABLES_LOINC: dict[str, tuple[str, ...]] = {
    "glucosa": ("2339-0", "2345-7"),        # mg/dL, sangre / suero
    "potasio": ("2823-3", "6298-4"),        # mmol/L, suero / sangre
    "hemoglobina": ("718-7",),              # g/dL
}
# Variables demográficas que se derivan del paciente sin exponerlo
VARIABLES_DEMOGRAFICAS = ("edad", "sexo")
VARIABLES_PERMITIDAS = frozenset(VARIABLES_DEMOGRAFICAS) | frozenset(VARIABLES_LOINC)

# Así se entrenó el modelo (ml/entrenar.py). 'O' (otro) no se codifica: se imputa.
SEXO_CODIGO = {"F": 0, "M": 1}


class ClaveSeudonimoFaltante(RuntimeError):
    """Sin IA_SEUDONIMO_KEY no se puede seudonimizar, y sin seudonimizar no se analiza."""


def seudonimo(paciente_id: str) -> str:
    clave = get_settings().ia_seudonimo_key
    if not clave:
        raise ClaveSeudonimoFaltante("Falta IA_SEUDONIMO_KEY en el entorno")
    return hmac.new(clave.encode(), paciente_id.strip().encode(), hashlib.sha256).hexdigest()[:16]


def edad_en_anios(nacimiento: date, hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def _numero(valor) -> float | int | None:
    """Solo pasan números finitos. Cualquier otra cosa se descarta (no se convierte)."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, Decimal):
        valor = float(valor)
    if isinstance(valor, (int, float)) and valor == valor and abs(valor) != float("inf"):
        return valor
    return None


def variables_clinicas(db: Session, paciente_id: str) -> dict[str, float]:
    """Último valor numérico activo de cada variable del modelo, desde observaciones."""
    codigos = [c for cs in VARIABLES_LOINC.values() for c in cs]
    filas = db.execute(text("""
        SELECT DISTINCT ON (codigo_loinc) codigo_loinc, valor_numerico
        FROM observaciones
        WHERE paciente_id = :p AND activo AND valor_numerico IS NOT NULL
          AND estado IN ('final', 'amended', 'preliminary')
          AND codigo_loinc = ANY(:codigos)
        ORDER BY codigo_loinc, fecha_hora DESC
    """), {"p": paciente_id, "codigos": codigos}).all()
    por_codigo = {f.codigo_loinc: f.valor_numerico for f in filas}
    salida: dict[str, float] = {}
    for variable, cods in VARIABLES_LOINC.items():
        for c in cods:                       # el primer código disponible gana
            if (v := _numero(por_codigo.get(c))) is not None:
                salida[variable] = v
                break
    return salida


def construir_payload(paciente, variables: dict) -> dict:
    """
    Arma el JSON EXACTO que se envía al modelo. `paciente` solo se usa para
    el identificador (que se seudonimiza), la fecha de nacimiento (que se
    reduce a edad en años) y el sexo (que se codifica 0/1). Ningún campo
    cifrado del paciente se lee aquí: ni siquiera se descifra.
    """
    datos: dict[str, float | int] = {}
    for clave, valor in variables.items():
        if clave in VARIABLES_LOINC and (v := _numero(valor)) is not None:
            datos[clave] = v
    if getattr(paciente, "fecha_nacimiento", None):
        datos["edad"] = edad_en_anios(paciente.fecha_nacimiento)
    if (s := SEXO_CODIGO.get(getattr(paciente, "sexo", None))) is not None:
        datos["sexo"] = s

    payload = {"pseudo_id": seudonimo(paciente.documento_bidx), "variables": dict(sorted(datos.items()))}
    verificar_payload(payload)
    return payload


def verificar_payload(payload: dict) -> None:
    """Última barrera antes de que el payload salga de la API."""
    if set(payload) != {"pseudo_id", "variables"}:
        raise ValueError(f"Payload con llaves no permitidas: {sorted(set(payload))}")
    extra = set(payload["variables"]) - VARIABLES_PERMITIDAS
    if extra:
        raise ValueError(f"Variables no permitidas hacia el modelo: {sorted(extra)}")
    no_numericas = [k for k, v in payload["variables"].items() if _numero(v) is None]
    if no_numericas:
        raise ValueError(f"Variables no numéricas hacia el modelo: {no_numericas}")
