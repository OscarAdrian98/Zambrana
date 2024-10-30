import pymysql


# Configuración para la base de datos de Prestashop
prestashop_config = {
    "host": "servidor",
    "port": "puerto",
    "user": "usuario",
    "password": "contraseña",
    "database": "base de datos",
}

# Configuración para la base de datos de proveedores
proveedores_config = {
    "host": "servidor",
    "port": "puerto",
    "user": "usuario",
    "password": "contraseña",
    "database": "base de datos",
}

# Función para conectar a una base de datos
def conectar_bd(config):
    try:
        conexion = pymysql.connect(**config)
        if conexion.open:
            print(f"Conectado a la base de datos {config['database']}")
            return conexion
    except pymysql.Error as err:
        print(f"Error: {err}")
        return None
    
# Función para cerrar una conexión a la base de datos
def cerrar_conexion(conexion):
    if conexion and conexion.open:  # Verifica si la conexión existe y está abierta
        conexion.close()
        print("Conexión cerrada")

# Función para reconectar a la base de datos
def reconectar_bd(conexion, config):
    cerrar_conexion(conexion)  # Cierra la conexión actual si está abierta
    return conectar_bd(config)