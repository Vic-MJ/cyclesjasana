{
    "name": "Cycles - Uniform RFID Management",
    "version": "19.0.2.2.0",
    "category": "Supply Chain/Inventory",
    "summary": "RFID-based uniform lifecycle management for hotels",
    "description": """
Cycles - Gestión de Uniformes con RFID
=======================================
* Gestión de tipos de prendas con ciclos máximos de lavado
* Seguimiento individual por EPC/RFID
* Conteo automático de ciclos de lavado
* Asignación de prendas a empleados
* Lectura masiva RFID con deduplicación
* Reportes: inventario, ciclos, prendas por empleado, alertas
    """,
    "author": "Jasana",
    "license": "LGPL-3",
    "depends": ["stock", "hr", "purchase", "purchase_stock"],
    "data": [
        "security/cycles_security.xml",
        "security/ir.model.access.csv",
        "data/cycles_data.xml",
        "data/cycles_cron.xml",
        "views/garment_type_views.xml",
        "views/garment_views.xml",
        "views/movement_views.xml",
        "views/stock_picking_views.xml",
        "views/hr_employee_views.xml",
        "views/dashboard_views.xml",
        "views/epc_replace_wizard_views.xml",
        "views/menus.xml",
        "views/rfid_scanner_views.xml",
        "views/audit_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "cycles/static/src/scss/rfid_scanner.scss",
            "cycles/static/src/js/rfid_scanner.js",
            "cycles/static/src/xml/rfid_scanner.xml",
            "cycles/static/src/js/cycles_audit.js",
            "cycles/static/src/xml/cycles_audit.xml",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
