"""Provisiona la nueva infraestructura de baja en almacenes existentes.

La operación "Baja de Uniformes" añade una ubicación tipo scrap
(``cycles_loc_baja_id``) y su tipo de operación (``cycles_pick_type_baja_id``).
``_cycles_provision`` es idempotente (solo crea lo que falta), pero el
``post_init_hook`` solo corre en instalación, no en upgrade, así que esta
post-migración lo dispara para cada almacén ya existente.
"""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    warehouses = env["stock.warehouse"].with_context(active_test=False).search([])
    warehouses._cycles_provision()
