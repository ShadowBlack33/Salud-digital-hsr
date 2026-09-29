"""Configuración central. Todos los secretos vienen del entorno, nunca del código."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Aplicación
    app_nombre: str = "API Coordinación de Capacidad Quirúrgica"
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

    # CORS
    cors_origenes: list[str] = ["*"]

    class Config:
        env_file = ".env"
        extra = "ignore"

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
        if self.cors_origenes == ["*"]:
            raise RuntimeError("CORS '*' no está permitido en producción")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validar_produccion()
    return s
