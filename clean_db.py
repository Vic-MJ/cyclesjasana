import logging

_logger = logging.getLogger(__name__)

def clean_database(env):
    _logger.info("INICIANDO LIMPIEZA DE BASE DE DATOS")
    
    # 1. Renombrar Compañía y Usuario Admin
    company = env['res.company'].search([], limit=1)
    if company:
        company.write({'name': 'ADMINISTRACIÓN CYCLES'})
        _logger.info("Empresa renombrada a ADMINISTRACIÓN CYCLES")

    # Assuming user 2 is admin (Odoo default)
    admin_user = env['res.users'].browse(2)
    if admin_user.exists():
        admin_user.write({'login': 'admin@cycles.com', 'email': 'admin@cycles.com'})
        _logger.info("Usuario admin renombrado a admin@cycles.com")

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
    try:
        env.cr.execute("DELETE FROM stock_valuation_layer")
    except Exception:
        pass
    _logger.info("Operaciones de inventario eliminadas por SQL")

    # 4. Borrar Lotes (EPCs)
    env.cr.execute("DELETE FROM stock_lot")
    _logger.info("Lotes (EPCs) eliminados por SQL")

    # 5. Borrar Empleados
    env.cr.execute("DELETE FROM hr_employee")
    _logger.info("Empleados eliminados por SQL")

    # 6. Borrar Tipos de Prenda y Productos
    env.cr.execute("DELETE FROM cycles_garment_type")
    
    try:
        env['product.product'].search([]).unlink()
        env['product.template'].search([]).unlink()
        _logger.info("Productos eliminados mediante ORM")
    except Exception as e:
        _logger.error(f"Error borrando productos por ORM, forzando por SQL: {e}")
        env.cr.execute("DELETE FROM product_product")
        env.cr.execute("DELETE FROM product_template")

    env.cr.commit()
    _logger.info("LIMPIEZA FINALIZADA CON ÉXITO")

clean_database(env)
