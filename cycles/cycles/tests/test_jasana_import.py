from odoo.tests.common import TransactionCase


class TestJasanaImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Import = cls.env["cycles.jasana.import"]
        cls.payload = {
            "external_ref": "jasana:testdb:1",
            "origin": "S00001",
            "client_order_ref": "PO-CLIENTE-77",
            "partner": {"name": "Jasana Test", "vat": "", "email": ""},
            "lines": [
                {
                    "code": "UNI-FIL-001",
                    "name": "Filipina Azul M",
                    "qty": 5.0,
                    "price_unit": 120.0,
                    "description_sale": "Filipina de algodón",
                    "barcode": "7501234567890",
                    "list_price": 150.0,
                    "image": False,
                    "attributes": [
                        {"attribute": "Color", "value": "Azul"},
                        {"attribute": "Talla", "value": "M"},
                    ],
                },
            ],
        }

    def test_import_creates_incoming_entry(self):
        result = self.Import.import_inventory_entry(self.payload)
        self.assertTrue(result["created"])
        picking = self.env["stock.picking"].browse(result["picking_id"])
        self.assertEqual(picking.picking_type_id.code, "incoming")
        self.assertEqual(picking.jasana_external_ref, self.payload["external_ref"])
        self.assertIn(picking.state, ("assigned", "confirmed", "waiting"))
        self.assertTrue(picking.move_ids, "La entrada debe tener movimientos.")

    def test_import_uses_client_order_ref_as_origin(self):
        result = self.Import.import_inventory_entry(self.payload)
        picking = self.env["stock.picking"].browse(result["picking_id"])
        self.assertEqual(picking.origin, "PO-CLIENTE-77")

    def test_import_falls_back_to_origin_without_client_ref(self):
        payload = dict(self.payload, external_ref="jasana:testdb:2")
        payload.pop("client_order_ref")
        result = self.Import.import_inventory_entry(payload)
        picking = self.env["stock.picking"].browse(result["picking_id"])
        self.assertEqual(picking.origin, "S00001")

    def test_import_auto_creates_garment_type(self):
        self.Import.import_inventory_entry(self.payload)
        garment_type = self.env["cycles.garment.type"].search(
            [("code", "=", "UNI-FIL-001")]
        )
        self.assertEqual(len(garment_type), 1)
        self.assertTrue(garment_type.product_tmpl_id)
        self.assertEqual(garment_type.product_tmpl_id.tracking, "serial")

    def test_import_copies_product_fields(self):
        self.Import.import_inventory_entry(self.payload)
        template = self.env["cycles.garment.type"].search(
            [("code", "=", "UNI-FIL-001")]
        ).product_tmpl_id
        self.assertEqual(template.description_sale, "Filipina de algodón")
        self.assertEqual(template.list_price, 150.0)
        self.assertEqual(template.product_variant_id.barcode, "7501234567890")

    def test_import_replicates_attributes_as_no_variant(self):
        self.Import.import_inventory_entry(self.payload)
        template = self.env["cycles.garment.type"].search(
            [("code", "=", "UNI-FIL-001")]
        ).product_tmpl_id
        attr_names = template.attribute_line_ids.attribute_id.mapped("name")
        self.assertIn("Color", attr_names)
        self.assertIn("Talla", attr_names)
        # Un solo valor por atributo: el producto sigue siendo de variante única.
        self.assertEqual(len(template.product_variant_ids), 1)

    def test_import_reuses_existing_attribute(self):
        # Un atributo "Color" ya existente (p. ej. estándar) debe reutilizarse,
        # no duplicarse al importar.
        existing = self.env["product.attribute"].create(
            {"name": "Color", "create_variant": "always"}
        )
        self.Import.import_inventory_entry(self.payload)
        colors = self.env["product.attribute"].search([("name", "=", "Color")])
        self.assertEqual(len(colors), 1)
        self.assertEqual(colors, existing)

    def test_import_is_idempotent(self):
        first = self.Import.import_inventory_entry(self.payload)
        second = self.Import.import_inventory_entry(self.payload)
        self.assertFalse(second["created"])
        self.assertEqual(second["picking_id"], first["picking_id"])
        pickings = self.env["stock.picking"].search(
            [("jasana_external_ref", "=", self.payload["external_ref"])]
        )
        self.assertEqual(len(pickings), 1)

    def test_import_reuses_existing_garment_type(self):
        garment_type = self.env["cycles.garment.type"].create(
            {"name": "Filipina existente", "code": "UNI-FIL-001"}
        )
        result = self.Import.import_inventory_entry(self.payload)
        picking = self.env["stock.picking"].browse(result["picking_id"])
        product = garment_type.product_tmpl_id.product_variant_id
        self.assertEqual(picking.move_ids.product_id, product)
