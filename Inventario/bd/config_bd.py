"""SQL Server se configura mediante variables del proceso."""
import os
DB_CONFIG = {
    'driver': os.environ.get('SQLSERVER_DRIVER', 'ODBC Driver 18 for SQL Server'),
    'server': os.environ.get('SQLSERVER_HOST', 'localhost'),
    'database': os.environ.get('SQLSERVER_DATABASE', 'inventory_example'),
    'username': os.environ.get('SQLSERVER_USER', ''),
    'password': os.environ.get('SQLSERVER_PASSWORD', ''),
}
