from odoo import api, fields, models
from odoo.exceptions import UserError


class StockWarehouse(models.Model):
    """Owns the Cycles uniform infrastructure (locations + operation types).

    Each company has exactly one uniform warehouse. The three internal
    locations (Ropería, Lavandería, En Uso) and the three operation types
    (entrada, traslado, entrega) are provisioned per warehouse so the whole
    flow is company-scoped instead of pointing at a single global warehouse.
    """

    _inherit = "stock.warehouse"

    cycles_loc_roperia_id = fields.Many2one(
        "stock.location", string="Ubicación Ropería", copy=False
    )
    cycles_loc_lavanderia_id = fields.Many2one(
        "stock.location", string="Ubicación Lavandería", copy=False
    )
    cycles_loc_en_uso_id = fields.Many2one(
        "stock.location", string="Ubicación En Uso", copy=False
    )
    cycles_loc_baja_id = fields.Many2one(
        "stock.location", string="Ubicación Desechos (Baja)", copy=False
    )
    cycles_pick_type_entrada_id = fields.Many2one(
        "stock.picking.type", string="Tipo Entrada Uniformes", copy=False
    )
    cycles_pick_type_traslado_id = fields.Many2one(
        "stock.picking.type", string="Tipo Traslado Uniformes", copy=False
    )
    cycles_pick_type_entrega_id = fields.Many2one(
        "stock.picking.type", string="Tipo Entrega Uniformes", copy=False
    )
    cycles_pick_type_baja_id = fields.Many2one(
        "stock.picking.type", string="Tipo Baja Uniformes", copy=False
    )

    # ------------------------------------------------------------------
    # Provisioning
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        warehouses = super().create(vals_list)
        for warehouse in warehouses:
            warehouse._cycles_provision()
        return warehouses

    def _cycles_provision(self):
        """Create the uniform locations/operation types for this warehouse.

        Idempotent: each resource is only created when its field is empty,
        so it is safe to call on warehouse creation and from the post-init
        migration for pre-existing warehouses.
        """
        for warehouse in self:
            warehouse._cycles_provision_locations()
            warehouse._cycles_provision_picking_types()

    def _cycles_provision_locations(self):
        self.ensure_one()
        location_env = self.env["stock.location"]
        loc_defs = [
            ("cycles_loc_roperia_id", "Roperia", "ROPERIA"),
            ("cycles_loc_en_uso_id", "En Uso", "ENUSO"),
            ("cycles_loc_lavanderia_id", "Lavanderia", "LAVANDERIA"),
            ("cycles_loc_baja_id", "Desechos", "BAJA"),
        ]
        for field_name, name, barcode in loc_defs:
            if self[field_name]:
                continue
            usage = "inventory" if field_name == "cycles_loc_baja_id" else "internal"
            barcode_val = "%s-%s" % (self.code, barcode)
            location = location_env.search(
                [
                    ("barcode", "=", barcode_val),
                    ("company_id", "=", self.company_id.id),
                ],
                limit=1,
            )
            if not location:
                location = location_env.create(
                    {
                        "name": name,
                        "usage": usage,
                        "location_id": self.lot_stock_id.id,
                        "company_id": self.company_id.id,
                        "barcode": barcode_val,
                    }
                )
            self[field_name] = location.id

    def _cycles_provision_picking_types(self):
        self.ensure_one()
        pick_type_env = self.env["stock.picking.type"]
        supplier_loc = self.env.ref("stock.stock_location_suppliers")
        # (field, name, code, sequence_code, src, dest, create_lots,
        #  existing_lots, create_backorder, barcode)
        type_defs = [
            (
                "cycles_pick_type_entrada_id",
                "Entrada Uniformes",
                "incoming",
                "UNIF/IN",
                supplier_loc,
                self.lot_stock_id,
                True,
                False,
                "always",
                "ENTRADA",
            ),
            (
                "cycles_pick_type_traslado_id",
                "Traslado Uniformes",
                "internal",
                "UNIF/INT",
                self.cycles_loc_roperia_id,
                self.cycles_loc_en_uso_id,
                False,
                True,
                "ask",
                "TRASLADO",
            ),
            (
                "cycles_pick_type_entrega_id",
                "Entrega Uniformes",
                "internal",
                "UNIF/ENT",
                self.cycles_loc_roperia_id,
                self.cycles_loc_en_uso_id,
                False,
                True,
                "ask",
                "ENTREGA",
            ),
            (
                "cycles_pick_type_baja_id",
                "Baja Uniformes",
                "outgoing",
                "UNIF/BAJA",
                self.cycles_loc_baja_id,
                self.cycles_loc_baja_id,
                False,
                True,
                "ask",
                "BAJA",
            ),
        ]
        for (
            field_name,
            name,
            code,
            seq_code,
            src,
            dest,
            create_lots,
            existing_lots,
            backorder,
            barcode,
        ) in type_defs:
            if self[field_name]:
                continue
            barcode_val = "%s-UNIF-%s" % (self.code, barcode)
            picking_type = pick_type_env.search(
                [
                    ("barcode", "=", barcode_val),
                    ("company_id", "=", self.company_id.id),
                ],
                limit=1,
            )
            if not picking_type:
                picking_type = pick_type_env.create(
                    {
                        "name": name,
                        "code": code,
                        "sequence_code": seq_code,
                        "warehouse_id": self.id,
                        "company_id": self.company_id.id,
                        "default_location_src_id": src.id,
                        "default_location_dest_id": dest.id,
                        "use_create_lots": create_lots,
                        "use_existing_lots": existing_lots,
                        "create_backorder": backorder,
                        "barcode": barcode_val,
                    }
                )
            self[field_name] = picking_type.id

    # ------------------------------------------------------------------
    # Resolver
    # ------------------------------------------------------------------

    @api.model
    def _cycles_get_warehouse(self, company=None):
        """Return the uniform warehouse of the given company.

        Picks the warehouse that already has the uniform infrastructure
        provisioned; falls back to the company's first warehouse.
        """
        company = company or self.env.company
        warehouse = self.search(
            [
                ("company_id", "=", company.id),
                ("cycles_loc_roperia_id", "!=", False),
            ],
            limit=1,
        )
        if not warehouse:
            warehouse = self.search(
                [("company_id", "=", company.id)], limit=1
            )
        return warehouse

    @api.model
    def _cycles_get_config(self, company=None):
        """Return the resolved uniform resources for a company.

        :returns: dict with keys warehouse, roperia, lavanderia, en_uso,
            pick_entrada, pick_traslado, pick_entrega.
        :raises UserError: if the company has no provisioned uniform warehouse.
        """
        company = company or self.env.company
        warehouse = self._cycles_get_warehouse(company)
        if not warehouse or not warehouse.cycles_loc_roperia_id:
            raise UserError(
                self.env._(
                    "La compañía '%s' no tiene un almacén de uniformes"
                    " configurado. Reinstala o actualiza el módulo Cycles."
                )
                % company.display_name
            )
        return {
            "warehouse": warehouse,
            "roperia": warehouse.cycles_loc_roperia_id,
            "lavanderia": warehouse.cycles_loc_lavanderia_id,
            "en_uso": warehouse.cycles_loc_en_uso_id,
            "loc_baja": warehouse.cycles_loc_baja_id,
            "pick_entrada": warehouse.cycles_pick_type_entrada_id,
            "pick_traslado": warehouse.cycles_pick_type_traslado_id,
            "pick_entrega": warehouse.cycles_pick_type_entrega_id,
            "pick_baja": warehouse.cycles_pick_type_baja_id,
        }
