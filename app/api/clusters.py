"""
Clusters del dataset tabular (R07).

  GET /analitica/clusters   [{cluster, descripcion, n_reales, n_sinteticos}]
                            con ?detalle=true agrega el perfil preoperatorio de cada grupo

Solo lectura, con el permiso `analitica:read` (el mismo de las demás rutas de
/analitica). Los datos salen de MongoDB: se cargan con scripts/cargar_clusters.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.contabilidad import _servicio
from app.core.deps import ContextoAcceso, RequierePermiso
from app.services import clusters as svc

router = APIRouter(prefix="/analitica", tags=["Analítica y caso de negocio"])


@router.get("/clusters", summary="Grupos del dataset tabular (VitalDB) con casos reales y sintéticos")
def clusters(detalle: bool = Query(False, description="Incluye el perfil preoperatorio medio de cada grupo"),
             ctx: ContextoAcceso = Depends(RequierePermiso("analitica", "read"))):
    return _servicio(svc.resumen, detalle)
