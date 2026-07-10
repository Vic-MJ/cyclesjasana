from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    garment_type_id = fields.Many2one("cycles.garment.type", string="Tipo de Prenda")
