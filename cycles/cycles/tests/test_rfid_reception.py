from odoo.tests.common import TransactionCase


class TestRfidReception(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Processor = cls.env["cycles.rfid.processor"]
        cls.garment_type = cls.env["cycles.garment.type"].create(
            {"name": "Filipina Recepción", "code": "REC-001"}
        )
        cls.product = cls.garment_type.product_tmpl_id.product_variant_id
        # Generar el picking de entrada a través de la importación
        result = cls.env["cycles.jasana.import"].import_inventory_entry(
            {
                "external_ref": "jasana:testdb:99",
                "origin": "S00099",
                "client_order_ref": "PO-CLIENTE-99",
                "partner": {"name": "Jasana Test"},
                "lines": [
                    {
                        "code": "REC-001",
                        "name": "Filipina",
                        "qty": 3.0,
                        "price_unit": 10.0,
                    }
                ],
            }
        )
        cls.picking = cls.env["stock.picking"].browse(result["picking_id"])

    def test_partial_reception_creates_backorder(self):
        res = self.Processor.process_scan(
            ["EPC-A", "EPC-B"],
            "entrada",
            self.picking.picking_type_id.id,
            self.picking.location_id.id,
            self.picking.location_dest_id.id,
            None,
            self.garment_type.id,
            self.picking.id,
        )
        self.assertEqual(res["processed_count"], 2)
        self.assertEqual(self.picking.state, "done")
        backorder = self.env["stock.picking"].search(
            [("backorder_id", "=", self.picking.id)]
        )
        self.assertTrue(backorder, "Una recepción parcial debe generar backorder.")
        lots = self.env["stock.lot"].search(
            [("name", "in", ["EPC-A", "EPC-B"]), ("product_id", "=", self.product.id)]
        )
        self.assertEqual(len(lots), 2)

    def test_scan_dedupes_epcs(self):
        res = self.Processor.process_scan(
            ["EPC-X", "EPC-X", " EPC-X ", "EPC-Y"],
            "entrada",
            self.picking.picking_type_id.id,
            self.picking.location_id.id,
            self.picking.location_dest_id.id,
            None,
            self.garment_type.id,
            self.picking.id,
        )
        self.assertEqual(res["processed_count"], 2)
        lots = self.env["stock.lot"].search([("name", "=", "EPC-X")])
        self.assertEqual(len(lots), 1, "El EPC duplicado no debe duplicar lotes.")

    def test_pending_receptions_lists_imported_picking(self):
        receptions = self.Processor.get_pending_receptions()
        ids = [r["picking_id"] for r in receptions]
        self.assertIn(self.picking.id, ids)
