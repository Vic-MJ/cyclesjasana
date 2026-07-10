from odoo import api, fields, models
from odoo.exceptions import ValidationError


class GarmentType(models.Model):
    _name = "cycles.garment.type"
    _description = "Tipo de Prenda"
    _order = "name"

    name = fields.Char(string="Nombre", required=True)
    code = fields.Char(string="Código", required=True)
    max_wash_cycles = fields.Integer(
        string="Ciclos Máximos de Lavado",
        required=True,
        default=50,
        help="Número máximo de ciclos de lavado antes de que la prenda"
        " necesite reemplazo.",
    )
    warning_cycles_threshold = fields.Integer(
        string="Umbral de Alerta (%)",
        default=80,
        help="Porcentaje de ciclos máximos a partir del cual se muestra"
        " la alerta 'Próximo a Reemplazo'.",
    )
    min_inventory = fields.Integer(
        string="Inventario Mínimo",
        default=0,
        help="Cantidad mínima de prendas en Ropería antes de generar una alerta.",
    )
    inactivity_days = fields.Integer(
        string="Alerta de Inactividad (días)",
        default=30,
        help="Días sin movimiento antes de marcar una prenda como inactiva.",
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Producto",
        help="Producto vinculado para el seguimiento de inventario.",
    )
    garment_ids = fields.One2many("stock.lot", "garment_type_id", string="Prendas")
    garment_count = fields.Integer(
        string="Total de Prendas", compute="_compute_garment_count"
    )
    company_id = fields.Many2one(
        "res.company", string="Empresa", default=lambda self: self.env.company
    )
    active = fields.Boolean(default=True)

    @api.constrains("max_wash_cycles")
    def _check_max_wash_cycles(self):
        for record in self:
            if record.max_wash_cycles <= 0:
                raise ValidationError(
                    "Los ciclos máximos de lavado deben ser mayores a cero."
                )

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "¡El código debe ser único por empresa!",
        ),
        (
            "max_wash_cycles_positive",
            "CHECK(max_wash_cycles > 0)",
            "Los ciclos máximos de lavado deben ser mayores a cero.",
        ),
    ]

    @api.depends("garment_ids")
    def _compute_garment_count(self):
        for rec in self:
            rec.garment_count = len(rec.garment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.product_tmpl_id:
                rec._create_product_template()
        return records

    def _create_product_template(self):
        self.ensure_one()
        category = self.env.ref(
            "cycles.product_category_uniformes", raise_if_not_found=False
        )
        product_vals = {
            "name": self.name,
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
            "sale_ok": False,
            "purchase_ok": True,
            "garment_type_id": self.id,
        }
        if category:
            product_vals["categ_id"] = category.id
        product = self.env["product.template"].create(product_vals)
        self.product_tmpl_id = product.id

    def action_view_garments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Prendas - %s") % self.name,
            "res_model": "stock.lot",
            "view_mode": "list,form",
            "domain": [("garment_type_id", "=", self.id)],
            "context": {"default_garment_type_id": self.id},
        }
