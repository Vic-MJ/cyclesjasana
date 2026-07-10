# -*- coding: utf-8 -*-
{
    "name": "Cycles Admin",
    "version": "19.0.1.0.0",
    "category": "Administration",
    "summary": "Panel de Administración Global para Cycles",
    "description": """
Cycles Admin
============
Módulo independiente para la administración global del sistema Cycles.
Permite a los administradores gestionar:
* Empresas
* Almacenes
* Usuarios
* Desglose completo de prendas (Stock Lots)
    """,
    "author": "Jasana",
    "license": "LGPL-3",
    "depends": ["base", "stock", "cycles"],
    'data': [
        'security/ir.model.access.csv',
        'views/res_company_views.xml',
        'views/cycles_admin_menus.xml',
        'views/res_config_settings_views.xml',
        'wizard/import_jasana_wizard_views.xml',
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
