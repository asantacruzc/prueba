from odoo import models, fields, api
import requests
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    rindegastos_userid = fields.Char(string='Rindegastos User ID', help='ID del usuario en Rindegastos, importado por email')

    def action_import_rindegastos_userid(self):
        """Importa el User ID de Rindegastos usando el email del empleado y actualiza el campo. Si no existe, deja en blanco."""
        self.ensure_one()
        if not self.work_email:
            raise UserError("El empleado no tiene un correo electrónico configurado (work_email).")

        token = self.env.company.rindegastos_tokenid
        if not token:
            raise UserError("No se ha configurado un token de Rindegastos en la configuración de la compañía.")

        api_url = "https://api.rindegastos.com/v1/getUser"
        headers = {"Authorization": f"Bearer {token}"}
        params = {'Email': self.work_email}

        _logger.info(f"Enviando solicitud a {api_url} para email: {self.work_email}")
        try:
            response = requests.get(api_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data and 'Id' in data and data['Id'] and str(data['Id']) != '0':
                self.rindegastos_userid = str(data['Id'])
                _logger.info(f"User ID importado y actualizado: {self.rindegastos_userid} para el empleado {self.name}")
                message = f'User ID de Rindegastos actualizado: {self.rindegastos_userid}'
            else:
                self.rindegastos_userid = ''
                _logger.warning(f"No se encontró un usuario válido en Rindegastos para el email {self.work_email}. Campo dejado en blanco.")
                message = f'No se encontró un usuario válido para el email {self.work_email}. Campo dejado en blanco.'

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Resultado de Importación',
                    'message': message,
                    'sticky': False,
                }
            }
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al conectar con la API de Rindegastos: {str(e)}")
            raise UserError(f"Error al conectar con la API de Rindegastos: {str(e)}")