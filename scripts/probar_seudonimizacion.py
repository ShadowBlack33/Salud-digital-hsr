#!/usr/bin/env python3
"""
Prueba del canario de R12, a nivel de la capa de seudonimización (sin base
de datos ni API). Crea un paciente falso con datos personales inconfundibles,
arma el payload que iría al modelo y comprueba que ninguno de esos datos
aparezca en él, ni siquiera dentro de otro texto.

    python scripts/probar_seudonimizacion.py

La prueba de punta a punta contra la API (crear paciente, /ia/analizar y
leer /ia/reportes/{id}/payload) va en scripts/prueba_canario.py.
"""
import json
import os
import sys
from datetime import date
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("IA_SEUDONIMO_KEY", "clave-solo-para-esta-prueba")

from app.services import seudonimizacion as S  # noqa: E402

CANARIOS = {
    "nombre": "CANARIO_NOMBRE", "apellido": "CANARIO_APELLIDO",
    "documento": "CANARIO_DOC_987654321", "telefono": "3009998877",
    "email": "canario@prueba.invalid", "direccion": "Calle CANARIO 123",
}

# Paciente "en claro" a propósito: si la capa leyera estos atributos, se notaría.
paciente = SimpleNamespace(
    documento_bidx="b" * 64, fecha_nacimiento=date(1948, 3, 2), sexo="F",
    nombre_cifrado=CANARIOS["nombre"], apellido_cifrado=CANARIOS["apellido"],
    documento_cifrado=CANARIOS["documento"], telefono_cifrado=CANARIOS["telefono"],
    email_cifrado=CANARIOS["email"], direccion_cifrada=CANARIOS["direccion"],
    **CANARIOS,
)

fallas = []


def chequear(nombre, condicion, detalle=""):
    print(("OK    " if condicion else "FALLA ") + nombre + (f"  {detalle}" if detalle else ""))
    if not condicion:
        fallas.append(nombre)


# 1. Variables legítimas + intentos de colar datos personales por el diccionario
variables = {"glucosa": 42, "potasio": 6.6, "hemoglobina": 6.8,
             "nombre": CANARIOS["nombre"], "telefono": CANARIOS["telefono"],
             "observacion": f"paciente {CANARIOS['nombre']}", "glucosa_texto": "alta"}
payload = S.construir_payload(paciente, variables)
texto = json.dumps(payload, ensure_ascii=False)
print("Payload:", texto)

for campo, valor in CANARIOS.items():
    chequear(f"no viaja {campo}", valor.lower() not in texto.lower())
chequear("solo llaves pseudo_id y variables", set(payload) == {"pseudo_id", "variables"})
chequear("solo variables permitidas", set(payload["variables"]) <= S.VARIABLES_PERMITIDAS,
         str(sorted(payload["variables"])))
chequear("todo valor es numérico",
         all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in payload["variables"].values()))
chequear("edad en años, sin fecha de nacimiento", "1948" not in texto and isinstance(payload["variables"]["edad"], int))
chequear("sexo codificado 0/1", payload["variables"].get("sexo") == 0)

# 2. Seudónimo: estable, de 16 hex, distinto por paciente, no contiene el id
p = payload["pseudo_id"]
chequear("seudónimo de 16 hex", len(p) == 16 and all(c in "0123456789abcdef" for c in p), p)
chequear("seudónimo estable", S.seudonimo(paciente.documento_bidx) == p)
chequear("seudónimo distinto por paciente", S.seudonimo("c" * 64) != p)
chequear("el id real no viaja", paciente.documento_bidx not in texto)

# 3. La última barrera rechaza un payload adulterado
for nombre, malo in [
    ("llave extra en raíz", {**payload, "nombre": CANARIOS["nombre"]}),
    ("variable no permitida", {**payload, "variables": {**payload["variables"], "nombre": 1}}),
    ("valor de texto", {**payload, "variables": {**payload["variables"], "glucosa": CANARIOS["nombre"]}}),
]:
    try:
        S.verificar_payload(malo)
        chequear(f"rechaza {nombre}", False)
    except ValueError:
        chequear(f"rechaza {nombre}", True)

# 4. Sin clave no se seudonimiza
# (se reemplaza la configuración: así la prueba no depende de lo que diga el .env)
S.get_settings = lambda: SimpleNamespace(ia_seudonimo_key="")
try:
    S.seudonimo("x")
    chequear("sin clave no seudonimiza", False)
except S.ClaveSeudonimoFaltante:
    chequear("sin clave no seudonimiza", True)

print(f"\n{'TODO BIEN' if not fallas else f'{len(fallas)} FALLAS'}")
sys.exit(1 if fallas else 0)
