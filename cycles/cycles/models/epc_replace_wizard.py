from odoo import models, fields
from odoo.exceptions import ValidationError

from markupsafe import Markup


class EpcReplaceWizard(models.TransientModel):
    _name = "cycles.epc.replace.wizard"
    _description = "Asistente para Reemplazo de EPC"

    old_epc = fields.Char(string="EPC Viejo", required=True)
    new_epc = fields.Char(string="Nuevo EPC", required=True)

    def action_replace_epc(self):
        self.ensure_one()
        old_epc = self.old_epc.strip()
        new_epc = self.new_epc.strip()

        if old_epc == new_epc:
            raise ValidationError(
                self.env._("El nuevo EPC no puede ser igual al viejo.")
            )

        garment_env = self.env["stock.lot"]
        garment = garment_env.search(
            [("name", "=", old_epc), ("is_garment", "=", True)], limit=1
        )
        if not garment:
            raise ValidationError(
                self.env._("No se encontró ninguna prenda con el EPC: %s") % old_epc
            )

        existing_new = garment_env.search([("name", "=", new_epc)], limit=1)
        if existing_new:
            raise ValidationError(
                self.env._(
                    "El nuevo EPC (%s) ya está asignado a otra etiqueta en el sistema."
                ) % new_epc
            )

        garment.name = new_epc
        garment.message_post(
            body=Markup(
                self.env._(
                    "El EPC de esta prenda fue reemplazado.<br/><ul>"
                    "<li><b>EPC Anterior:</b> %s</li>"
                    "<li><b>EPC Nuevo:</b> %s</li></ul>"
                )
            ) % (old_epc, new_epc)
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Éxito"),
                "message": self.env._("EPC reemplazado correctamente."),
                "sticky": False,
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
