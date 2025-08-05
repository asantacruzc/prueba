{
    'name': 'Rindegastos Mov Integration',
    'version': '1.0',
    'summary': 'Módulo unificado para integrar reports y expenses de Rindegastos API a diarios contables en Odoo v17',
    'author': 'Maatyer',
    'depends': ['account', 'rindegastos_userid', 'account_accountant', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/rindegastos_mov_wizard_views.xml',
        'views/rindegastos_report_views.xml',
        'views/rindegastos_expense_views.xml',
        'views/account_journal_views.xml',
        'views/res_config_settings_views.xml',
        'views/bank_statement_line_views.xml',  # Debe estar aquí
        'data/cron.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}