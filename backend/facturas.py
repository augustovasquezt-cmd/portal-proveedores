import re
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_provider_user
from models import Proveedor, OrdenCompra, Factura, FacturaRegistro, Sociedad, ProveedorCliente
from tenancy import sociedades_usuario, sociedad_autorizada

router = APIRouter(prefix='/facturas', tags=['facturas'])
MAX_FILE = 5 * 1024 * 1024
NS = {'cbc':'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2', 'cac':'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'}

def fail(message, status=400):
    raise HTTPException(status_code=status, detail=message)

def parse_xml(data, ruc):
    if not data or len(data) > MAX_FILE: fail('El XML debe tener como máximo 5 MB.')
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper() or b'\x00' in data:
        fail('XML no permitido. Utiliza un XML UBL en UTF-8 sin DTD ni entidades.')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        fail('El XML no es válido.')
    if root.tag != '{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice': fail('Se requiere un XML UBL de factura.')
    def value(path):
        return (root.findtext(path, default='', namespaces=NS) or '').strip()
    if value('cbc:InvoiceTypeCode') != '01': fail('Solo se admiten facturas (tipo 01).')
    emisor = value('cac:AccountingSupplierParty/cac:Party/cac:PartyIdentification/cbc:ID') or value('cac:AccountingSupplierParty/cbc:CustomerAssignedAccountID')
    if emisor != ruc: fail('El RUC emisor del XML no coincide con tu empresa.')
    numero = value('cbc:ID').upper()
    if not re.fullmatch(r'[A-Z0-9]{1,10}-[0-9]{1,10}', numero): fail('Serie o correlativo inválido.')
    serie, correlativo = numero.split('-')
    correlativo = str(int(correlativo))
    if int(correlativo) < 1: fail('El correlativo debe ser mayor que cero.')
    try:
        fecha = date.fromisoformat(value('cbc:IssueDate'))
        subtotal = Decimal(value('cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount') or value('cac:LegalMonetaryTotal/cbc:LineExtensionAmount'))
        impuestos = root.findall('cac:TaxTotal/cbc:TaxAmount', NS)
        igv = sum((Decimal(e.text or '') for e in impuestos), Decimal('0'))
        total = Decimal(value('cac:LegalMonetaryTotal/cbc:PayableAmount'))
        if not all(v.is_finite() and v >= 0 and v < Decimal('10000000000') and v == v.quantize(Decimal('.01')) for v in [subtotal, igv, total]): raise ValueError()
    except (ValueError, InvalidOperation): fail('Fecha o importes inválidos en el XML.')
    if fecha > date.today(): fail('La fecha de emisión no puede ser futura.')
    if total <= 0 or subtotal + igv != total: fail('El subtotal y los impuestos deben sumar el total; no se admiten anticipos o ajustes en este registro.')
    moneda = value('cbc:DocumentCurrencyCode')
    if moneda != 'PEN': fail('Las órdenes actuales están en soles. Solo se admite moneda PEN.')
    return dict(serie=serie, correlativo=correlativo, fecha_emision=fecha, moneda=moneda, monto_subtotal=subtotal, monto_igv=igv, monto_total=total)

def proveedor_actual(db, user, lock=False):
    query = db.query(Proveedor).filter(Proveedor.ruc == user['ruc'])
    if lock: query = query.with_for_update()
    p = query.first()
    if not p: fail('Proveedor no encontrado.', 404)
    return p

def sociedades_receptoras(user, db):
    return [{'id': row.id, 'ruc': row.ruc, 'razon_social': row.razon_social, 'codigo_sap': row.codigo_sap or ''} for row in sociedades_usuario(db, user)]

def validar_sociedad_receptora(ruc, user, db):
    receptor = str(ruc or '').strip()
    if not receptor:
        sociedades = sociedades_receptoras(user, db)
        receptor = sociedades[0]['ruc'] if len(sociedades) == 1 else ''
    society = db.query(Sociedad).filter(Sociedad.cliente_id == user['cliente_id'], Sociedad.ruc == receptor, Sociedad.activo.is_(True)).first() if receptor else None
    if not society or not any(row['id'] == society.id for row in sociedades_receptoras(user, db)):
        fail('Selecciona una sociedad receptora configurada para esta empresa.')
    return society

def obtener_sociedad_receptora(ruc, user, db):
    return validar_sociedad_receptora(ruc, user, db)

@router.get('/configuracion-registro')
def configuracion_registro(user: dict = Depends(get_current_provider_user), db: Session = Depends(get_db)):
    return {'ruc_proveedor': user['ruc'], 'cliente_id': user['cliente_id'], 'sociedades_receptoras': sociedades_receptoras(user, db)}

@router.post('/previsualizar')
async def previsualizar(xml: UploadFile = File(...), user: dict = Depends(get_current_provider_user), orden_compra_id: str = Form(''), multipedido: bool = Form(False), ruc_receptor: str = Form(''), db: Session = Depends(get_db)):
    from xml_review import review_xml
    p = proveedor_actual(db, user)
    orden = db.query(OrdenCompra).filter(OrdenCompra.id == orden_compra_id, OrdenCompra.proveedor_id == p.id, OrdenCompra.cliente_id == user['cliente_id']).first()
    society = validar_sociedad_receptora(ruc_receptor, user, db)
    return review_xml(await xml.read(MAX_FILE + 1), user['ruc'], None if multipedido else orden, db, multipedido=multipedido, ruc_receptor=society.ruc, cliente_id=user['cliente_id'])

@router.post('')
async def registrar_legacy(user: dict = Depends(get_current_provider_user)):
    fail('Utiliza el registro por posiciones del pedido.', 410)


def serialize(f, registro=None):
    return dict(id=f.id, serie=f.serie, correlativo=f.correlativo, monto_subtotal=float(f.monto_subtotal), monto_igv=float(f.monto_igv), monto_total=float(f.monto_total), estado=f.estado, creado_en=f.creado_en, orden_compra_id=f.orden_compra_id, fecha_emision=registro.fecha_emision if registro else None, moneda=registro.moneda if registro else 'PEN', ruc_receptor=registro.ruc_receptor if registro else None, adjuntos=bool(registro), tiene_xml=bool(registro and registro.xml), lineas=[dict(id=l.id, numero_linea=l.numero_linea, descripcion=l.descripcion, cantidad=float(l.cantidad), precio_unitario=float(l.precio_unitario), monto_subtotal=float(l.monto_subtotal), igv=float(l.igv), monto_total=float(l.monto_total)) for l in f.lineas])

@router.get('')
def listado(user: dict = Depends(get_current_provider_user), db: Session = Depends(get_db)):
    p = proveedor_actual(db, user)
    return [serialize(f) for f in db.query(Factura).filter(Factura.proveedor_id == p.id, Factura.cliente_id == user['cliente_id']).order_by(Factura.creado_en.desc()).all()]

@router.get('/{fid}')
def detalle(fid: str, user: dict = Depends(get_current_provider_user), db: Session = Depends(get_db)):
    p = proveedor_actual(db, user)
    f = db.query(Factura).filter(Factura.id == fid, Factura.proveedor_id == p.id, Factura.cliente_id == user['cliente_id']).first()
    if not f: fail('Factura no encontrada.',404)
    result = serialize(f, db.get(FacturaRegistro,fid))
    from models import FacturaEnvioSAP
    envio=db.get(FacturaEnvioSAP,fid)
    result['sap'] = dict(estado=envio.estado,documento=envio.documento_sap) if envio else None
    from models import FacturaAsignacion, OrdenPosicion, OrdenCompra
    from models import FacturaOrigen, DocumentoBaseLinea, DocumentoBase
    result['documentos_base'] = [dict(tipo=d.tipo,numero=d.numero,linea=l.numero,cantidad=float(a.cantidad)) for d,l,a in db.query(DocumentoBase,DocumentoBaseLinea,FacturaAsignacion).join(DocumentoBaseLinea,DocumentoBaseLinea.documento_id==DocumentoBase.id).join(FacturaOrigen,FacturaOrigen.documento_linea_id==DocumentoBaseLinea.id).join(FacturaAsignacion,FacturaAsignacion.id==FacturaOrigen.asignacion_id).filter(FacturaAsignacion.factura_id==fid).all()]
    result['posiciones'] = [dict(pedido=db.get(OrdenCompra,p.orden_id).numero, numero=p.numero, material=p.material, cantidad=float(a.cantidad), subtotal=float(a.subtotal), igv=float(a.igv), total=float(a.total)) for a,p in db.query(FacturaAsignacion,OrdenPosicion).join(OrdenPosicion,OrdenPosicion.id==FacturaAsignacion.posicion_id).filter(FacturaAsignacion.factura_id==fid).all()]
    return result

@router.get('/{fid}/archivos/{tipo}')
def archivo(fid: str, tipo: str, user: dict = Depends(get_current_provider_user), db: Session = Depends(get_db)):
    p = proveedor_actual(db,user)
    f = db.query(Factura).filter(Factura.id == fid, Factura.proveedor_id == p.id, Factura.cliente_id == user['cliente_id']).first()
    registro = db.get(FacturaRegistro,fid) if f else None
    if not registro or tipo not in ['xml','pdf'] or (tipo == 'xml' and not registro.xml): fail('Archivo no encontrado.',404)
    return Response(getattr(registro,tipo), media_type='application/pdf' if tipo=='pdf' else 'application/xml', headers={'Content-Disposition':f'attachment; filename="factura.{tipo}"','X-Content-Type-Options':'nosniff'})






