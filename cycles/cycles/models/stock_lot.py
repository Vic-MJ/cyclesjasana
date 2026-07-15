from odoo import api, fields, models
from odoo.exceptions import ValidationError
class StockLot(models.Model):
    _inherit = "stock.lot"

    is_garment = fields.Boolean(
        string="Es Prenda", compute="_compute_is_garment", store=True
    )
    garment_type_id = fields.Many2one(
        "cycles.garment.type",
        string="Tipo de Prenda",
        compute="_compute_garment_type_id",
        store=True,
    )
    employee_id = fields.Many2one(
        "hr.employee", string="Empleado Asignado", tracking=True
    )
    wash_cycle_count = fields.Integer(
        string="Ciclos de Lavado", default=0, tracking=True
    )
    max_wash_cycles = fields.Integer(
        string="Máx. Ciclos de Lavado",
        related="garment_type_id.max_wash_cycles",
        store=True,
    )
    lifecycle_state = fields.Selection(
        [
            ("ok", "OK"),
            ("warning", "Próximo a Reemplazo"),
            ("replace", "Reemplazar"),
            ("retired", "Retirada"),
        ],
        string="Estado del Ciclo de Vida",
        compute="_compute_lifecycle_state",
        store=True,
    )
    last_wash_date = fields.Datetime(string="Último Lavado")
    last_movement_date = fields.Datetime(string="Último Movimiento")
    assignment_date = fields.Date(string="Fecha de Asignación")
    movement_ids = fields.One2many(
        "cycles.movement", "lot_id", string="Historial de Movimientos"
    )
    movement_count = fields.Integer(
        string="Movimientos", compute="_compute_movement_count"
    )

    @api.depends("product_id", "product_id.product_tmpl_id.garment_type_id")
    def _compute_is_garment(self):
        for lot in self:
            lot.is_garment = bool(lot.product_id.product_tmpl_id.garment_type_id)

    @api.depends("product_id", "product_id.product_tmpl_id.garment_type_id")
    def _compute_garment_type_id(self):
        for lot in self:
            lot.garment_type_id = lot.product_id.product_tmpl_id.garment_type_id

    @api.depends("wash_cycle_count", "max_wash_cycles", "is_garment")
    def _compute_lifecycle_state(self):
        for lot in self:
            if not lot.is_garment or not lot.max_wash_cycles:
                lot.lifecycle_state = False
                continue
            ratio = lot.wash_cycle_count / lot.max_wash_cycles
            threshold = (lot.garment_type_id.warning_cycles_threshold or 80) / 100.0
            if ratio >= 1.0:
                lot.lifecycle_state = "replace"
            elif ratio >= threshold:
                lot.lifecycle_state = "warning"
            else:
                lot.lifecycle_state = "ok"

    @api.depends("movement_ids")
    def _compute_movement_count(self):
        for lot in self:
            lot.movement_count = len(lot.movement_ids)

    @api.constrains("employee_id", "lifecycle_state")
    def _check_retired_assignment(self):
        for lot in self:
            if lot.employee_id and lot.lifecycle_state == "retired":
                raise ValidationError("Este EPC se encuentra fuera de operaciones (Retirada) y no puede ser asignado a un empleado.")

    def action_view_movements(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Movimientos - %s") % self.name,
            "res_model": "cycles.movement",
            "view_mode": "list,form",
            "domain": [("lot_id", "=", self.id)],
        }

    def _cycles_check_alerts(self):
        """Cron method: check garment alerts and create activities."""
        garments = self.search([("is_garment", "=", True)])
        today = fields.Datetime.now()

        for garment in garments:
            alerts = []
            # Alert: excess cycles
            if garment.lifecycle_state == "replace":
                alerts.append(
                    self.env._(
                        "La prenda ha alcanzado el máximo de ciclos de lavado (%s/%s)."
                    )
                    % (garment.wash_cycle_count, garment.max_wash_cycles)
                )

            # Alert: inactivity
            inactivity_days = garment.garment_type_id.inactivity_days or 30
            if garment.last_movement_date:
                days_since = (today - garment.last_movement_date).days
                if days_since > inactivity_days:
                    alerts.append(
                        self.env._("Sin movimiento en %s días (umbral: %s días).")
                        % (days_since, inactivity_days)
                    )

            if alerts:
                note = "\n".join(alerts)
                existing = self.env["mail.activity"].search(
                    [
                        ("res_model", "=", "stock.lot"),
                        ("res_id", "=", garment.id),
                        (
                            "activity_type_id",
                            "=",
                            self.env.ref("mail.mail_activity_data_todo").id,
                        ),
                        ("summary", "=", self.env._("Alerta de Prenda")),
                    ],
                    limit=1,
                )
                if not existing:
                    garment.activity_schedule(
                        "mail.mail_activity_data_todo",
                        summary=self.env._("Alerta de Prenda"),
                        note=note,
                    )

        # Alert: minimum inventory per garment type
        # Log low inventory warnings via the first garment of that type.
        # Ropería is provisioned per company, so resolve it per garment type.
        warehouse_env = self.env["stock.warehouse"]
        garment_types = self.env["cycles.garment.type"].search(
            [("min_inventory", ">", 0)]
        )
        for gtype in garment_types:
            warehouse = warehouse_env._cycles_get_warehouse(gtype.company_id)
            roperia = warehouse.cycles_loc_roperia_id
            if roperia:
                count = self.env["stock.quant"].search_count(
                    [
                        ("lot_id.garment_type_id", "=", gtype.id),
                        ("location_id", "=", roperia.id),
                        ("quantity", ">", 0),
                    ]
                )
                if count < gtype.min_inventory:
                    sample_garment = self.search(
                        [
                            ("garment_type_id", "=", gtype.id),
                        ],
                        limit=1,
                    )
                    if sample_garment:
                        existing = self.env["mail.activity"].search(
                            [
                                ("res_model", "=", "stock.lot"),
                                ("res_id", "=", sample_garment.id),
                                (
                                    "summary",
                                    "=",
                                    self.env._("Inventario Bajo: %s") % gtype.name,
                                ),
                            ],
                            limit=1,
                        )
                        if not existing:
                            sample_garment.activity_schedule(
                                "mail.mail_activity_data_todo",
                                summary=self.env._("Inventario Bajo: %s") % gtype.name,
                                note=self.env._(
                                    "Inventario bajo: %s prendas"
                                    " en Ropería (mínimo: %s)."
                                )
                                % (count, gtype.min_inventory),
                            )
