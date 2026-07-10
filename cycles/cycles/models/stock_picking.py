from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    garment_employee_id = fields.Many2one(
        "hr.employee",
        string="Entregar a Empleado",
        help="Empleado que recibe las prendas en esta transferencia.",
    )
    jasana_external_ref = fields.Char(
        string="Referencia Jasana",
        index=True,
        copy=False,
        help="Identificador único del documento de origen en Jasana."
        " Garantiza idempotencia al importar entradas de inventario.",
    )

    _sql_constraints = [
        (
            "jasana_external_ref_company_uniq",
            "unique(jasana_external_ref, company_id)",
            "Ya existe una entrada de inventario para esta referencia de Jasana.",
        ),
    ]

    def button_validate(self):
        res = super().button_validate()
        for picking in self.filtered(
            lambda p: p.garment_employee_id and p.state == "done"
        ):
            garment_lots = picking.move_line_ids.lot_id.filtered("is_garment")
            garment_lots.write(
                {
                    "employee_id": picking.garment_employee_id.id,
                    "assignment_date": fields.Date.today(),
                }
            )
        return res
