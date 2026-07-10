from odoo.tests.common import TransactionCase


class TestMulticompany(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Warehouse = cls.env["stock.warehouse"]
        cls.company1 = cls.env.company
        # Creating a company auto-creates its warehouse (stock.res_company),
        # which our override provisions with the uniform infrastructure.
        cls.company2 = cls.env["res.company"].create({"name": "Cycles Co 2"})
        cls.wh2 = cls.Warehouse._cycles_get_warehouse(cls.company2)

    def test_each_company_has_own_infrastructure(self):
        wh1 = self.Warehouse._cycles_get_warehouse(self.company1)
        self.assertTrue(wh1.cycles_loc_roperia_id)
        self.assertTrue(self.wh2.cycles_loc_roperia_id)
        # The two companies must not share locations or operation types.
        self.assertNotEqual(
            wh1.cycles_loc_roperia_id, self.wh2.cycles_loc_roperia_id
        )
        self.assertNotEqual(
            wh1.cycles_pick_type_entrada_id, self.wh2.cycles_pick_type_entrada_id
        )
        # Resources belong to the right company.
        self.assertEqual(self.wh2.cycles_loc_roperia_id.company_id, self.company2)
        self.assertEqual(
            self.wh2.cycles_pick_type_entrada_id.company_id, self.company2
        )

    def test_provision_is_idempotent(self):
        roperia_before = self.wh2.cycles_loc_roperia_id
        self.wh2._cycles_provision()
        self.assertEqual(self.wh2.cycles_loc_roperia_id, roperia_before)

    def test_scan_operations_follow_active_company(self):
        config2 = self.Warehouse._cycles_get_config(self.company2)
        ops = (
            self.env["cycles.rfid.processor"]
            .with_company(self.company2)
            .get_scan_operations()
        )
        entrada = next(op for op in ops if op["code"] == "entrada")
        self.assertEqual(
            entrada["picking_type_id"], config2["pick_entrada"].id
        )
        self.assertEqual(
            entrada["location_dest_id"], config2["warehouse"].lot_stock_id.id
        )

    def test_entrada_scan_is_company_scoped(self):
        garment_type = (
            self.env["cycles.garment.type"]
            .with_company(self.company2)
            .create({"name": "Filipina C2", "code": "C2-001"})
        )
        self.assertEqual(garment_type.company_id, self.company2)
        config2 = self.Warehouse._cycles_get_config(self.company2)
        result = (
            self.env["cycles.rfid.processor"]
            .with_company(self.company2)
            .process_scan(
                ["C2-EPC-1", "C2-EPC-2"],
                "entrada",
                config2["pick_entrada"].id,
                self.env.ref("stock.stock_location_suppliers").id,
                config2["roperia"].id,
                None,
                garment_type.id,
                None,
            )
        )
        self.assertEqual(result["processed_count"], 2)
        picking = self.env["stock.picking"].browse(result["picking_id"])
        self.assertEqual(picking.company_id, self.company2)
        lots = self.env["stock.lot"].search(
            [("name", "in", ["C2-EPC-1", "C2-EPC-2"])]
        )
        self.assertEqual(len(lots), 2)
        self.assertEqual(lots.company_id, self.company2)
