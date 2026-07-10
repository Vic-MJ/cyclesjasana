import sys

file_path = 'cycles/models/cycles_rfid.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix Chunk 1:
content = content.replace(
    '"code": (move.product_id.default_code or move.product_id.name)[:20],',
    '"code": (move.product_id.default_code\n                            or move.product_id.name)[:20],'
)

# Fix Chunk 2:
content = content.replace(
    'raise UserError(\n                    self.env._("Selecciona un empleado para la asignación de uniformes."))',
    'raise UserError(\n                    self.env._(\n                        "Selecciona un empleado para la asignación de uniformes."\n                    )\n                )'
)
content = content.replace(
    'self.env._("Error de Asignación:\\nLa prenda %s (%s) ya está asignada al empleado \'%s\'.") %\n                        (lot.name, lot.product_id.display_name, lot.employee_id.name)',
    'self.env._(\n                            "Error de Asignación:\\n"\n                            "La prenda %s (%s) ya está asignada al empleado \'%s\'."\n                        ) % (lot.name, lot.product_id.display_name, lot.employee_id.name)'
)
# And split that last long line if it's still long
content = content.replace(
    ') % (lot.name, lot.product_id.display_name, lot.employee_id.name)',
    ') % (\n                            lot.name, lot.product_id.display_name,\n                            lot.employee_id.name)'
)

# Fix Chunk 3:
content = content.replace(
    'self.env._("Error de Desasignación:\\nLa prenda %s (%s) no tiene un empleado asignado.") %\n                        (lot.name, lot.product_id.display_name)',
    'self.env._(\n                            "Error de Desasignación:\\n"\n                            "La prenda %s (%s) no tiene un empleado asignado."\n                        ) % (lot.name, lot.product_id.display_name)'
)

# Fix Chunk 4:
content = content.replace(
    'self.env._(\n                            "Error de Validación:\\nLa prenda %s (%s) no tiene un empleado asignado.\\nDebe asignarse antes de poder circular."\n                        ) % (lot.name, lot.product_id.display_name)',
    'self.env._(\n                            "Error de Validación:\\n"\n                            "La prenda %s (%s) no tiene un empleado asignado.\\n"\n                            "Debe asignarse antes de poder circular."\n                        ) % (lot.name, lot.product_id.display_name)'
)

# Fix Chunk 5 (Long lines from 332 to 352):
# We fix the `elif` -> `if`
content = content.replace(
    'elif quant.location_id.id != location_src.id:',
    'if quant.location_id.id != location_src.id:'
)
content = content.replace(
    'self.env._(\n                            "Error de Ciclo:\\nLa prenda %s (%s) no se encuentra en el inventario.\\nSe esperaba que estuviera en: \'%s\'."\n                        ) % (lot.name, lot.product_id.display_name, location_src.display_name)',
    'self.env._(\n                            "Error de Ciclo:\\n"\n                            "La prenda %s (%s) no se encuentra en el inventario.\\n"\n                            "Se esperaba que estuviera en: \'%s\'."\n                        ) % (lot.name, lot.product_id.display_name, location_src.display_name)'
)
content = content.replace(
    ') % (lot.name, lot.product_id.display_name, location_src.display_name)',
    ') % (\n                            lot.name, lot.product_id.display_name,\n                            location_src.display_name)'
)

content = content.replace(
    '(op for op in ops if op.get("location_src_id") == quant.location_id.id), None)',
    '(\n                            op for op in ops\n                            if op.get("location_src_id") == quant.location_id.id\n                        ), None)'
)

content = content.replace(
    'current_op_name = expected_op["name"] if expected_op else quant.location_id.display_name',
    'current_op_name = (\n                        expected_op["name"] if expected_op\n                        else quant.location_id.display_name\n                    )'
)

content = content.replace(
    'attempted_op_name = attempted_op["name"] if attempted_op else operation_code',
    'attempted_op_name = (\n                        attempted_op["name"] if attempted_op else operation_code\n                    )'
)

content = content.replace(
    'self.env._(\n                            "Error de Ciclo:\\nLa prenda %s (%s) requiere la operación \'%s\'.\\nEstás intentando realizar la operación \'%s\'."\n                        ) % (lot.name, lot.product_id.display_name, current_op_name, attempted_op_name)',
    'self.env._(\n                            "Error de Ciclo:\\n"\n                            "La prenda %s (%s) requiere la operación \'%s\'.\\n"\n                            "Estás intentando realizar la operación \'%s\'."\n                        ) % (\n                            lot.name, lot.product_id.display_name,\n                            current_op_name, attempted_op_name\n                        )'
)

# Fix Chunk 6:
content = content.replace(
    '"""Processes the user\'s decision to either create a backorder or cancel missing lines."""',
    '"""Processes the decision to create a backorder or cancel."""'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Formatting applied.")
