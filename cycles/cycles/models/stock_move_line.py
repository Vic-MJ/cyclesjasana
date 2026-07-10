from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _action_done(self):
        res = super()._action_done()
        self._cycles_process_garment_movements()
        return res

    def _cycles_process_garment_movements(self):
        """After move lines are done, create garment movements and
        increment wash cycles."""
        # Guard clause first: skip the warehouse lookup for non-garment moves.
        garment_lines = self.filtered(
            lambda ml: ml.lot_id and ml.lot_id.is_garment and ml.picked
        )
        if not garment_lines:
            return

        # Laundry is provisioned per company, so resolve it for each company
        # the garment lines belong to (a wash is a move into that laundry).
        warehouse_env = self.env["stock.warehouse"]
        laundry_by_company = {}
        for company in garment_lines.company_id:
            warehouse = warehouse_env._cycles_get_warehouse(company)
            laundry_by_company[company.id] = warehouse.cycles_loc_lavanderia_id

        movement_vals = []
        lots_to_update = {}

        for ml in garment_lines:
            lot = ml.lot_id
            laundry_location = laundry_by_company.get(ml.company_id.id)
            is_wash = bool(laundry_location) and ml.location_dest_id == laundry_location

            movement_vals.append(
                {
                    "lot_id": lot.id,
                    "picking_id": ml.picking_id.id if ml.picking_id else False,
                    "location_from_id": ml.location_id.id,
                    "location_to_id": ml.location_dest_id.id,
                    "is_wash_cycle": is_wash,
                }
            )

            if lot.id not in lots_to_update:
                lots_to_update[lot.id] = {
                    "lot": lot,
                    "is_wash": is_wash,
                }
            elif is_wash:
                lots_to_update[lot.id]["is_wash"] = True

        # Batch create movements
        if movement_vals:
            self.env["cycles.movement"].create(movement_vals)

        # Update lots
        now = fields.Datetime.now()
        for data in lots_to_update.values():
            lot = data["lot"]
            vals = {"last_movement_date": now}
            if data["is_wash"]:
                vals["wash_cycle_count"] = lot.wash_cycle_count + 1
                vals["last_wash_date"] = now
            lot.write(vals)
