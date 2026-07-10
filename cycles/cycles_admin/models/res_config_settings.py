# -*- coding: utf-8 -*-
from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    jasana_url = fields.Char(string='URL de Jasana', config_parameter='cycles_admin.jasana_url')
    jasana_db = fields.Char(string='Base de Datos Jasana', config_parameter='cycles_admin.jasana_db')
    jasana_user = fields.Char(string='Usuario Jasana (Email)', config_parameter='cycles_admin.jasana_user')
    jasana_api_key = fields.Char(string='API Key Jasana', config_parameter='cycles_admin.jasana_api_key')
