"""
Contabilidad (R09). Contrato en docs/CONTRATO_FACTURACION.md; guía en docs/CONTABILIDAD.md.

  GET   /contabilidad/facturas              lista (filtros opcionales; sin paginar = todas)
  POST  /contabilidad/facturas              crea una factura (201)
  PATCH /contabilidad/facturas/{id}/pagar   pendiente | radicada | glosada -> pagada
  PATCH /contabilidad/facturas/{id}/anular  con motivo (una factura pagada no se anula)
  GET   /contabilidad/tarifario             [{codigo, nombre, tipo_cobro, valor}]

Solo operan estas rutas el contable y el admin. Los permisos del sistema solo
tienen 'facturacion:read' (sin permiso de escritura), así que el nivel 1 exige
ese permiso y el rol se valida aquí: cualquier otro rol (coordinador incluido,
que sí tiene facturacion:read) recibe 403 y el intento queda auditado.
La paciente ve sus cobros en GET /mi-cuenta, que no pasa por este módulo.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import ContextoAcceso, RequierePermiso, get_db
from app.services import contabilidad as svc
from app.services.auditoria import registrar

router = APIRouter(prefix="/contabilidad", tags=["Contabilidad (R09)"])

ROLES_CONTABLES = ("contable", "admin")
TipoCobro = Literal["consulta", "urgencias", "hospitalizacion", "cirugia", "imagenologia",
                    "laboratorio", "medicamentos", "insumos", "terapia", "ia", "remision", "otros"]


class Cobertura(BaseModel):
    tipo: Literal["particular", "eps", "especial", "soat", "prepagada"]
    entidad: str = Field(..., min_length=1, max_length=150)
    regimen: Literal["contributivo", "subsidiado", "especial"] | None = None


class FacturaCrear(BaseModel):
    paciente_id: str = Field(..., min_length=1, max_length=64, description="documento_bidx del paciente (nunca la cédula)")
    servicio: str = Field(..., min_length=2, max_length=60)
    valor: float = Field(..., gt=0, le=10_000_000_000, description="Total en COP")
    fecha: datetime | None = None
    estado_pago: Literal["pendiente", "radicada", "glosada", "pagada"] = "pendiente"
    reporte_id: int | None = Field(None, description="Si viene, es la factura automática de un reporte de IA (idempotente)")
    tipo_cobro: TipoCobro | None = None
    cups: str | None = Field(None, max_length=20)
    descripcion: str | None = Field(None, max_length=200)
    cantidad: int | None = Field(None, ge=1, le=100000)
    valor_unitario: float | None = Field(None, ge=0)
    paciente_nombre: str | None = Field(None, max_length=160)
    paciente_documento: str | None = Field(None, max_length=40)
    cobertura: Cobertura | None = None
    valor_paciente: float | None = Field(None, ge=0)
    valor_entidad: float | None = Field(None, ge=0)
    origen: Literal["manual", "automatica"] | None = Field(None, description="Se ignora: lo decide el servidor")


class Anulacion(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=300)


def contable(ctx: ContextoAcceso = Depends(RequierePermiso("facturacion", "read"))) -> ContextoAcceso:
    """Nivel 1 (permiso) + rol: solo contable y admin. Lo demás, 403 auditado."""
    rol = getattr(getattr(ctx.usuario, "rol", None), "codigo", None)
    if rol not in ROLES_CONTABLES:
        registrar(ctx.db, ctx.usuario, "factura", None, "read", resultado="denegado", request=ctx.request)
        ctx.db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el contable y el administrador operan la contabilidad")
    return ctx


def _servicio(fn, *args, **kwargs):
    """Llama al servicio y traduce sus errores: de negocio -> su HTTP; Mongo caído -> 503."""
    try:
        return fn(*args, **kwargs)
    except svc.ErrorContabilidad as e:
        raise HTTPException(e.codigo, e.mensaje) from None
    except ImportError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "El módulo de contabilidad no está instalado (falta pymongo)") from None
    except Exception as e:  # noqa: BLE001
        try:
            from pymongo.errors import PyMongoError  # noqa: PLC0415
        except ImportError:
            raise
        if isinstance(e, PyMongoError):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                "MongoDB no está disponible en este momento") from None
        raise


@router.get("/facturas", summary="Lista de facturas")
def listar_facturas(
    tipo: TipoCobro | None = Query(None, description="Tipo de cobro"),
    estado: Literal["pendiente", "radicada", "glosada", "pagada", "anulada"] | None = Query(None),
    entidad: str | None = Query(None, description="Entidad que responde (p. ej. 'EPS Gamma')"),
    q: str | None = Query(None, max_length=100, description="Factura, CUPS, documento (****1234) o nombre (palabra completa)"),
    desde: str | None = Query(None, description="AAAA-MM-DD o ISO 8601"),
    hasta: str | None = Query(None, description="AAAA-MM-DD o ISO 8601 (inclusive)"),
    pagina: int | None = Query(None, ge=1),
    por_pagina: int | None = Query(None, ge=1, le=500),
    ctx: ContextoAcceso = Depends(contable),
):
    """
    Sin `pagina` ni `por_pagina` responde una lista simple con todas las que
    cumplen el filtro (el front actual las filtra y pagina). Con alguno de los
    dos responde `{"facturas": [...], "total": N}` ya paginada.
    """
    facturas, total = _servicio(svc.listar, tipo=tipo, estado=estado, entidad=entidad, q=q,
                                desde=desde, hasta=hasta, pagina=pagina, por_pagina=por_pagina)
    if pagina is None and por_pagina is None:
        return facturas
    return {"facturas": facturas, "total": total}


@router.post("/facturas", status_code=status.HTTP_201_CREATED, summary="Crear una factura")
def crear_factura(datos: FacturaCrear, request: Request,
                  ctx: ContextoAcceso = Depends(contable), db: Session = Depends(get_db)):
    """
    Lo que no se envía se completa: tipo de cobro (por servicio o CUPS), reparto
    paciente/entidad (reglas de referencia), y —si el paciente existe— nombre,
    documento enmascarado y cobertura. La cédula nunca se guarda completa.
    Con `reporte_id` es la factura automática del reporte: si ya existe, se
    devuelve la misma (200) en vez de crear otra.
    """
    d = datos.model_dump(exclude_none=True)
    d.pop("origen", None)
    if d.get("cobertura"):
        d["cobertura"] = dict(d["cobertura"])
    ficha = svc.datos_para_factura(db, datos.paciente_id)
    if not ficha:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    for k, v in ficha.items():
        d.setdefault(k, v)

    factura, creada = _servicio(svc.crear, d, usuario_id=ctx.usuario.id)
    if not creada:   # el reporte ya tenía factura: se devuelve la misma, sin cobrar dos veces
        return JSONResponse(jsonable_encoder(factura), status_code=status.HTTP_200_OK)
    registrar(db, ctx.usuario, "factura", factura["id"], "create",
              valor_nuevo={"id": factura["id"], "valor": factura["valor"], "tipo_cobro": factura["tipo_cobro"],
                           "estado_pago": factura["estado_pago"], "origen": factura["origen"]},
              request=request)
    db.commit()
    return factura


@router.patch("/facturas/{factura_id}/pagar", summary="Marcar como pagada")
def pagar_factura(factura_id: str, request: Request,
                  ctx: ContextoAcceso = Depends(contable), db: Session = Depends(get_db)):
    factura = _servicio(svc.pagar, factura_id, usuario_id=ctx.usuario.id)
    registrar(db, ctx.usuario, "factura", factura_id, "update",
              valor_nuevo={"estado_pago": "pagada"}, request=request)
    db.commit()
    return factura


@router.patch("/facturas/{factura_id}/anular", summary="Anular con motivo")
def anular_factura(factura_id: str, cuerpo: Anulacion, request: Request,
                   ctx: ContextoAcceso = Depends(contable), db: Session = Depends(get_db)):
    factura = _servicio(svc.anular, factura_id, cuerpo.motivo, usuario_id=ctx.usuario.id)
    registrar(db, ctx.usuario, "factura", factura_id, "update",
              valor_nuevo={"estado_pago": "anulada", "motivo": cuerpo.motivo[:200]}, request=request)
    db.commit()
    return factura


@router.get("/tarifario", summary="Tarifario de referencia")
def ver_tarifario(ctx: ContextoAcceso = Depends(contable)):
    return _servicio(svc.tarifario)
