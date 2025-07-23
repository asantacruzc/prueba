from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rindegastos_tokenid = fields.Char(string='Rindegastos Token ID', related='company_id.rindegastos_tokenid', readonly=False)