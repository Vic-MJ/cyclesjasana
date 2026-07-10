import logging

_logger = logging.getLogger(__name__)

# Legacy global XML IDs created by the pre-multicompany version of the module.
# They are adopted (re-linked to the owning warehouse) instead of recreated so
# historical lots/movements/quants stay valid.
_LEGACY_LOCATION_XMLIDS = {
    "cycles_loc_roperia_id": "cycles.stock_location_roperia",
    "cycles_loc_en_uso_id": "cycles.stock_location_en_uso",
    "cycles_loc_lavanderia_id": "cycles.stock_location_lavanderia",
}
_LEGACY_PICKING_TYPE_XMLIDS = {
    "cycles_pick_type_entrada_id": "cycles.picking_type_entrada",
    "cycles_pick_type_traslado_id": "cycles.picking_type_traslado",
    "cycles_pick_type_entrega_id": "cycles.picking_type_entrega",
}


def _adopt_legacy_infrastructure(env):
    """Re-link the old global locations/picking types to their warehouse.

    Runs once when upgrading from the pre-multicompany version. After the
    legacy records are wired into the warehouse fields, their ``ir.model.data``
    rows are dropped so the module's orphan cleanup (those records are no
    longer in the XML) does not delete them on update.
    """
    roperia = env.ref(
        _LEGACY_LOCATION_XMLIDS["cycles_loc_roperia_id"], raise_if_not_found=False
    )
    if not roperia:
        return  # Fresh install: nothing to adopt.

    # The legacy Ropería hangs off the warehouse's WH/Stock (lot_stock_id).
    warehouse = env["stock.warehouse"].search(
        [("lot_stock_id", "=", roperia.location_id.id)], limit=1
    )
    if not warehouse:
        warehouse = env["stock.warehouse"].search(
            [("company_id", "=", roperia.company_id.id or env.company.id)], limit=1
        )
    if not warehouse:
        return

    detach_xmlids = []
    for field_name, xmlid in _LEGACY_LOCATION_XMLIDS.items():
        record = env.ref(xmlid, raise_if_not_found=False)
        if record and not warehouse[field_name]:
            record.company_id = warehouse.company_id.id
            warehouse[field_name] = record.id
            detach_xmlids.append(xmlid)
    for field_name, xmlid in _LEGACY_PICKING_TYPE_XMLIDS.items():
        record = env.ref(xmlid, raise_if_not_found=False)
        if record and not warehouse[field_name]:
            warehouse[field_name] = record.id
            detach_xmlids.append(xmlid)

    # Detach the xmlids so the records survive the module orphan cleanup.
    for xmlid in detach_xmlids:
        module, name = xmlid.split(".", 1)
        imd = env["ir.model.data"].search(
            [("module", "=", module), ("name", "=", name)], limit=1
        )
        imd.unlink()

    _logger.info(
        "Cycles: infraestructura heredada adoptada por el almacén %s.",
        warehouse.display_name,
    )


def post_init_hook(env):
    """Provision uniform infrastructure for every existing warehouse.

    Company 1's legacy records are adopted first; the remaining warehouses
    (other companies) get their own locations and operation types created.
    """
    _adopt_legacy_infrastructure(env)
    warehouses = env["stock.warehouse"].with_context(active_test=False).search([])
    warehouses._cycles_provision()
