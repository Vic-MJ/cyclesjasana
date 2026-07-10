from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from odoo.tests.common import TransactionCase


def _load_post_migration():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "19.0.2.2.0"
        / "post-migration.py"
    )
    spec = spec_from_file_location("cycles_post_migration_19_0_2_2_0", module_path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


POST_MIGRATION = _load_post_migration()


class TestPostMigration190220(TransactionCase):
    def test_migrate_backfills_templates_and_repairs_orphans(self):
        template = self.env["product.template"].create(
            {
                "name": "Producto legado Cycles",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "purchase_ok": True,
                "sale_ok": False,
                "default_code": "LEGACY-OLD",
                "cycles_is_garment": True,
            }
        )
        garment_type = self.env["cycles.garment.type"].create(
            {
                "name": "Prenda legado",
                "code": "LEGACY-001",
                "product_tmpl_id": template.id,
            }
        )
        orphan_template = self.env["product.template"].with_context(
            cycles_skip_template_sync=True,
        ).create(
            {
                "name": "Producto huérfano Cycles",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "purchase_ok": True,
                "sale_ok": False,
                "default_code": "ORPHAN-001",
                "cycles_is_garment": True,
            }
        )

        self.cr.execute(
            """
            UPDATE product_template
               SET garment_type_id = NULL,
                   cycles_is_garment = FALSE,
                   cycles_max_wash_cycles = %s,
                   cycles_warning_cycles_threshold = %s,
                   cycles_min_inventory = %s,
                   cycles_inactivity_days = %s,
                   default_code = NULL
             WHERE id = %s
            """,
            (5, 10, 0, 1, template.id),
        )
        self.cr.execute(
            """
            UPDATE cycles_garment_type
               SET max_wash_cycles = %s,
                   warning_cycles_threshold = %s,
                   min_inventory = %s,
                   inactivity_days = %s
             WHERE id = %s
            """,
            (72, 88, 4, 21, garment_type.id),
        )
        self.env.invalidate_all()

        POST_MIGRATION.migrate(self.cr, "19.0.2.2.0")
        self.env.invalidate_all()

        template = self.env["product.template"].browse(template.id)
        orphan_template = self.env["product.template"].browse(orphan_template.id)
        garment_type = self.env["cycles.garment.type"].browse(garment_type.id)

        self.assertEqual(template.garment_type_id, garment_type)
        self.assertTrue(template.cycles_is_garment)
        self.assertEqual(template.cycles_max_wash_cycles, 72)
        self.assertEqual(template.cycles_warning_cycles_threshold, 88)
        self.assertEqual(template.cycles_min_inventory, 4)
        self.assertEqual(template.cycles_inactivity_days, 21)
        self.assertEqual(template.default_code, "LEGACY-001")

        self.assertTrue(orphan_template.garment_type_id)
        self.assertEqual(
            orphan_template.garment_type_id.product_tmpl_id,
            orphan_template,
        )
        self.assertEqual(orphan_template.garment_type_id.code, "ORPHAN-001")
