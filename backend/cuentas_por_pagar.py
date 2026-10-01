"""Bandeja interna de revisión y seguimiento de facturas."""
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from auth import get_current_ap_user
from database import get_db
from models import (
    DocumentoBase, DocumentoBaseLinea, Factura, FacturaAsignacion, FacturaEvento,
    FacturaOrigen, FacturaRegistro, OrdenCompra, OrdenPosicion, Proveedor,
    SolicitudCuentasPorPagar,
)
from tenancy import ids_sociedades_usuario

router = APIRouter(prefix="/cuentas-por-pagar", tags=["cuentas por pagar"])

ESTADOS = {
    "pendientes": ["Pendiente de revisión", "Enviada a contabilidad", "Pendiente de recepción"],
    "recibidas": ["Recibida por contabilidad"],
    "aceptadas": ["Aceptada por contabilidad"],
    "programadas": ["Programada para pago"],
    "pagadas": ["Pagada"],
    "rechazadas": ["Rechazada"],
}


def _status_filter(query, estado):
    estados = ESTADOS.get(estado)
    if estados:
        return query.filter(Factura.estado.in_(estados))
    if estado == "todas" or not estado:
        return query
    raise HTTPException(status_code=400, detail="Filtro de estado inválido")


def _ids_por_factura(db, facturas):
    ids = [f.id for f in facturas]
    if not ids:
        return {}
    rows = db.query(FacturaAsignacion.factura_id, OrdenCompra.numero).join(
        OrdenPosicion, OrdenPosicion.id == FacturaAsignacion.posicion_id
    ).join(OrdenCompra, OrdenCompra.id == OrdenPosicion.orden_id).filter(FacturaAsignacion.factura_id.in_(ids)).all()
    result = {}
    for factura_id, numero in rows:
        result.setdefault(factura_id, set()).add(numero)
    return result


def _row(db, factura, provider, order_numbers=None):
    registro = db.get(FacturaRegistro, factura.id)
    return {
        "id": factura.id,
        "serie": factura.serie,
        "correlativo": factura.correlativo,
        "numero": f"{factura.serie}-{factura.correlativo}",
        "proveedor": {"id": provider.id, "ruc": provider.ruc, "razon_social": provider.razon_social, "email": provider.email},
        "ruc_receptor": registro.ruc_receptor if registro else None,
        "fecha_emision": registro.fecha_emision.isoformat() if registro and registro.fecha_emision else None,
        "moneda": registro.moneda if registro else "PEN",
        "monto_subtotal": float(factura.monto_subtotal),
        "monto_igv": float(factura.monto_igv),
        "monto_total": float(factura.monto_total),
        "estado": factura.estado,
        "creado_en": factura.creado_en.isoformat() if factura.creado_en else None,
        "pedidos": sorted(order_numbers or []),
        "tiene_pdf": bool(registro and registro.pdf),
        "tiene_xml": bool(registro and registro.xml),
        "recibida_contabilidad_en": factura.recibida_contabilidad_en.isoformat() if factura.recibida_contabilidad_en else None,
        "aceptada_portal_en": factura.aceptada_portal_en.isoformat() if factura.aceptada_portal_en else None,
        "fecha_pago_programada": factura.fecha_pago_programada.isoformat() if factura.fecha_pago_programada else None,
        "pagada_en": factura.pagada_en.isoformat() if factura.pagada_en else None,
        "motivo_rechazo": factura.motivo_rechazo,
    }


@router.get("/resumen")
def resumen(_user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    society_ids = ids_sociedades_usuario(db, _user)
    base = db.query(Factura.estado, func.count(Factura.id), func.coalesce(func.sum(Factura.monto_total), 0)).filter(Factura.cliente_id == _user['cliente_id'], Factura.sociedad_id.in_(society_ids)).group_by(Factura.estado).all()
    counts = {key: 0 for key in ESTADOS}
    amounts = {key: 0.0 for key in ESTADOS}
    for state, count, amount in base:
        for key, values in ESTADOS.items():
            if state in values:
                counts[key] += count
                amounts[key] += float(amount)
                break
    return {"facturas": counts, "montos": amounts, "total": sum(counts.values())}


@router.get("/datos-maestros")
def datos_maestros(_user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    from tenancy import sociedades_usuario
    from models import ProveedorCliente
    proveedores = db.query(Proveedor).join(ProveedorCliente, ProveedorCliente.proveedor_id == Proveedor.id).filter(ProveedorCliente.cliente_id == _user['cliente_id'], ProveedorCliente.activo.is_(True)).order_by(Proveedor.razon_social.asc()).all()
    return {
        "proveedores": [{"id": p.id, "ruc": p.ruc, "razon_social": p.razon_social, "email": p.email, "estado": p.estado, "activo": bool(p.activo)} for p in proveedores],
        "sociedades": [{'ruc': s.ruc, 'razon_social': s.razon_social, 'codigo_sap': s.codigo_sap} for s in sociedades_usuario(db, _user)],
    }


@router.get("/solicitudes")
def listar_solicitudes(user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    rows = db.query(SolicitudCuentasPorPagar, Factura).outerjoin(Factura, Factura.id == SolicitudCuentasPorPagar.factura_id).filter(SolicitudCuentasPorPagar.usuario_id == user["usuario_id"], SolicitudCuentasPorPagar.cliente_id == user['cliente_id']).order_by(SolicitudCuentasPorPagar.creado_en.desc()).all()
    return [{"id": request.id, "categoria": request.categoria, "asunto": request.asunto, "descripcion": request.descripcion, "estado": request.estado, "creado_en": request.creado_en.isoformat() if request.creado_en else None, "factura_id": request.factura_id, "factura": f"{invoice.serie}-{invoice.correlativo}" if invoice else None} for request, invoice in rows]


@router.post("/solicitudes", status_code=201)
def crear_solicitud(payload: dict, user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    categoria = str(payload.get("categoria", "")).strip()
    asunto = str(payload.get("asunto", "")).strip()
    descripcion = str(payload.get("descripcion", "")).strip()
    factura_id = str(payload.get("factura_id", "")).strip() or None
    if categoria not in {"Consulta de factura", "Problema de pago", "Datos maestros", "Acceso al portal", "Otra consulta"}:
        raise HTTPException(status_code=400, detail="Selecciona una categoría válida")
    if not asunto or len(asunto) > 200 or len(descripcion) < 10 or len(descripcion) > 3000:
        raise HTTPException(status_code=400, detail="Completa el asunto y una descripción de 10 a 3000 caracteres")
    society_ids = ids_sociedades_usuario(db, user)
    if factura_id and not db.query(Factura.id).filter(Factura.id == factura_id, Factura.cliente_id == user['cliente_id'], Factura.sociedad_id.in_(society_ids)).first():
        raise HTTPException(status_code=404, detail="La factura seleccionada no existe")
    request = SolicitudCuentasPorPagar(usuario_id=user["usuario_id"], cliente_id=user['cliente_id'], factura_id=factura_id, categoria=categoria, asunto=asunto, descripcion=descripcion)
    db.add(request)
    db.commit()
    db.refresh(request)
    return {"id": request.id, "estado": request.estado, "creado_en": request.creado_en.isoformat() if request.creado_en else None}


@router.get("/facturas")
def listar(
    estado: str = "todas", buscar: str = "", desde: date | None = None, hasta: date | None = None,
    receptor: str = "", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    _user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db),
):
    society_ids = ids_sociedades_usuario(db, _user)
    query = db.query(Factura, Proveedor).join(Proveedor, Proveedor.id == Factura.proveedor_id).filter(Factura.cliente_id == _user['cliente_id'], Factura.sociedad_id.in_(society_ids))
    query = _status_filter(query, estado)
    if desde:
        query = query.join(FacturaRegistro, FacturaRegistro.factura_id == Factura.id).filter(FacturaRegistro.fecha_emision >= desde)
    if hasta:
        if not desde:
            query = query.join(FacturaRegistro, FacturaRegistro.factura_id == Factura.id)
        query = query.filter(FacturaRegistro.fecha_emision <= hasta)
    if receptor.strip():
        if not desde and not hasta:
            query = query.join(FacturaRegistro, FacturaRegistro.factura_id == Factura.id)
        query = query.filter(FacturaRegistro.ruc_receptor == receptor.strip())
    needle = buscar.strip()
    if needle:
        matching_orders = db.query(OrdenCompra.id).filter(OrdenCompra.cliente_id == _user['cliente_id'], OrdenCompra.numero.ilike(f"%{needle}%")).subquery()
        matching_positions = db.query(OrdenPosicion.id).filter(OrdenPosicion.orden_id.in_(matching_orders)).subquery()
        matching_invoices = db.query(FacturaAsignacion.factura_id).filter(FacturaAsignacion.posicion_id.in_(matching_positions)).subquery()
        query = query.filter(or_(Factura.serie.ilike(f"%{needle}%"), Factura.correlativo.ilike(f"%{needle}%"), Proveedor.ruc.ilike(f"%{needle}%"), Proveedor.razon_social.ilike(f"%{needle}%"), Factura.id.in_(matching_invoices)))
    total = query.count()
    rows = query.order_by(Factura.creado_en.desc(), Factura.id.desc()).offset(offset).limit(limit).all()
    order_numbers = _ids_por_factura(db, [f for f, _ in rows])
    return {"items": [_row(db, factura, provider, order_numbers.get(factura.id, set())) for factura, provider in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/facturas/{factura_id}")
def detalle(factura_id: str, user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    society_ids = ids_sociedades_usuario(db, user)
    row = db.query(Factura, Proveedor).join(Proveedor, Proveedor.id == Factura.proveedor_id).filter(Factura.id == factura_id, Factura.cliente_id == user['cliente_id'], Factura.sociedad_id.in_(society_ids)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    factura, provider = row
    result = _row(db, factura, provider, _ids_por_factura(db, [factura]).get(factura.id, set()))
    registro = db.get(FacturaRegistro, factura_id)
    result["posiciones"] = []
    assigns = db.query(FacturaAsignacion, OrdenPosicion, OrdenCompra).join(OrdenPosicion, OrdenPosicion.id == FacturaAsignacion.posicion_id).join(OrdenCompra, OrdenCompra.id == OrdenPosicion.orden_id).filter(FacturaAsignacion.factura_id == factura_id).all()
    for assignment, position, order in assigns:
        result["posiciones"].append({"pedido": order.numero, "posicion": position.numero, "tipo": position.tipo, "codigo": position.codigo_servicio if position.tipo == "servicio" else position.material, "descripcion": position.descripcion, "unidad": position.unidad, "cantidad": float(assignment.cantidad), "subtotal": float(assignment.subtotal), "igv": float(assignment.igv), "total": float(assignment.total)})
    result["documentos_base"] = [
        {"tipo": doc.tipo, "numero": doc.numero, "linea": line.numero, "cantidad": float(assignment.cantidad)}
        for doc, line, assignment in db.query(DocumentoBase, DocumentoBaseLinea, FacturaAsignacion)
        .join(DocumentoBaseLinea, DocumentoBaseLinea.documento_id == DocumentoBase.id)
        .join(FacturaOrigen, FacturaOrigen.documento_linea_id == DocumentoBaseLinea.id)
        .join(FacturaAsignacion, FacturaAsignacion.id == FacturaOrigen.asignacion_id)
        .filter(FacturaAsignacion.factura_id == factura_id).all()
    ]
    result["historial"] = [
        {"accion": event.accion, "estado_anterior": event.estado_anterior, "estado_nuevo": event.estado_nuevo, "comentario": event.comentario, "actor": event.actor_nombre, "fecha": event.creado_en.isoformat() if event.creado_en else None, "fecha_pago_programada": event.fecha_pago_programada.isoformat() if event.fecha_pago_programada else None}
        for event in db.query(FacturaEvento).filter(FacturaEvento.factura_id == factura_id).order_by(FacturaEvento.creado_en.asc(), FacturaEvento.id.asc()).all()
    ]
    result["adjuntos"] = {"pdf": bool(registro and registro.pdf), "xml": bool(registro and registro.xml)}
    return result


@router.get("/facturas/{factura_id}/archivos/{tipo}")
def archivo(factura_id: str, tipo: str, _user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    if tipo not in {"xml", "pdf"}:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    society_ids = ids_sociedades_usuario(db, _user)
    if not db.query(Factura.id).filter(Factura.id == factura_id, Factura.cliente_id == _user['cliente_id'], Factura.sociedad_id.in_(society_ids)).first():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    registro = db.get(FacturaRegistro, factura_id)
    data = getattr(registro, tipo, None) if registro else None
    if not data:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return Response(data, media_type="application/pdf" if tipo == "pdf" else "application/xml", headers={"Content-Disposition": f'inline; filename="factura.{tipo}"', "X-Content-Type-Options": "nosniff"})


@router.post("/facturas/{factura_id}/acciones")
def accion_factura(factura_id: str, payload: dict, user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    society_ids = ids_sociedades_usuario(db, user)
    factura = db.query(Factura).filter(Factura.id == factura_id, Factura.cliente_id == user['cliente_id'], Factura.sociedad_id.in_(society_ids)).first()
    if not factura:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    accion = str(payload.get("accion", "")).strip().lower()
    comentario = str(payload.get("comentario", "")).strip() or None
    anterior = factura.estado
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if comentario and len(comentario) > 2000:
        raise HTTPException(status_code=400, detail="El comentario excede el máximo de 2000 caracteres")
    fecha_programada = None
    if accion == "recibir":
        if anterior not in ESTADOS["pendientes"]:
            raise HTTPException(status_code=409, detail="Solo una factura pendiente puede marcarse como recibida")
        factura.estado = "Recibida por contabilidad"
        factura.recibida_contabilidad_en = now
    elif accion == "aceptar":
        if anterior not in ESTADOS["recibidas"]:
            raise HTTPException(status_code=409, detail="Primero registra la recepción de la factura por contabilidad")
        factura.estado = "Aceptada por contabilidad"
        factura.aceptada_portal_en = now
    elif accion == "rechazar":
        if anterior not in ESTADOS["pendientes"] + ESTADOS["recibidas"]:
            raise HTTPException(status_code=409, detail="Solo una factura pendiente o recibida puede rechazarse")
        if not comentario or len(comentario) < 8:
            raise HTTPException(status_code=400, detail="Indica un motivo de rechazo claro (mínimo 8 caracteres)")
        if len(comentario) > 2000:
            raise HTTPException(status_code=400, detail="El motivo de rechazo excede el máximo de 2000 caracteres")
        factura.estado = "Rechazada"
        factura.motivo_rechazo = comentario
    elif accion == "programar_pago":
        if anterior not in ESTADOS["aceptadas"]:
            raise HTTPException(status_code=409, detail="La factura debe estar aceptada antes de programar el pago")
        try:
            fecha_programada = date.fromisoformat(str(payload.get("fecha_pago", "")))
        except ValueError:
            raise HTTPException(status_code=400, detail="Indica una fecha de pago válida")
        if fecha_programada < date.today():
            raise HTTPException(status_code=400, detail="La fecha de pago no puede estar en el pasado")
        factura.estado = "Programada para pago"
        factura.fecha_pago_programada = fecha_programada
    elif accion == "marcar_pagada":
        if anterior not in ESTADOS["programadas"]:
            raise HTTPException(status_code=409, detail="Solo una factura programada puede marcarse como pagada")
        factura.estado = "Pagada"
        factura.pagada_en = now
    else:
        raise HTTPException(status_code=400, detail="Acción inválida")
    event = FacturaEvento(factura_id=factura.id, cliente_id=user['cliente_id'], actor_id=user["usuario_id"], actor_nombre=user.get("nombre") or user.get("usuario") or "Cuentas por pagar", accion=accion, estado_anterior=anterior, estado_nuevo=factura.estado, comentario=comentario, fecha_pago_programada=fecha_programada)
    db.add(event)
    db.commit()
    return {"id": factura.id, "estado": factura.estado, "fecha_pago_programada": factura.fecha_pago_programada.isoformat() if factura.fecha_pago_programada else None}
