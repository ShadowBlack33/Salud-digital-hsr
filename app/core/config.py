"""Configuración central. Todos los secretos vienen del entorno, nunca del código."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Aplicación
    app_nombre: str = "Pulso API · coordinación hospitalaria (caso Hospital San Rafael)"
    app_version: str = "1.0.0"
    entorno: str = os.getenv("ENTORNO", "desarrollo")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Base de datos
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres@/hsanrafael?host=/tmp&port=5433",
    )

    # Servidor HAPI FHIR
    fhir_base_url: str = os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir")
    fhir_timeout: int = 30

    # Servidor PACS (Orthanc) -- imágenes médicas en DICOM
    orthanc_url: str = os.getenv("ORTHANC_URL", "http://localhost:8042")
    orthanc_user: str = os.getenv("ORTHANC_USER", "api")
    orthanc_password: str = os.getenv("ORTHANC_PASSWORD", "orthanc_dev_2026")

    # Seguridad
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    app_encryption_key: str = os.getenv("APP_ENCRYPTION_KEY", "")
    app_blind_index_key: str = os.getenv("APP_BLIND_INDEX_KEY", "")

    max_intentos_login: int = 3
    minutos_bloqueo: int = 15
    # Si es True, la respuesta de un login fallido dice cuántos intentos le
    # quedan a la cuenta. Es útil para el usuario, pero tiene un costo: quien
    # prueba usuarios al azar puede distinguir cuáles existen (solo esos
    # devuelven el contador). Se puede apagar con LOGIN_MOSTRAR_INTENTOS=false.
    login_mostrar_intentos: bool = True
    # R02: tras el bloqueo, la cuenta solo se libera cuando el admin la
    # desbloquea. En False vuelve al comportamiento del Corte 1 (se libera
    # sola a los minutos_bloqueo minutos).
    bloqueo_requiere_admin: bool = True

    # CORS (R03). Lista separada por comas en la variable CORS_ORIGENES.
    # En producción el front y la API comparten origen detrás de nginx, así
    # que aquí solo hace falta el servidor de desarrollo de Vite. Nunca "*".
    cors_origenes_texto: str = Field("http://localhost:5173",
                                     validation_alias="CORS_ORIGENES")

    # Servicios del Corte 2. Se declaran aquí, y no con os.getenv() suelto en
    # cada módulo, para que todos lean la misma configuración.
    mongo_url: str = "mongodb://localhost:27017/hsr"
    ml_url: str = "http://localhost:8001"
    # Secreto compartido con el rest-hook de la Subscription FHIR (R21).
    hook_secret: str = ""
    # Dirección con la que HAPI alcanza a la API (red interna de Docker). Si la
    # API corre fuera de Docker, apuntar a host.docker.internal:8000.
    hook_url_base: str = "http://api:8000"

    # Sistema reactivo (R17-R21)
    # Minutos sin reconocer antes de escalar una alerta crítica al admin.
    # Debe coincidir con VITE_MINUTOS_ESCALAMIENTO (la cuenta regresiva del front).
    alerta_escalamiento_minutos: int = 5  # ALERTA_ESCALAMIENTO_MINUTOS
    # Tarifa de referencia de la factura automática del análisis de IA (COP).
    tarifa_analisis_ia: int = 45000
    # false = no arrancar las tareas de fondo (registro de la
    # Subscription FHIR). Las pruebas automáticas lo apagan.
    tareas_fondo: bool = True

    @property
    def cors_origenes(self) -> list[str]:
        return [o.strip() for o in self.cors_origenes_texto.split(",") if o.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"
        populate_by_name = True

    def validar_produccion(self) -> None:
        """En producción no se arranca sin claves reales."""
        if self.entorno != "produccion":
            return
        faltantes = [
            n for n, v in {
                "JWT_SECRET_KEY": self.jwt_secret_key,
                "APP_ENCRYPTION_KEY": self.app_encryption_key,
                "APP_BLIND_INDEX_KEY": self.app_blind_index_key,
            }.items() if not v
        ]
        if faltantes:
            raise RuntimeError(f"Faltan secretos en producción: {faltantes}")
        if "*" in self.cors_origenes:
            raise RuntimeError("CORS '*' no está permitido en producción")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validar_produccion()
    return s
