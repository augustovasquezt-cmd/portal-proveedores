"""Recepción de CRE desde SAP y consulta segura por el proveedor autenticado."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from auth import get_current_provider_user
from database import get_db
from models import CertificadoRetencion, Proveedor, ProveedorCliente, ProveedorSociedad, Sociedad, Cliente

router = APIRouter(tags=['retenciones'])
MAX_FILE = 5 * 1024 * 1024
ESTADOS = {'pendiente', 'aceptado', 'rechazado', 'anulado'}


class FacturaRelacionada(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tipo: str = Field(min_length=2, max_length=2, examples=['01'])
    serie: str = Field(min_length=1, max_length=10)
    numero: str = Field(min_length=1, max_length=20)
    fecha_emision: date
    importe: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    moneda: str = Field(default='PEN', min_length=3, max_length=3)


class CertificadoEntrada(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evento_origen: str = Field(min_length=1, max_length=100, description='ID estable del evento para reintentos idempotentes')
    ruc_emisor: str = Field(pattern=r'^\d{11}$')
    ruc_proveedor: str = Field(pattern=r'^\d{11}$')
    sociedad: str | None = Field(default=None, max_length=4)
    serie: str = Field(pattern=r'^R[A-Za-z0-9]{3}$', description='Serie SUNAT de cuatro caracteres que empieza por R')
    correlativo: str = Field(pattern=r'^\d{1,20}$')
    fecha_emision: date
    moneda: str = Field(default='PEN', min_length=3, max_length=3)
    base_retencion: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    tasa_retencion: Decimal | None = Field(default=None, ge=0, le=100, max_digits=7, decimal_places=4)
    importe_retencion: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    fecha_pago: date | None = None
    referencia_pago: str | None = Field(default=None, max_length=100)
    documento_sap: str | None = Field(default=None, max_length=100)
    ejercicio_sap: str | None = Field(default=None, pattern=r'^\d{4}$')
    estado_sunat: Literal['pendiente', 'aceptado', 'rechazado', 'anulado']
    motivo_estado: str | None = Field(default=None, max_length=2000)
    facturas_relacionadas: list[FacturaRelacionada] = Field(default_factory=list, max_length=200)


class CambioEstado(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ruc_emisor: str = Field(pattern=r'^\d{11}$')
    serie: str = Field(pattern=r'^R[A-Za-z0-9]{3}$')
    correlativo: str = Field(pattern=r'^\d{1,20}$')
    estado_sunat: Literal['pendiente', 'aceptado', 'rechazado', 'anulado']
    motivo_estado: str | None = Field(default=None, max_length=2000)


def error(detail: str, code: int = 400):
    raise HTTPException(status_code=code, detail=detail)


def autorizacion_sap(authorization: str | None = Header(default=None, alias='Authorization'), db: Session = Depends(get_db)):
    scheme, _, supplied = (authorization or '').partition(' ')
    if scheme.lower() != 'bearer' or len(supplied) < 32:
        error('Credenciales de integración SAP inválidas.', 401)
    supplied_hash = hashlib.sha256(supplied.encode('utf-8')).hexdigest()
    tenant = db.query(Cliente).filter(Cliente.sap_api_key_hash == supplied_hash, Cliente.activo.is_(True)).first()
    if not tenant:
        error('Credenciales de integración SAP inválidas.', 401)
    return tenant


def leer_archivo(file: UploadFile, tipo: str) -> bytes:
    content = file.file.read(MAX_FILE + 1)
    if not content:
        error(f'El archivo {tipo.upper()} está vacío.')
    if len(content) > MAX_FILE:
        error(f'El archivo {tipo.upper()} supera el límite de 5 MB.')
    return content


def validar_xml_cre(content: bytes, metadata: CertificadoEntrada):
    upper = content.upper()
    if b'<!DOCTYPE' in upper or b'<!ENTITY' in upper or b'\x00' in content:
        error('El XML no puede contener DTD, entidades externas ni bytes nulos.')
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        error(f'El XML del CRE no es válido: {exc}')
    if root.tag.rsplit('}', 1)[-1].lower() != 'retention':
        error('Se requiere el XML UBL de un Comprobante de Retención (Retention).')
    def text_at(parent_name: str, child_name: str) -> str:
        parent = next((node for node in root.iter() if node.tag.rsplit('}', 1)[-1] == parent_name), None)
        if parent is None:
            return ''
        for node in parent.iter():
            if node.tag.rsplit('}', 1)[-1] == child_name and (node.text or '').strip():
                return node.text.strip()
        return ''
    # UBL uses cbc:ID directly under the document root; avoid matching party IDs.
    root_id = next(((node.text or '').strip() for node in list(root) if node.tag.rsplit('}', 1)[-1] == 'ID'), '')
    if root_id:
        series, separator, number = root_id.partition('-')
        if not separator or series.upper() != metadata.serie.upper() or number.lstrip('0') != metadata.correlativo.lstrip('0'):
            error('La serie o el correlativo del XML no coincide con los metadatos enviados.')
    agent_ruc = text_at('AgentParty', 'ID') or text_at('AgentParty', 'CustomerAssignedAccountID')
    receiver_ruc = text_at('ReceiverParty', 'ID') or text_at('ReceiverParty', 'CustomerAssignedAccountID')
    if agent_ruc and agent_ruc != metadata.ruc_emisor:
        error('El RUC emisor del XML no coincide con los metadatos enviados.')
    if receiver_ruc and receiver_ruc != metadata.ruc_proveedor:
        error('El RUC del proveedor en el XML no coincide con los metadatos enviados.')
    if not agent_ruc or not receiver_ruc:
        error('El XML debe incluir la identificación RUC del agente y del proveedor.')


def serializar(row: CertificadoRetencion):
    return {
        'id': row.id, 'ruc_emisor': row.ruc_emisor, 'sociedad': row.sociedad,
        'serie': row.serie, 'correlativo': row.correlativo,
        'numero': f'{row.serie}-{row.correlativo}',
        'fecha_emision': row.fecha_emision.isoformat(), 'moneda': row.moneda,
        'base_retencion': float(row.base_retencion),
        'tasa_retencion': float(row.tasa_retencion) if row.tasa_retencion is not None else None,
        'importe_retencion': float(row.importe_retencion),
        'fecha_pago': row.fecha_pago.isoformat() if row.fecha_pago else None,
        'referencia_pago': row.referencia_pago, 'documento_sap': row.documento_sap,
        'ejercicio_sap': row.ejercicio_sap,
        'facturas_relacionadas': json.loads(row.facturas_relacionadas or '[]'),
        'estado_sunat': row.estado_sunat, 'motivo_estado': row.motivo_estado,
        'archivos': {'xml': True, 'pdf': True, 'cdr': bool(row.cdr)},
        'sha256': {'xml': row.sha256_xml, 'pdf': row.sha256_pdf, 'cdr': row.sha256_cdr},
        'creado_en': row.creado_en.isoformat() if row.creado_en else None,
        'actualizado_en': row.actualizado_en.isoformat() if row.actualizado_en else None,
    }


@router.post('/integracion-sap/retenciones', summary='Recibir certificado de retención emitido por SAP')
async def recibir_certificado(
    certificado: str = Form(..., description='JSON según backend/INTEGRACION_RETENCIONES_SAP.md'),
    xml: UploadFile = File(...),
    pdf: UploadFile = File(...),
    cdr: UploadFile | None = File(default=None),
    tenant: Cliente = Depends(autorizacion_sap),
    db: Session = Depends(get_db),
):
    try:
        metadata = CertificadoEntrada.model_validate_json(certificado)
    except ValidationError as exc:
        issues = [{'campo': '.'.join(str(part) for part in item['loc']), 'mensaje': item['msg'], 'tipo': item['type']} for item in exc.errors(include_input=False)]
        error({'mensaje': 'Los metadatos no cumplen el contrato de retenciones.', 'errores': issues}, 422)
    if metadata.fecha_emision > date.today() or (metadata.fecha_pago and metadata.fecha_pago > date.today()):
        error('Las fechas del certificado no pueden estar en el futuro.')
    if int(metadata.correlativo) < 1:
        error('El correlativo del certificado debe ser mayor que cero.')
    society = db.query(Sociedad).filter(Sociedad.cliente_id == tenant.id, Sociedad.ruc == metadata.ruc_emisor, Sociedad.activo.is_(True)).first()
    if not society:
        error('El RUC emisor no está habilitado para este cliente.', 403)
    supplier = db.query(Proveedor).filter(Proveedor.ruc == metadata.ruc_proveedor, Proveedor.activo.is_(True)).first()
    if not supplier:
        error('No existe un proveedor activo con el RUC indicado.', 422)
    membership = db.query(ProveedorCliente).filter_by(proveedor_id=supplier.id, cliente_id=tenant.id, activo=True).first()
    supplier_society = db.query(ProveedorSociedad.id).filter_by(cliente_id=tenant.id, proveedor_cliente_id=membership.id if membership else None, sociedad_id=society.id).first()
    if not membership or not supplier_society:
        error('El proveedor no está habilitado para este cliente y sociedad.', 422)
    xml_bytes, pdf_bytes = leer_archivo(xml, 'xml'), leer_archivo(pdf, 'pdf')
    if not pdf_bytes.startswith(b'%PDF-'):
        error('El adjunto PDF no tiene una cabecera PDF válida.')
    validar_xml_cre(xml_bytes, metadata)
    cdr_bytes = leer_archivo(cdr, 'cdr') if cdr else None
    if cdr_bytes:
        try:
            cdr_root = ET.fromstring(cdr_bytes)
        except ET.ParseError:
            error('El CDR XML no es válido.')
        if cdr_root.tag.rsplit('}', 1)[-1].lower() != 'applicationresponse':
            error('El adjunto CDR debe ser un XML UBL ApplicationResponse.')
    hashes = {
        'xml': hashlib.sha256(xml_bytes).hexdigest(),
        'pdf': hashlib.sha256(pdf_bytes).hexdigest(),
        'cdr': hashlib.sha256(cdr_bytes).hexdigest() if cdr_bytes else None,
    }
    metadata_hash = hashlib.sha256(json.dumps(metadata.model_dump(mode='json'), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()
    previous_event = db.query(CertificadoRetencion).filter(CertificadoRetencion.cliente_id == tenant.id, CertificadoRetencion.evento_origen == metadata.evento_origen).first()
    if previous_event:
        if previous_event.sha256_metadatos == metadata_hash and previous_event.sha256_xml == hashes['xml'] and previous_event.sha256_pdf == hashes['pdf'] and previous_event.sha256_cdr == hashes['cdr']:
            return {'resultado': 'ya_recibido', **serializar(previous_event)}
        error('El ID de evento ya se usó con archivos diferentes.', 409)
    duplicate = db.query(CertificadoRetencion).filter_by(cliente_id=tenant.id, ruc_emisor=metadata.ruc_emisor, serie=metadata.serie.upper(), correlativo=metadata.correlativo.lstrip('0') or '0').first()
    if duplicate:
        error('Ya existe un certificado con esa sociedad, serie y correlativo. Usa el mismo evento para reintentar o emite una nueva referencia de origen.', 409)
    if metadata.estado_sunat == 'aceptado' and not cdr_bytes:
        error('Para publicar un CRE como aceptado, adjunta su CDR de SUNAT.', 422)
    row = CertificadoRetencion(
        id=str(uuid4()), proveedor_id=supplier.id, cliente_id=tenant.id, ruc_emisor=metadata.ruc_emisor,
        sociedad=metadata.sociedad, serie=metadata.serie.upper(), correlativo=metadata.correlativo.lstrip('0') or '0',
        fecha_emision=metadata.fecha_emision, moneda=metadata.moneda.upper(), base_retencion=metadata.base_retencion,
        tasa_retencion=metadata.tasa_retencion, importe_retencion=metadata.importe_retencion,
        fecha_pago=metadata.fecha_pago, referencia_pago=metadata.referencia_pago,
        documento_sap=metadata.documento_sap, ejercicio_sap=metadata.ejercicio_sap,
        facturas_relacionadas=json.dumps([item.model_dump(mode='json') for item in metadata.facturas_relacionadas], ensure_ascii=False),
        estado_sunat=metadata.estado_sunat, motivo_estado=metadata.motivo_estado,
        evento_origen=metadata.evento_origen, sha256_metadatos=metadata_hash,
        nombre_xml=f'{metadata.serie.upper()}-{metadata.correlativo}.xml',
        xml=xml_bytes, sha256_xml=hashes['xml'], nombre_pdf=f'{metadata.serie.upper()}-{metadata.correlativo}.pdf',
        pdf=pdf_bytes, sha256_pdf=hashes['pdf'], nombre_cdr=f'{metadata.serie.upper()}-{metadata.correlativo}-CDR.xml' if cdr_bytes else None,
        cdr=cdr_bytes, sha256_cdr=hashes['cdr'],
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return {'resultado': 'recibido', **serializar(row)}


@router.post('/integracion-sap/retenciones/cdr', summary='Adjuntar el CDR recibido posteriormente de SUNAT')
async def adjuntar_cdr(
    ruc_emisor: str = Form(...), serie: str = Form(...), correlativo: str = Form(...),
    cdr: UploadFile = File(...), tenant: Cliente = Depends(autorizacion_sap), db: Session = Depends(get_db),
):
    if not re.fullmatch(r'\d{11}', ruc_emisor) or not db.query(Sociedad.id).filter_by(cliente_id=tenant.id,ruc=ruc_emisor,activo=True).first():
        error('El RUC emisor no está habilitado para esta integración.', 403)
    if not re.fullmatch(r'R[A-Za-z0-9]{3}', serie) or not re.fullmatch(r'\d{1,20}', correlativo):
        error('Serie o correlativo inválido.')
    row = db.query(CertificadoRetencion).filter_by(
        cliente_id=tenant.id, ruc_emisor=ruc_emisor, serie=serie.upper(), correlativo=correlativo.lstrip('0') or '0',
    ).first()
    if not row:
        error('Certificado no encontrado.', 404)
    content = leer_archivo(cdr, 'cdr')
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        error('El CDR XML no es válido.')
    if root.tag.rsplit('}', 1)[-1].lower() != 'applicationresponse':
        error('El adjunto CDR debe ser un XML UBL ApplicationResponse.')
    row.cdr = content
    row.nombre_cdr = f'{row.serie}-{row.correlativo}-CDR.xml'
    row.sha256_cdr = hashlib.sha256(content).hexdigest()
    db.commit()
    db.refresh(row)
    return {'resultado': 'cdr_recibido', **serializar(row)}


@router.patch('/integracion-sap/retenciones/estado', summary='Actualizar estado SUNAT de un CRE')
def actualizar_estado(payload: CambioEstado, tenant: Cliente = Depends(autorizacion_sap), db: Session = Depends(get_db)):
    if not db.query(Sociedad.id).filter_by(cliente_id=tenant.id,ruc=payload.ruc_emisor,activo=True).first():
        error('El RUC emisor no está habilitado para esta integración.', 403)
    row = db.query(CertificadoRetencion).filter_by(
        cliente_id=tenant.id, ruc_emisor=payload.ruc_emisor, serie=payload.serie.upper(),
        correlativo=payload.correlativo.lstrip('0') or '0',
    ).first()
    if not row:
        error('Certificado no encontrado.', 404)
    if row.estado_sunat == 'anulado' and payload.estado_sunat != 'anulado':
        error('Un certificado anulado no puede volver a un estado activo.', 409)
    if payload.estado_sunat == 'aceptado' and not row.cdr:
        error('No se puede marcar como aceptado sin haber recibido el CDR de SUNAT.', 409)
    row.estado_sunat = payload.estado_sunat
    row.motivo_estado = payload.motivo_estado
    db.commit()
    db.refresh(row)
    return serializar(row)


@router.get('/retenciones', summary='Listar certificados de retención del proveedor autenticado')
def listar_certificados(
    desde: date | None = None,
    hasta: date | None = None,
    estado: str | None = Query(default=None, pattern=r'^(pendiente|aceptado|rechazado|anulado)$'),
    sociedad: str | None = Query(default=None, pattern=r'^\d{11}$'),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_provider_user), db: Session = Depends(get_db),
):
    if user.get('rol') != 'proveedor':
        error('Esta consulta está disponible solo para proveedores.', 403)
    supplier = db.query(Proveedor).filter(Proveedor.ruc == user.get('ruc'), Proveedor.activo.is_(True)).first()
    if not supplier:
        error('Proveedor no encontrado.', 404)
    from tenancy import ids_sociedades_usuario
    query = db.query(CertificadoRetencion).filter(CertificadoRetencion.proveedor_id == supplier.id, CertificadoRetencion.cliente_id == user['cliente_id'], CertificadoRetencion.ruc_emisor.in_([s.ruc for s in db.query(Sociedad).filter(Sociedad.id.in_(ids_sociedades_usuario(db,user))).all()]))
    if desde:
        query = query.filter(CertificadoRetencion.fecha_emision >= desde)
    if hasta:
        query = query.filter(CertificadoRetencion.fecha_emision <= hasta)
    if estado:
        query = query.filter(CertificadoRetencion.estado_sunat == estado)
    if sociedad:
        query = query.filter(CertificadoRetencion.ruc_emisor == sociedad)
    total = query.count()
    rows = query.order_by(CertificadoRetencion.fecha_emision.desc(), CertificadoRetencion.serie.desc(), CertificadoRetencion.correlativo.desc()).offset(offset).limit(limit).all()
    return {'items': [serializar(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}


@router.get('/retenciones/{certificado_id}/archivos/{tipo}', summary='Descargar XML, PDF o CDR de un CRE')
def descargar_archivo(certificado_id: str, tipo: Literal['xml', 'pdf', 'cdr'], user: dict = Depends(get_current_provider_user), db: Session = Depends(get_db)):
    if user.get('rol') != 'proveedor':
        error('La descarga está disponible solo para proveedores.', 403)
    supplier = db.query(Proveedor).filter(Proveedor.ruc == user.get('ruc'), Proveedor.activo.is_(True)).first()
    row = db.query(CertificadoRetencion).filter(
        CertificadoRetencion.id == certificado_id,
        CertificadoRetencion.proveedor_id == (supplier.id if supplier else None),
        CertificadoRetencion.cliente_id == user['cliente_id'],
    ).first()
    if not row:
        error('Certificado no encontrado.', 404)
    if row.estado_sunat != 'aceptado':
        error('El documento todavía no está aceptado por SUNAT y no se puede descargar como certificado válido.', 409)
    content = getattr(row, tipo)
    filename = getattr(row, f'nombre_{tipo}')
    if not content or not filename:
        error('Este certificado no tiene el archivo solicitado.', 404)
    media_type = {'xml': 'application/xml', 'pdf': 'application/pdf', 'cdr': 'application/xml'}[tipo]
    etag = getattr(row, f'sha256_{tipo}')
    return Response(content, media_type=media_type, headers={
        'Content-Disposition': f'attachment; filename="{filename}"',
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store',
        'ETag': f'"{etag}"',
    })
