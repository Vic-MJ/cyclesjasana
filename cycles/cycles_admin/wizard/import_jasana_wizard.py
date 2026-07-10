# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import xmlrpc.client
import base64

class ImportJasanaWizard(models.TransientModel):
    _name = 'cycles.import.jasana.wizard'
    _description = 'Importar Orden desde Jasana'

    name = fields.Char(string='Documento Jasana (OUT)', required=True, help="Ejemplo: WH/OUT/00001")
    company_id = fields.Many2one('res.company', string='Empresa (Destino)', required=True, default=lambda self: self.env.company)
    picking_type_id = fields.Many2one(
        'stock.picking.type', 
        string='Tipo de Operación (Destino)', 
        required=True,
        domain="[('company_id', '=', company_id), ('code', '=', 'incoming')]"
    )

    def _get_odoo_connection(self):
        self.ensure_one()
        param = self.env['ir.config_parameter'].sudo()
        url = param.get_param('cycles_admin.jasana_url')
        db = param.get_param('cycles_admin.jasana_db')
        user = param.get_param('cycles_admin.jasana_user')
        api_key = param.get_param('cycles_admin.jasana_api_key')

        if not all([url, db, user, api_key]):
            raise UserError(_("Faltan configurar las credenciales de Jasana en Ajustes Generales."))

        try:
            common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common', allow_none=True)
            uid = common.authenticate(db, user, api_key, {})
            if not uid:
                raise UserError(_("Autenticación fallida con Jasana. Revisa las credenciales."))
            models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object', allow_none=True)
            return uid, models, db, api_key
        except Exception as e:
            raise UserError(_("Error conectando a Jasana: %s") % str(e))

    def _get_or_create_attribute(self, name):
        name = name.strip()
        attr = self.env['product.attribute'].search([('name', '=ilike', name)], limit=1)
        if not attr:
            attr = self.env['product.attribute'].create({'name': name, 'create_variant': 'always'})
        return attr.id

    def _get_or_create_attribute_value(self, attr_id, name):
        name = name.strip()
        val = self.env['product.attribute.value'].search([('attribute_id', '=', attr_id), ('name', '=ilike', name)], limit=1)
        if not val:
            val = self.env['product.attribute.value'].create({'attribute_id': attr_id, 'name': name})
        return val.id

    def action_import_picking(self):
        self.ensure_one()
        self = self.sudo()
        j_uid, j_models, j_db, j_api_key = self._get_odoo_connection()

        picking_name = self.name.strip()
        picking_domain = ['|', ('name', '=', picking_name), ('name', 'ilike', picking_name)]
        pickings = j_models.execute_kw(
            j_db, j_uid, j_api_key, 'stock.picking', 'search_read', 
            [picking_domain], 
            {'fields': ['name', 'state', 'partner_id', 'date_done', 'origin'], 'limit': 1}
        )

        if not pickings:
            raise UserError(_("No se encontró la Orden de Entrega con nombre: %s") % picking_name)

        jasana_picking = pickings[0]
        picking_id = jasana_picking['id']

        moves = j_models.execute_kw(
            j_db, j_uid, j_api_key, 'stock.move', 'search_read',
            [[('picking_id', '=', picking_id)]],
            {'fields': ['name', 'product_id', 'product_uom_qty', 'quantity', 'sale_line_id', 'price_unit']}
        )

        if not moves:
            raise UserError(_("La orden %s no tiene líneas de productos.") % jasana_picking['name'])

        items = []
        for move in moves:
            prod_id_info = move['product_id']
            if not prod_id_info:
                continue
            prod_id = prod_id_info[0]

            prod_fields = ['name', 'default_code', 'product_template_attribute_value_ids', 'description_sale', 'image_1920', 'standard_price']
            prod = j_models.execute_kw(j_db, j_uid, j_api_key, 'product.product', 'read', [[prod_id]], {'fields': prod_fields})[0]

            talla, color, tela, contraste = '', '', '', ''

            attr_ids = prod.get('product_template_attribute_value_ids', [])
            if attr_ids:
                attrs_details = j_models.execute_kw(
                    j_db, j_uid, j_api_key, 'product.template.attribute.value', 'read', 
                    [attr_ids], {'fields': ['name', 'attribute_id']}
                )
                for ad in attrs_details:
                    attr_name = ad['attribute_id'][1].upper()
                    val_name = ad['name']
                    if 'TALLA' in attr_name: talla = val_name
                    elif 'COLOR' in attr_name: color = val_name
                    elif 'TELA' in attr_name: tela = val_name
                    elif 'CONTRASTE' in attr_name: contraste = val_name

            area = ''
            price_unit = 0.0
            sale_line_info = move.get('sale_line_id')
            if sale_line_info:
                sale_line_id = sale_line_info[0]
                sline_data = j_models.execute_kw(j_db, j_uid, j_api_key, 'sale.order.line', 'read', [[sale_line_id]], {'fields': ['sale_area_id', 'price_unit']})
                if sline_data:
                    if sline_data[0].get('sale_area_id'): area = sline_data[0]['sale_area_id'][1]
                    if sline_data[0].get('price_unit'): price_unit = float(sline_data[0]['price_unit'])

            if not price_unit and move.get('price_unit'): price_unit = float(move['price_unit'])
            if not price_unit and prod.get('standard_price'): price_unit = float(prod['standard_price'])

            parent_name = prod['name']
            default_code = prod.get('default_code') or ''
            sku = default_code or parent_name

            if not default_code:
                default_code = f"{sku}-{talla or 'UNI'}-{color or 'UNI'}".replace(' ', '')

            image_b64 = ''
            if prod.get('image_1920'):
                image_b64 = prod['image_1920']
                if isinstance(image_b64, bytes): image_b64 = image_b64.decode('utf-8')

            qty = move.get('quantity') or move.get('product_uom_qty') or 0.0
            if not tela and '-' in sku:
                parts = sku.split('-')
                if len(parts) >= 3: tela = parts[2]

            items.append({
                'sku': sku,
                'default_code': default_code,
                'talla': talla,
                'qty': qty,
                'tela': tela,
                'color': color,
                'contraste': contraste,
                'description_sale': prod.get('description_sale') or '',
                'area': area,
                'image_b64': image_b64,
                'price_unit': price_unit
            })

        # Process Items in Local Database
        grouped_items = {}
        for item in items:
            sku = item.get('sku', '').strip()
            if not sku: continue
            if sku not in grouped_items: grouped_items[sku] = []
            grouped_items[sku].append(item)

        categ_id = self.env['product.category'].search([('name', '=ilike', 'Uniformes')], limit=1)
        if not categ_id:
            categ_id = self.env['product.category'].search([], limit=1)

        talla_attr_id = self._get_or_create_attribute('TALLA')
        contraste_attr_id = self._get_or_create_attribute('CONTRASTE')
        color_attr_id = self._get_or_create_attribute('COLOR')

        moves_data = []

        for sku, group in grouped_items.items():
            first_item = group[0]
            price_unit_tmpl = float(first_item.get('price_unit', 0.0))

            tmpl = self.env['product.template'].search([('name', '=', sku)], limit=1)
            
            unique_tallas = list(set([i.get('talla', 'UNI') for i in group if i.get('talla')])) or ['UNI']
            unique_contrastes = list(set([i.get('contraste', '0') for i in group if i.get('contraste')])) or ['0']
            unique_colors = list(set([i.get('color', 'UNI') for i in group if i.get('color')])) or ['UNI']

            talla_val_map = {t: self._get_or_create_attribute_value(talla_attr_id, t) for t in unique_tallas}
            contraste_val_map = {c: self._get_or_create_attribute_value(contraste_attr_id, c) for c in unique_contrastes}
            color_val_map = {col: self._get_or_create_attribute_value(color_attr_id, col) for col in unique_colors}

            if tmpl:
                tmpl.write({
                    'is_storable': True, 
                    'tracking': 'serial', 
                    'sale_ok': False, 
                    'purchase_ok': True, 
                    'company_id': self.company_id.id,
                    'list_price': 0.0,
                    'standard_price': price_unit_tmpl if price_unit_tmpl > 0 else tmpl.standard_price,
                    'categ_id': categ_id.id if categ_id else tmpl.categ_id.id
                })
            else:
                attribute_line_ids = [
                    (0, 0, {'attribute_id': talla_attr_id, 'value_ids': [(6, 0, list(talla_val_map.values()))]}),
                    (0, 0, {'attribute_id': contraste_attr_id, 'value_ids': [(6, 0, list(contraste_val_map.values()))]}),
                    (0, 0, {'attribute_id': color_attr_id, 'value_ids': [(6, 0, list(color_val_map.values()))]})
                ]
                tmpl_vals = {
                    'name': sku,
                    'attribute_line_ids': attribute_line_ids,
                    'company_id': self.company_id.id,
                    'is_storable': True,
                    'tracking': 'serial',
                    'sale_ok': False,
                    'purchase_ok': True,
                    'standard_price': price_unit_tmpl,
                    'list_price': 0.0,
                    'categ_id': categ_id.id if categ_id else False
                }
                base_img = next((i.get('image_b64') for i in group if i.get('image_b64')), '')
                if base_img:
                    tmpl_vals['image_1920'] = base_img

                tmpl = self.env['product.template'].create(tmpl_vals)

            variants = self.env['product.product'].search([('product_tmpl_id', '=', tmpl.id)])
            
            for var in variants:
                talla_name, contraste_name, color_name = '', '', ''
                for pav in var.product_template_attribute_value_ids:
                    attr_name = pav.attribute_id.name.upper()
                    if 'TALLA' in attr_name: talla_name = pav.name
                    elif 'CONTRASTE' in attr_name: contraste_name = pav.name
                    elif 'COLOR' in attr_name: color_name = pav.name

                matched_item = None
                for item in group:
                    if (talla_name == (item.get('talla') or 'UNI')) and \
                       (contraste_name == (item.get('contraste') or '0')) and \
                       (color_name == (item.get('color') or 'UNI')):
                        matched_item = item
                        break
                
                if not matched_item and len(group) == 1:
                    matched_item = group[0]

                if matched_item:
                    default_code = matched_item.get('default_code', '')
                    desc_sale = matched_item.get('description_sale', '')
                    tela = matched_item.get('tela', '')
                    color = matched_item.get('color', '')
                    area = matched_item.get('area', '')
                    qty = float(matched_item.get('qty', 0.0))
                    image_b64 = matched_item.get('image_b64', '')
                    price_unit = float(matched_item.get('price_unit', 0.0))

                    desc_details = [f"SKU: {sku}"]
                    if talla_name: desc_details.append(f"Talla: {talla_name}")
                    if tela: desc_details.append(f"Tela: {tela}")
                    if color_name or color: desc_details.append(f"Color: {color_name or color}")
                    if contraste_name: desc_details.append(f"Contraste: {contraste_name}")
                    if area: desc_details.append(f"Área: {area}")
                    
                    metadata_block = "\n".join(desc_details)
                    full_description = f"{metadata_block}\n---\n{desc_sale}" if desc_sale else metadata_block

                    write_vals = {
                        'default_code': default_code,
                        'description_sale': full_description,
                    }
                    if price_unit > 0.0: write_vals['standard_price'] = price_unit
                    if image_b64: write_vals['image_1920'] = image_b64

                    var.write(write_vals)

                    tname = talla_name or 'UNI'
                    garment_type_name = f"{sku} ({tname})"
                    
                    if 'cycles.garment.type' in self.env:
                        existing_gt = self.env['cycles.garment.type'].search([('product_tmpl_id', '=', tmpl.id), ('name', '=', garment_type_name)], limit=1)
                        if not existing_gt:
                            clean_n = "".join([c for c in (sku + tname) if c.isalnum()]).upper()
                            base_c = clean_n[:3] if len(clean_n) >= 3 else (clean_n + "XXX")[:3]
                            g_code = base_c
                            suff = 1
                            while self.env['cycles.garment.type'].search([('code', '=', g_code)], limit=1):
                                g_code = f"{base_c[:2]}{suff}"
                                suff += 1
                            
                            self.env['cycles.garment.type'].create({
                                'name': garment_type_name,
                                'code': g_code,
                                'product_tmpl_id': tmpl.id
                            })

                    moves_data.append({
                        'prod_id': var.id,
                        'name': f"{sku} ({talla_name}, {color_name or color})" if (talla_name or color_name or color) else sku,
                        'qty': qty,
                        'price_unit': price_unit
                    })

        loc_src_id = self.picking_type_id.default_location_src_id.id
        loc_dest_id = self.picking_type_id.default_location_dest_id.id
        
        # Get partner_id of company
        company_partner_id = self.company_id.partner_id.id if self.company_id.partner_id else False

        picking_vals = {
            'picking_type_id': self.picking_type_id.id,
            'company_id': self.company_id.id,
            'origin': f"Jasana: {jasana_picking['name']}",
            'location_id': loc_src_id,
            'location_dest_id': loc_dest_id,
        }
        if company_partner_id:
            picking_vals['partner_id'] = company_partner_id

        picking = self.env['stock.picking'].create(picking_vals)

        for md in moves_data:
            self.env['stock.move'].create({
                'product_id': md['prod_id'],
                'product_uom_qty': md['qty'],
                'product_uom': self.env.ref('uom.product_uom_unit').id,
                'picking_id': picking.id,
                'location_id': loc_src_id,
                'location_dest_id': loc_dest_id,
                'company_id': self.company_id.id,
                'description_picking': md['name'],
                'price_unit': md['price_unit']
            })

        picking.action_confirm()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Recepción Importada'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }
