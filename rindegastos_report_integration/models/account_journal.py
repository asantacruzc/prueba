from odoo import models, fields, api

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    bank_feed_type = fields.Selection([
        ('manual', 'Manual'),
        ('rindegastos', 'Rindegastos Sincronización'),
    ], string='Tipo de Sincronización Bancaria', default='manual', help='Seleccione el tipo de sincronización para el diario bancario')
    employee_id = fields.Many2one('hr.employee', string='Empleado Rindegastos', help='Empleado asociado para filtrar reportes en Rindegastos API', domain=[('rindegastos_userid', '!=', False)])

    def action_open_rindegastos_report_wizard(self):
        """Abre el wizard para importar reportes de Rindegastos."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Importar Reportes de Rindegastos',
            'res_model': 'bank.api.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_journal_id': self.id},
        }