from odoo import api, models


class CyclesAudit(models.AbstractModel):
    _name = "cycles.audit"
    _description = "Auditoría RFID de Inventario"

    @api.model
    def get_audit_config_data(self):
        """Return locations and garment types for the audit config step."""
        locations = self.env["stock.location"].search(
            [
                ("usage", "=", "internal"),
                ("company_id", "in", [False, self.env.company.id]),
            ],
            order="complete_name asc",
        )
        garment_types = self.env["cycles.garment.type"].search(
            [("active", "=", True)],
            order="name asc",
        )
        return {
            "locations": [
                {"id": loc.id, "name": loc.display_name}
                for loc in locations
            ],
            "garment_types": [
                {"id": gt.id, "name": gt.name}
                for gt in garment_types
            ],
        }

    @api.model
    def load_expected_inventory(self, location_id, garment_type_ids):
        """Return lots expected at location filtered by garment types.

        :param location_id: id of stock.location to audit
        :param garment_type_ids: list of cycles.garment.type ids to include;
            empty list means all garment types
        :returns: list of dicts with lot details
        """
        quants = self.env["stock.quant"].search(
            [
                ("location_id", "=", location_id),
                ("lot_id", "!=", False),
                ("quantity", ">", 0),
            ]
        )
        garment_quants = quants.filtered(lambda q: q.lot_id.is_garment)
        if garment_type_ids:
            type_set = set(garment_type_ids)
            garment_quants = garment_quants.filtered(
                lambda q: q.lot_id.garment_type_id.id in type_set
            )
        result = []
        for quant in garment_quants:
            lot = quant.lot_id
            gt = lot.garment_type_id
            result.append(
                {
                    "lot_id": lot.id,
                    "lot_name": lot.name,
                    "product_id": lot.product_id.id,
                    "product_name": lot.product_id.display_name,
                    "garment_type_id": gt.id if gt else False,
                    "garment_type_name": gt.name if gt else "",
                }
            )
        return result

    @api.model
    def process_audit(self, scanned_epcs, location_id, garment_type_ids):
        """Reconcile scanned EPCs against the expected inventory.

        EPCs that do not match the location+garment_type filter are excluded
        (ignored) and never counted as found or missing.

        :param scanned_epcs: list of EPC strings read by the RFID scanner
        :param location_id: id of stock.location being audited
        :param garment_type_ids: list of cycles.garment.type ids (empty = all)
        :returns: dict with found/missing/ignored counts and detail lists
        """
        # Deduplicate preserving order (same logic as cycles.rfid.processor)
        seen: set = set()
        deduped = []
        for epc in scanned_epcs or []:
            epc = (epc or "").strip()
            if epc and epc not in seen:
                seen.add(epc)
                deduped.append(epc)

        expected = self.load_expected_inventory(location_id, garment_type_ids)
        expected_epc_set = {item["lot_name"] for item in expected}

        found_epcs = []
        ignored_epcs = []
        for epc in deduped:
            if epc in expected_epc_set:
                found_epcs.append(epc)
            else:
                ignored_epcs.append(epc)

        found_set = set(found_epcs)
        missing_lots = [
            item for item in expected if item["lot_name"] not in found_set
        ]

        # Breakdown by garment type
        summary: dict = {}
        for item in expected:
            gt_name = item["garment_type_name"] or "Sin tipo"
            if gt_name not in summary:
                summary[gt_name] = {"expected": 0, "found": 0, "missing": 0}
            summary[gt_name]["expected"] += 1
            if item["lot_name"] in found_set:
                summary[gt_name]["found"] += 1
            else:
                summary[gt_name]["missing"] += 1

        return {
            "found_count": len(found_epcs),
            "missing_count": len(missing_lots),
            "ignored_count": len(ignored_epcs),
            "missing_lots": missing_lots[:50],
            "ignored_epcs": ignored_epcs[:20],
            "by_garment_type": [
                {
                    "name": name,
                    "expected": data["expected"],
                    "found": data["found"],
                    "missing": data["missing"],
                }
                for name, data in sorted(summary.items())
            ],
        }
