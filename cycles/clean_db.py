import logging

_logger = logging.getLogger(__name__)

def clean_database(env):
    _logger.info("INICIANDO LIMPIEZA DE BASE DE DATOS")
    
    # 1. Renombrar Compañía y Usuario Admin
    main_company = env['res.company'].search([('name', '=', 'ADMINISTRACIÓN CYCLES')], limit=1)
    if not main_company:
        main_company = env['res.company'].search([], limit=1)
        main_company.write({'name': 'ADMINISTRACIÓN CYCLES'})
    _logger.info("Empresa principal asegurada: ADMINISTRACIÓN CYCLES")

    admin_user = env['res.users'].search([('login', '=', 'admin@cycles.com')], limit=1)
    if not admin_user:
        admin_user = env['res.users'].browse(2)
        admin_user.write({'login': 'admin@cycles.com', 'email': 'admin@cycles.com'})
    _logger.info("Usuario principal asegurado: admin@cycles.com")

    # Reasignar compañía del admin
    admin_user.write({
        'company_id': main_company.id,
        'company_ids': [(6, 0, [main_company.id])]
    })

    # Archivar otros usuarios excepto portal, public, odoobot y el admin
    protected_users = [admin_user.id]
    protected_logins = ['public', 'portaltemplate', 'default', 'odoobot']
    other_users = env['res.users'].search([('id', 'not in', protected_users), ('login', 'not in', protected_logins)])
    for u in other_users:
        try:
            u.write({'active': False})
        except Exception:
            pass
    _logger.info("Otros usuarios archivados")

    # Archivar otras compañías
    other_companies = env['res.company'].search([('id', '!=', main_company.id)])
    for c in other_companies:
        try:
            c.write({'active': False})
        except Exception:
            pass
    _logger.info("Otras empresas archivadas")


    # 2. Borrar Movimientos RFID (Cycles)
    movements = env['cycles.movement'].search([])
    movements.unlink()
    _logger.info("Movimientos de Cycles eliminados")

    # 3. Borrar Operaciones de Stock
    # To delete stock moves/pickings, we must bypass the state checks
    env.cr.execute("DELETE FROM stock_move_line")
    env.cr.execute("DELETE FROM stock_move")
    env.cr.execute("DELETE FROM stock_picking")
    env.cr.execute("DELETE FROM stock_quant")
    _logger.info("Operaciones de inventario eliminadas por SQL")

    # 4. Borrar Lotes (EPCs)
    env.cr.execute("DELETE FROM stock_lot")
    _logger.info("Lotes (EPCs) eliminados por SQL")

    # 5. Borrar Empleados
    env.cr.execute("DELETE FROM hr_employee")
    _logger.info("Empleados eliminados por SQL")

    # 6. Borrar Tipos de Prenda y Productos
    env.cr.execute("DELETE FROM cycles_garment_type")
    
    # We must delete product_product and product_template by SQL to avoid constraints
    env.cr.execute("DELETE FROM product_product")
    env.cr.execute("DELETE FROM product_template")

    env.cr.commit()
    _logger.info("LIMPIEZA FINALIZADA CON ÉXITO")

clean_database(env)
