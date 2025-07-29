{
    'name': 'Rindegastos API Integration',
    'version': '1.1',
    'summary': 'Módulo para integrar movimientos de Rindegastos API a un diario contable',
    'category': 'Account',
	'author': 'Maatyer',
    'depends': ['account', 'rindegastos_userid','account_accountant'],  # Agrega dependencia
    'data': [
        'security/ir.model.access.csv',
        'views/bank_api_transaction_wizard_views.xml',
        'views/bank_api_transaction_views.xml',
        'views/account_journal_views.xml',
        'views/res_config_settings_views.xml',
        'data/cron.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}