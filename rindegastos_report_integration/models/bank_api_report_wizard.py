from odoo import models, fields, api

class BankApiReportWizard(models.TransientModel):
    _name = 'bank.api.report.wizard'
    _description = 'Asistente para importar reportes de Rindegastos'

    since = fields.Date(string='Fecha de Inicio', required=True, default=fields.Date.today)
    until = fields.Date(string='Fecha de Término', required=True, default=fields.Date.today)
    journal_id = fields.Many2one('account.journal', string='Diario Contable', domain=[('type', '=', 'bank'), ('employee_id.rindegastos_userid', '!=', False)], required=True)

    def action_import_reports(self):
        """Importa reportes usando los filtros del asistente."""
        self.env['bank.api.report'].fetch_and_create_reports(
            journal_id=self.journal_id,
            since=self.since,
            until=self.until
        )
        reports = self.env['bank.api.report'].search([('journal_id', '=', self.journal_id.id), ('state', '=', 'draft')])
        if reports:
            reports.create_account_move()
        return {'type': 'ir.actions.act_window_close'}