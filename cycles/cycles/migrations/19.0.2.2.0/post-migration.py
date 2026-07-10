from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    template_env = env["product.template"]
    cr.execute(
        """
        SELECT
            id,
            product_tmpl_id,
            code,
            max_wash_cycles,
            warning_cycles_threshold,
            min_inventory,
            inactivity_days
        FROM cycles_garment_type
        WHERE product_tmpl_id IS NOT NULL
        """
    )
    for (
        garment_type_id,
        product_tmpl_id,
        code,
        max_wash_cycles,
        warning_cycles_threshold,
        min_inventory,
        inactivity_days,
    ) in cr.fetchall():
        template_env.browse(product_tmpl_id).write(
            {
                "garment_type_id": garment_type_id,
                "cycles_is_garment": True,
                "cycles_max_wash_cycles": max_wash_cycles or 50,
                "cycles_warning_cycles_threshold": (
                    warning_cycles_threshold or 80
                ),
                "cycles_min_inventory": min_inventory or 0,
                "cycles_inactivity_days": inactivity_days or 30,
                "default_code": code
                or env["product.template"].browse(product_tmpl_id).default_code,
            }
        )

    orphan_templates = template_env.search(
        [
            ("cycles_is_garment", "=", True),
            ("garment_type_id", "=", False),
        ]
    )
    orphan_templates._cycles_ensure_compatibility_garment_type()
