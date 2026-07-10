"""Migración a multicompañía: adopta la infraestructura heredada.

Las ubicaciones (Ropería/Lavandería/En Uso) y los tipos de operación dejaron
de declararse como singletons en el XML para provisionarse por almacén. Esta
post-migración corre antes de la limpieza de huérfanos del módulo, así que
adopta los registros existentes (re-enlazándolos al almacén y soltando su
``ir.model.data``) para que no se borren, y luego provisiona los almacenes que
aún no tengan infraestructura de uniformes.
"""

from odoo import api, SUPERUSER_ID

from odoo.addons.cycles.hooks import (
    _adopt_legacy_infrastructure,
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _adopt_legacy_infrastructure(env)
    warehouses = env["stock.warehouse"].with_context(active_test=False).search([])
    warehouses._cycles_provision()
