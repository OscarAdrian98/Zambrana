import pymysql
import logging
# Función para obtener la configuración FTP y Excel de un proveedor desde la base de datos
def obtener_configuraciones_proveedor(id_proveedor, conexion_proveedores):
    try:
        cursor = conexion_proveedores.cursor()
        consulta = (
            "SELECT ftp_server_configuracion, ftp_port_configuracion, "
            "ftp_user_configuracion, ftp_pass_configuracion, "
            "fichero_configuracion, extension_configuracion, "
            "col_referencia_configuracion, col_stock_configuracion, "
            "fila_comienzo_configuracion, separador_csv_configuracion, "
            "id_marca, http_configuracion, plazo_entrega_proveedor, "
            "col_ean_configuracion, col_fecha_configuracion "
            "FROM configuracion_proveedores cp "
            "INNER JOIN proveedores p ON cp.id_proveedor = p.id_proveedor "
            "WHERE p.id_proveedor = %s"
        )
        print(f"Consulta SQL: {consulta}")
        cursor.execute(consulta, (id_proveedor,))
        resultados = cursor.fetchall()
        return resultados
    except pymysql.Error as err:
        print(f"Error al obtener las configuraciones FTP y Excel: {err}")
        return None
    
# Función para sincronizar las bases de datos.
def comparar_bases_de_datos(conexion_proveedores, conexion_prestashop, id_proveedor, id_marca):
    resultados = []

    try:
        # Realizar INNER JOIN en la base de datos con la nueva consulta
        query = """
        SELECT
            tb_prestashop.id_product,
            tb_prestashop.id_product_attribute,
            tb_prestashop.reference,
            tb_prestashop.ean13,
            tb_prestashop.quantity,
            tb_proveedores.id_proveedor,
            tb_proveedores.id_marca,
            tb_proveedores.stock_txt_producto,
            tb_proveedores.hay_stock_producto,
            tb_proveedores.ean_producto,
            tb_proveedores.fecha_disponibilidad_producto
        FROM
            (SELECT
                p.id_product,
                0 AS id_product_attribute,
                p.reference,
                p.ean13,
                sa.quantity 
            FROM
                ps_product p
                LEFT JOIN ps_stock_available sa ON 
                    (p.id_product = sa.id_product AND sa.id_product_attribute = 0)
            WHERE
                (p.reference <> '' AND p.reference IS NOT NULL AND p.reference NOT LIKE 'pack_%%')
                
            UNION 
                
            SELECT
                pa.id_product,
                pa.id_product_attribute,
                pa.reference,
                pa.ean13,
                sa.quantity 
            FROM
                ps_product_attribute pa
                LEFT JOIN ps_stock_available sa ON 
                    (pa.id_product_attribute = sa.id_product_attribute)
            WHERE
                (pa.reference <> '' AND pa.reference IS NOT NULL AND pa.reference NOT LIKE 'pack_%%' AND pa.id_product <> 0)

            UNION

            SELECT
                p.id_product,
                0 AS id_product_attribute,
                ps.product_supplier_reference AS reference,
                '' AS ean13,
                sa.quantity 
            FROM
                ps_product p
                INNER JOIN ps_product_supplier ps ON 
                    (p.id_product = ps.id_product AND ps.id_product_attribute = 0)
                LEFT JOIN ps_stock_available sa ON 
                    (p.id_product = sa.id_product AND sa.id_product_attribute = 0)
            WHERE
                (ps.product_supplier_reference <> '' AND ps.product_supplier_reference IS NOT NULL AND ps.product_supplier_reference NOT LIKE 'pack_%%' AND p.reference <> '' AND p.reference IS NOT NULL)

            UNION

            SELECT
                pa.id_product,
                pa.id_product_attribute,
                ps.product_supplier_reference AS reference,
                '' AS ean13,
                sa.quantity 
            FROM
                ps_product_attribute pa
                INNER JOIN ps_product_supplier ps ON 
                    (pa.id_product_attribute = ps.id_product_attribute)
                LEFT JOIN ps_stock_available sa ON 
                    (pa.id_product_attribute = sa.id_product_attribute)
            WHERE
                (ps.product_supplier_reference <> '' AND ps.product_supplier_reference IS NOT NULL AND ps.product_supplier_reference NOT LIKE 'pack_%%' AND pa.reference <> '' AND pa.reference IS NOT NULL AND pa.id_product <> 0)
            ) AS tb_prestashop
        JOIN 
            stock_proveedores.productos AS tb_proveedores ON tb_proveedores.referencia_producto = tb_prestashop.reference
        WHERE tb_proveedores.id_proveedor = %s AND tb_proveedores.id_marca = %s
        
        UNION

        SELECT
            tb_prestashop.id_product,
            tb_prestashop.id_product_attribute,
            tb_prestashop.reference,
            tb_prestashop.ean13,
            tb_prestashop.quantity,
            tb_proveedores.id_proveedor,
            tb_proveedores.id_marca,
            tb_proveedores.stock_txt_producto,
            tb_proveedores.hay_stock_producto,
            tb_proveedores.ean_producto,
            tb_proveedores.fecha_disponibilidad_producto
        FROM
            (SELECT
                p.id_product,
                0 AS id_product_attribute,
                p.reference,
                p.ean13,
                sa.quantity 
            FROM
                ps_product p
                LEFT JOIN ps_stock_available sa ON 
                    (p.id_product = sa.id_product AND sa.id_product_attribute = 0)
            WHERE
                (p.reference <> '' AND p.reference IS NOT NULL AND p.reference NOT LIKE 'pack_%%')
                
            UNION 
                
            SELECT
                pa.id_product,
                pa.id_product_attribute,
                pa.reference,
                pa.ean13,
                sa.quantity 
            FROM
                ps_product_attribute pa
                LEFT JOIN ps_stock_available sa ON 
                    (pa.id_product_attribute = sa.id_product_attribute)
            WHERE
                (pa.reference <> '' AND pa.reference IS NOT NULL AND pa.reference NOT LIKE 'pack_%%' AND pa.id_product <> 0)

            UNION

            SELECT
                p.id_product,
                0 AS id_product_attribute,
                ps.product_supplier_reference AS reference,
                '' AS ean13,
                sa.quantity 
            FROM
                ps_product p
                INNER JOIN ps_product_supplier ps ON 
                    (p.id_product = ps.id_product AND ps.id_product_attribute = 0)
                LEFT JOIN ps_stock_available sa ON 
                    (p.id_product = sa.id_product AND sa.id_product_attribute = 0)
            WHERE
                (ps.product_supplier_reference <> '' AND ps.product_supplier_reference IS NOT NULL AND ps.product_supplier_reference NOT LIKE 'pack_%%' AND p.reference <> '' AND p.reference IS NOT NULL)

            UNION

            SELECT
                pa.id_product,
                pa.id_product_attribute,
                ps.product_supplier_reference AS reference,
                '' AS ean13,
                sa.quantity 
            FROM
                ps_product_attribute pa
                INNER JOIN ps_product_supplier ps ON 
                    (pa.id_product_attribute = ps.id_product_attribute)
                LEFT JOIN ps_stock_available sa ON 
                    (pa.id_product_attribute = sa.id_product_attribute)
            WHERE
                (ps.product_supplier_reference <> '' AND ps.product_supplier_reference IS NOT NULL AND ps.product_supplier_reference NOT LIKE 'pack_%%' AND pa.reference <> '' AND pa.reference IS NOT NULL AND pa.id_product <> 0)
            ) AS tb_prestashop
        JOIN 
            stock_proveedores.productos AS tb_proveedores ON tb_proveedores.ean_producto = tb_prestashop.ean13
        WHERE tb_proveedores.id_proveedor = %s AND tb_proveedores.id_marca = %s
"""

        with conexion_prestashop.cursor() as cursor_prestashop:
            cursor_prestashop.execute(query, (id_proveedor, id_marca, id_proveedor, id_marca))
            resultados = cursor_prestashop.fetchall()

        # Extraer y devolver los campos necesarios
        campos_necesarios = [{'reference': resultado[2], 
                            'quantity': resultado[4],
                            'stock_txt_producto': resultado[7], 
                            'hay_stock_producto': resultado[8], 
                            'ean_producto': resultado[9],
                            'fecha_disponibilidad_producto': resultado[10]}
                            for resultado in resultados]
        return campos_necesarios

    except pymysql.Error as e:
        logging.error(f"Error al comparar bases de datos: {e}")
        return resultados