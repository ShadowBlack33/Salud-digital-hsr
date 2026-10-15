"""
Clusters del dataset tabular (R07). Los produce scripts/clusters_vitaldb.py y los
sube scripts/cargar_clusters.py a MongoDB (colecciones `clusters_resumen` y
`dataset_tabular`); aquí solo se leen. Ver docs/DATASETS.md y docs/INFORME_CLUSTERS.md.
"""
from __future__ import annotations

from app.services.contabilidad import ErrorContabilidad, base_mongo

CAMPOS = ("cluster", "descripcion", "n_reales", "n_sinteticos")


def resumen(detalle: bool = False) -> list[dict]:
    """Un elemento por cluster: cluster, descripcion, n_reales, n_sinteticos (y perfil si detalle)."""
    docs = list(base_mongo()["clusters_resumen"].find({}, {"_id": 0}).sort("cluster", 1))
    if not docs:
        raise ErrorContabilidad(
            404, "Aún no hay clusters cargados. Ejecute scripts/clusters_vitaldb.py y luego scripts/cargar_clusters.py.")
    campos = CAMPOS + (("perfil",) if detalle else ())
    return [{k: d.get(k) for k in campos} for d in docs]
