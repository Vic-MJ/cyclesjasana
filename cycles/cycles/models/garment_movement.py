from odoo import fields, models


class GarmentMovement(models.Model):
    _name = "cycles.movement"
    _description = "Movimiento de Prenda"
    _order = "date desc"

    lot_id = fields.Many2one(
        "stock.lot",
        string="Prenda",
        required=True,
        domain=[("is_garment", "=", True)],
        ondelete="cascade",
        index=True,
    )
    garment_type_id = fields.Many2one(
        related="lot_id.garment_type_id", store=True, string="Tipo de Prenda"
    )
    employee_id = fields.Many2one(
        related="lot_id.employee_id", store=True, string="Empleado"
    )
    picking_id = fields.Many2one("stock.picking", string="Transferencia", index=True)
    location_from_id = fields.Many2one(
        "stock.location", string="Ubicación Origen", required=True
    )
    location_to_id = fields.Many2one(
        "stock.location", string="Ubicación Destino", required=True
    )
    date = fields.Datetime(
        string="Fecha", default=fields.Datetime.now, required=True, index=True
    )
    is_wash_cycle = fields.Boolean(
        string="Es Ciclo de Lavado",
        default=False,
        help="Verdadero si este movimiento representa entrada a lavandería.",
    )
    user_id = fields.Many2one(
        "res.users", string="Realizado Por", default=lambda self: self.env.user
    )
    company_id = fields.Many2one(
        "res.company", string="Empresa", default=lambda self: self.env.company
    )
