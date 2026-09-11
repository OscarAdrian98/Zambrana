"""Adaptador de configuración para las interfaces existentes."""
import os
driver = os.environ.get('SQLSERVER_DRIVER', 'ODBC Driver 18 for SQL Server')
host_ambar = os.environ.get('SQLSERVER_HOST', 'localhost')
bd_ambar = os.environ.get('SQLSERVER_DATABASE', 'erp_example')
user_ambar = os.environ.get('SQLSERVER_USER', '')
pass_ambar = os.environ.get('SQLSERVER_PASSWORD', '')
host_prest = os.environ.get('MYSQL_HOST', 'localhost')
puerto = int(os.environ.get('MYSQL_PORT', '3306'))
bd_prest = os.environ.get('MYSQL_DATABASE', 'prestashop_example')
user_prest = os.environ.get('MYSQL_USER', '')
pass_prest = os.environ.get('MYSQL_PASSWORD', '')
