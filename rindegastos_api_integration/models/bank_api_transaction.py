from odoo import models, fields, api
import requests
from odoo.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class BankApiTransaction(models.Model):
    _name = 'bank.api.transaction'
    _description = 'Movimientos desde Rindegastos API'

    name = fields.Char(string='Referencia', required=True)
    date = fields.Date(string='Fecha', required=True)
    amount = fields.Float(string='Monto', required=True)
    description = fields.Text(string='Descripción')
    journal_id = fields.Many2one('account.journal', string='Diario Contable', domain=[('type', '=', 'bank')])
    move_id = fields.Many2one('account.move', string='Asiento Contable', readonly=True)
    state = fields.Selection([('draft', 'Borrador'), ('posted', 'Contabilizado')], default='draft')
    partner_id = fields.Many2one('res.partner', string='Contacto', readonly=True)
    employee_name = fields.Char(string='Empleado', compute='_compute_employee_name', store=False, help='Nombre del empleado que rindió el gasto')
    report_id = fields.Char(string='ID de Reporte', help='ID del reporte de Rindegastos')
    file_url = fields.Char(string='Enlace al Archivo', help='Enlace al archivo del gasto en Rindegastos')
    file_preview = fields.Html(string='Vista Previa del Archivo', compute='_compute_file_preview', store=False, help='Vista previa de la imagen del archivo')

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

    def fetch_and_create_transactions(self, journal_id=None, since=None, until=None):
        """Consulta la API de Rindegastos y crea movimientos con filtros."""
        journals = journal_id or self.env['account.journal'].search([('type', '=', 'bank'), ('employee_id.rindegastos_userid', '!=', False)])
        
        for journal in journals:
            token = self.env.company.rindegastos_tokenid
            if not token:
                _logger.error(f"No se ha configurado un token de Rindegastos para la compañía {self.env.company.name}")
                raise UserError(f"No se ha configurado un token de Rindegastos para la compañía {self.env.company.name}.")
            
            if not journal.employee_id or not journal.employee_id.rindegastos_userid:
                _logger.error(f"No se ha configurado un empleado con User ID de Rindegastos para el diario {journal.name}")
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
                    transactions = data.get('Expenses', [])
                    if not transactions:
                        _logger.warning(f"No se encontraron transacciones para el diario {journal.name} con UserId {journal.employee_id.rindegastos_userid}, Página {page}")
                        break

                    for tx in transactions:
                        _logger.debug(f"Procesando transacción: {tx}")
                        if not all([tx.get('Id'), tx.get('IssueDate'), tx.get('Total')]):
                            _logger.warning(f"Transacción inválida: {tx}")
                            continue

                        try:
                            tx_date = datetime.strptime(tx['IssueDate'], '%Y-%m-%d').date()
                        except ValueError:
                            _logger.warning(f"Fecha inválida en transacción: {tx.get('IssueDate')}")
                            continue

                        existing_tx = self.search([
                            ('name', '=', str(tx['Id'])),
                            ('journal_id', '=', journal.id),
                            ('date', '=', tx_date),
                            ('amount', '=', -float(tx['Total'])),
                        ])
                        if existing_tx:
                            _logger.info(f"Transacción {tx['Id']} ya existe para el diario {journal.name} con fecha {tx_date} y monto {-float(tx['Total'])}")
                            continue

                        category = tx.get('Category', '') or 'Sin categoría'
                        supplier = tx.get('Supplier', '') or 'Sin proveedor'
                        tipo_documento = ''
                        numero_documento = ''
                        report_id = tx.get('ReportId', '') or ''
                        file_url = ''
                        for extra_field in tx.get('ExtraFields', []):
                            if extra_field.get('Name') == 'Tipo de Documento':
                                tipo_documento = extra_field.get('Value', '') or 'Sin tipo'
                            if extra_field.get('Name') == 'Numero de Documento':
                                numero_documento = extra_field.get('Value', '') or ''
                        payment_ref = f"{category} {supplier} {tipo_documento}" + (f" - {numero_documento}" if numero_documento else "").strip()

                        # Extraer enlace Large del primer archivo en Files
                        files = tx.get('Files', [])
                        if files and isinstance(files, list) and 'Large' in files[0]:
                            file_url = files[0].get('Large', '')
                            _logger.debug(f"Enlace Large extraído: {file_url}")
                        else:
                            _logger.debug(f"No se encontraron archivos o Large en transacción: {tx['Id']}")

                        partner_id = False
                        if tipo_documento in ['Factura Afecta', 'Factura Exenta', 'Honorarios']:
                            for extra_field in tx.get('ExtraFields', []):
                                if extra_field.get('Name') == 'Rut Proveedor':
                                    rut_proveedor = extra_field.get('Value', '')
                                    if rut_proveedor:
                                        partner = self.env['res.partner'].search([('vat', '=', rut_proveedor)], limit=1)
                                        partner_id = partner.id if partner else False
                                        if not partner:
                                            _logger.warning(f"No se encontró partner con RUT {rut_proveedor} para la transacción {tx['Id']}")
                                    break

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
                        _logger.info(f"Transacción creada: {tx['Id']} para el diario {journal.name} con payment_ref: {payment_ref}, report_id: {report_id}, file_url: {file_url}")

                    total_pages = data.get('Records', {}).get('Pages', 1)
                    if page >= total_pages:
                        break
                    page += 1
                except requests.exceptions.RequestException as e:
                    _logger.error(f"Error al conectar con la API de Rindegastos para el diario {journal.name}: {str(e)}")
                    raise UserError(f"Error al conectar con la API de Rindegastos: {str(e)}")

    def create_account_move(self):
        """Crea una línea en el estado de cuenta bancario para cada transacción, dejando el asiento en borrador."""
        for transaction in self:
            if transaction.state == 'posted':
                continue

            if not transaction.journal_id:
                _logger.error(f"No se ha configurado un diario contable para la transacción {transaction.name}")
                raise UserError("Seleccione un diario contable para la transacción.")

            if not transaction.journal_id.suspense_account_id:
                _logger.error(f"No se ha configurado una cuenta transitoria para el diario {transaction.journal_id.name}")
                raise UserError(f"No se ha configurado una cuenta transitoria para el diario {transaction.journal_id.name}")

            default_account = transaction.journal_id.default_account_id
            if not default_account:
                _logger.error(f"No se ha configurado una cuenta predeterminada para el diario {transaction.journal_id.name}")
                raise UserError(f"No se ha configurado una cuenta predeterminada para el diario {transaction.journal_id.name}")

            statement_line_vals = {
                'date': transaction.date,
                'payment_ref': transaction.description or transaction.name,
                'ref': transaction.name,
                'amount': transaction.amount,
                'journal_id': transaction.journal_id.id,
                'partner_id': transaction.partner_id.id if transaction.partner_id else False,
            }
            existing_statement_line = self.env['account.bank.statement.line'].search([
                ('ref', '=', transaction.name),
                ('journal_id', '=', transaction.journal_id.id),
                ('date', '=', transaction.date),
                ('amount', '=', transaction.amount),
            ])
            if existing_statement_line:
                _logger.info(f"Línea de estado de cuenta ya existe para la transacción {transaction.name} en el diario {transaction.journal_id.name}")
                continue

            statement_line = self.env['account.bank.statement.line'].create(statement_line_vals)
            _logger.info(f"Línea de estado de cuenta creada: {statement_line.payment_ref}")

            move = statement_line.move_id
            if move:
                transaction.write({
                    'move_id': move.id,
                    'state': 'draft',
                })
                _logger.info(f"Asiento contable {move.name} creado en borrador para la transacción {transaction.name}")
            else:
                _logger.error(f"No se generó un asiento contable para la línea {statement_line.payment_ref}")
                raise UserError(f"No se generó un asiento contable para la línea {statement_line.payment_ref}")

    @api.model
    def cron_fetch_transactions(self):
        """Tarea programada para consultar la API periódicamente."""
        self.fetch_and_create_transactions()
        transactions = self.search([('state', '=', 'draft')])
        transactions.create_account_move()