from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestGarmentType(TransactionCase):
    @mute_logger("odoo.sql_db")
    def test_max_wash_cycles_must_be_positive(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["cycles.garment.type"].create(
                {"name": "Inválida", "code": "BAD-1", "max_wash_cycles": 0}
            )
            self.env.flush_all()

    def test_create_auto_generates_serial_product(self):
        garment_type = self.env["cycles.garment.type"].create(
            {"name": "Filipina", "code": "OK-1"}
        )
        self.assertTrue(garment_type.product_tmpl_id)
        self.assertEqual(garment_type.product_tmpl_id.tracking, "serial")
