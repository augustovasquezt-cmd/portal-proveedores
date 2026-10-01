"""Carga por Excel de facturas de Cuentas por pagar contra OC/OS."""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import PurePosixPath
import re
import zipfile
import xml.etree.ElementTree as ET
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import get_current_ap_user
from database import get_db
from facturas import MAX_FILE, parse_xml, proveedor_actual
from facturas_sin_orden import _read, _safe_name, _society
from models import (
    DocumentoBase, DocumentoBaseLinea, Factura, FacturaAsignacion,
    FacturaLinea, FacturaRegistro, OrdenCompra, OrdenPosicion,
    Proveedor, ProveedorCliente, Sociedad,
)
from posiciones import EXCLUIDOS, posiciones, validar

router = APIRouter(prefix='/cuentas-por-pagar/carga-masiva-oc', tags=['cuentas por pagar - carga masiva con OC/OS'])
MAX_XLSX = 2 * 1024 * 1024
MAX_INVOICES = 100
MAX_LINES = 1000
MAX_BATCH_BYTES = 30 * 1024 * 1024
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
NS_MAIN = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
NS_REL = {'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
NS_PACKAGE_REL = {'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}

INVOICE_HEADERS = [
    'clave_factura', 'ruc_proveedor', 'razon_social_proveedor', 'ruc_sociedad',
    'serie', 'correlativo', 'fecha_emision', 'moneda', 'subtotal', 'igv',
    'total', 'archivo_xml', 'archivo_pdf',
]
POSITION_HEADERS = [
    'clave_factura', 'pedido', 'posicion', 'cantidad', 'linea_xml',
    'tipo_documento', 'numero_documento', 'posicion_documento',
]
SHEET_HEADERS = {'Facturas': INVOICE_HEADERS, 'Posiciones': POSITION_HEADERS}
DOCUMENT_STATES = {'mercancia': 'recibido', 'servicio': 'aceptado', 'guia': 'despachado'}


def _fail(message: str, status: int = 400):
    raise HTTPException(status_code=status, detail=message)


def _column_number(reference: str) -> int:
    letters = re.match(r'[A-Z]+', reference.upper())
    if not letters:
        raise ValueError('Referencia de celda inválida.')
    value = 0
    for char in letters.group(0):
        value = value * 26 + ord(char) - 64
    return value - 1


def _workbook_rows(data: bytes) -> dict[str, list[dict[str, str]]]:
    if not data or len(data) > MAX_XLSX:
        _fail('El Excel debe tener contenido y no superar 2 MB.')
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except (zipfile.BadZipFile, OSError):
        _fail('El archivo no es un Excel .xlsx válido.')
    with archive:
        infos = archive.infolist()
        if len(infos) > 100 or sum(item.file_size for item in infos) > 20 * 1024 * 1024:
            _fail('El Excel excede los límites de seguridad de lectura.')
        if any(item.file_size > 10 * 1024 * 1024 or PurePosixPath(item.filename).is_absolute() or '..' in PurePosixPath(item.filename).parts for item in infos):
            _fail('El Excel contiene componentes no permitidos.')
        names = set(archive.namelist())
        if 'xl/vbaProject.bin' in names or 'xl/externalLinks/externalLink1.xml' in names:
            _fail('No se admiten macros ni vínculos externos en el Excel.')
        try:
            workbook = ET.fromstring(archive.read('xl/workbook.xml'))
            relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        except (KeyError, ET.ParseError):
            _fail('El Excel no contiene un libro válido.')
        rel_targets = {item.get('Id'): item.get('Target', '') for item in relationships.findall('p:Relationship', NS_PACKAGE_REL)}
        sheets = {}
        for sheet in workbook.findall('m:sheets/m:sheet', NS_MAIN):
            name = sheet.get('name', '')
            relationship_id = sheet.get(f"{{{NS_REL['r']}}}id")
            target = rel_targets.get(relationship_id, '')
            if not name or not target or target.startswith(('http:', 'https:', '//')):
                continue
            path = str(PurePosixPath('xl') / target)
            normalized = str(PurePosixPath(path))
            if normalized.startswith('../') or normalized not in names:
                continue
            sheets[name.casefold()] = normalized
        shared_strings = []
        if 'xl/sharedStrings.xml' in names:
            try:
                root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
                shared_strings = [''.join(node.itertext()) for node in root.findall('m:si', NS_MAIN)]
            except ET.ParseError:
                _fail('La tabla de textos del Excel está dañada.')
        result = {}
        for expected_name, expected_headers in SHEET_HEADERS.items():
            sheet_path = sheets.get(expected_name.casefold())
            if not sheet_path:
                _fail(f'Falta la hoja "{expected_name}". Usa la plantilla oficial.')
            try:
                root = ET.fromstring(archive.read(sheet_path))
            except ET.ParseError:
                _fail(f'La hoja "{expected_name}" no se puede leer.')
            rows = root.findall('m:sheetData/m:row', NS_MAIN)
            if not rows:
                _fail(f'La hoja "{expected_name}" está vacía.')
            values = []
            for row in rows:
                row_values = {}
                for cell in row.findall('m:c', NS_MAIN):
                    reference = cell.get('r', '')
                    if cell.find('m:f', NS_MAIN) is not None:
                        _fail('No uses fórmulas; pega valores en las hojas de carga.')
                    cell_type = cell.get('t')
                    if cell_type == 'inlineStr':
                        value = ''.join(cell.find('m:is', NS_MAIN).itertext()) if cell.find('m:is', NS_MAIN) is not None else ''
                    else:
                        value_node = cell.find('m:v', NS_MAIN)
                        value = value_node.text if value_node is not None else ''
                        if cell_type == 's' and value:
                            try:
                                value = shared_strings[int(value)]
                            except (ValueError, IndexError):
                                _fail('El Excel contiene una referencia de texto inválida.')
                    row_values[_column_number(reference)] = (value or '').strip()
                values.append(row_values)
                if len(values) > MAX_LINES + 1:
                    _fail(f'La hoja "{expected_name}" supera el máximo de filas permitido.')
            header_row = values[0]
            headers = [header_row.get(index, '').strip().casefold() for index in range(len(expected_headers))]
            if headers != expected_headers:
                _fail(f'Los encabezados de "{expected_name}" no coinciden con la plantilla oficial.')
            records = []
            for row in values[1:]:
                record = {header: row.get(index, '').strip() for index, header in enumerate(expected_headers)}
                if any(record.values()):
                    records.append(record)
            result[expected_name] = records
    return result


def _cell(ref: str, value: str) -> ET.Element:
    cell = ET.Element('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c', {'r': ref, 't': 'inlineStr'})
    inline = ET.SubElement(cell, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is')
    text = ET.SubElement(inline, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
    text.text = value
    return cell


def _column_name(number: int) -> str:
    result = ''
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def build_template() -> bytes:
    ET.register_namespace('', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main')
    ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
    ET.register_namespace('', 'http://schemas.openxmlformats.org/package/2006/relationships')
    sheet_data = [
        ("Instrucciones", [
            ['Carga masiva de facturas con OC/OS'],
            ['1. Una fila por factura en Facturas; usa una clave_factura única, por ejemplo F001-123.'],
            ['2. Una o varias filas por factura en Posiciones. Puedes combinar pedidos si pertenecen al mismo proveedor y sociedad.'],
            ['3. La cantidad y el importe se validan contra el saldo vigente de cada posición. No ingreses el precio: se toma de la OC.'],
            ['4. PDF obligatorio por factura; XML opcional. El nombre debe coincidir exactamente con archivo_pdf / archivo_xml.'],
            ['5. Si incluyes XML, completa linea_xml con el número de línea UBL, empezando en 1, para cada fila de Posiciones.'],
            ['6. Para servicios indica tipo_documento=servicio, numero_documento y posicion_documento de la hoja de entrada aceptada.'],
            ['7. Para material, puedes dejar documento vacío o indicar mercancia / guia y su número y posición.'],
            ['8. Usa fecha YYYY-MM-DD, moneda PEN y valores numéricos sin símbolo de moneda. No uses fórmulas.'],
            ['9. Primero carga y valida; después registra las facturas válidas como Pendiente de revisión. No se contabilizan en SAP.'],
        ]),
        ('Facturas', [INVOICE_HEADERS]),
        ('Posiciones', [POSITION_HEADERS]),
    ]
    content_types = ET.Element('{http://schemas.openxmlformats.org/package/2006/content-types}Types')
    ET.SubElement(content_types, '{http://schemas.openxmlformats.org/package/2006/content-types}Default', {'Extension': 'rels', 'ContentType': 'application/vnd.openxmlformats-package.relationships+xml'})
    ET.SubElement(content_types, '{http://schemas.openxmlformats.org/package/2006/content-types}Default', {'Extension': 'xml', 'ContentType': 'application/xml'})
    ET.SubElement(content_types, '{http://schemas.openxmlformats.org/package/2006/content-types}Override', {'PartName': '/xl/workbook.xml', 'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'})
    for index in range(1, len(sheet_data) + 1):
        ET.SubElement(content_types, '{http://schemas.openxmlformats.org/package/2006/content-types}Override', {'PartName': f'/xl/worksheets/sheet{index}.xml', 'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
    root_rels = ET.Element('{http://schemas.openxmlformats.org/package/2006/relationships}Relationships')
    ET.SubElement(root_rels, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship', {'Id': 'rId1', 'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument', 'Target': 'xl/workbook.xml'})
    workbook = ET.Element('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook')
    workbook_sheets = ET.SubElement(workbook, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets')
    wb_rels = ET.Element('{http://schemas.openxmlformats.org/package/2006/relationships}Relationships')
    sheet_bytes = []
    for index, (name, rows) in enumerate(sheet_data, 1):
        ET.SubElement(workbook_sheets, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet', {'name': name, 'sheetId': str(index), '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id': f'rId{index}'})
        ET.SubElement(wb_rels, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship', {'Id': f'rId{index}', 'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet', 'Target': f'worksheets/sheet{index}.xml'})
        sheet = ET.Element('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}worksheet')
        data = ET.SubElement(sheet, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData')
        for row_index, values in enumerate(rows, 1):
            row = ET.SubElement(data, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row', {'r': str(row_index)})
            for col_index, value in enumerate(values, 1):
                row.append(_cell(f'{_column_name(col_index)}{row_index}', str(value)))
        sheet_bytes.append(ET.tostring(sheet, encoding='utf-8', xml_declaration=True))
    output = BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as workbook_zip:
        workbook_zip.writestr('[Content_Types].xml', ET.tostring(content_types, encoding='utf-8', xml_declaration=True))
        workbook_zip.writestr('_rels/.rels', ET.tostring(root_rels, encoding='utf-8', xml_declaration=True))
        workbook_zip.writestr('xl/workbook.xml', ET.tostring(workbook, encoding='utf-8', xml_declaration=True))
        workbook_zip.writestr('xl/_rels/workbook.xml.rels', ET.tostring(wb_rels, encoding='utf-8', xml_declaration=True))
        for index, payload in enumerate(sheet_bytes, 1):
            workbook_zip.writestr(f'xl/worksheets/sheet{index}.xml', payload)
    return output.getvalue()


def _money(value: str, label: str) -> Decimal:
    try:
        result = Decimal(value)
        if not result.is_finite() or result < 0 or result >= Decimal('10000000000') or result != result.quantize(Decimal('.01')):
            raise ValueError()
        return result
    except (InvalidOperation, ValueError):
        _fail(f'{label}: importe inválido; usa dos decimales como máximo.')


def _issue_date(value: str) -> date:
    try:
        try:
            result = date.fromisoformat(value)
        except ValueError:
            # Excel may serialize a date cell as days since 1899-12-30.
            serial = Decimal(value)
            if not serial.is_finite() or serial < 1 or serial > 100000:
                raise ValueError()
            result = date(1899, 12, 30) + timedelta(days=int(serial))
        if result > date.today():
            raise ValueError()
        return result
    except (InvalidOperation, ValueError):
        _fail('La fecha de emisión debe ser válida y no futura (YYYY-MM-DD).')


def _normal_position(value: str) -> str:
    trimmed = value.strip()
    return trimmed.lstrip('0') or '0'


async def _attachments(files: list[UploadFile], kind: str) -> dict[str, tuple[str, bytes]]:
    result = {}
    total = 0
    for upload in files or []:
        name, data = await _read(upload, kind)
        total += len(data)
        if total > MAX_BATCH_BYTES:
            _fail('Los adjuntos superan 30 MB en total.')
        key = name.casefold()
        if key in result:
            _fail(f'El adjunto "{name}" está repetido.')
        if kind == 'pdf' and b'%%EOF' not in data[-1024:]:
            _fail(f'{name}: el PDF está incompleto o dañado.')
        result[key] = (name, data)
    return result


def _header_decimal(data: dict, field: str) -> Decimal:
    return _money(data[field], field)


def _validate_group(db: Session, user: dict, header: dict, line_rows: list[dict], xml_by_name: dict, pdf_by_name: dict, *, save: bool):
    key = header['clave_factura'].strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', key):
        _fail('La clave_factura solo admite letras, números, punto, guion y guion bajo.')
    ruc = header['ruc_proveedor'].strip()
    if not re.fullmatch(r'\d{11}', ruc):
        _fail('El RUC del proveedor debe tener 11 dígitos.')
    supplier = db.query(Proveedor).filter(Proveedor.ruc == ruc, Proveedor.activo.is_(True)).with_for_update().first()
    if not supplier:
        _fail(f'Proveedor {ruc} no encontrado o inactivo.', 404)
    membership = db.query(ProveedorCliente).filter_by(proveedor_id=supplier.id, cliente_id=user['cliente_id'], activo=True).first()
    if not membership:
        _fail(f'El proveedor {ruc} no está habilitado para este cliente.', 403)
    society = db.query(Sociedad).filter_by(cliente_id=user['cliente_id'], ruc=header['ruc_sociedad'].strip(), activo=True).first()
    if not society:
        _fail('El RUC de sociedad no pertenece a una sociedad activa del cliente.')
    society = _society(db, user, society.id)
    if not re.fullmatch(r'[A-Za-z0-9]{1,10}', header['serie'].strip()):
        _fail('La serie de la factura no es válida.')
    if not re.fullmatch(r'\d{1,10}', header['correlativo'].strip()) or int(header['correlativo']) < 1:
        _fail('El correlativo de la factura no es válido.')
    serie = header['serie'].strip().upper()
    correlativo = str(int(header['correlativo']))
    issue_date = _issue_date(header['fecha_emision'])
    currency = header['moneda'].strip().upper()
    if currency != 'PEN':
        _fail('Las órdenes actuales están en soles; solo se admite PEN.')
    amounts = {name: _header_decimal(header, field) for name, field in [('monto_subtotal', 'subtotal'), ('monto_igv', 'igv'), ('monto_total', 'total')]}
    if amounts['monto_total'] <= 0:
        _fail('El total de la factura debe ser mayor que cero.')
    if not line_rows:
        _fail('La factura debe tener al menos una posición en la hoja Posiciones.')
    if not header['archivo_pdf'].strip():
        _fail('El PDF de la factura es obligatorio.')
    pdf_file = pdf_by_name.get(header['archivo_pdf'].strip().casefold())
    if not pdf_file:
        _fail(f'No se adjuntó el PDF indicado: {header["archivo_pdf"]}.')
    xml_data = b''
    xml_name = ''
    revision = None
    if header['archivo_xml'].strip():
        xml_file = xml_by_name.get(header['archivo_xml'].strip().casefold())
        if not xml_file:
            _fail(f'No se adjuntó el XML indicado: {header["archivo_xml"]}.')
        xml_name, xml_data = xml_file
        invoice_data = parse_xml(xml_data, ruc)
        if invoice_data['serie'] != serie or invoice_data['correlativo'] != correlativo or invoice_data['fecha_emision'] != issue_date or invoice_data['moneda'] != currency:
            _fail('La serie, correlativo, fecha o moneda del Excel no coincide con el XML.')
        for field in ('monto_subtotal', 'monto_igv', 'monto_total'):
            if invoice_data[field] != amounts[field]:
                _fail('Los importes del Excel no coinciden con el XML.')
        if invoice_data['ruc_receptor'] and invoice_data['ruc_receptor'] != society.ruc:
            _fail('El RUC receptor del XML no coincide con la sociedad seleccionada.')
        from xml_review import review_xml
        revision = review_xml(xml_data, ruc, None, db, multipedido=True, ruc_receptor=society.ruc, cliente_id=user['cliente_id'])
        errors = [check['detalle'] for check in revision['validaciones'] if check['estado'] == 'error']
        if errors:
            _fail(' '.join(errors))
    if db.query(Factura.id).filter(
        Factura.cliente_id == user['cliente_id'], Factura.proveedor_id == supplier.id,
        Factura.serie.ilike(serie), Factura.correlativo == correlativo,
    ).first():
        _fail('La factura ya está registrada para este cliente.', 409)

    orders_by_number = {}
    assignments = []
    for line_number, row in enumerate(line_rows, 1):
        if row['clave_factura'].strip().casefold() != key.casefold():
            continue
        order_number = row['pedido'].strip()
        if not order_number or not row['posicion'].strip():
            _fail(f'Posiciones, fila {line_number + 1}: pedido y posición son obligatorios.')
        if order_number not in orders_by_number:
            order = db.query(OrdenCompra).filter(
                OrdenCompra.numero == order_number, OrdenCompra.proveedor_id == supplier.id,
                OrdenCompra.cliente_id == user['cliente_id'],
            ).with_for_update().first()
            if not order:
                _fail(f'No se encontró el pedido {order_number} para el proveedor {ruc}.', 404)
            if order.sociedad_id != society.id:
                _fail(f'El pedido {order_number} pertenece a otra sociedad receptora.')
            if (order.estado or '').strip().casefold() in EXCLUIDOS:
                _fail(f'El pedido {order_number} está cancelado o anulado.')
            orders_by_number[order_number] = order
        order = orders_by_number[order_number]
        state = posiciones(db, order)
        if state['bloqueo']:
            _fail(f'{order_number}: {state["bloqueo"]}')
        position = next((item for item in state['posiciones'] if _normal_position(item['numero']) == _normal_position(row['posicion'])), None)
        if not position:
            _fail(f'No existe la posición {row["posicion"]} en el pedido {order_number}.')
        try:
            quantity = Decimal(row['cantidad'])
            if not quantity.is_finite() or quantity <= 0 or quantity != quantity.quantize(Decimal('.0001')):
                raise ValueError()
        except (InvalidOperation, ValueError):
            _fail(f'Cantidad inválida en {order_number} / posición {row["posicion"]}.')
        document_line_id = None
        document_type = row['tipo_documento'].strip().casefold()
        document_number = row['numero_documento'].strip()
        document_position = row['posicion_documento'].strip()
        if document_type or document_number or document_position:
            if document_type not in DOCUMENT_STATES or not document_number or not document_position:
                _fail('Completa tipo_documento, numero_documento y posicion_documento para la referencia.')
            document = db.query(DocumentoBase).filter(
                DocumentoBase.proveedor_id == supplier.id, DocumentoBase.cliente_id == user['cliente_id'],
                DocumentoBase.tipo == document_type, DocumentoBase.numero == document_number,
                DocumentoBase.estado == DOCUMENT_STATES[document_type],
            ).first()
            if not document:
                _fail(f'No se encontró un documento {document_type} vigente con número {document_number}.')
            doc_line = db.query(DocumentoBaseLinea).filter(
                DocumentoBaseLinea.documento_id == document.id,
                DocumentoBaseLinea.posicion_id == position['id'],
            ).all()
            doc_line = next((line for line in doc_line if _normal_position(line.numero) == _normal_position(document_position)), None)
            if not doc_line:
                _fail(f'La posición de documento {document_position} no corresponde al pedido {order_number} / {row["posicion"]}.')
            document_line_id = doc_line.id
        if position['tipo'] == 'servicio' and (document_type != 'servicio' or not document_line_id):
            _fail(f'La posición de servicio {order_number} / {row["posicion"]} requiere una hoja de entrada aceptada.')
        xml_line = None
        if revision is not None:
            try:
                xml_line = int(row['linea_xml']) - 1
            except (ValueError, TypeError):
                _fail('Si adjuntas XML, completa linea_xml en todas las posiciones (numeración desde 1).')
            if xml_line < 0:
                _fail('linea_xml debe ser un número desde 1.')
        elif row['linea_xml'].strip():
            _fail('Deja linea_xml vacío si no adjuntas un XML.')
        assignments.append({
            'posicion_id': position['id'], 'documento_linea_id': document_line_id,
            'cantidad': str(quantity), 'linea_xml': xml_line,
        })
    if not assignments:
        _fail('No hay posiciones asignadas a esta factura.')
    if revision is not None and len(assignments) != len(revision['lineas']):
        _fail('El XML y la hoja Posiciones deben tener el mismo número de líneas.')
    from documentos_base import validar_origenes
    validar_origenes(db, assignments, supplier.id, user['cliente_id'])
    pedidos = sorted(orders_by_number.values(), key=lambda order: order.id)
    for order in pedidos:
        order = db.query(OrdenCompra).filter(OrdenCompra.id == order.id).with_for_update().one()
    datos = {
        'serie': serie, 'correlativo': correlativo, 'fecha_emision': issue_date, 'moneda': currency,
        'monto_subtotal': amounts['monto_subtotal'], 'monto_igv': amounts['monto_igv'], 'monto_total': amounts['monto_total'],
    }
    lines = validar(db, pedidos, datos, assignments, revision)
    from saldos import importes_por_orden
    order_amounts = importes_por_orden(db, supplier.id, user['cliente_id'])
    for order in pedidos:
        applied = sum((line['total'] for line in lines if line['orden_id'] == order.id), Decimal(0))
        if applied > order.monto_total - Decimal(str(order_amounts.get(order.id, 0))):
            _fail(f'El importe supera el saldo pendiente del pedido {order.numero}.', 409)
    if not save:
        return {
            'clave_factura': key, 'estado': 'validada', 'numero': f'{serie}-{correlativo}',
            'proveedor': f'{ruc} · {supplier.razon_social}', 'total': str(amounts['monto_total']),
            'pedidos': [order.numero for order in pedidos], 'posiciones': len(lines),
            'documentos': [name for name in (header['archivo_xml'].strip(), header['archivo_pdf'].strip()) if name],
        }
    factura_id = str(uuid4())
    invoice = Factura(
        id=factura_id, proveedor_id=supplier.id, cliente_id=user['cliente_id'], sociedad_id=society.id,
        serie=serie, correlativo=correlativo,
        orden_compra_id=pedidos[0].id if len(pedidos) == 1 else None,
        estado='Pendiente de revisión', monto_subtotal=amounts['monto_subtotal'],
        monto_igv=amounts['monto_igv'], monto_total=amounts['monto_total'],
    )
    db.add(invoice)
    db.flush()
    pdf_name, pdf_data = pdf_file
    db.add(FacturaRegistro(
        factura_id=factura_id, fecha_emision=issue_date, moneda=currency,
        ruc_receptor=society.ruc, sociedad_id=society.id, xml=xml_data,
        pdf=pdf_data,
    ))
    for index, line in enumerate(lines, 1):
        allocation = FacturaAsignacion(
            factura_id=factura_id, **{name: line[name] for name in ('posicion_id', 'linea_xml', 'cantidad', 'subtotal', 'igv', 'total')},
        )
        db.add(allocation)
        db.flush()
        if line.get('documento_linea_id'):
            from models import FacturaOrigen
            db.add(FacturaOrigen(asignacion_id=allocation.id, documento_linea_id=line['documento_linea_id']))
        db.add(FacturaLinea(
            factura_id=factura_id, numero_linea=index, descripcion=line['descripcion'],
            cantidad=line['cantidad'], precio_unitario=line['precio'], monto_subtotal=line['subtotal'],
            igv=line['igv'], monto_total=line['total'],
            codigo_producto=line['codigo_producto'],
        ))
    from sap_integracion import preparar
    preparar(db, invoice, datos, lines, supplier.ruc, society.ruc, society)
    return {
        'clave_factura': key, 'estado': 'registrada', 'id': factura_id,
        'numero': f'{serie}-{correlativo}', 'proveedor': f'{ruc} · {supplier.razon_social}',
        'total': str(amounts['monto_total']), 'pedidos': [order.numero for order in pedidos],
        'posiciones': len(lines), 'documentos': [name for name in (xml_name, pdf_name) if name],
    }


async def _run_batch(excel: UploadFile, xml_files: list[UploadFile], pdf_files: list[UploadFile], user: dict, db: Session, *, persist: bool):
    filename = _safe_name(excel)
    if not filename.lower().endswith('.xlsx'):
        _fail('Sube el archivo Excel en formato .xlsx; no se admiten .xls ni macros .xlsm.')
    workbook_bytes = await excel.read(MAX_XLSX + 1)
    sheets = _workbook_rows(workbook_bytes)
    headers = sheets['Facturas']
    position_rows = sheets['Posiciones']
    if not headers:
        _fail('La hoja Facturas no tiene filas para importar.')
    if len(headers) > MAX_INVOICES:
        _fail(f'El máximo es {MAX_INVOICES} facturas por lote.')
    if not position_rows or len(position_rows) > MAX_LINES:
        _fail(f'El lote requiere posiciones y admite hasta {MAX_LINES} filas en Posiciones.')
    lines_by_key = {}
    for row in position_rows:
        key = row['clave_factura'].strip().casefold()
        if not key:
            _fail('Todas las filas de Posiciones deben tener clave_factura.')
        lines_by_key.setdefault(key, []).append(row)
    header_by_key = {}
    for row in headers:
        key = row['clave_factura'].strip().casefold()
        if not key:
            _fail('Todas las filas de Facturas deben tener clave_factura.')
        if key in header_by_key:
            _fail(f'La clave_factura "{row["clave_factura"]}" está duplicada en la hoja Facturas.')
        header_by_key[key] = row
    referenced_pdf_names = [row['archivo_pdf'].strip().casefold() for row in headers if row['archivo_pdf'].strip()]
    referenced_xml_names = [row['archivo_xml'].strip().casefold() for row in headers if row['archivo_xml'].strip()]
    if len(referenced_pdf_names) != len(set(referenced_pdf_names)) or len(referenced_xml_names) != len(set(referenced_xml_names)):
        _fail('Cada archivo PDF o XML debe corresponder a una sola factura del lote.')
    unknown_keys = set(lines_by_key) - set(header_by_key)
    if unknown_keys:
        _fail('Hay filas en Posiciones con clave_factura inexistente en Facturas.')
    xml_by_name = await _attachments(xml_files, 'xml')
    pdf_by_name = await _attachments(pdf_files, 'pdf')
    batch_bytes = len(workbook_bytes) + sum(len(item[1]) for item in (*xml_by_name.values(), *pdf_by_name.values()))
    if batch_bytes > MAX_BATCH_BYTES:
        _fail('El tamaño total del lote supera 30 MB.')
    outcomes = []
    for key, header in header_by_key.items():
        savepoint = db.begin_nested()
        try:
            outcome = _validate_group(db, user, header, position_rows, xml_by_name, pdf_by_name, save=True)
            db.flush()
            savepoint.commit()
            if persist:
                db.commit()
            else:
                # Keep staged invoices visible to later groups for duplicate and balance checks.
                # The whole preview transaction is rolled back after all groups are checked.
                pass
            outcomes.append(outcome if persist else {**outcome, 'estado': 'validada', 'id': None})
        except HTTPException as exc:
            if savepoint.is_active:
                savepoint.rollback()
            outcomes.append({'clave_factura': header.get('clave_factura', key), 'estado': 'error', 'detalle': exc.detail})
        except IntegrityError:
            if savepoint.is_active:
                savepoint.rollback()
            outcomes.append({'clave_factura': header.get('clave_factura', key), 'estado': 'error', 'detalle': 'La factura duplica un registro o viola una regla de integridad.'})
        except Exception:
            if savepoint.is_active:
                savepoint.rollback()
            outcomes.append({'clave_factura': header.get('clave_factura', key), 'estado': 'error', 'detalle': 'No se pudo registrar esta factura; revisa el Excel, sus posiciones y adjuntos.'})
    if not persist:
        db.rollback()
    else:
        # A rejected row must not roll back invoices already committed successfully.
        db.rollback()
    referenced_xml = {row['archivo_xml'].strip().casefold() for row in headers if row['archivo_xml'].strip()}
    referenced_pdf = {row['archivo_pdf'].strip().casefold() for row in headers if row['archivo_pdf'].strip()}
    unused = [
        {'archivo': name, 'estado': 'aviso', 'detalle': 'Adjunto no referenciado en la hoja Facturas.'}
        for mapping, referenced in ((xml_by_name, referenced_xml), (pdf_by_name, referenced_pdf))
        for name, _ in mapping.values() if name.casefold() not in referenced
    ]
    outcomes.extend(unused)
    return {
        'modo': 'registrado' if persist else 'validacion',
        'registradas': sum(row['estado'] == 'registrada' for row in outcomes),
        'validas': sum(row['estado'] == 'validada' for row in outcomes),
        'errores': sum(row['estado'] == 'error' for row in outcomes),
        'total': len(header_by_key), 'items': outcomes,
    }


@router.get('/plantilla.xlsx')
def plantilla(user: dict = Depends(get_current_ap_user)):
    return Response(
        build_template(), media_type=XLSX_MIME,
        headers={'Content-Disposition': 'attachment; filename="plantilla_facturas_con_oc.xlsx"', 'X-Content-Type-Options': 'nosniff'},
    )


@router.post('/validar')
async def validar_lote(
    excel: UploadFile = File(...), xml_files: list[UploadFile] = File(default=[]),
    pdf_files: list[UploadFile] = File(...), user: dict = Depends(get_current_ap_user),
    db: Session = Depends(get_db),
):
    return await _run_batch(excel, xml_files, pdf_files, user, db, persist=False)


@router.post('/registrar', status_code=201)
async def registrar_lote(
    excel: UploadFile = File(...), xml_files: list[UploadFile] = File(default=[]),
    pdf_files: list[UploadFile] = File(...), user: dict = Depends(get_current_ap_user),
    db: Session = Depends(get_db),
):
    return await _run_batch(excel, xml_files, pdf_files, user, db, persist=True)
