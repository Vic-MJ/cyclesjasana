import sys
import os
import zipfile
import subprocess
import shutil
import tkinter as tk
from tkinter import filedialog

if len(sys.argv) >= 2:
    archivo_respaldo = sys.argv[1]
else:
    ventana_raiz = tk.Tk()
    ventana_raiz.withdraw()
    ventana_raiz.attributes('-topmost', True)
    
    print("Abriendo explorador de archivos...")
    archivo_respaldo = filedialog.askopenfilename(
        title="Selecciona el archivo .zip de respaldo de Odoo",
        filetypes=[("Archivos ZIP", "*.zip"), ("Todos los archivos", "*.*")]
    )
    
    if not archivo_respaldo:
        print("ERROR: Operación cancelada. No seleccionaste ningún archivo.")
        sys.exit(1)
        
    print(f"Archivo seleccionado: {archivo_respaldo}")

if not os.path.exists(archivo_respaldo):
    print(f"ERROR: No se encuentra {archivo_respaldo}")
    sys.exit(1)

CONTENEDOR_BD = "cycles_db"
USUARIO_BD = "odoo"
NOMBRE_BD = "cycles_local"
CONTENEDOR_ODOO = "cycles_odoo"

print(f"Restaurando respaldo: {archivo_respaldo}")

directorio_extraccion = archivo_respaldo.replace(".zip", "_extraido")
if os.path.exists(directorio_extraccion):
    shutil.rmtree(directorio_extraccion)
os.makedirs(directorio_extraccion)

print("Extrayendo respaldo...")
with zipfile.ZipFile(archivo_respaldo, "r") as archivo_zip:
    archivo_zip.extractall(directorio_extraccion)
    contenido = archivo_zip.namelist()
    print(f"  Contenido: {contenido[:10]}")

archivo_sql = None
for raiz, directorios, archivos in os.walk(directorio_extraccion):
    for archivo in archivos:
        if archivo == "dump.sql":
            archivo_sql = os.path.join(raiz, archivo)
            break

if not archivo_sql:
    print("ERROR: No se encontró dump.sql en el respaldo")
    sys.exit(1)

print(f"  SQL encontrado: {archivo_sql}")

print("\nCopiando SQL al contenedor de base de datos...")
resultado = subprocess.run(
    ["docker", "cp", archivo_sql, f"{CONTENEDOR_BD}:/tmp/dump.sql"],
    capture_output=True, text=True
)
if resultado.returncode != 0:
    print(f"ERROR: {resultado.stderr}")
    print("Asegúrate de que Docker Desktop esté corriendo y el contenedor de base de datos esté activo.")
    sys.exit(1)

print("Restaurando base de datos...")
print("Deteniendo Odoo temporalmente para liberar la base de datos...")
subprocess.run(["docker", "stop", CONTENEDOR_ODOO], capture_output=True)

subprocess.run(
    ["docker", "exec", CONTENEDOR_BD, "psql", "-U", USUARIO_BD, "-d", "postgres", "-c", f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{NOMBRE_BD}';"],
    capture_output=True
)

resultado_borrar = subprocess.run(
    ["docker", "exec", CONTENEDOR_BD, "psql", "-U", USUARIO_BD, "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {NOMBRE_BD};"],
    capture_output=True, text=True
)
if resultado_borrar.returncode != 0:
    print(f"ERROR al borrar la base de datos: {resultado_borrar.stderr}")
    subprocess.run(["docker", "start", CONTENEDOR_ODOO])
    sys.exit(1)

resultado_crear = subprocess.run(
    ["docker", "exec", CONTENEDOR_BD, "psql", "-U", USUARIO_BD, "-d", "postgres", "-c", f"CREATE DATABASE {NOMBRE_BD} OWNER {USUARIO_BD};"],
    capture_output=True, text=True
)
if resultado_crear.returncode != 0:
    print(f"ERROR al crear la base de datos: {resultado_crear.stderr}")
    subprocess.run(["docker", "start", CONTENEDOR_ODOO])
    sys.exit(1)

resultado = subprocess.run(
    ["docker", "exec", CONTENEDOR_BD, "psql", "-U", USUARIO_BD, "-d", NOMBRE_BD, "-f", "/tmp/dump.sql"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
if resultado.returncode != 0:
    print(f"ADVERTENCIA: Error durante la restauración SQL (algunos errores son normales).")
else:
    print("  SQL restaurado exitosamente.")

print("Reiniciando Odoo para habilitar la copia de archivos de sistema...")
subprocess.run(["docker", "start", CONTENEDOR_ODOO], capture_output=True)

origen_archivos = None
for raiz, directorios, archivos in os.walk(directorio_extraccion):
    if os.path.basename(raiz) == "filestore":
        origen_archivos = raiz
        break

if origen_archivos:
    print("Copiando archivos de sistema (filestore)...")
    subprocess.run(["docker", "exec", "-u", "root", CONTENEDOR_ODOO, "mkdir", "-p", f"/var/lib/odoo/.local/share/Odoo/filestore/{NOMBRE_BD}"])
    
    resultado = subprocess.run(
        ["docker", "cp", origen_archivos + "/.", f"{CONTENEDOR_ODOO}:/var/lib/odoo/.local/share/Odoo/filestore/{NOMBRE_BD}/"],
        capture_output=True, text=True
    )
    subprocess.run(["docker", "exec", "-u", "root", CONTENEDOR_ODOO, "chown", "-R", "odoo:odoo", f"/var/lib/odoo/.local/share/Odoo/filestore/{NOMBRE_BD}"])
    if resultado.returncode == 0:
        print("  Archivos de sistema copiados exitosamente.")
    else:
        print(f"  ADVERTENCIA de archivos de sistema: {resultado.stderr[:200]}")

shutil.rmtree(directorio_extraccion)

print("Aplicando correcciones a la base de datos para evitar colisiones...")
subprocess.run(
    ["docker", "exec", CONTENEDOR_BD, "psql", "-U", USUARIO_BD, "-d", NOMBRE_BD, "-c", "UPDATE ir_model_data SET res_id = (SELECT id FROM stock_warehouse WHERE code='WH' LIMIT 1) WHERE module='stock' AND name='warehouse0';"],
    capture_output=True
)

print("Actualizando los módulos de Odoo para sincronizar la base de datos (esto puede tardar unos segundos)...")
subprocess.run(
    ["docker", "exec", CONTENEDOR_ODOO, "odoo", "-c", "/etc/odoo/odoo.conf", "-d", NOMBRE_BD, "-u", "all", "--stop-after-init"],
    capture_output=True
)

print("Realizando reinicio limpio de Odoo para refrescar conexiones...")
subprocess.run(["docker", "restart", CONTENEDOR_ODOO], capture_output=True)

print(f"\n¡Restauración completa!")
print(f"Abre http://localhost:8069 y selecciona la base de datos '{NOMBRE_BD}'")
