#!/usr/bin/env python3
"""
(Re)indexa el RAG: todas las guías de docs/rag/guias y la historia aprobada
de cada paciente activo con al menos un reporte de IA aprobado.

Uso:  python scripts/rag_indexar.py            (guías + historias)
      python scripts/rag_indexar.py --guias    (solo guías)
Necesita:  pip install fastembed   (si no está, indexa sin vectores y el RAG usa BM25)
Hay que correrlo de nuevo si se cambia el modelo de embeddings.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from sqlalchemy import text  # noqa: E402

from app.core.deps import SessionLocal  # noqa: E402  -- ajustar si la sesión vive en otro módulo
from app.services import rag  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        print(f"Guías: {rag.indexar_guias(db)} fragmentos")
        if "--guias" in sys.argv:
            return
        pacientes = [r[0] for r in db.execute(text(
            "SELECT DISTINCT paciente_id FROM reportes_ia WHERE estado = 'aprobado'")).all()]
        total, bloqueados = 0, 0
        for pid in pacientes:
            try:
                total += rag.indexar_paciente(db, pid)
            except rag.CanarioDetectado:
                db.rollback()
                bloqueados += 1
        print(f"Historias: {len(pacientes)} pacientes, {total} fragmentos, {bloqueados} bloqueados por canario")
    finally:
        db.close()


if __name__ == "__main__":
    main()
