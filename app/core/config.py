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

    # Seguridad
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    app_encryption_key: str = os.getenv("APP_ENCRYPTION_KEY", "")
    app_blind_index_key: str = os.getenv("APP_BLIND_INDEX_KEY", "")

    max_intentos_login: int = 3
    minutos_bloqueo: int = 15

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