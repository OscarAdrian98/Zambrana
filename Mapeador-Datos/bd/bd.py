import mysql.connector
import pyodbc
from mysql.connector import Error as MySQLError
from pyodbc import Error as SQLServerError
import bd.confi

class DatabaseConnector:
    def __init__(self):
        # Credenciales para AMBAR (SQL Server)
        self.ambar_config = {
            'driver': bd.confi.driver,
            'server': bd.confi.host_ambar,  
            'database': bd.confi.bd_ambar,
            'user': bd.confi.user_ambar,
            'password': bd.confi.pass_ambar
        }
        
        # Credenciales para PRESTASHOP (MySQL)
        self.prestashop_config = {
            'host': bd.confi.host_prest,
            'port': bd.confi.puerto,
            'user': bd.confi.user_prest,
            'password': bd.confi.pass_prest,
            'database': bd.confi.bd_prest
        }
        
        self.ambar_connection = None
        self.prestashop_connection = None

    def connect_to_ambar(self):
        """Establece conexión con la base de datos AMBAR (SQL Server)"""
        try:
            # Crear string de conexión para SQL Server
            conn_str = (
                f"DRIVER={self.ambar_config['driver']};"
                f"SERVER={self.ambar_config['server']};"
                f"DATABASE={self.ambar_config['database']};"
                f"UID={self.ambar_config['user']};"
                f"PWD={self.ambar_config['password']}"
            )
            
            self.ambar_connection = pyodbc.connect(conn_str)
            print("Conexión exitosa a AMBAR")
            return self.ambar_connection
            
        except SQLServerError as e:
            print(f"Error al conectar a AMBAR: {e}")
            return None

    def connect_to_prestashop(self):
        """Establece conexión con la base de datos PRESTASHOP (MySQL)"""
        try:
            self.prestashop_connection = mysql.connector.connect(**self.prestashop_config)
            if self.prestashop_connection.is_connected():
                print("Conexión exitosa a PRESTASHOP")
                return self.prestashop_connection
        except MySQLError as e:
            print(f"Error al conectar a PRESTASHOP: {e}")
            return None

    def close_connections(self):
        """Cierra las conexiones a ambas bases de datos"""
        if self.ambar_connection:
            try:
                self.ambar_connection.close()
                print("Conexión a AMBAR cerrada")
            except SQLServerError as e:
                print(f"Error al cerrar conexión de AMBAR: {e}")
            
        if self.prestashop_connection and self.prestashop_connection.is_connected():
            try:
                self.prestashop_connection.close()
                print("Conexión a PRESTASHOP cerrada")
            except MySQLError as e:
                print(f"Error al cerrar conexión de PRESTASHOP: {e}")

# Ejemplo de uso
if __name__ == "__main__":
    # Crear instancia del conector
    db = DatabaseConnector()
    
    # Establecer conexiones
    ambar_conn = db.connect_to_ambar()
    prestashop_conn = db.connect_to_prestashop()
    
    # Cerrar conexiones
    db.close_connections()