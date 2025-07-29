{
    'name': 'Rindegastos Report Integration',
    'version': '1.0',
    'summary': 'Módulo para integrar reportes de Rindegastos API a un diario contable',
    'author': 'Maatyer',
    'depends': ['account', 'rindegastos_userid','rindegastos_api_integration'],
    'data': [
        'security/ir.model.access.csv',
        'views/bank_api_report_wizard_views.xml',
        'views/bank_api_report_views.xml',
        'views/account_journal_views.xml',
        'views/res_config_settings_views.xml',
        'data/cron.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}