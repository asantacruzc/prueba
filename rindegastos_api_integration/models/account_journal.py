from odoo import models, fields

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    bank_feed_type = fields.Selection([
        ('manual', 'Manual'),
        ('rindegastos', 'Rindegastos Sincronización'),
    ], string='Tipo de Sincronización Bancaria', default='manual', help='Seleccione el tipo de sincronización para el diario bancario')
    rindegastos_userid = fields.Char(string='Rindegastos User ID', help='ID del usuario de Rindegastos para filtrar gastos en la API')