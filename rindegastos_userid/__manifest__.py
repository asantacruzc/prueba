{
    'name': 'Rindegastos User ID Integration',
    'version': '1.0',
    'summary': 'Integra User ID de Rindegastos con empleados en Odoo',
    'author': 'Maatyer',
    'depends': ['hr'],  # Solo depende de hr
    'data': [
        'views/hr_employee_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}