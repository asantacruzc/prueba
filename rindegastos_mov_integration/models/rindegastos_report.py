from odoo import models, fields, api
import requests
from odoo.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class RindegastosReport(models.Model):
    _name = 'rindegastos.report'
    _description = 'Reportes desde Rindegastos API'

    name = fields.Char(string='Referencia', required=True)
    date = fields.Date(string='Fecha', required=True)
    amount = fields.Float(string='Monto', required=True)
    note = fields.Text(string='Nota')
    journal_id = fields.Many2one('account.journal', string='Diario Contable', domain=[('type', '=', 'bank')])
    move_id = fields.Many2one('account.move', string='Asiento Contable', readonly=True)
    state = fields.Selection([('draft', 'Borrador'), ('posted', 'Contabilizado')], default='draft')
    employee_name = fields.Char(string='Empleado', compute='_compute_employee_name', store=False, help='Nombre del empleado que rindió el reporte')
    report_number = fields.Char(string='Número de Reporte', help='Número de reporte de Rindegastos')
    policy_name = fields.Char(string='Política', help='Nombre de la política de Rindegastos')
    file_url = fields.Char(string='Enlace al Archivo', help='Enlace al archivo del reporte en Rindegastos')
    file_preview = fields.Html(string='Vista Previa del Archivo', compute='_compute_file_preview', store=False, help='Vista previa de la imagen del archivo')
    report_total_approved = fields.Float(string='Monto Aprobado', help='Monto total aprobado del reporte en Rindegastos')
    total_difference = fields.Float(string='Diferencia Total', compute='_compute_total_difference', store=False, help='Diferencia entre monto total y monto aprobado')
    title = fields.Char(string='Título', help='Título del reporte de Rindegastos')
    expense_ids = fields.One2many('rindegastos.expense', 'report_id', string='Expenses Relacionados')

    @api.depends('journal_id.employee_id')
    def _compute_employee_name(self):
        for record in self:
            record.employee_name = record.journal_id.employee_id.name if record.journal_id.employee_id else ''

    @api.depends('file_url')
    def _compute_file_preview(self):
        for record in self:
            if record.file_url:
                record.file_preview = f'<a href="{record.file_url}" target="_blank"><img src="{record.file_url}" style="max-width: 300px; max-height: 300px;" alt="Vista previa del archivo"/></a>'
            else:
                record.file_preview = ''

    @api.depends('amount', 'report_total_approved')
    def _compute_total_difference(self):
        for record in self:
            record.total_difference = record.amount - record.report_total_approved

    def fetch_and_create_reports(self, journal_id=None, since=None, until=None):
        journals = journal_id or self.env['account.journal'].search([('type', '=', 'bank'), ('employee_id.rindegastos_userid', '!=', False)])
        
        for journal in journals:
            token = self.env.company.rindegastos_tokenid
            if not token:
                raise UserError(f"No se ha configurado un token de Rindegastos para la compañía {self.env.company.name}.")
            
            if not journal.employee_id or not journal.employee_id.rindegastos_userid:
                raise UserError(f"No se ha configurado un empleado con User ID de Rindegastos para el diario {journal.name}.")

            api_url = "https://api.rindegastos.com/v1/getExpenseReports"
            headers = {"Authorization": f"Bearer {token}"}
            page = 1
            while True:
                params = {
                    'Status': 1,
                    'UserId': journal.employee_id.rindegastos_userid,
                    'ResultsPerPage': 100,
                    'Page': page
                }
                if since:
                    params['Since'] = since.strftime('%Y-%m-%d')
                if until:
                    params['Until'] = until.strftime('%Y-%m-%d')
                
                try:
                    response = requests.get(api_url, headers=headers, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    reports = data.get('ExpenseReports', [])
                    if not reports:
                        break

                    for report in reports:
                        if not all([report.get('Id'), report.get('SendDate'), report.get('ReportTotal')]):
                            continue

                        report_date = datetime.strptime(report['SendDate'], '%Y-%m-%d').date()

                        existing_report = self.search([
                            ('name', '=', str(report['Id'])),
                            ('journal_id', '=', journal.id),
                            ('date', '=', report_date),
                            ('amount', '=', float(report['ReportTotal'])),
                        ])
                        if existing_report:
                            continue

                        file_url = ''
                        files = report.get('Files', [])
                        if files and isinstance(files, list) and 'Large' in files[0]:
                            file_url = files[0].get('Large', '')

                        new_report = self.create({
                            'name': str(report['Id']),
                            'date': report_date,
                            'amount': float(report['ReportTotal']),
                            'note': report.get('Note', ''),
                            'journal_id': journal.id,
                            'report_number': report.get('ReportNumber', ''),
                            'policy_name': report.get('PolicyName', ''),
                            'file_url': file_url,
                            'report_total_approved': float(report.get('ReportTotalApproved', 0.0)),
                            'title': report.get('Title', ''),
                        })

                        # Importa automáticamente los expenses asociados a este report
                        self.env['rindegastos.expense'].fetch_and_create_expenses(
                            journal_id=journal,
                            since=since,
                            until=until,
                            report_api_id=report['Id']
                        )

                        # Crea el move para este report
                        new_report.create_account_move()

                        # Crea moves para los nuevos expenses asociados
                        new_expenses = self.env['rindegastos.expense'].search([
                            ('report_id', '=', new_report.id),
                            ('state', '=', 'draft')
                        ])
                        if new_expenses:
                            new_expenses.create_account_move()

                    total_pages = data.get('Records', {}).get('Pages', 1)
                    if page >= total_pages:
                        break
                    page += 1
                except requests.exceptions.RequestException as e:
                    raise UserError(f"Error al conectar con la API de Rindegastos: {str(e)}")

    def create_account_move(self):
        for report in self:
            if report.state == 'posted':
                continue

            if not report.journal_id or not report.journal_id.suspense_account_id or not report.journal_id.default_account_id:
                raise UserError("Configuración incompleta en el diario.")

            statement_line_vals = {
                'date': report.date,
                'payment_ref': f"Informe {report.name}-{report.report_number}: {report.title}" if report.report_number and report.title else report.note or report.name,
                'ref': report.name,
                'amount': report.report_total_approved,  # Positivo para reports
                'journal_id': report.journal_id.id,
                'rindegastos_file_url': report.file_url,  # Poblado para bank statement
            }
            existing_statement_line = self.env['account.bank.statement.line'].search([
                ('ref', '=', report.name),
                ('journal_id', '=', report.journal_id.id),
                ('date', '=', report.date),
                ('amount', '=', report.report_total_approved),
            ])
            if existing_statement_line:
                continue

            statement_line = self.env['account.bank.statement.line'].create(statement_line_vals)
            move = statement_line.move_id
            if move:
                report.write({'move_id': move.id, 'state': 'draft'})

    @api.model
    def cron_fetch_mov(self):
        """Tarea unificada: importa reports y automáticamente sus expenses asociados."""
        self.fetch_and_create_reports()

    def action_open_rindegastos_mov_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Importar Movimientos y Reports de Rindegastos',
            'res_model': 'rindegastos.mov.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_journal_id': self.journal_id.id, 'hide_journal': False},  # Visible journal_id
        }