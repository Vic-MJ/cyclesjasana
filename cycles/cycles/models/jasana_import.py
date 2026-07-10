import logging

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CyclesJasanaImport(models.AbstractModel):
    """Service exposed via the standard Odoo external API (JSON-RPC).

    Jasana (origen) calls ``import_inventory_entry`` through ``execute_kw``
    to push the validated deliveries of a sale order as an incoming
    inventory entry in Cycles (destino). All the mapping/domain logic lives
    here so the origin side only needs to build a plain payload.
    """

    _name = "cycles.jasana.import"
    _description = "Importador de Entradas desde Jasana"

    @api.model
    def import_inventory_entry(self, payload):
        """Create an incoming inventory entry from a Jasana sale order.

        :param payload: dict with keys:
            - external_ref (str): stable unique id of the source document.
            - origin (str): human readable source reference (SO name).
            - client_order_ref (str): customer reference, used as origin.
            - partner (dict): {name, vat, email} of the supplier (Jasana).
            - lines (list[dict]): {code, name, qty, price_unit,
              description_sale, barcode, list_price, image, attributes}.
        :returns: dict with picking_id, name, created.
        """
        external_ref = (payload or {}).get("external_ref")
        if not external_ref:
            raise UserError(self.env._("Falta 'external_ref' en el payload."))

        lines = payload.get("lines") or []
        if not lines:
            raise UserError(
                self.env._("El pedido %s no tiene líneas para importar.")
                % payload.get("origin", external_ref)
            )

        # Idempotency: never duplicate a previously imported document.
        existing = self.env["stock.picking"].search(
            [("jasana_external_ref", "=", external_ref)], limit=1
        )
        if existing:
            _logger.info(
                "Jasana import: entrada %s ya existe para ref %s (idempotente).",
                existing.name,
                external_ref,
            )
            return self._build_result(existing, created=False)

        partner = self._resolve_partner(payload.get("partner") or {})
        picking_type = self.env["stock.warehouse"]._cycles_get_config()[
            "pick_entrada"
        ]
        moves = [
            (0, 0, self._prepare_move_vals(line, picking_type)) for line in lines
        ]
        picking = self.env["stock.picking"].create(
            self._prepare_picking_vals(payload, partner, picking_type, moves)
        )
        picking.action_confirm()
        _logger.info(
            "Jasana import: entrada %s creada desde %s.",
            picking.name,
            payload.get("origin", external_ref),
        )
        return self._build_result(picking, created=True)

    # ------------------------------------------------------------------
    # Helpers (small and overridable)
    # ------------------------------------------------------------------

    def _resolve_partner(self, partner_data):
        """Find or create the supplier partner (the Jasana company)."""
        partner_env = self.env["res.partner"]
        vat = (partner_data.get("vat") or "").strip()
        name = (partner_data.get("name") or "").strip()
        partner = partner_env.browse()
        if vat:
            partner = partner_env.search([("vat", "=", vat)], limit=1)
        if not partner and name:
            partner = partner_env.search([("name", "=", name)], limit=1)
        if not partner:
            if not name:
                raise UserError(
                    self.env._("Falta el nombre del proveedor en el payload.")
                )
            partner = partner_env.create(
                {
                    "name": name,
                    "vat": vat or False,
                    "email": partner_data.get("email") or False,
                    "supplier_rank": 1,
                    "company_type": "company",
                }
            )
        elif not partner.supplier_rank:
            partner.supplier_rank = 1
        return partner

    def _resolve_garment_type(self, line):
        """Map a payload line to a cycles.garment.type by code (SKU).

        Auto-creates the garment type (and its serial product) if missing.
        """
        code = (line.get("code") or "").strip()
        if not code:
            raise UserError(
                self.env._(
                    "La línea '%s' no tiene código (SKU) y no puede mapearse"
                    " a un tipo de prenda."
                )
                % (line.get("name") or "")
            )
        garment_type_env = self.env["cycles.garment.type"]
        garment_type = garment_type_env.search([("code", "=", code)], limit=1)
        if not garment_type:
            garment_type = garment_type_env.create(
                {
                    "name": line.get("name") or code,
                    "code": code,
                }
            )
            # Recién creado: replicar los datos del producto de origen (Jasana).
            self._sync_product_fields(garment_type.product_tmpl_id, line)
        return garment_type

    def _resolve_product(self, line):
        garment_type = self._resolve_garment_type(line)
        product = garment_type.product_tmpl_id.product_variant_id
        if not product:
            raise UserError(
                self.env._("El tipo de prenda '%s' no tiene variante de producto.")
                % garment_type.name
            )
        return product

    def _sync_product_fields(self, template, line):
        """Copia descripción de ventas, imagen, precio y atributos al producto."""
        if not template:
            return
        vals = {}
        if line.get("description_sale"):
            vals["description_sale"] = line["description_sale"]
        if line.get("list_price"):
            vals["list_price"] = line["list_price"]
        if line.get("image"):
            vals["image_1920"] = line["image"]
        if vals:
            template.write(vals)
        self._sync_product_attributes(template, line.get("attributes") or [])
        # El código de barras vive en la variante (producto de variante única).
        barcode = (line.get("barcode") or "").strip()
        variant = template.product_variant_id
        if barcode and variant and not variant.barcode:
            variant.barcode = barcode

    def _sync_product_attributes(self, template, attributes):
        """Replica los atributos del origen, reutilizando los de Cycles.

        Solo se crea un atributo (o valor) cuando no existe ya uno con el
        mismo nombre. Los atributos nuevos se crean como ``no_variant`` para
        no generar combinaciones: usar un único valor por atributo mantiene
        el tipo de prenda como un producto de variante única.
        """
        attribute_env = self.env["product.attribute"]
        value_env = self.env["product.attribute.value"]
        attr_lines = []
        for attr in attributes:
            attr_name = (attr.get("attribute") or "").strip()
            val_name = (attr.get("value") or "").strip()
            if not attr_name or not val_name:
                continue
            attribute = attribute_env.search(
                [("name", "=", attr_name)], limit=1
            )
            if not attribute:
                attribute = attribute_env.create(
                    {"name": attr_name, "create_variant": "no_variant"}
                )
            value = value_env.search(
                [("attribute_id", "=", attribute.id), ("name", "=", val_name)],
                limit=1,
            )
            if not value:
                value = value_env.create(
                    {"attribute_id": attribute.id, "name": val_name}
                )
            attr_lines.append(
                (
                    0,
                    0,
                    {"attribute_id": attribute.id, "value_ids": [(4, value.id)]},
                )
            )
        if attr_lines:
            template.write({"attribute_line_ids": attr_lines})

    def _prepare_move_vals(self, line, picking_type):
        product = self._resolve_product(line)
        return {
            "description_picking": line.get("name") or product.display_name,
            "product_id": product.id,
            "product_uom_qty": line.get("qty") or 0.0,
            "product_uom": product.uom_id.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": picking_type.default_location_dest_id.id,
        }

    def _prepare_picking_vals(self, payload, partner, picking_type, moves):
        # The incoming picking type already targets Ropería with
        # use_create_lots=True, so the RFID reception lands stock there.
        return {
            "picking_type_id": picking_type.id,
            "partner_id": partner.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": picking_type.default_location_dest_id.id,
            "origin": (
                payload.get("client_order_ref")
                or payload.get("origin")
                or payload["external_ref"]
            ),
            "jasana_external_ref": payload["external_ref"],
            "move_ids": moves,
        }

    def _build_result(self, picking, created):
        return {
            "picking_id": picking.id,
            "name": picking.name,
            "created": created,
        }
