from odoo import models, fields, api

class RindegastosMovWizard(models.TransientModel):
    _name = 'rindegastos.mov.wizard'
    _description = 'Asistente unificado para importar reports y expenses de Rindegastos'

    since = fields.Date(string='Fecha de Inicio', required=True, default=fields.Date.today)
    until = fields.Date(string='Fecha de Término', required=True, default=fields.Date.today)
    journal_id = fields.Many2one('account.journal', string='Diario Contable', domain=[('type', '=', 'bank'), ('employee_id.rindegastos_userid', '!=', False)], required=True)

    def action_import_mov(self):
        """Importa reports y automáticamente sus expenses asociados usando los filtros del asistente."""
        report_model = self.env['rindegastos.report']

        # Solo importa reports (y auto expenses dentro)
        report_model.fetch_and_create_reports(
            journal_id=self.journal_id,
            since=self.since,
            until=self.until
        )
        # Crea moves para nuevos registros (ya que expenses se importan dentro de fetch_reports)
        reports = report_model.search([('journal_id', '=', self.journal_id.id), ('state', '=', 'draft')])
        if reports:
            reports.create_account_move()
        return {'type': 'ir.actions.act_window_close'}