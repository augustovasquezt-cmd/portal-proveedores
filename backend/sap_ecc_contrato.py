"""Traducción pura del contrato del portal a tablas de factura entrante ECC.

No ejecuta RFC, no importa pyrfc y no confirma documentos. La selección final
de función/campos debe contrastarse con SE37/BAPI Explorer en el ECC del cliente.
"""
from decimal import Decimal, InvalidOperation
from datetime import date


class ErrorContratoECC(ValueError):
    """El payload no tiene los datos necesarios para preparar la llamada ECC."""


def _decimal(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ErrorContratoECC(f"Importe inválido en {field}.") from None
    if not number.is_finite():
        raise ErrorContratoECC(f"Importe inválido en {field}.")
    return number


def preparar_datos_bapi(payload, *, sociedad, proveedor_sap, fecha_contabilizacion, codigos_impuesto):
    """Construye HEADERDATA e ITEMDATA sin invocar SAP.

    `codigos_impuesto` debe mapear tasas decimales a códigos SAP, por ejemplo
    {"18.00": "V1", "0.00": "V0"}. Los códigos nunca se deducen del XML.
    Los pedidos y posiciones deben ser sus números reales de SAP, no IDs DEMO.
    """
    if not isinstance(payload, dict) or not payload.get("posiciones"):
        raise ErrorContratoECC("La factura debe tener al menos una posición de pedido.")
    required = ("serie", "numero", "fecha_emision", "moneda", "subtotal", "impuestos", "total")
    missing = [field for field in required if payload.get(field) in (None, "")]
    if missing:
        raise ErrorContratoECC("Faltan datos de cabecera: " + ", ".join(missing) + ".")
    if not sociedad or not proveedor_sap or not fecha_contabilizacion:
        raise ErrorContratoECC("Debe configurarse la sociedad, el proveedor SAP y la fecha de contabilización.")
    try:
        fecha_documento = date.fromisoformat(str(payload["fecha_emision"]))
        fecha_posting = date.fromisoformat(str(fecha_contabilizacion))
    except ValueError:
        raise ErrorContratoECC("Las fechas deben tener formato AAAA-MM-DD.") from None

    header = {
        "INVOICE_IND": "X",
        "DOC_DATE": fecha_documento.strftime("%Y%m%d"),
        "PSTNG_DATE": fecha_posting.strftime("%Y%m%d"),
        "COMP_CODE": str(sociedad),
        "CURRENCY": str(payload["moneda"]),
        "GROSS_AMOUNT": str(_decimal(payload["total"], "total")),
        "REF_DOC_NO": f"{payload['serie']}-{payload['numero']}",
        "HEADER_TXT": f"Portal proveedores {payload.get('factura_portal', '')}"[:25],
    }

    items = []
    for index, line in enumerate(payload["posiciones"], start=1):
        po_number = str(line.get("pedido") or "").strip()
        po_item = str(line.get("posicion") or "").strip()
        unit = str(line.get("unidad") or "").strip()
        if not po_number or not po_item or not unit:
            raise ErrorContratoECC(f"La línea {index} requiere pedido, posición y unidad SAP.")
        service_context = None
        if line.get("tipo_posicion") == "servicio":
            reference = line.get("referencia") or {}
            if reference.get("tipo") != "servicio" or not reference.get("numero"):
                raise ErrorContratoECC(f"La línea {index} de servicio requiere una hoja de entrada de servicios aceptada.")
            if not line.get("paquete_servicio") or not line.get("numero_servicio"):
                raise ErrorContratoECC(f"La línea {index} requiere la referencia SAP de paquete y sublínea de servicio.")
            service_context = {
                "service_package": str(line["paquete_servicio"]),
                "service_line": str(line["numero_servicio"]),
                "accepted_service_entry_sheet": str(reference["numero"]),
                "accepted_service_entry_line": str(reference.get("posicion") or ""),
            }
        rate = _decimal(line.get("tasa_impuesto"), f"tasa_impuesto de línea {index}")
        tax_code = codigos_impuesto.get(f"{rate:.2f}") or codigos_impuesto.get(str(rate))
        if not tax_code:
            raise ErrorContratoECC(f"No hay código de impuesto SAP configurado para la tasa {rate:.2f}%.")
        item = {
            "INVOICE_DOC_ITEM": str(index * 10).zfill(6),
            "PO_NUMBER": po_number,
            "PO_ITEM": po_item.zfill(5),
            "ITEM_AMOUNT": str(_decimal(line.get("subtotal"), f"subtotal de línea {index}")),
            "QUANTITY": str(_decimal(line.get("cantidad"), f"cantidad de línea {index}")),
            "PO_UNIT": unit,
            "TAX_CODE": str(tax_code),
            "ITEM_TEXT": str(line.get("descripcion") or line.get("material") or "")[:50],
        }
        if service_context:
            # Keep service hierarchy explicit for the customer-specific ECC
            # adapter; BAPI service tables vary by release/configuration.
            item["SERVICE_CONTEXT"] = service_context
        items.append(item)

    return {
        "headerdata": header,
        "itemdata": items,
        "portal_reference": str(payload.get("factura_portal", "")),
        "mapping_context": {"supplier_sap": str(proveedor_sap)},
        "attachments_reference": payload.get("adjuntos", {}),
        "note": "Preparado solamente; requiere validar campos y BAPI disponible en el ECC objetivo.",
    }
