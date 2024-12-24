from odoo import models, _, fields
from odoo.exceptions import UserError


class EighteenModel(models.Model):
    _name = "eighteen.model"

    name = fields.Char(_("Näme"))  # pylint: disable=translation-field

    def my_method7(self):
        user_id = 1
        if user_id != 99:
            # Method with translation
            raise UserError(_("String with translation"))
        raise UserError(self.env._("String with good translation"))
