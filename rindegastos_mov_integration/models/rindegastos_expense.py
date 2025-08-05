from odoo import models, fields, api
import requests
from odoo.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class RindegastosExpense(models.Model):
    _name = 'rindegastos.expense'
    _description = 'Expenses desde Rindegastos API'

    name = fields.Char(string='Referencia', required=True)
    date = fields.Date(string='Fecha', required=True)
    amount = fields.Float(string='Monto', required=True)
    description = fields.Text(string='Descripción')
    journal_id = fields.Many2one('account.journal', string='Diario Contable', domain=[('type', '=', 'bank')])
    move_id = fields.Many2one('account.move', string='Asiento Contable', readonly=True)
    state = fields.Selection([('draft', 'Borrador'), ('posted', 'Contabilizado')], default='draft')
    partner_id = fields.Many2one('res.partner', string='Contacto', readonly=True)
    employee_name = fields.Char(string='Empleado', compute='_compute_employee_name', store=False, help='Nombre del empleado que rindió el gasto')
    report_id = fields.Many2one('rindegastos.report', string='Reporte Relacionado')  # Many2one para relación real
    file_url = fields.Char(string='Enlace al Archivo', help='Enlace al archivo del gasto en Rindegastos')
    file_preview = fields.Html(string='Vista Previa del Archivo', compute='_compute_file_preview', store=False, help='Vista previa de la imagen del archivo')

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

    def fetch_and_create_expenses(self, journal_id=None, since=None, until=None, report_api_id=None):
        journals = journal_id or self.env['account.journal'].search([('type', '=', 'bank'), ('employee_id.rindegastos_userid', '!=', False)])
        
        for journal in journals:
            token = self.env.company.rindegastos_tokenid
            if not token:
                raise UserError(f"No se ha configurado un token de Rindegastos para la compañía {self.env.company.name}.")
            
            if not journal.employee_id or not journal.employee_id.rindegastos_userid:
                raise UserError(f"No se ha configurado un empleado con User ID de Rindegastos para el diario {journal.name}.")

            api_url = "https://api.rindegastos.com/v1/getExpenses"
            headers = {"Authorization": f"Bearer {token}"}
            page = 1
            while True:
                params = {
                    'Status': 1,
                    'UserId': journal.employee_id.rindegastos_userid,
                    'ResultsPerPage': 100,
                    'Page': page
                }
                # Solo agregar fechas si NO hay ReportId
                if not report_api_id:
                    if since:
                        params['Since'] = since.strftime('%Y-%m-%d')
                    if until:
                        params['Until'] = until.strftime('%Y-%m-%d')
                if report_api_id:
                    params['ReportId'] = report_api_id
                
                try:
                    response = requests.get(api_url, headers=headers, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    transactions = data.get('Expenses', [])
                    if not transactions:
                        break

                    for tx in transactions:
                        if not all([tx.get('Id'), tx.get('IssueDate'), tx.get('Total')]):
                            continue

                        tx_date = datetime.strptime(tx['IssueDate'], '%Y-%m-%d').date()

                        existing_tx = self.search([
                            ('name', '=', str(tx['Id'])),
                            ('journal_id', '=', journal.id),
                            ('date', '=', tx_date),
                            ('amount', '=', -float(tx['Total'])),
                        ])
                        if existing_tx:
                            continue

                        category = tx.get('Category', '') or 'Sin categoría'
                        supplier = tx.get('Supplier', '') or 'Sin proveedor'
                        tipo_documento = ''
                        numero_documento = ''
                        report_api_id_tx = tx.get('ReportId', '') or ''
                        file_url = ''
                        for extra_field in tx.get('ExtraFields', []):
                            if extra_field.get('Name') == 'Tipo de Documento':
                                tipo_documento = extra_field.get('Value', '') or 'Sin tipo'
                            if extra_field.get('Name') == 'Numero de Documento':
                                numero_documento = extra_field.get('Value', '') or ''
                        payment_ref = f"{category} {supplier} {tipo_documento}" + (f" - {numero_documento}" if numero_documento else "").strip()

                        files = tx.get('Files', [])
                        if files and isinstance(files, list) and 'Large' in files[0]:
                            file_url = files[0].get('Large', '')

                        partner_id = False
                        if tipo_documento in ['Factura Afecta', 'Factura Exenta', 'Honorarios']:
                            for extra_field in tx.get('ExtraFields', []):
                                if extra_field.get('Name') == 'Rut Proveedor':
                                    rut_proveedor = extra_field.get('Value', '')
                                    if rut_proveedor:
                                        partner = self.env['res.partner'].search([('vat', '=', rut_proveedor)], limit=1)
                                        partner_id = partner.id if partner else False
                                    break

                        # Enlace al report
                        report_id = False
                        if report_api_id_tx:
                            report = self.env['rindegastos.report'].search([('name', '=', report_api_id_tx)], limit=1)
                            if report:
                                report_id = report.id
                            else:
                                _logger.warning(f"No se encontró report con ID {report_api_id_tx} para expense {tx['Id']}. Enlace no creado.")

                        self.create({
                            'name': str(tx['Id']),
                            'date': tx_date,
                            'amount': -float(tx['Total']),
                            'description': payment_ref,
                            'journal_id': journal.id,
                            'partner_id': partner_id,
                            'report_id': report_id,
                            'file_url': file_url,
                        })

                    total_pages = data.get('Records', {}).get('Pages', 1)
                    if page >= total_pages:
                        break
                    page += 1
                except requests.exceptions.RequestException as e:
                    raise UserError(f"Error al conectar con la API de Rindegastos: {str(e)}")

    def create_account_move(self):
        for expense in self:
            if expense.state == 'posted':
                continue

            if not expense.journal_id or not expense.journal_id.suspense_account_id or not expense.journal_id.default_account_id:
                raise UserError("Configuración incompleta en el diario.")

            statement_line_vals = {
                'date': expense.date,
                'payment_ref': expense.description or expense.name,
                'ref': expense.name,
                'amount': expense.amount,
                'journal_id': expense.journal_id.id,
                'partner_id': expense.partner_id.id if expense.partner_id else False,
                'rindegastos_file_url': expense.file_url,
            }
            existing_statement_line = self.env['account.bank.statement.line'].search([
                ('ref', '=', expense.name),
                ('journal_id', '=', expense.journal_id.id),
                ('date', '=', expense.date),
                ('amount', '=', expense.amount),
            ])
            if existing_statement_line:
                continue

            statement_line = self.env['account.bank.statement.line'].create(statement_line_vals)
            move = statement_line.move_id
            if move:
                expense.write({'move_id': move.id, 'state': 'draft'})

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