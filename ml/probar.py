"""Prueba el servicio ml desde adentro del contenedor: python probar.py"""
import json
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8001"
URL = f"{BASE}/predict"


def esperar_servicio(segundos: int = 60) -> None:
    """Recién levantado el contenedor, uvicorn tarda unos segundos en escuchar."""
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            with urllib.request.urlopen(f"{BASE}/salud", timeout=2) as r:
                salud = json.loads(r.read())
            if not salud.get("modelo_cargado"):
                raise SystemExit(f"El servicio arrancó pero sin modelo: {salud}")
            print("Servicio listo:", salud.get("version"), "umbral", salud.get("umbral"))
            return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(1)
    raise SystemExit(f"El servicio no respondió en {segundos} s: revisa 'docker compose logs ml'")


def llamar(variables):
    req = urllib.request.Request(
        URL, data=json.dumps({"pseudo_id": "prueba", "variables": variables}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# (nombre, variables, código esperado, critico esperado o None si no importa)
# Valores críticos: son los que van al tester.yaml como paciente_critico (R20).
CASOS = [
    ("normal", {"edad": 35, "sexo": 1, "glucosa": 95, "potasio": 4.1, "hemoglobina": 14}, 200, False),
    ("critico", {"edad": 78, "sexo": 0, "glucosa": 42, "potasio": 6.6, "hemoglobina": 6.8}, 200, True),
    ("llave extra", {"edad": 35, "nombre": "CANARIO"}, 422, None),
    ("texto", {"glucosa": "alta"}, 422, None),
    ("vacio", {}, 422, None),
    ("solo edad", {"edad": 50, "sexo": 1}, 422, None),
    ("incompleto", {"edad": 50, "glucosa": 110}, 200, None),
]

esperar_servicio()
fallas = 0
for nombre, variables, codigo, critico in CASOS:
    c, cuerpo = llamar(variables)
    ok = c == codigo and (critico is None or cuerpo.get("critico") is critico)
    if nombre == "llave extra":   # debe rechazar por el NOMBRE y no devolver el dato
        ok = ok and "nombre" in str(cuerpo) and "CANARIO" not in str(cuerpo)
    fallas += not ok
    print("OK   " if ok else "FALLA", nombre, c, cuerpo)
raise SystemExit(1 if fallas else 0)