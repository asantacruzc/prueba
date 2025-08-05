from odoo import models, fields, api
from odoo.exceptions import UserError

class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    rindegastos_file_url = fields.Char(string='Rindegastos File URL', readonly=True)
    rindegastos_file_preview = fields.Html(string='Rindegastos File Preview', compute='_compute_rindegastos_preview', readonly=True)

    @api.depends('rindegastos_file_url')
    def _compute_rindegastos_preview(self):
        for record in self:
            if record.rindegastos_file_url:
                record.rindegastos_file_preview = f'<a href="{record.rindegastos_file_url}" target="_blank"><img src="{record.file_url}" style="max-width: 300px; max-height: 300px;" alt="Vista previa del archivo"/></a>'
            else:
                record.rindegastos_file_preview = ''

    def action_import_rindegastos(self):
        self.ensure_one()
        if self.journal_id.bank_statements_source != 'rindegastos':
            raise UserError("Esta línea no está asociada a sincronización con Rindegastos.")
        return self.journal_id.action_open_rindegastos_mov_wizard()  # El context se maneja en el journal