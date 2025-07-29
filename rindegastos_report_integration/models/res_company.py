from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    rindegastos_tokenid = fields.Char(string='Rindegastos Token ID', help='Token de acceso para la API de Rindegastos')