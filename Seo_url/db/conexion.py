# conexion.py

import pymysql
from db.config import prestashop_config, seo_config

def basedatos_prestashop():
    """
    Devuelve una conexión a la base de datos PrestaShop.
    """
    connection = pymysql.connect(
        host=prestashop_config["host"],
        port=prestashop_config["port"],
        user=prestashop_config["user"],
        password=prestashop_config["password"],
        database=prestashop_config["database"],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    return connection

def basedatos_seo():
    """
    Devuelve una conexión a la base de datos plantilla_importar.
    """
    connection = pymysql.connect(
        host=seo_config["host"],
        port=seo_config["port"],
        user=seo_config["user"],
        password=seo_config["password"],
        database=seo_config["database"],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    return connection
