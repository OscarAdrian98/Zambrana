import pymysql
import time
from typing import Optional, Dict

# Configuración para la base de datos de Prestashop
prestashop_config = {
    "host": "",
    "port": ,
    "user": "",
    "password": "",
    "database": "",
    "connect_timeout": 300,        # 5 minutos timeout conexión
    "read_timeout": 300,           # 5 minutos timeout lectura
    "write_timeout": 300,          # 5 minutos timeout escritura
    "charset": 'utf8mb4',
    "init_command": 'SET NAMES utf8mb4'
}

# Configuración para la base de datos de proveedores
proveedores_config = {
    "host": "",
    "port": ,
    "user": "",
    "password": "",
    "database": "",
    "connect_timeout": 300,
    "read_timeout": 300,
    "write_timeout": 300,
    "charset": 'utf8mb4',
    "init_command": 'SET NAMES utf8mb4'
}

def crear_conexion_con_reintentos(config: Dict, max_intentos: int = 3, espera: int = 5) -> Optional[pymysql.Connection]:
    """
    Crea una conexión a la base de datos con reintentos automáticos.
    
    Args:
        config: Diccionario con la configuración de la base de datos
        max_intentos: Número máximo de intentos de conexión
        espera: Tiempo de espera entre intentos en segundos
    """
    for intento in range(max_intentos):
        try:
            conexion = pymysql.connect(**config)
            # Configurar la sesión para mayor estabilidad
            with conexion.cursor() as cursor:
                # Ejecutar cada comando por separado
                cursor.execute("SET SESSION net_read_timeout=300")
                cursor.execute("SET SESSION net_write_timeout=300")
                cursor.execute("SET SESSION wait_timeout=300")
                cursor.execute("SET SESSION interactive_timeout=300")
            conexion.commit()
            print(f"Conectado a la base de datos {config['database']}")
            return conexion
        except pymysql.Error as e:
            print(f"Intento {intento + 1}/{max_intentos} falló: {e}")
            if intento < max_intentos - 1:
                time.sleep(espera)
            else:
                raise
    return None

def reconectar_bd_si_necesario(conexion: pymysql.Connection, config: Dict) -> Optional[pymysql.Connection]:
    """
    Verifica y reconecta la base de datos si es necesario.
    """
    try:
        conexion.ping(reconnect=True)
        return conexion
    except (pymysql.Error, AttributeError):
        print("Reconectando a la base de datos...")
        return crear_conexion_con_reintentos(config)

def conectar_bd(config: Dict) -> Optional[pymysql.Connection]:
    """
    Función principal para conectar a la base de datos.
    """
    try:
        conexion = crear_conexion_con_reintentos(config)
        return conexion
    except pymysql.Error as err:
        print(f"Error: {err}")
        return None

def ejecutar_query_con_reintentos(conexion: pymysql.Connection, query: str, params=None, max_intentos: int = 3):
    """
    Ejecuta una query con reintentos automáticos si hay errores de conexión.
    
    Args:
        conexion: Conexión a la base de datos
        query: Consulta SQL a ejecutar
        params: Parámetros para la consulta (opcional)
        max_intentos: Número máximo de intentos
    """
    for intento in range(max_intentos):
        try:
            if not conexion.open:
                conexion = reconectar_bd_si_necesario(conexion, conexion.config)
            
            with conexion.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
        except pymysql.Error as e:
            if "MySQL server has gone away" in str(e) and intento < max_intentos - 1:
                print(f"Conexión perdida, reintentando... ({intento + 1}/{max_intentos})")
                time.sleep(5)
                conexion = reconectar_bd_si_necesario(conexion, conexion.config)
            else:
                raise

def cerrar_conexion(conexion: Optional[pymysql.Connection]):
    """
    Cierra la conexión de manera segura.
    """
    if conexion and getattr(conexion, 'open', False):
        try:
            conexion.close()
            print("Conexión cerrada correctamente")
        except pymysql.Error as e:
            print(f"Error al cerrar la conexión: {e}")
