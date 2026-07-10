from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestStockLot(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.garment_type = cls.env["cycles.garment.type"].create(
            {
                "name": "Mandil",
                "code": "LOT-001",
                "max_wash_cycles": 10,
                "warning_cycles_threshold": 80,
                "min_inventory": 1,
                "inactivity_days": 5,
            }
        )
        cls.template = cls.garment_type.product_tmpl_id
        cls.product = cls.template.product_variant_id

    def test_lifecycle_state_uses_product_template_thresholds(self):
        lot = self.env["stock.lot"].create(
            {
                "name": "LOT-STATE-1",
                "product_id": self.product.id,
                "wash_cycle_count": 7,
            }
        )
        self.assertEqual(lot.lifecycle_state, "ok")

        self.template.cycles_warning_cycles_threshold = 70
        lot.invalidate_recordset(["lifecycle_state"])
        self.assertEqual(lot.lifecycle_state, "warning")

        lot.wash_cycle_count = 10
        lot.invalidate_recordset(["lifecycle_state"])
        self.assertEqual(lot.lifecycle_state, "replace")

    def test_alerts_use_template_inactivity_and_inventory_settings(self):
        lot = self.env["stock.lot"].create(
            {
                "name": "LOT-ALERT-1",
                "product_id": self.product.id,
                "wash_cycle_count": 10,
                "last_movement_date": fields.Datetime.now() - timedelta(days=7),
            }
        )

        self.env["stock.lot"]._cycles_check_alerts()

        activities = self.env["mail.activity"].search(
            [
                ("res_model", "=", "stock.lot"),
                ("res_id", "=", lot.id),
            ]
        )
        self.assertEqual(len(activities), 2)
        alert_activity = activities.filtered(
            lambda activity: activity.summary == "Alerta de Prenda"
        )
        inventory_activity = activities.filtered(
            lambda activity: activity.summary.startswith("Inventario Bajo:")
        )
        self.assertTrue(alert_activity)
        self.assertIn("Sin movimiento en 7 días", alert_activity.note)
        self.assertIn("10/10", alert_activity.note)
        self.assertTrue(inventory_activity)
        self.assertIn("mínimo: 1", inventory_activity.note)
