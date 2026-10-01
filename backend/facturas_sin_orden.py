"""Recepción de facturas de Cuentas por pagar que no tienen OC/OS."""
import csv
import io
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import func

from auth import get_current_ap_user
from database import get_db
from models import Factura, FacturaSinOrden, FacturaSinOrdenEvento, Proveedor, Sociedad
from tenancy import ids_sociedades_usuario

router = APIRouter(prefix='/cuentas-por-pagar/sin-oc', tags=['cuentas por pagar - facturas sin OC/OS'])
MAX_FILE = 5 * 1024 * 1024
MAX_BATCH = 30
MAX_BATCH_BYTES = 30 * 1024 * 1024
NS = {
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
}
CATEGORIAS = {'Servicios básicos', 'Servicios profesionales', 'Alquileres', 'Tributos y tasas', 'Otros'}


def _error(message, status=400):
    raise HTTPException(status_code=status, detail=message)


def _parse_xml(data: bytes):
    if not data or len(data) > MAX_FILE:
        _error('Cada XML debe tener contenido y no superar 5 MB.')
    upper = data.upper()
    if b'<!DOCTYPE' in upper or b'<!ENTITY' in upper or b'\x00' in data:
        _error('XML no permitido. Se rechazó DTD o entidades externas.')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        _error('El XML no es válido.')
    if root.tag != '{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice':
        _error('El archivo debe ser una factura electrónica UBL (Invoice).')

    def value(path):
        return (root.findtext(path, default='', namespaces=NS) or '').strip()

    supplier = root.find('cac:AccountingSupplierParty', NS)
    customer = root.find('cac:AccountingCustomerParty', NS)
    def party_value(party, path):
        if party is None:
            return ''
        return (party.findtext(path, default='', namespaces=NS) or '').strip()

    ruc = party_value(supplier, 'cac:Party/cac:PartyIdentification/cbc:ID') or party_value(supplier, 'cbc:CustomerAssignedAccountID')
    name = party_value(supplier, 'cac:Party/cac:PartyLegalEntity/cbc:RegistrationName') or party_value(supplier, 'cac:Party/cac:PartyTaxScheme/cbc:RegistrationName')
    receiver = party_value(customer, 'cac:Party/cac:PartyIdentification/cbc:ID') or party_value(customer, 'cbc:CustomerAssignedAccountID')
    identity = value('cbc:ID').upper()
    match = re.fullmatch(r'([A-Z0-9]{1,10})-([0-9]{1,20})', identity)
    if not re.fullmatch(r'\d{11}', ruc):
        _error('El XML debe incluir un RUC emisor de 11 dígitos.')
    if not name:
        _error('El XML no incluye la razón social del emisor.')
    if not match or int(match.group(2)) < 1:
        _error('La serie y el correlativo del XML no tienen un formato válido.')
    if value('cbc:InvoiceTypeCode') != '01':
        _error('Por ahora solo se admiten facturas electrónicas tipo 01.')
    try:
        issue_date = date.fromisoformat(value('cbc:IssueDate'))
        currency = value('cbc:DocumentCurrencyCode').upper()
        subtotal_text = value('cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount') or value('cac:LegalMonetaryTotal/cbc:LineExtensionAmount')
        subtotal = Decimal(subtotal_text or '0')
        tax_values = [Decimal(e.text or '0') for e in root.findall('cac:TaxTotal/cbc:TaxAmount', NS)]
        tax = sum(tax_values, Decimal('0'))
        total = Decimal(value('cac:LegalMonetaryTotal/cbc:PayableAmount'))
        amounts = [subtotal, tax, total]
        if not all(x.is_finite() and x >= 0 and x < Decimal('1000000000000') for x in amounts):
            raise ValueError()
    except (ValueError, InvalidOperation):
        _error('La fecha o los importes del XML no son válidos.')
    if issue_date > date.today():
        _error('La fecha de emisión no puede estar en el futuro.')
    if not re.fullmatch(r'[A-Z]{3}', currency):
        _error('El XML no incluye un código de moneda válido.')
    if total <= 0:
        _error('El total del comprobante debe ser mayor que cero.')
    warnings = []
    if subtotal + tax != total:
        warnings.append('El total no es igual a subtotal más impuestos; requiere revisión por cargos, descuentos u otros conceptos.')
    if not receiver:
        warnings.append('El XML no informa el RUC receptor.')
    return {
        'proveedor_ruc': ruc, 'proveedor_razon_social': name[:200], 'ruc_receptor': receiver,
        'serie': match.group(1), 'correlativo': str(int(match.group(2))), 'fecha_emision': issue_date,
        'moneda': currency, 'monto_subtotal': subtotal, 'monto_igv': tax, 'monto_total': total,
        'warnings': warnings,
    }


def _clean_name(filename: str):
    name = PurePath(filename or 'archivo').name
    name = re.sub(r'[^\w .()_-]', '_', name, flags=re.UNICODE).strip(' .')
    return (name or 'archivo')[:255]


def _safe_name(upload: UploadFile):
    return _clean_name(upload.filename or 'archivo')


async def _read(upload: UploadFile, kind: str):
    name = _safe_name(upload)
    expected = '.xml' if kind == 'xml' else '.pdf'
    if not name.lower().endswith(expected):
        _error(f'{name}: el archivo debe tener extensión {expected}.')
    data = await upload.read(MAX_FILE + 1)
    if not data or len(data) > MAX_FILE:
        _error(f'{name}: el tamaño máximo es 5 MB.')
    if kind == 'pdf' and not data.startswith(b'%PDF-'):
        _error(f'{name}: el contenido no parece ser un PDF válido.')
    return name, data


def _society(db, user, society_id):
    if society_id not in ids_sociedades_usuario(db, user):
        _error('No tienes acceso a la sociedad receptora seleccionada.', 403)
    return db.query(Sociedad).filter(Sociedad.id == society_id, Sociedad.cliente_id == user['cliente_id'], Sociedad.activo.is_(True)).first()


def _duplicate(db, client_id, ruc, serie, correlativo):
    in_manual_inbox = db.query(FacturaSinOrden.id).filter(
        FacturaSinOrden.cliente_id == client_id, FacturaSinOrden.proveedor_ruc == ruc,
        func.upper(FacturaSinOrden.serie) == serie.upper(), FacturaSinOrden.correlativo == correlativo,
    ).first()
    in_supplier_inbox = db.query(Factura.id).join(Proveedor, Proveedor.id == Factura.proveedor_id).filter(
        Factura.cliente_id == client_id, Proveedor.ruc == ruc,
        func.upper(Factura.serie) == serie.upper(), Factura.correlativo == correlativo,
    ).first()
    return bool(in_manual_inbox or in_supplier_inbox)


def _serialize(row):
    return {
        'id': row.id, 'proveedor_ruc': row.proveedor_ruc, 'proveedor_razon_social': row.proveedor_razon_social,
        'numero': f'{row.serie}-{row.correlativo}', 'serie': row.serie, 'correlativo': row.correlativo,
        'fecha_emision': row.fecha_emision.isoformat(), 'moneda': row.moneda, 'categoria': row.categoria,
        'descripcion': row.descripcion, 'centro_costo': row.centro_costo, 'cuenta_contable': row.cuenta_contable,
        'periodo_servicio': row.periodo_servicio, 'monto_subtotal': float(row.monto_subtotal), 'monto_igv': float(row.monto_igv),
        'monto_total': float(row.monto_total), 'origen': row.origen, 'estado': row.estado,
        'sociedad_id': row.sociedad_id, 'tiene_xml': bool(row.xml), 'tiene_pdf': bool(row.pdf),
        'nombre_xml': row.nombre_xml, 'nombre_pdf': row.nombre_pdf, 'observacion': row.observacion,
        'creado_en': row.creado_en.isoformat() if row.creado_en else None,
    }


@router.get('/sociedades')
def sociedades(user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    return [{'id': s.id, 'ruc': s.ruc, 'razon_social': s.razon_social} for s in db.query(Sociedad).filter(
        Sociedad.id.in_(ids_sociedades_usuario(db, user)), Sociedad.activo.is_(True),
    ).order_by(Sociedad.razon_social.asc()).all()]


@router.get('')
def listar(estado: str = 'todas', buscar: str = '', sociedad_id: str = '', limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    query = db.query(FacturaSinOrden).filter(FacturaSinOrden.cliente_id == user['cliente_id'], FacturaSinOrden.sociedad_id.in_(ids_sociedades_usuario(db, user)))
    if estado and estado != 'todas':
        if estado not in {'Pendiente de revisión', 'Aprobada para integración SAP', 'Rechazada'}:
            _error('Filtro de estado inválido.')
        query = query.filter(FacturaSinOrden.estado == estado)
    if sociedad_id:
        _society(db, user, sociedad_id)
        query = query.filter(FacturaSinOrden.sociedad_id == sociedad_id)
    if buscar.strip():
        term = f'%{buscar.strip()}%'
        query = query.filter((FacturaSinOrden.serie.ilike(term)) | (FacturaSinOrden.correlativo.ilike(term)) | (FacturaSinOrden.proveedor_ruc.ilike(term)) | (FacturaSinOrden.proveedor_razon_social.ilike(term)))
    total = query.count()
    rows = query.order_by(FacturaSinOrden.creado_en.desc()).offset(offset).limit(limit).all()
    return {'items': [_serialize(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}


@router.post('/lote', status_code=201)
async def cargar_lote(
    sociedad_id: str = Form(...), categoria: str = Form('Otros'), descripcion: str = Form(''),
    centro_costo: str = Form(''), cuenta_contable: str = Form(''), periodo_servicio: str = Form(''),
    xml_files: list[UploadFile] = File(...), pdf_files: list[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db),
):
    _society(db, user, sociedad_id)
    if categoria not in CATEGORIAS:
        _error('Selecciona una categoría válida.')
    if not xml_files or len(xml_files) > MAX_BATCH:
        _error(f'Selecciona entre 1 y {MAX_BATCH} XML por lote.')
    pdf_by_stem = {}
    errors = []
    if len(pdf_files) > MAX_BATCH:
        _error(f'Selecciona como máximo {MAX_BATCH} PDF por lote.')
    total_bytes = 0
    for pdf in pdf_files:
        try:
            name, data = await _read(pdf, 'pdf')
            total_bytes += len(data)
            if total_bytes > MAX_BATCH_BYTES:
                _error('El lote supera el tamaño total máximo de 30 MB.')
            stem = name.rsplit('.', 1)[0].casefold()
            if stem in pdf_by_stem:
                errors.append({'archivo': name, 'estado': 'error', 'detalle': 'Hay más de un PDF con el mismo nombre base.'})
            else:
                pdf_by_stem[stem] = (name, data)
        except HTTPException as exc:
            errors.append({'archivo': _safe_name(pdf), 'estado': 'error', 'detalle': exc.detail})
    items = []
    for upload in xml_files:
        name = _safe_name(upload)
        try:
            xml_name, xml_data = await _read(upload, 'xml')
            total_bytes += len(xml_data)
            if total_bytes > MAX_BATCH_BYTES:
                _error('El lote supera el tamaño total máximo de 30 MB.')
            data = _parse_xml(xml_data)
            if data['ruc_receptor'] and data['ruc_receptor'] != db.get(Sociedad, sociedad_id).ruc:
                _error('El RUC receptor del XML no coincide con la sociedad seleccionada.')
            if _duplicate(db, user['cliente_id'], data['proveedor_ruc'], data['serie'], data['correlativo']):
                _error('Ese comprobante ya está registrado para este cliente.')
            pdf = pdf_by_stem.pop(xml_name.rsplit('.', 1)[0].casefold(), None)
            row = FacturaSinOrden(
                cliente_id=user['cliente_id'], sociedad_id=sociedad_id, usuario_id=user['usuario_id'],
                proveedor_ruc=data['proveedor_ruc'], proveedor_razon_social=data['proveedor_razon_social'],
                serie=data['serie'], correlativo=data['correlativo'], fecha_emision=data['fecha_emision'],
                moneda=data['moneda'], categoria=categoria, descripcion=descripcion.strip()[:500] or None,
                centro_costo=centro_costo.strip()[:80] or None, cuenta_contable=cuenta_contable.strip()[:80] or None,
                periodo_servicio=periodo_servicio.strip()[:20] or None,
                monto_subtotal=data['monto_subtotal'], monto_igv=data['monto_igv'], monto_total=data['monto_total'],
                origen='xml', estado='Pendiente de revisión', nombre_xml=xml_name, xml=xml_data,
                nombre_pdf=pdf[0] if pdf else None, pdf=pdf[1] if pdf else None,
                observacion=' '.join(data['warnings']) or (None if pdf else 'Pendiente adjuntar PDF según política del cliente.'),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            items.append({'archivo': xml_name, 'estado': 'registrada', 'factura': _serialize(row), 'advertencias': data['warnings'] + ([] if pdf else ['No se adjuntó PDF.'])})
        except HTTPException as exc:
            db.rollback()
            items.append({'archivo': name, 'estado': 'error', 'detalle': exc.detail})
        except IntegrityError:
            db.rollback()
            items.append({'archivo': name, 'estado': 'error', 'detalle': 'El comprobante ya existe; no se creó un duplicado.'})
        except Exception:
            db.rollback()
            items.append({'archivo': name, 'estado': 'error', 'detalle': 'No se pudo procesar el archivo. Verifica el XML y vuelve a intentar.'})
    items.extend(errors)
    unmatched_pdfs = [{'archivo': filename, 'estado': 'aviso', 'detalle': 'No se encontró un XML con el mismo nombre base; no se vinculó.'} for filename, _ in pdf_by_stem.values()]
    items.extend(unmatched_pdfs)
    return {'registradas': sum(item['estado'] == 'registrada' for item in items), 'total_resultados': len(items), 'items': items}


@router.post('/manual', status_code=201)
async def cargar_manual(
    sociedad_id: str = Form(...), proveedor_ruc: str = Form(...), proveedor_razon_social: str = Form(...),
    serie: str = Form(...), correlativo: str = Form(...), fecha_emision: str = Form(...), moneda: str = Form('PEN'),
    categoria: str = Form('Servicios básicos'), descripcion: str = Form(''), centro_costo: str = Form(''),
    cuenta_contable: str = Form(''), periodo_servicio: str = Form(''), monto_subtotal: str = Form('0'),
    monto_igv: str = Form('0'), monto_total: str = Form(...), pdf: UploadFile = File(...),
    user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db),
):
    _society(db, user, sociedad_id)
    if categoria not in CATEGORIAS:
        _error('Selecciona una categoría válida.')
    if not re.fullmatch(r'\d{11}', proveedor_ruc.strip()):
        _error('El RUC del proveedor debe tener 11 dígitos.')
    if not proveedor_razon_social.strip() or len(proveedor_razon_social.strip()) > 200:
        _error('Indica una razón social válida del proveedor.')
    if not re.fullmatch(r'[A-Za-z0-9]{1,10}', serie.strip()) or not re.fullmatch(r'\d{1,20}', correlativo.strip()) or int(correlativo) < 1:
        _error('Revisa la serie y el correlativo del comprobante.')
    try:
        issued = date.fromisoformat(fecha_emision)
        subtotal = Decimal(monto_subtotal or '0')
        tax = Decimal(monto_igv or '0')
        total = Decimal(monto_total)
        if issued > date.today() or not all(x.is_finite() and x >= 0 for x in (subtotal, tax, total)) or total <= 0:
            raise ValueError()
    except (ValueError, InvalidOperation):
        _error('Revisa la fecha y los importes ingresados; el total debe ser mayor que cero.')
    currency = moneda.strip().upper()
    if not re.fullmatch(r'[A-Z]{3}', currency):
        _error('Indica un código de moneda de tres letras.')
    pdf_name, pdf_data = await _read(pdf, 'pdf')
    supplier_ruc = proveedor_ruc.strip()
    series = serie.strip().upper()
    number = str(int(correlativo))
    if _duplicate(db, user['cliente_id'], supplier_ruc, series, number):
        _error('Ese comprobante ya está registrado para este cliente.', 409)
    row = FacturaSinOrden(
        cliente_id=user['cliente_id'], sociedad_id=sociedad_id, usuario_id=user['usuario_id'],
        proveedor_ruc=supplier_ruc, proveedor_razon_social=proveedor_razon_social.strip(), serie=series,
        correlativo=number, fecha_emision=issued, moneda=currency, categoria=categoria,
        descripcion=descripcion.strip()[:500] or None, centro_costo=centro_costo.strip()[:80] or None,
        cuenta_contable=cuenta_contable.strip()[:80] or None, periodo_servicio=periodo_servicio.strip()[:20] or None,
        monto_subtotal=subtotal, monto_igv=tax, monto_total=total,
        origen='manual', estado='Pendiente de revisión', nombre_pdf=pdf_name, pdf=pdf_data,
        observacion='Registro manual sin XML; requiere cotejo con el PDF antes de aprobar.',
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _error('Ese comprobante ya está registrado para este cliente.', 409)
    db.refresh(row)
    return _serialize(row)


@router.post('/lote-pdf', status_code=201)
async def cargar_lote_pdf(
    sociedad_id: str = Form(...), manifiesto: UploadFile = File(...), pdf_files: list[UploadFile] = File(...),
    user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db),
):
    """Bulk manual receipt intake from a CSV manifest with exact PDF filenames."""
    _society(db, user, sociedad_id)
    manifest_name = _safe_name(manifiesto)
    if not manifest_name.lower().endswith('.csv'):
        _error('El manifiesto debe ser un archivo CSV.')
    raw = await manifiesto.read(1024 * 1024 + 1)
    if not raw or len(raw) > 1024 * 1024:
        _error('El manifiesto CSV no debe superar 1 MB.')
    try:
        text = raw.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
    except (UnicodeDecodeError, csv.Error):
        _error('No se pudo leer el CSV. Guárdalo como CSV UTF-8.')
    required = {'pdf_filename', 'proveedor_ruc', 'proveedor_razon_social', 'serie', 'correlativo', 'fecha_emision', 'moneda', 'categoria', 'monto_subtotal', 'monto_igv', 'monto_total'}
    if not reader.fieldnames or not required.issubset({field.strip() for field in reader.fieldnames if field}):
        _error('Al CSV le faltan columnas requeridas. Descarga la plantilla y conserva los encabezados.')
    try:
        rows = list(reader)
    except csv.Error:
        _error('El CSV tiene filas mal formadas. Revisa la plantilla y vuelve a cargarlo.')
    if not rows or len(rows) > MAX_BATCH:
        _error(f'El CSV debe incluir entre 1 y {MAX_BATCH} registros.')
    pdf_by_name = {}
    errors = []
    if len(pdf_files) > MAX_BATCH:
        _error(f'Selecciona como máximo {MAX_BATCH} PDF por lote.')
    total_bytes = 0
    for upload in pdf_files:
        try:
            name, data = await _read(upload, 'pdf')
            total_bytes += len(data)
            if total_bytes > MAX_BATCH_BYTES:
                _error('El lote supera el tamaño total máximo de 30 MB.')
            key = name.casefold()
            if key in pdf_by_name:
                errors.append({'archivo': name, 'estado': 'error', 'detalle': 'Nombre de PDF duplicado en el lote.'})
            else:
                pdf_by_name[key] = (name, data)
        except HTTPException as exc:
            errors.append({'archivo': _safe_name(upload), 'estado': 'error', 'detalle': exc.detail})

    results = []
    consumed_pdf_names = set()
    for index, raw_row in enumerate(rows, start=2):
        row = {(str(key or '').strip()): str(value or '').strip() for key, value in raw_row.items() if key is not None}
        pdf_name = _clean_name(row.get('pdf_filename') or '')
        try:
            supplier_ruc = row.get('proveedor_ruc', '')
            supplier_name = row.get('proveedor_razon_social', '')
            serie = row.get('serie', '').upper()
            correlativo_raw = row.get('correlativo', '')
            if not re.fullmatch(r'\d{11}', supplier_ruc) or not supplier_name or len(supplier_name) > 200:
                _error('Revisa el RUC y la razón social del proveedor.')
            if not re.fullmatch(r'[A-Za-z0-9]{1,10}', serie) or not re.fullmatch(r'\d{1,20}', correlativo_raw) or int(correlativo_raw) < 1:
                _error('Revisa la serie y el correlativo.')
            try:
                issued = date.fromisoformat(row.get('fecha_emision', ''))
                subtotal = Decimal(row.get('monto_subtotal', ''))
                tax = Decimal(row.get('monto_igv', ''))
                total = Decimal(row.get('monto_total', ''))
                if issued > date.today() or not all(x.is_finite() and x >= 0 for x in (subtotal, tax, total)) or total <= 0:
                    raise ValueError()
            except (ValueError, InvalidOperation):
                _error('Revisa fecha, subtotal, impuesto y total; el total debe ser mayor que cero.')
            currency = row.get('moneda', '').upper()
            category = row.get('categoria', '')
            if not re.fullmatch(r'[A-Z]{3}', currency):
                _error('La moneda debe ser un código de tres letras, por ejemplo PEN o USD.')
            if category not in CATEGORIAS:
                _error('La categoría no coincide con las opciones permitidas.')
            if not pdf_name.lower().endswith('.pdf') or pdf_name.casefold() not in pdf_by_name:
                _error('No se encontró el PDF indicado en la columna pdf_filename.')
            if pdf_name.casefold() in consumed_pdf_names:
                _error('Este PDF ya está vinculado a otra fila del manifiesto.')
            number = str(int(correlativo_raw))
            if _duplicate(db, user['cliente_id'], supplier_ruc, serie, number):
                _error('Ese comprobante ya está registrado para este cliente.')
            attached_name, attached_pdf = pdf_by_name[pdf_name.casefold()]
            record = FacturaSinOrden(
                cliente_id=user['cliente_id'], sociedad_id=sociedad_id, usuario_id=user['usuario_id'],
                proveedor_ruc=supplier_ruc, proveedor_razon_social=supplier_name[:200], serie=serie,
                correlativo=number, fecha_emision=issued, moneda=currency, categoria=category,
                descripcion=row.get('descripcion', '')[:500] or None,
                centro_costo=row.get('centro_costo', '')[:80] or None,
                cuenta_contable=row.get('cuenta_contable', '')[:80] or None,
                periodo_servicio=row.get('periodo_servicio', '')[:20] or None,
                monto_subtotal=subtotal, monto_igv=tax, monto_total=total, origen='manual_csv',
                estado='Pendiente de revisión', nombre_pdf=attached_name, pdf=attached_pdf,
                observacion='Registro manual desde CSV; revisar datos contra el PDF antes de aprobar.',
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            consumed_pdf_names.add(pdf_name.casefold())
            results.append({'fila': index, 'archivo': attached_name, 'estado': 'registrada', 'factura': _serialize(record)})
        except HTTPException as exc:
            db.rollback()
            results.append({'fila': index, 'archivo': row.get('pdf_filename', ''), 'estado': 'error', 'detalle': exc.detail})
        except IntegrityError:
            db.rollback()
            results.append({'fila': index, 'archivo': row.get('pdf_filename', ''), 'estado': 'error', 'detalle': 'El comprobante ya existe; no se creó un duplicado.'})
        except Exception:
            db.rollback()
            results.append({'fila': index, 'archivo': row.get('pdf_filename', ''), 'estado': 'error', 'detalle': 'No se pudo procesar esta fila; revisa el CSV y el PDF.'})
    for name in pdf_by_name:
        if name not in consumed_pdf_names:
            errors.append({'archivo': pdf_by_name[name][0], 'estado': 'aviso', 'detalle': 'PDF sin una fila registrada que lo vincule.'})
    results.extend(errors)
    return {'registradas': sum(result['estado'] == 'registrada' for result in results), 'total_resultados': len(results), 'items': results}


@router.get('/{invoice_id}')
def detalle(invoice_id: str, user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    row = db.query(FacturaSinOrden).filter(
        FacturaSinOrden.id == invoice_id, FacturaSinOrden.cliente_id == user['cliente_id'],
        FacturaSinOrden.sociedad_id.in_(ids_sociedades_usuario(db, user)),
    ).first()
    if not row:
        _error('Comprobante no encontrado.', 404)
    result = _serialize(row)
    result['historial'] = [
        {'accion': event.accion, 'estado_anterior': event.estado_anterior, 'estado_nuevo': event.estado_nuevo,
         'comentario': event.comentario, 'actor': event.actor_nombre, 'fecha': event.creado_en.isoformat() if event.creado_en else None}
        for event in db.query(FacturaSinOrdenEvento).filter(FacturaSinOrdenEvento.factura_id == invoice_id, FacturaSinOrdenEvento.cliente_id == user['cliente_id']).order_by(FacturaSinOrdenEvento.creado_en.asc()).all()
    ]
    return result


@router.get('/{invoice_id}/archivos/{kind}')
def archivo(invoice_id: str, kind: str, user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    if kind not in {'xml', 'pdf'}:
        _error('Archivo no encontrado.', 404)
    row = db.query(FacturaSinOrden).filter(
        FacturaSinOrden.id == invoice_id, FacturaSinOrden.cliente_id == user['cliente_id'],
        FacturaSinOrden.sociedad_id.in_(ids_sociedades_usuario(db, user)),
    ).first()
    content = getattr(row, kind, None) if row else None
    if not content:
        _error('Archivo no encontrado.', 404)
    return Response(content, media_type='application/pdf' if kind == 'pdf' else 'application/xml', headers={
        'Content-Disposition': f'inline; filename="{getattr(row, f"nombre_{kind}") or f"factura.{kind}"}"',
        'X-Content-Type-Options': 'nosniff',
    })


@router.post('/{invoice_id}/acciones')
def accion(invoice_id: str, payload: dict, user: dict = Depends(get_current_ap_user), db: Session = Depends(get_db)):
    row = db.query(FacturaSinOrden).filter(
        FacturaSinOrden.id == invoice_id, FacturaSinOrden.cliente_id == user['cliente_id'],
        FacturaSinOrden.sociedad_id.in_(ids_sociedades_usuario(db, user)),
    ).first()
    if not row:
        _error('Comprobante no encontrado.', 404)
    action = str(payload.get('accion', '')).strip().lower()
    comment = str(payload.get('comentario', '')).strip()
    previous = row.estado
    if action == 'aprobar':
        if previous != 'Pendiente de revisión':
            _error('Solo un comprobante pendiente puede aprobarse.', 409)
        row.estado = 'Aprobada para integración SAP'
    elif action == 'rechazar':
        if previous != 'Pendiente de revisión':
            _error('Solo un comprobante pendiente puede rechazarse.', 409)
        if len(comment) < 8 or len(comment) > 2000:
            _error('Indica un motivo de rechazo claro (8 a 2000 caracteres).')
        row.estado = 'Rechazada'
    elif action == 'reabrir':
        if previous != 'Rechazada':
            _error('Solo un comprobante rechazado puede reabrirse.', 409)
        row.estado = 'Pendiente de revisión'
    else:
        _error('Acción inválida.')
    row.observacion = comment or row.observacion
    db.add(FacturaSinOrdenEvento(
        factura_id=row.id, cliente_id=user['cliente_id'], actor_id=user['usuario_id'],
        actor_nombre=user.get('nombre') or user.get('usuario') or 'Cuentas por pagar',
        accion=action, estado_anterior=previous, estado_nuevo=row.estado, comentario=comment or None,
    ))
    db.commit()
    db.refresh(row)
    return _serialize(row)
