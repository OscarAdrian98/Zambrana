import pyodbc
from bd.config_bd import DB_CONFIG  # Importamos la configuración

def get_connection():
    """Establece la conexión con SQL Server y la retorna."""
    try:
        conn = pyodbc.connect(
            f"DRIVER={DB_CONFIG['driver']};"
            f"SERVER={DB_CONFIG['server']};"
            f"DATABASE={DB_CONFIG['database']};"
            f"UID={DB_CONFIG['username']};"
            f"PWD={DB_CONFIG['password']};"
        )
        return conn
    except Exception as e:
        print(f"❌ Error al conectar con la base de datos: {e}")
        return None

def ejecutar_consulta(query: str, params: tuple = ()):
    """
    Ejecuta una consulta SQL y devuelve los resultados.

    :param query: Consulta SQL a ejecutar.
    :param params: Parámetros de la consulta (opcional).
    :return: Lista de resultados de la consulta.
    """
    conn = get_connection()
    if conn is None:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        resultados = cursor.fetchall()
        conn.close()
        return resultados
    except Exception as e:
        print(f"❌ Error al ejecutar consulta: {e}")
        return []
