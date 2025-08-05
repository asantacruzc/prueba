from odoo import models, fields

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _get_bank_statements_available_sources(self):
        sources = super()._get_bank_statements_available_sources()
        sources.append(('rindegastos', 'Rindegastos Sincronización'))
        return sources

    bank_statements_source = fields.Selection(selection=_get_bank_statements_available_sources)
    employee_id = fields.Many2one('hr.employee', string='Empleado Rindegastos', help='Empleado asociado para filtrar en Rindegastos API', domain=[('rindegastos_userid', '!=', False)])

    def action_open_rindegastos_mov_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Importar Movimientos y Reports de Rindegastos',
            'res_model': 'rindegastos.mov.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_journal_id': self.id, 'hide_journal': True},  # Oculta journal_id
        }