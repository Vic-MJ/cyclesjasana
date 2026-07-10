from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError


class CyclesRfidProcessor(models.AbstractModel):
    _name = "cycles.rfid.processor"
    _description = "Procesador de Escaneo RFID"

    @api.model
    def get_scan_operations(self):
        """Return the list of available scan operations for the scanner UI.

        Resources are resolved from the active company's uniform warehouse so
        every operator scans against their own locations and operation types.
        """
        config = self.env["stock.warehouse"]._cycles_get_config()
        suppliers = self.env.ref("stock.stock_location_suppliers")
        roperia = config["roperia"]
        lavanderia = config["lavanderia"]
        en_uso = config["en_uso"]
        loc_baja = config.get("loc_baja")

        ops_def = [
            {
                "code": "en_uso",
                "name": "1- Ropería → En Uso",
                "image": "En_Uso.png",
                "picking_type": config["pick_traslado"],
                "location_src": roperia,
                "location_dest": en_uso,
                "needs_garment_type": False,
                "needs_employee": False,
                "no_stock_move": False,
            },
            {
                "code": "devolucion",
                "name": "2- En Uso → Lavandería",
                "image": "Devolucion_Lavanderia.png",
                "picking_type": config["pick_traslado"],
                "location_src": en_uso,
                "location_dest": lavanderia,
                "needs_garment_type": False,
                "needs_employee": False,
                "no_stock_move": False,
            },
            {
                "code": "retorno",
                "name": "3- Lavandería → Ropería",
                "image": "Retorno_Roperia.png",
                "picking_type": config["pick_traslado"],
                "location_src": lavanderia,
                "location_dest": roperia,
                "needs_garment_type": False,
                "needs_employee": False,
                "no_stock_move": False,
            },
            {
                "code": "asignacion",
                "name": "Asignación de Uniformes",
                "image": "Asignacion_Uniformes.png",
                "picking_type": config["pick_traslado"],
                "location_src": config["warehouse"].lot_stock_id,
                "location_dest": roperia,
                "needs_garment_type": False,
                "needs_employee": True,
                "no_stock_move": False,
            },
            {
                "code": "desasignacion",
                "name": "Desasignación de Uniformes",
                "image": "Desasignacion_Uniformes.png",
                "picking_type": config["pick_traslado"],
                "location_src": roperia,
                "location_dest": config["warehouse"].lot_stock_id,
                "needs_garment_type": False,
                "needs_employee": False,
                "no_stock_move": False,
            },
            {
                "code": "baja",
                "name": "Baja de Uniformes",
                "image": "Baja_Uniformes.png",
                "picking_type": config.get("pick_baja"),
                "location_src": loc_baja or roperia,
                "location_dest": loc_baja,
                "needs_garment_type": False,
                "needs_employee": False,
                "no_stock_move": False,
            },
            {
                "code": "entrada",
                "name": "Ingreso de Inventario",
                "image": "Entrrada_Roperia.png",
                "picking_type": config["pick_entrada"],
                "location_src": suppliers,
                "location_dest": config["warehouse"].lot_stock_id,
                "needs_garment_type": True,
                "needs_employee": False,
                "no_stock_move": False,
            },
        ]

        result = []
        for op in ops_def:
            picking_type = op["picking_type"]
            loc_src = op["location_src"]
            loc_dest = op["location_dest"]
            if not picking_type or not loc_src or not loc_dest:
                continue
            result.append(
                {
                    "code": op["code"],
                    "name": op["name"],
                    "image": op["image"],
                    "picking_type_id": picking_type.id,
                    "location_src_id": loc_src.id,
                    "location_src_name": loc_src.display_name,
                    "location_dest_id": loc_dest.id,
                    "location_dest_name": loc_dest.display_name,
                    "needs_garment_type": op["needs_garment_type"],
                    "needs_employee": op["needs_employee"],
                    "no_stock_move": op.get("no_stock_move", False),
                }
            )
        return result

    @api.model
    def resolve_epcs(self, epcs):
        # [MODIFICACION] Busca los nombres de producto en vivo
        # para mostrarlos en el escáner
        if not epcs:
            return {}
        lots = self.env["stock.lot"].search([
            ("name", "in", epcs),
            ("company_id", "=", self.env.company.id)
        ])
        return {
            lot.name: {
                "product_name": lot.product_id.display_name,
                "product_id": lot.product_id.id,
                "employee_name": lot.employee_id.name if lot.employee_id else False,
            } for lot in lots
        }

    @api.model
    def get_pending_receptions(self):
        """Return open incoming entries imported from Jasana.

        These are the pickings the RFID 'entrada' operation receives against.
        Each one lists its pending lines (garment type + demand) so the
        operator can pick which type to scan.
        """
        pickings = self.env["stock.picking"].search(
            [
                ("picking_type_id.code", "=", "incoming"),
                ("state", "in", ("assigned", "confirmed", "waiting")),
            ],
            order="scheduled_date asc",
        )
        result = []
        for picking in pickings:
            lines = []
            pending_moves = picking.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            )
            for move in pending_moves:
                gtype = move.product_id.product_tmpl_id.garment_type_id
                if not gtype:
                    # Automatically create the garment type on the fly
                    gtype = self.env["cycles.garment.type"].sudo().create({
                        "name": move.product_id.name,
                        "code": (move.product_id.default_code or
                                 move.product_id.name)[:20],
                        "product_tmpl_id": move.product_id.product_tmpl_id.id,
                    })
                    move.product_id.product_tmpl_id.sudo().garment_type_id = gtype.id
                # Odoo 17 pre-fills move lines. We only count lines that have a lot_name
                # or lot_id as actually scanned.
                scanned_lines = move.move_line_ids.filtered(
                    lambda ml: ml.lot_id or ml.lot_name)
                scanned_qty = sum(scanned_lines.mapped('quantity'))

                remaining = move.product_uom_qty - scanned_qty
                if remaining <= 0:
                    continue

                lines.append(
                    {
                        "garment_type_id": gtype.id,
                        "garment_type_name": move.product_id.display_name,
                        "product_id": move.product_id.id,
                        "demand": remaining,
                    }
                )
            result.append(
                {
                    "picking_id": picking.id,
                    "picking_name": picking.name,
                    "origin": picking.origin or "",
                    "partner_name": picking.partner_id.display_name or "",
                    "location_dest_name": picking.location_dest_id.display_name or "",
                    "lines": lines,
                }
            )
        return result

    @api.model
    def process_scan(
        self,
        epcs,
        operation_code,
        picking_type_id,
        location_src_id,
        location_dest_id,
        employee_id=None,
        garment_type_id=None,
        picking_id=None,
        auto_validate=True,
    ):
        """
        Process a bulk RFID scan.

        :param epcs: list of EPC strings (serial numbers)
        :param operation_code: str identifying the operation type
        :param picking_type_id: id of stock.picking.type
        :param location_src_id: id of source stock.location
        :param location_dest_id: id of destination stock.location
        :param employee_id: optional id of hr.employee (for deliveries)
        :param garment_type_id: optional id of cycles.garment.type (for entrada)
        :param picking_id: optional id of an existing incoming picking (from a
            confirmed PO) to receive against; only used for 'entrada'.
        :returns: dict with picking_id, picking_name, processed_count,
            error_count, errors
        """
        epcs = self._dedupe_epcs(epcs)
        if not epcs:
            raise UserError(self.env._("No hay EPCs para procesar."))

        # Entrada against an existing reception (the picking generated by a PO).
        if operation_code == "entrada" and picking_id:
            # When receiving against a picking, the UI dropdown sends the product_id 
            # in the garment_type_id parameter to support multiple sizes/variants.
            product_for_entrada = self.env["product.product"].browse(garment_type_id)
            if not product_for_entrada.exists():
                raise UserError(self.env._("Producto no válido."))
            return self._receive_against_picking(
                epcs, picking_id, product_for_entrada.id, auto_validate
            )

        # Early return block for desasignacion was removed to allow stock move creation

        # Baja: move each lot from its current location to Desechos.
        if operation_code == "baja":
            lots, errors = self._resolve_lots(epcs, None, create_missing=False)
            if not lots:
                raise UserError(
                    self.env._(
                        "No se encontraron prendas válidas.\nEPCs desconocidos:\n%s"
                    ) % "\n".join(errors[:20])
                )
            picking_type = self.env["stock.picking.type"].browse(picking_type_id)
            location_dest = self.env["stock.location"].browse(location_dest_id)
            return self._process_baja(lots, picking_type, location_dest)

        picking_type = self.env["stock.picking.type"].browse(picking_type_id)
        location_src = self.env["stock.location"].browse(location_src_id)
        location_dest = self.env["stock.location"].browse(location_dest_id)

        # For ad-hoc entrada (no PO): resolve garment type → product variant.
        product_for_entrada = None
        if operation_code == "entrada":
            product_for_entrada = self._resolve_entrada_product(garment_type_id)

        # Resolve lots (create missing only on entrada).
        lots, errors = self._resolve_lots(
            epcs,
            product_for_entrada,
            create_missing=operation_code == "entrada",
        )
        if not lots:
            raise UserError(
                self.env._("No se encontraron prendas válidas.\nEPCs desconocidos:\n%s")
                % "\n".join(errors[:20])
            )

        # [MODIFICACION] Para la Asignación, vinculamos el empleado a cada lote
        if operation_code == "asignacion":
            if not employee_id:
                raise UserError(
                    self.env._(
                        "Selecciona un empleado para la asignación de uniformes."
                    )
                )
            today = fields.Date.context_today(self)
            for lot in lots:
                if lot.employee_id:
                    raise UserError(
                        self.env._(
                            "Error de Asignación:\n"
                            "La prenda %s (%s) ya está asignada al empleado '%s'."
                        ) % (
                            lot.name, lot.product_id.display_name,
                            lot.employee_id.name))
                lot.write({
                    "employee_id": employee_id,
                    "assignment_date": today,
                })

        # [MODIFICACION] Limpiar el empleado para la desasignacion
        if operation_code == "desasignacion":
            for lot in lots:
                if not lot.employee_id:
                    raise UserError(
                        self.env._(
                            "Error de Desasignación:\n"
                            "La prenda %s (%s) no tiene un empleado asignado."
                        ) % (lot.name, lot.product_id.display_name))
                lot.write({
                    "employee_id": False,
                    "assignment_date": False,
                })

        # [MODIFICACION] Validacion de prenda asignada para operaciones de ciclo
        if operation_code in ("en_uso", "devolucion", "retorno"):
            for lot in lots:
                if not lot.employee_id:
                    raise UserError(
                        self.env._(
                            "Error de Validación:\n"
                            "La prenda %s (%s) no tiene un empleado asignado.\n"
                            "Debe asignarse antes de poder circular."
                        ) % (lot.name, lot.product_id.display_name)
                    )

        # [MODIFICACION] Validacion estricta del ciclo (ubicación de origen)
        if operation_code not in ("entrada", "asignacion", "baja"):
            quant_env = self.env["stock.quant"]
            for lot in lots:
                quant = quant_env.search([
                    ("lot_id", "=", lot.id),
                    ("quantity", ">", 0),
                    ("location_id.usage", "in", ("internal", "transit"))
                ], limit=1, order="quantity desc")

                if not quant:
                    raise UserError(
                        self.env._(
                            "Error de Ciclo:\n"
                            "La prenda %s (%s) no se encuentra en el inventario.\n"
                            "Se esperaba que estuviera en: '%s'."
                        ) % (
                            lot.name, lot.product_id.display_name,
                            location_src.display_name)
                    )
                if quant.location_id.id != location_src.id:
                    # Buscar los nombres de las operaciones para dar un mensaje más
                    # amigable
                    ops = self.get_scan_operations()
                    expected_op = next(
                        (
                            op for op in ops
                            if op.get("location_src_id") == quant.location_id.id
                        ), None)
                    current_op_name = (
                        expected_op["name"] if expected_op
                        else quant.location_id.display_name
                    )

                    attempted_op = next(
                        (op for op in ops if op.get("code") == operation_code), None)
                    attempted_op_name = (
                        attempted_op["name"] if attempted_op else operation_code
                    )

                    raise UserError(
                        self.env._(
                            "Error de Ciclo:\n"
                            "La prenda %s (%s) requiere la operación '%s'.\n"
                            "Estás intentando realizar la operación '%s'."
                        ) % (
                            lot.name, lot.product_id.display_name,
                            current_op_name, attempted_op_name
                        )
                    )

        # Group lots by product to create one stock.move per product
        lots_by_product = defaultdict(list)
        for lot in lots:
            lots_by_product[lot.product_id.id].append(lot)

        # Create picking
        picking_vals = {
            "picking_type_id": picking_type.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "origin": self.env._("Escaneo RFID"),
        }
        if employee_id and operation_code == "entrega":
            picking_vals["garment_employee_id"] = employee_id

        picking = self.env["stock.picking"].create(picking_vals)

        # Create moves and move lines
        for product_id, product_lots in lots_by_product.items():
            product = self.env["product.product"].browse(product_id)
            move = self.env["stock.move"].create(
                {
                    "product_id": product.id,
                    "product_uom_qty": len(product_lots),
                    "product_uom": product.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": location_src.id,
                    "location_dest_id": location_dest.id,
                }
            )
            self._create_move_lines(move, product, product_lots)

        # Validate picking (skip backorder/sms dialogs)
        picking.with_context(skip_backorder=True, skip_sms=True).button_validate()

        return {
            "picking_id": picking.id,
            "picking_name": picking.name,
            "processed_count": len(lots),
            "error_count": len(errors),
            "errors": errors[:10],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _process_baja(self, lots, picking_type, location_dest):

        quant_env = self.env["stock.quant"]
        lots_by_src = defaultdict(list)

        errors = []
        for lot in lots:
            quant = quant_env.search(
                [
                    ("lot_id", "=", lot.id),
                    ("location_id.usage", "=", "internal"),
                    ("quantity", ">", 0),
                ],
                limit=1,
                order="quantity desc",
            )
            if quant:
                lots_by_src[quant.location_id.id].append(lot)
            else:
                errors.append(lot.name)

        processed = 0
        picking_ids = []
        for src_loc_id, src_lots in lots_by_src.items():
            src_loc = self.env["stock.location"].browse(src_loc_id)
            lots_by_product = defaultdict(list)
            for lot in src_lots:
                lots_by_product[lot.product_id.id].append(lot)

            picking = self.env["stock.picking"].create({
                "picking_type_id": picking_type.id,
                "location_id": src_loc.id,
                "location_dest_id": location_dest.id,
                "origin": self.env._("Baja de Uniformes — Escaneo RFID"),
            })
            for product_id, product_lots in lots_by_product.items():
                product = self.env["product.product"].browse(product_id)
                move = self.env["stock.move"].create({
                    "product_id": product.id,
                    "product_uom_qty": len(product_lots),
                    "product_uom": product.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": src_loc.id,
                    "location_dest_id": location_dest.id,
                })
                self._create_move_lines(move, product, product_lots)

            picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
            picking_ids.append(picking.id)

            for lot in src_lots:
                lot.write({"lifecycle_state": "retired"})
            processed += len(src_lots)

        return {
            "picking_id": picking_ids[0] if picking_ids else False,
            "picking_name": self.env._("Baja de Uniformes"),
            "processed_count": processed,
            "error_count": len(errors),
            "errors": errors[:10],
        }

    def _dedupe_epcs(self, epcs):
        """Strip and de-duplicate the EPC list, preserving order.

        Backend-side deduplication so duplicate reads never create duplicate
        lots, regardless of what the scanner UI sends.
        """
        seen = set()
        result = []
        for epc in epcs or []:
            epc = (epc or "").strip()
            if epc and epc not in seen:
                seen.add(epc)
                result.append(epc)
        return result

    def _resolve_entrada_product(self, garment_type_id):
        if not garment_type_id:
            raise UserError(
                self.env._(
                    "Selecciona un tipo de prenda para operaciones de entrada."
                )
            )
        garment_type = self.env["cycles.garment.type"].browse(garment_type_id)
        tmpl = garment_type.product_tmpl_id
        if not tmpl:
            raise UserError(
                self.env._("El tipo de prenda '%s' no tiene producto vinculado.")
                % garment_type.name
            )
        product = tmpl.product_variant_id
        if not product:
            raise UserError(
                self.env._("El tipo de prenda '%s' no tiene variante de producto.")
                % garment_type.name
            )
        return product

    def _resolve_lots(self, epcs, product, create_missing):
        """Resolve EPCs to stock.lot records.

        :param product: expected product.product (or None for ops where the
            lot already exists with its own product).
        :param create_missing: create the lot when not found (entrada only).
        :returns: tuple (lots list, errors list of EPC strings).
        """
        lot_env = self.env["stock.lot"]
        company = self.env.company
        lots = []
        errors = []
        for epc in epcs:
            lot = lot_env.search(
                [("name", "=", epc), ("company_id", "=", company.id)], limit=1
            )
            if lot:
                # An existing EPC must belong to the expected product.
                if product and lot.product_id != product:
                    errors.append(epc)
                    continue
                lots.append(lot)
            elif create_missing and product:
                lots.append(
                    lot_env.create(
                        {
                            "name": epc,
                            "product_id": product.id,
                            "company_id": company.id,
                        }
                    )
                )
            else:
                errors.append(epc)
        return lots, errors

    def _create_move_lines(self, move, product, lots):
        for lot in lots:
            self.env["stock.move.line"].create(
                {
                    "move_id": move.id,
                    "picking_id": move.picking_id.id,
                    "product_id": product.id,
                    "lot_id": lot.id,
                    "quantity": 1.0,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                }
            )

    def _receive_against_picking(
            self,
            epcs,
            picking_id,
            product_id,
            auto_validate=True):
        """Receive scanned EPCs against an existing incoming picking."""
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists():
            raise UserError(self.env._("La recepción seleccionada no existe."))
        if picking.state in ("done", "cancel"):
            raise UserError(
                self.env._("La recepción %s ya está finalizada o cancelada.")
                % picking.name
            )

        product = self.env["product.product"].browse(product_id)
        if not product.exists():
            raise UserError("Producto inválido.")

        move = picking.move_ids.filtered(
            lambda m: m.product_id == product and m.state not in ("done", "cancel")
        )[:1]
        if not move:
            raise UserError(
                self.env._(
                    "La recepción %s no espera el tipo de prenda seleccionado."
                )
                % picking.name
            )

        lots, errors = self._resolve_lots(epcs, product, create_missing=True)
        if not lots:
            raise UserError(
                self.env._("No se encontraron prendas válidas.\nEPCs desconocidos:\n%s")
                % "\n".join(errors[:20])
            )

        # Delete dummy/empty lines across the entire picking so Odoo doesn't block
        # partial validation
        empty_lines = picking.move_line_ids.filtered(
            lambda ml: not ml.lot_id and not ml.lot_name)
        empty_lines.unlink()

        self._create_move_lines(move, product, lots)

        requires_backorder = False
        wizard_id = False
        if auto_validate:
            res = picking.with_context(skip_sms=True).button_validate()

            # If Odoo requests a backorder for the unscanned products, return it to UI
            if isinstance(res, dict) and res.get(
                    'res_model') == 'stock.backorder.confirmation':
                wizard = self.env['stock.backorder.confirmation'].with_context(
                    res.get('context', {})).create({'pick_ids': [(4, picking.id)]})
                requires_backorder = True
                wizard_id = wizard.id

        return {
            "picking_id": picking.id,
            "picking_name": picking.name,
            "processed_count": len(lots),
            "error_count": len(errors),
            "errors": errors[:10],
            "auto_validate": auto_validate,
            "requires_backorder": requires_backorder,
            "wizard_id": wizard_id,
        }

    @api.model
    def validate_picking(self, picking_id):
        """Validates an incoming picking directly, creating a backorder if necessary."""
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists() or picking.state in ("done", "cancel"):
            return False

        empty_lines = picking.move_line_ids.filtered(
            lambda ml: not ml.lot_id and not ml.lot_name)
        empty_lines.unlink()

        requires_backorder = False
        wizard_id = False
        res = picking.with_context(skip_sms=True).button_validate()
        if isinstance(res, dict) and res.get(
                'res_model') == 'stock.backorder.confirmation':
            wizard = self.env['stock.backorder.confirmation'].with_context(
                res.get('context', {})).create({'pick_ids': [(4, picking.id)]})
            requires_backorder = True
            wizard_id = wizard.id

        return {
            "picking_id": picking.id,
            "picking_name": picking.name,
            "requires_backorder": requires_backorder,
            "wizard_id": wizard_id,
        }

    @api.model
    def process_backorder_decision(self, wizard_id, create_backorder):
        """Processes the decision to create a backorder or cancel."""
        wizard = self.env['stock.backorder.confirmation'].browse(wizard_id)
        if not wizard.exists():
            return False

        if create_backorder:
            wizard.process()
        else:
            wizard.process_cancel_backorder()

        return True
