from odoo import models, fields, api
import requests
from odoo.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class BankApiReport(models.Model):
    _name = 'bank.api.report'
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

    @api.depends('journal_id.employee_id')
    def _compute_employee_name(self):
        """Calcula el nombre del empleado desde el diario."""
        for record in self:
            record.employee_name = record.journal_id.employee_id.name if record.journal_id.employee_id else ''

    @api.depends('file_url')
    def _compute_file_preview(self):
        """Genera una etiqueta HTML para mostrar la imagen del file_url, clickable para vista completa."""
        for record in self:
            if record.file_url:
                record.file_preview = f'<a href="{record.file_url}" target="_blank"><img src="{record.file_url}" style="max-width: 300px; max-height: 300px;" alt="Vista previa del archivo"/></a>'
            else:
                record.file_preview = ''

    @api.depends('amount', 'report_total_approved')
    def _compute_total_difference(self):
        """Calcula la diferencia entre ReportTotal y ReportTotalApproved."""
        for record in self:
            record.total_difference = record.amount - record.report_total_approved

    def fetch_and_create_reports(self, journal_id=None, since=None, until=None):
        """Consulta la API de Rindegastos y crea reportes con filtros."""
        journals = journal_id or self.env['account.journal'].search([('type', '=', 'bank'), ('employee_id.rindegastos_userid', '!=', False)])
        
        for journal in journals:
            token = self.env.company.rindegastos_tokenid
            if not token:
                _logger.error(f"No se ha configurado un token de Rindegastos para la compañía {self.env.company.name}")
                raise UserError(f"No se ha configurado un token de Rindegastos para la compañía {self.env.company.name}.")
            
            if not journal.employee_id or not journal.employee_id.rindegastos_userid:
                _logger.error(f"No se ha configurado un empleado con User ID de Rindegastos para el diario {journal.name}")
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
                
                _logger.info(f"Enviando solicitud a {api_url} con parámetros: {params}")
                try:
                    response = requests.get(api_url, headers=headers, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    _logger.debug(f"Respuesta completa de la API para diario {journal.name}, Página {page}: {data}")
                    reports = data.get('ExpenseReports', [])
                    if not reports:
                        _logger.warning(f"No se encontraron reportes para el diario {journal.name} con UserId {journal.employee_id.rindegastos_userid}, Página {page}")
                        break

                    for report in reports:
                        if not all([report.get('Id'), report.get('SendDate'), report.get('ReportTotal')]):
                            _logger.warning(f"Reporte inválido: {report}")
                            continue

                        try:
                            report_date = datetime.strptime(report['SendDate'], '%Y-%m-%d').date()
                        except ValueError:
                            _logger.warning(f"Fecha inválida en reporte: {report.get('SendDate')}")
                            continue

                        existing_report = self.search([
                            ('name', '=', str(report['Id'])),
                            ('journal_id', '=', journal.id),
                            ('date', '=', report_date),
                            ('amount', '=', float(report['ReportTotal'])),
                        ])
                        if existing_report:
                            _logger.info(f"Reporte {report['Id']} ya existe para el diario {journal.name} con fecha {report_date} y monto {float(report['ReportTotal'])}")
                            continue

                        file_url = ''
                        files = report.get('Files', [])
                        if files and isinstance(files, list) and 'Large' in files[0]:
                            file_url = files[0].get('Large', '')
                            _logger.debug(f"Enlace Large extraído: {file_url}")
                        else:
                            _logger.debug(f"No se encontraron archivos o Large en reporte: {report['Id']}")

                        self.create({
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
                        _logger.info(f"Reporte creado: {report['Id']} para el diario {journal.name} con report_number: {report.get('ReportNumber')}, title: {report.get('Title')}, file_url: {file_url}, report_total_approved: {report.get('ReportTotalApproved')}")

                    total_pages = data.get('Records', {}).get('Pages', 1)
                    if page >= total_pages:
                        break
                    page += 1
                except requests.exceptions.RequestException as e:
                    _logger.error(f"Error al conectar con la API de Rindegastos para el diario {journal.name}: {str(e)}")
                    raise UserError(f"Error al conectar con la API de Rindegastos: {str(e)}")

    def create_account_move(self):
        """Crea una línea en el estado de cuenta bancario para cada reporte, dejando el asiento en borrador."""
        for report in self:
            if report.state == 'posted':
                continue

            if not report.journal_id:
                _logger.error(f"No se ha configurado un diario contable para el reporte {report.name}")
                raise UserError("Seleccione un diario contable para el reporte.")

            if not report.journal_id.suspense_account_id:
                _logger.error(f"No se ha configurado una cuenta transitoria para el diario {report.journal_id.name}")
                raise UserError(f"No se ha configurado una cuenta transitoria para el diario {report.journal_id.name}")

            default_account = report.journal_id.default_account_id
            if not default_account:
                _logger.error(f"No se ha configurado una cuenta predeterminada para el diario {report.journal_id.name}")
                raise UserError(f"No se ha configurado una cuenta predeterminada para el diario {report.journal_id.name}")

            statement_line_vals = {
                'date': report.date,
                'payment_ref': f"{report.name}-{report.report_number}: {report.title}" if report.report_number and report.title else report.note or report.name,
                'ref': report.name,
                'amount': report.report_total_approved,  # Usar ReportTotalApproved, negativo para gasto
                'journal_id': report.journal_id.id,
            }
            existing_statement_line = self.env['account.bank.statement.line'].search([
                ('ref', '=', report.name),
                ('journal_id', '=', report.journal_id.id),
                ('date', '=', report.date),
                ('amount', '=', report.report_total_approved),
            ])
            if existing_statement_line:
                _logger.info(f"Línea de estado de cuenta ya existe para el reporte {report.name} en el diario {report.journal_id.name}")
                continue

            statement_line = self.env['account.bank.statement.line'].create(statement_line_vals)
            _logger.info(f"Línea de estado de cuenta creada: {statement_line.payment_ref}")

            move = statement_line.move_id
            if move:
                report.write({
                    'move_id': move.id,
                    'state': 'draft',
                })
                _logger.info(f"Asiento contable {move.name} creado en borrador para el reporte {report.name}")
            else:
                _logger.error(f"No se generó un asiento contable para la línea {statement_line.payment_ref}")
                raise UserError(f"No se generó un asiento contable para la línea {statement_line.payment_ref}")

    @api.model
    def cron_fetch_reports(self):
        """Tarea programada para consultar la API periódicamente."""
        self.fetch_and_create_reports()
        reports = self.search([('state', '=', 'draft')])
        reports.create_account_move()