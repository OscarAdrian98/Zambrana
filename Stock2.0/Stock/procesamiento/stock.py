import pymysql
import logging
import pandas as pd

# Función para obtener referencias y stock de la base de datos proveedor.
def obtener_todas_referencias_y_stock(id_proveedor, conexion_proveedores):
    try:
        cursor = conexion_proveedores.cursor()

        # Obtener todas las referencias y el stock para el proveedor específico
        consulta_stock = (
            "SELECT referencia_producto, stock_txt_producto "
            "FROM productos "
            "WHERE id_proveedor = %s"
        )
        cursor.execute(consulta_stock, (id_proveedor,))
        resultados = cursor.fetchall()


        # Crear un DataFrame con los resultados
        df_stock = pd.DataFrame(resultados, columns=['referencia_producto', 'stock_txt_producto'])
        #print("Datos obtenidos correctamente:")
        #print(df_stock)  # Agrega esta línea para imprimir los datos obtenidos
        return df_stock

    except pymysql.Error as err:
        print(f"Error al obtener todas las referencias y el stock desde la base de datos: {err}")
        return None

# Función para verificar si hay stock en la base de datos Prestashop.
def has_stock(connection_proveedores, connection_prestashop, id_proveedor, original_reference):
    cursor_prestashop = connection_prestashop.cursor()

    try:
        logging.info(f"Debug - Verificando si hay stock para la referencia: {original_reference}")

        # Consulta para verificar la cantidad en ps_stock_available para ps_product_attribute
        query_attribute = """
            SELECT quantity
            FROM ps_stock_available
            WHERE id_product_attribute IN (SELECT id_product_attribute FROM ps_product_attribute WHERE reference = %s)
        """

        # Consulta para verificar la cantidad en ps_stock_available para ps_product
        query_product = """
            SELECT quantity
            FROM ps_stock_available
            WHERE id_product IN (SELECT id_product FROM ps_product WHERE reference = %s)
        """

        # Consulta para verificar la cantidad en ps_stock_available para ps_product_supplier (id_product)
        query_supplier_id_product_attribute = """
            SELECT quantity
            FROM ps_stock_available
            WHERE id_product_attribute IN (SELECT id_product_attribute FROM ps_product_supplier WHERE product_supplier_reference = %s)
        """

        # Consulta para verificar la cantidad en ps_stock_available para ps_product_supplier (id_product)
        query_supplier_id_product = """
            SELECT quantity
            FROM ps_stock_available
            WHERE id_product IN (SELECT id_product FROM ps_product_supplier WHERE product_supplier_reference = %s)
        """

        # Verificar si la referencia está en las referencias del proveedor
        df_referencias = obtener_todas_referencias_y_stock(id_proveedor, connection_proveedores)

        if df_referencias is not None:
            referencias_prestashop = set(df_referencias['referencia_producto'])

            if original_reference in referencias_prestashop:
                # Verificar si hay stock en ps_stock_available para ps_product_attribute
                cursor_prestashop.execute(query_attribute, (original_reference,))
                result_attribute = cursor_prestashop.fetchone()

                if result_attribute and result_attribute[0] > 0:
                    print(f"Debug - Has_stock encontrado en ps_stock_available para ps_product_attribute: {result_attribute[0]}")
                    return True

                # Si no hay stock en ps_stock_available para ps_product_attribute, verificar en ps_stock_available para ps_product
                cursor_prestashop.execute(query_product, (original_reference,))
                result_product = cursor_prestashop.fetchone()

                if result_product and result_product[0] > 0:
                    print(f"Debug - Has_stock encontrado en ps_stock_available para ps_product: {result_product[0]}")
                    return True

                # Si no hay stock en ps_stock_available para ps_product_attribute ni en ps_stock_available para ps_product, verificar en ps_stock_available para ps_product_supplier (id_product)
                cursor_prestashop.execute(query_supplier_id_product, (original_reference,))
                result_supplier_id_product = cursor_prestashop.fetchone()

                if result_supplier_id_product and result_supplier_id_product[0] > 0:
                    print("Debug - Has_stock encontrado en ps_stock_available para ps_product_supplier (id_product)")
                    return True

                # Si no hay stock en ninguna de las anteriores, verificar en ps_stock_available para ps_product_supplier (id_product_attribute)
                cursor_prestashop.execute(query_supplier_id_product_attribute, (original_reference,))
                result_supplier_id_product_attribute = cursor_prestashop.fetchone()

                if result_supplier_id_product_attribute and result_supplier_id_product_attribute[0] > 0:
                    print("Debug - Has_stock encontrado en ps_stock_available para ps_product_supplier (id_product_attribute)")
                    return True

        # Retornar False si no hay stock en ninguna tabla o si la referencia no está en las referencias del proveedor
        return False

    except Exception as e:
        print(f"Error al verificar si hay stock para {original_reference}: {e}")
        return False

    finally:
        cursor_prestashop.close()