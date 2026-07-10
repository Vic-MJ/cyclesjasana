FROM odoo:19.0

USER root

# Copiar el archivo de configuración base
COPY ./odoo.conf /etc/odoo/odoo.conf

# Limpiar las credenciales locales de odoo.conf para que Odoo use las Variables de Entorno en Render
RUN sed -i '/db_host/d' /etc/odoo/odoo.conf && \
    sed -i '/db_port/d' /etc/odoo/odoo.conf && \
    sed -i '/db_user/d' /etc/odoo/odoo.conf && \
    sed -i '/db_password/d' /etc/odoo/odoo.conf && \
    sed -i '/db_name/d' /etc/odoo/odoo.conf && \
    echo "db_name = cycles_db_c08t" >> /etc/odoo/odoo.conf && \
    echo "proxy_mode = True" >> /etc/odoo/odoo.conf

# Copiar los módulos personalizados de tu proyecto
COPY ./cycles /mnt/extra-addons/

# Asegurar que el usuario odoo sea dueño de los archivos copiados
RUN chown -R odoo:odoo /etc/odoo/odoo.conf /mnt/extra-addons/

# Odoo requiere el usuario "odoo" para correr
USER odoo

# El puerto que expone Odoo por defecto
EXPOSE 8069
