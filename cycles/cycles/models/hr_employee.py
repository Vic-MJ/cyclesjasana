from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    garment_lot_ids = fields.One2many(
        "stock.lot",
        "employee_id",
        string="Prendas Asignadas",
        domain=[("is_garment", "=", True)],
    )
    garment_count = fields.Integer(string="Prendas", compute="_compute_garment_count")

    @api.depends("garment_lot_ids")
    def _compute_garment_count(self):
        for employee in self:
            employee.garment_count = len(employee.garment_lot_ids)

    def action_view_garments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Prendas - %s") % self.name,
            "res_model": "stock.lot",
            "view_mode": "list,form",
            "domain": [("employee_id", "=", self.id), ("is_garment", "=", True)],
        }
