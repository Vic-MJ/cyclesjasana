from odoo.tests.common import TransactionCase


class TestRfidEpcInfo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Processor = cls.env["cycles.rfid.processor"]
        cls.garment_type = cls.env["cycles.garment.type"].create(
            {"name": "Filipina EPC Info", "code": "EPC-INFO-001"}
        )
        cls.product = cls.garment_type.product_tmpl_id.product_variant_id
        cls.lot = cls.env["stock.lot"].create(
            {
                "name": "EPC-INFO-TEST-1",
                "product_id": cls.product.id,
                "company_id": cls.env.company.id,
            }
        )

    def test_get_epc_info_returns_known_lot(self):
        info = self.Processor.get_epc_info(
            [self.lot.name, "UNKNOWN-EPC"]
        )
        self.assertIn(self.lot.name, info)
        entry = info[self.lot.name]
        self.assertTrue(entry["product_name"])
        self.assertEqual(entry["lot_id"], self.lot.id)
        self.assertNotIn("UNKNOWN-EPC", info)

    def test_get_epc_info_empty_returns_empty_dict(self):
        self.assertEqual(self.Processor.get_epc_info([]), {})

    def test_get_epc_info_returns_product_template_name(self):
        expected_name = self.product.display_name
        info = self.Processor.get_epc_info([self.lot.name])
        self.assertEqual(info[self.lot.name]["product_name"], expected_name)
