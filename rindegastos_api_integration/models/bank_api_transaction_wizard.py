from odoo import models, fields, api

class BankApiTransactionWizard(models.TransientModel):
    _name = 'bank.api.transaction.wizard'
    _description = 'Asistente para importar movimientos de Rindegastos'

    since = fields.Date(string='Fecha de Inicio', required=True, default=fields.Date.today)
    until = fields.Date(string='Fecha de Término', required=True, default=fields.Date.today)
    journal_id = fields.Many2one('account.journal', string='Diario Contable', domain=[('type', '=', 'bank'), ('rindegastos_userid', '!=', False)], required=True)

    def action_import_transactions(self):
        """Importa movimientos usando los filtros del asistente."""
        self.env['bank.api.transaction'].fetch_and_create_transactions(
            journal_id=self.journal_id,
            since=self.since,
            until=self.until
        )
        transactions = self.env['bank.api.transaction'].search([('journal_id', '=', self.journal_id.id), ('state', '=', 'draft')])
        if transactions:
            transactions.create_account_move()
        return {'type': 'ir.actions.act_window_close'}