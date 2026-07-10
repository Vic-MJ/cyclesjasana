import psycopg2

print("=== INICIANDO DESTRUCCIÓN TOTAL EN CASCADA ===")

companies_to_delete = ['PRUEBAS JSN', 'HG', 'My Company']
companies = env['res.company'].with_context(active_test=False).search(['|', '|', ('name', 'ilike', 'PRUEBAS JSN'), ('name', 'ilike', 'HG'), ('name', 'ilike', 'My Company')])

if not companies:
    print("No se encontraron empresas con esos nombres.")
else:
    company_ids = tuple(companies.ids)
    print(f"Empresas a destruir (IDs): {company_ids}")

    # Encontrar TODAS las tablas que hacen referencia a res_company
    env.cr.execute("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name
          AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name='res_company';
    """)
    
    fk_references = env.cr.fetchall()
    
    # Algunas tablas son criticas y no queremos borrarlas enteras si no que limpiar la referencia (SET NULL)
    # pero el usuario pidió destruir los registros, así que lo haremos con cuidado.
    # Repetiremos el proceso hasta que pase limpio (por si hay dependencias de dependencias)
    
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            with env.cr.savepoint():
                env.cr.execute("DELETE FROM res_company WHERE id IN %s", (company_ids,))
            print("DESTRUCCIÓN DE EMPRESAS COMPLETADA CON ÉXITO.")
            break
        except psycopg2.errors.ForeignKeyViolation as e:
            error_msg = str(e)
            print(f"Dependencia encontrada, limpiando... (Intento {attempt+1}/{max_attempts})")
            
            # Borrar todos los registros en tablas que referencian a estas empresas
            for table_name, column_name in fk_references:
                # Ignoramos res_users porque ya movimos a los usuarios y no queremos borrarlos, 
                # solo le hacemos SET NULL o los borramos si están vinculados 100% a la empresa
                # Obtenemos la empresa válida (si existe) para redirigir
                valid_company_id = env['res.company'].with_context(active_test=False).search([('id', 'not in', company_ids)], limit=1).id
                if not valid_company_id:
                    valid_company_id = "NULL" # Fallback extremo
                
                if table_name == 'res_users' or table_name == 'res_company':
                    try:
                        with env.cr.savepoint():
                            env.cr.execute(f"UPDATE {table_name} SET {column_name} = {valid_company_id} WHERE {column_name} IN %s", (company_ids,))
                    except Exception: pass
                else:
                    try:
                        with env.cr.savepoint():
                            env.cr.execute(f"DELETE FROM {table_name} WHERE {column_name} IN %s", (company_ids,))
                    except Exception as inner_e:
                        pass # Puede fallar si hay cascadas secundarias, lo resolveremos iterando
        except Exception as e:
            print(f"Error inesperado: {e}")
            break

env.cr.commit()
print("=== PROCESO TERMINADO ===")
