# -*- coding: utf-8 -*-
from odoo import api, fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    cycles_warehouse_ids = fields.One2many(
        'stock.warehouse', 'company_id', string='Almacenes'
    )


