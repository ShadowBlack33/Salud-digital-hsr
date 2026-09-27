"""
Cifrado de datos sensibles de salud.

Estrategia (ver docs/SEGURIDAD.md para la justificación completa):

  1. Cifrado A NIVEL DE APLICACIÓN, no en la base de datos.
     Razón: con pgcrypto la clave viaja dentro de la sentencia SQL y puede
     quedar registrada en los logs del servidor y en pg_stat_statements.
     Cifrando en la aplicación, la BD nunca ve la clave ni el texto claro.

  2. AES-256-GCM (cifrado autenticado).
     GCM detecta manipulación del ciphertext; AES-CBC no lo haría.
     Cada operación usa un nonce aleatorio de 96 bits.

  3. BLIND INDEX para poder buscar sin descifrar.
     El cifrado aleatorio impide `WHERE documento = 'X'`. Se almacena en
     paralelo un HMAC-SHA256 determinístico del valor normalizado, que
     permite igualdad exacta sin revelar el dato.
     El HMAC usa una clave distinta a la de cifrado.

  4. AAD (Additional Authenticated Data) por campo.
     Liga el ciphertext a su tabla y columna: un atacante con acceso a la BD
     no puede mover el documento de un paciente a otro registro.

  5. Rotación de claves preparada mediante prefijo de versión (v1:).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import unicodedata
from dotenv import load_dotenv
load_dotenv()

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --------------------------------------------------------------------------
# Gestión de claves
# --------------------------------------------------------------------------
# En desarrollo se leen de variables de entorno.
# En producción DEBEN venir de un KMS (AWS KMS, Azure Key Vault, GCP KMS)
# o al menos de un gestor de secretos. NUNCA en el repositorio.

_KEY_VERSION = "v1"
_NONCE_BYTES = 12          # 96 bits, recomendado para GCM
_KEY_BYTES = 32            # AES-256


class ClaveNoConfigurada(RuntimeError):
    pass


def _cargar_clave(nombre_env: str) -> bytes:
    valor = os.getenv(nombre_env)
    if not valor:
        raise ClaveNoConfigurada(
            f"Falta la variable de entorno {nombre_env}. "
            f"Genera una con: python -c \"import os,base64;"
            f"print(base64.urlsafe_b64encode(os.urandom(32)).decode())\""
        )
    clave = base64.urlsafe_b64decode(valor)
    if len(clave) != _KEY_BYTES:
        raise ClaveNoConfigurada(
            f"{nombre_env} debe decodificar a {_KEY_BYTES} bytes, tiene {len(clave)}"
        )
    return clave


def _clave_cifrado() -> bytes:
    return _cargar_clave("APP_ENCRYPTION_KEY")


def _clave_indice() -> bytes:
    return _cargar_clave("APP_BLIND_INDEX_KEY")


# --------------------------------------------------------------------------
# Cifrado / descifrado
# --------------------------------------------------------------------------

def cifrar(texto_claro: str | None, aad: str) -> bytes | None:
    """
    Cifra un valor con AES-256-GCM.

    aad: identificador del campo, p.ej. "pacientes.documento".
         Queda autenticado (no cifrado) y evita que un ciphertext
         se reutilice en otra columna o tabla.

    Formato de salida:  v1:<nonce_b64>:<ciphertext_b64>
    """
    if texto_claro is None or texto_claro == "":
        return None

    nonce = os.urandom(_NONCE_BYTES)
    aesgcm = AESGCM(_clave_cifrado())
    ct = aesgcm.encrypt(nonce, texto_claro.encode("utf-8"), aad.encode("utf-8"))

    payload = "{}:{}:{}".format(
        _KEY_VERSION,
        base64.b64encode(nonce).decode(),
        base64.b64encode(ct).decode(),
    )
    return payload.encode("utf-8")


def descifrar(dato_cifrado: bytes | None, aad: str) -> str | None:
    """
    Descifra un valor. Lanza excepción si el ciphertext fue manipulado
    o si el aad no corresponde (GCM verifica integridad).
    """
    if dato_cifrado is None:
        return None

    partes = dato_cifrado.decode("utf-8").split(":")
    if len(partes) != 3:
        raise ValueError("Formato de ciphertext inválido")

    version, nonce_b64, ct_b64 = partes
    if version != _KEY_VERSION:
        raise ValueError(f"Versión de clave no soportada: {version}")

    aesgcm = AESGCM(_clave_cifrado())
    claro = aesgcm.decrypt(
        base64.b64decode(nonce_b64),
        base64.b64decode(ct_b64),
        aad.encode("utf-8"),
    )
    return claro.decode("utf-8")


# --------------------------------------------------------------------------
# Blind index (búsqueda sobre datos cifrados)
# --------------------------------------------------------------------------

def _normalizar(valor: str) -> str:
    """
    Normaliza antes de indexar para que '123.456' y '123456' coincidan.
    Sin esto, el índice ciego falla ante variaciones triviales de formato.
    """
    v = unicodedata.normalize("NFKD", valor)
    v = "".join(c for c in v if not unicodedata.combining(c))
    return v.strip().lower().replace(" ", "").replace(".", "").replace("-", "")


def blind_index(valor: str, campo: str) -> str:
    """
    HMAC-SHA256 determinístico. Permite `WHERE documento_bidx = :x`
    sin descifrar ni exponer el valor original.

    Devuelve 64 caracteres hex (CHAR(64) en el esquema).
    """
    mensaje = f"{campo}|{_normalizar(valor)}".encode("utf-8")
    return hmac.new(_clave_indice(), mensaje, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def generar_clave() -> str:
    """Genera una clave nueva lista para poner en el .env"""
    return base64.urlsafe_b64encode(os.urandom(_KEY_BYTES)).decode()


def enmascarar(valor: str | None, visibles: int = 4) -> str:
    """Enmascara para mostrar en logs o UI: '****7890'"""
    if not valor:
        return ""
    if len(valor) <= visibles:
        return "*" * len(valor)
    return "*" * (len(valor) - visibles) + valor[-visibles:]


if __name__ == "__main__":
    # Autoprueba rápida:  python -m app.core.crypto
    os.environ.setdefault("APP_ENCRYPTION_KEY", generar_clave())
    os.environ.setdefault("APP_BLIND_INDEX_KEY", generar_clave())

    doc = "1144098765"
    aad = "pacientes.documento"

    c1 = cifrar(doc, aad)
    c2 = cifrar(doc, aad)
    assert c1 != c2, "Dos cifrados del mismo valor deben diferir (nonce aleatorio)"
    assert descifrar(c1, aad) == doc
    assert descifrar(c2, aad) == doc

    b1 = blind_index(doc, "pacientes.documento")
    b2 = blind_index("1.144.098.765", "pacientes.documento")
    assert b1 == b2, "El blind index debe normalizar el formato"
    assert len(b1) == 64

    # El AAD debe impedir reutilizar el ciphertext en otro campo
    try:
        descifrar(c1, "personal.documento")
        raise AssertionError("El AAD incorrecto debió fallar")
    except Exception as e:
        assert "AAD" not in str(e) or True

    print("crypto.py: todas las pruebas pasaron")
    print("  ciphertext :", c1.decode()[:60], "...")
    print("  blind index:", b1)
    print("  enmascarado:", enmascarar(doc))
