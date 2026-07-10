# -*- coding: utf-8 -*-
from odoo import api, fields, models

class ResUsers(models.Model):
    _inherit = 'res.users'

    cycles_admin_role = fields.Selection([
        ('none', 'Ninguno (Sin acceso)'),
        ('user', 'Usuario (Lectura/Operación)'),
        ('manager', 'Administrador (Configuración)')
    ], string='Permisos de Cycles', compute='_compute_cycles_admin_role', inverse='_inverse_cycles_admin_role')

    generated_password = fields.Char(string='Contraseña Generada', copy=False, help="Contraseña temporal generada para copiar")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'generated_password' in fields_list or 'password' in fields_list:
            import random
            import string
            chars = string.ascii_letters + string.digits
            new_pass = ''.join(random.choice(chars) for _ in range(10))
            if 'generated_password' in fields_list:
                res['generated_password'] = new_pass
            if 'password' in fields_list:
                res['password'] = new_pass
        return res

    def action_generate_password(self):
        for user in self:
            import random
            import string
            chars = string.ascii_letters + string.digits
            new_pass = ''.join(random.choice(chars) for _ in range(10))
            user.password = new_pass
            user.generated_password = new_pass
        return True

    def _compute_cycles_admin_role(self):
        for user in self:
            # We can use has_group which is safer and doesn't require complex depends
            if user.has_group('cycles.group_cycles_manager'):
                user.cycles_admin_role = 'manager'
            elif user.has_group('cycles.group_cycles_user'):
                user.cycles_admin_role = 'user'
            else:
                user.cycles_admin_role = 'none'

    def _inverse_cycles_admin_role(self):
        group_user = self.env.ref('cycles.group_cycles_user', raise_if_not_found=False)
        group_manager = self.env.ref('cycles.group_cycles_manager', raise_if_not_found=False)
        
        if not group_user or not group_manager:
            return

        for user in self:
            if user.cycles_admin_role == 'manager':
                # Add manager and user
                group_manager.sudo().write({'user_ids': [(4, user.id)]})
                group_user.sudo().write({'user_ids': [(4, user.id)]})
            elif user.cycles_admin_role == 'user':
                # Add user, remove manager
                group_user.sudo().write({'user_ids': [(4, user.id)]})
                group_manager.sudo().write({'user_ids': [(3, user.id)]})
            else:
                # Remove both
                group_manager.sudo().write({'user_ids': [(3, user.id)]})
                group_user.sudo().write({'user_ids': [(3, user.id)]})
