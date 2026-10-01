import unittest

from sap_ecc_contrato import ErrorContratoECC, preparar_datos_bapi


class ContratoECCtests(unittest.TestCase):
    def setUp(self):
        self.factura = {
            "factura_portal": "portal-123",
            "serie": "F001",
            "numero": "42",
            "fecha_emision": "2026-09-29",
            "moneda": "PEN",
            "subtotal": "300.00",
            "impuestos": "54.00",
            "total": "354.00",
            "adjuntos": {"factura_id": "portal-123"},
            "posiciones": [
                {"pedido": "4500000010", "posicion": "00010", "unidad": "NIU", "cantidad": "2", "subtotal": "100.00", "tasa_impuesto": "18.00", "descripcion": "Material A"},
                {"pedido": "4500000020", "posicion": "00020", "unidad": "NIU", "cantidad": "4", "subtotal": "200.00", "tasa_impuesto": "18.00", "descripcion": "Material B"},
            ],
        }

    def preparar(self, payload=None, tax_codes=None):
        return preparar_datos_bapi(
            payload or self.factura,
            sociedad="1000",
            proveedor_sap="0000100001",
            fecha_contabilizacion="2026-09-29",
            codigos_impuesto={"18.00": "V1"} if tax_codes is None else tax_codes,
        )

    def test_prepara_una_factura_con_varios_pedidos(self):
        result = self.preparar()
        self.assertEqual(result["headerdata"]["COMP_CODE"], "1000")
        self.assertEqual(result["headerdata"]["DOC_DATE"], "20260929")
        self.assertEqual(result["headerdata"]["PSTNG_DATE"], "20260929")
        self.assertEqual([line["PO_NUMBER"] for line in result["itemdata"]], ["4500000010", "4500000020"])
        self.assertEqual([line["PO_ITEM"] for line in result["itemdata"]], ["00010", "00020"])
        self.assertEqual(result["mapping_context"]["supplier_sap"], "0000100001")

    def test_exige_mapeo_explicito_de_impuesto(self):
        with self.assertRaisesRegex(ErrorContratoECC, "código de impuesto"):
            self.preparar(tax_codes={})

    def test_no_envia_linea_sin_referencia_sap(self):
        invalid = {**self.factura, "posiciones": [{**self.factura["posiciones"][0], "pedido": ""}]}
        with self.assertRaisesRegex(ErrorContratoECC, "pedido, posición y unidad"):
            self.preparar(payload=invalid)

    def test_servicio_requiere_hes_y_preserva_contexto_de_paquete(self):
        service = {
            **self.factura["posiciones"][0],
            "tipo_posicion": "servicio",
            "paquete_servicio": "0000123456",
            "numero_servicio": "0000000010",
            "referencia": {"tipo": "servicio", "numero": "1000001234", "posicion": "0000000010"},
        }
        result = self.preparar(payload={**self.factura, "posiciones": [service]})
        self.assertEqual(result["itemdata"][0]["SERVICE_CONTEXT"], {
            "service_package": "0000123456",
            "service_line": "0000000010",
            "accepted_service_entry_sheet": "1000001234",
            "accepted_service_entry_line": "0000000010",
        })
        invalid = {**service, "referencia": None}
        with self.assertRaisesRegex(ErrorContratoECC, "hoja de entrada"):
            self.preparar(payload={**self.factura, "posiciones": [invalid]})

if __name__ == "__main__":
    unittest.main()
