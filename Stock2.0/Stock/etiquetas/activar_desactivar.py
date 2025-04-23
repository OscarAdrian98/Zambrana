import logging
import config.etiquetas
from config.logging import logger_funciones_especificas

# Funcion para activar productos.
def activate_products(connection, dataframe, batch_size=5000):
    cursor = connection.cursor()

    try:
        # Filtrar solo las referencias de la tabla ps_product
        ps_product_df = dataframe[dataframe['table'] == 'ps_product']

        # Preparación de lotes de referencias para ps_product
        references = [(row['reference'], row['stock_combinado']) for index, row in ps_product_df.iterrows()]
        reference_batches = [references[i:i+batch_size] for i in range(0, len(references), batch_size)]

        for batch in reference_batches:
            # Preparación de referencias para la actualización
            references_to_activate = [reference for reference, combined_stock in batch if combined_stock > 0]

            if references_to_activate:
                # Actualizar ps_product y ps_product_shop en lote
                placeholders = ', '.join(['%s'] * len(references_to_activate))
                query_activate_product = f"UPDATE ps_product SET active = 1 WHERE reference IN ({placeholders})"
                query_activate_product_shop = f"""
                    UPDATE ps_product_shop
                    SET active = 1
                    WHERE id_product IN (
                        SELECT id_product
                        FROM ps_product
                        WHERE reference IN ({placeholders})
                    )
                """
                cursor.execute(query_activate_product, tuple(references_to_activate))
                cursor.execute(query_activate_product_shop, tuple(references_to_activate))

                connection.commit()

                for reference in references_to_activate:
                    logging.info(f"Productos activados para referencia {reference} con stock disponible.")
                    logger_funciones_especificas.info(f"Productos activados para referencia {reference} con stock disponible.")

    except Exception as e:
        logging.error(f"Error durante la activación de productos en lote: {e}")
        logger_funciones_especificas.error(f"Error durante la activación de productos en lote: {e}")
        connection.rollback()

    finally:
        cursor.close()

# Funcion para activar productos supplier.
def activate_simple_products_from_supplier(connection, dataframe, batch_size=5000):
    cursor = connection.cursor()

    try:
        # Filtrar el DataFrame para obtener solo las referencias de la tabla "ps_product_supplier"
        ps_product_supplier_df = dataframe[dataframe['table'] == 'ps_product_supplier']

        # Crear una lista de referencias y stocks para la tabla "ps_product_supplier"
        references_and_stock = [(row['reference'], row['stock_combinado']) for index, row in ps_product_supplier_df.iterrows()]

        # Dividir las referencias en lotes de tamaño especificado
        references_batches = [references_and_stock[i:i+batch_size] for i in range(0, len(references_and_stock), batch_size)]

        for batch in references_batches:
            # Crear una lista de referencias para el lote
            references_batch = [reference for reference, combined_stock in batch if combined_stock > 0]

            # Crear marcadores de posición para la consulta SQL ('%s', '%s', ...)
            placeholders = ', '.join(['%s'] * len(references_batch))

            if references_batch:
                # Activar productos que no son atributos y tienen stock
                query_activate_products = f"""
                    UPDATE ps_product pp
                    INNER JOIN ps_product_supplier ps ON pp.id_product = ps.id_product
                    SET pp.active = 1
                    WHERE ps.product_supplier_reference IN ({placeholders})
                    AND ps.id_product_attribute = 0
                """
                cursor.execute(query_activate_products, tuple(references_batch))

                # Activar en ps_product_shop
                query_activate_product_shop = f"""
                    UPDATE ps_product_shop
                    SET active = 1
                    WHERE id_product IN (
                        SELECT id_product
                        FROM ps_product_supplier
                        WHERE product_supplier_reference IN ({placeholders})
                    )
                """
                cursor.execute(query_activate_product_shop, tuple(references_batch))

                connection.commit()
                for reference in references_batch:
                    logging.info(f"Activando productos ps_product_supplier para referencia {reference} con stock disponible.")
                    logger_funciones_especificas.info(f"Activando productos ps_product_supplier para referencia {reference} con stock disponible.")

    except Exception as e:
        logging.error(f"Error durante la activación de productos simples: {e}")
        logger_funciones_especificas.error(f"Error durante la activación de productos simples: {e}")

    finally:
        cursor.close()

# Funcion para desactivar Attributos.
def deactivate_attributes(connection, dataframe, batch_size=500):
    cursor = connection.cursor()
    # Lista para almacenar los id_product únicos afectados
    affected_products = set()
    # Lista para almacenar id_product para actualizar available_for_order
    products_to_update_available = set()

    try:
        ps_product_attribute_df = dataframe[dataframe['table'] == 'ps_product_attribute']
        ps_product_attribute_df = ps_product_attribute_df[ps_product_attribute_df['id_proveedor'].isin([8, 9, 10])]
        references_and_stock = [(row['reference'], row['stock_combinado']) for index, row in ps_product_attribute_df.iterrows()]
        batches = [references_and_stock[i:i + batch_size] for i in range(0, len(references_and_stock), batch_size)]

        for batch in batches:
            refs_with_stock = [ref for ref, stock in batch if stock > 0]
            refs_without_stock = [ref for ref, stock in batch if stock == 0]

            if refs_without_stock:
                placeholders = ', '.join(['%s'] * len(refs_without_stock))
                query_deactivate = f"""
                    UPDATE ps_product_attribute_shop
                    SET id_shop = {config.etiquetas.desactivar_atributo}
                    WHERE id_product_attribute IN (
                        SELECT id_product_attribute
                        FROM ps_product_attribute
                        WHERE reference IN ({placeholders})
                    )
                """
                cursor.execute(query_deactivate, tuple(refs_without_stock))

                # Actualizar cache_default_attribute en lotes
                query_update_cache = f"""
                    UPDATE ps_product_shop
                    SET cache_default_attribute = NULL
                    WHERE id_product IN (
                        SELECT DISTINCT id_product
                        FROM ps_product_attribute
                        WHERE reference IN ({placeholders})
                    )
                """
                cursor.execute(query_update_cache, tuple(refs_without_stock))
                query_update_cache = f"""
                    UPDATE ps_product
                    SET cache_default_attribute = NULL
                    WHERE id_product IN (
                        SELECT DISTINCT id_product
                        FROM ps_product_attribute
                        WHERE reference IN ({placeholders})
                    )
                """
                cursor.execute(query_update_cache, tuple(refs_without_stock))

                for ref in refs_without_stock:
                    logging.info(f"Referencia '{ref}' desactivada y cache_default_attribute actualizado a NULL. id_shop establecido en {config.etiquetas.desactivar_atributo}.")
                    logger_funciones_especificas.info(f"Referencia '{ref}' desactivada y cache_default_attribute actualizado a NULL. id_shop establecido en {config.etiquetas.desactivar_atributo}.")

                # Agregar id_product afectados a la lista para la verificación final
                query_get_affected_products = f"""
                    SELECT DISTINCT id_product
                    FROM ps_product_attribute
                    WHERE reference IN ({placeholders})
                """
                cursor.execute(query_get_affected_products, tuple(refs_without_stock))
                affected_products.update([item[0] for item in cursor.fetchall()])

            # Actualizar referencias con stock
            if refs_with_stock:
                placeholders = ', '.join(['%s'] * len(refs_with_stock))
                query_activate = f"""
                    UPDATE ps_product_attribute_shop
                    SET id_shop = {config.etiquetas.activar_atributo}
                    WHERE id_product_attribute IN (
                        SELECT id_product_attribute
                        FROM ps_product_attribute
                        WHERE reference IN ({placeholders})
                    )
                """
                cursor.execute(query_activate, tuple(refs_with_stock))

                # Obtener id_product de los atributos activados y activar el producto correspondiente
                query_get_id_product = f"""
                    SELECT DISTINCT id_product
                    FROM ps_product_attribute
                    WHERE reference IN ({placeholders})
                """
                cursor.execute(query_get_id_product, tuple(refs_with_stock))
                id_products_to_activate = cursor.fetchall()

                if id_products_to_activate:
                    placeholders_products = ', '.join(['%s'] * len(id_products_to_activate))
                    query_activate_product = f"UPDATE ps_product SET active = 1, available_for_order = 1 WHERE id_product IN ({placeholders_products})"
                    query_activate_product_shop = f"UPDATE ps_product_shop SET active = 1, available_for_order = 1 WHERE id_product IN ({placeholders_products})"
                    cursor.execute(query_activate_product, id_products_to_activate)
                    cursor.execute(query_activate_product_shop, id_products_to_activate)

                for ref in refs_with_stock:
                    logging.info(f"Referencia '{ref}' activada y available_for_order. id_shop establecido en {config.etiquetas.activar_atributo}.")
                    logger_funciones_especificas.info(f"Referencia '{ref}' activada y available_for_order. id_shop establecido en {config.etiquetas.activar_atributo}.")

            connection.commit()

        # Verificación final para cada id_product afectado
        for id_product in affected_products:
            check_id_shop_query = f"""
                SELECT COUNT(*) AS total, SUM(CASE WHEN id_shop = 99 THEN 1 ELSE 0 END) AS total_99
                FROM ps_product_attribute_shop
                WHERE id_product = %s
            """
            cursor.execute(check_id_shop_query, (id_product,))
            result = cursor.fetchone()
            total, total_99 = result

            if total == total_99:
                # Agregar id_product a la lista para la actualización en lote de available_for_order
                products_to_update_available.add(id_product)

        # Si hay productos para actualizar available_for_order, hacerlo en lote
        if products_to_update_available:
            placeholders = ', '.join(['%s'] * len(products_to_update_available))
            update_available_for_order_query = f"""
                UPDATE ps_product
                SET available_for_order = 0
                WHERE id_product IN ({placeholders})
            """
            cursor.execute(update_available_for_order_query, tuple(products_to_update_available))

            update_available_for_order_shop_query = f"""
                UPDATE ps_product_shop
                SET available_for_order = 0
                WHERE id_product IN ({placeholders})
            """
            cursor.execute(update_available_for_order_shop_query, tuple(products_to_update_available))

            for id_product in products_to_update_available:
                logging.info(f"available_for_order actualizado a 0 para el producto con id_product {id_product} ya que todos los id_shop están en 99.")
                logger_funciones_especificas.info(f"available_for_order actualizado a 0 para el producto con id_product {id_product} ya que todos los id_shop están en 99.")

        # 🟢 Verificación global: reactivar available_for_order para productos que tienen al menos un atributo con stock y activo
        try:
            query_reactivar = """
                UPDATE ps_product p
                INNER JOIN (
                    SELECT pa.id_product
                    FROM ps_product_attribute_shop pas
                    INNER JOIN ps_product_attribute pa ON pas.id_product_attribute = pa.id_product_attribute
                    INNER JOIN ps_stock_available sa ON sa.id_product_attribute = pa.id_product_attribute AND sa.id_shop = 1
                    WHERE pas.id_shop = 1 AND sa.quantity > 0
                    GROUP BY pa.id_product
                ) activos ON p.id_product = activos.id_product
                SET p.available_for_order = 1
            """
            cursor.execute(query_reactivar)

            query_reactivar_shop = """
                UPDATE ps_product_shop ps
                INNER JOIN (
                    SELECT pa.id_product
                    FROM ps_product_attribute_shop pas
                    INNER JOIN ps_product_attribute pa ON pas.id_product_attribute = pa.id_product_attribute
                    INNER JOIN ps_stock_available sa ON sa.id_product_attribute = pa.id_product_attribute AND sa.id_shop = 1
                    WHERE pas.id_shop = 1 AND sa.quantity > 0
                    GROUP BY pa.id_product
                ) activos ON ps.id_product = activos.id_product
                SET ps.available_for_order = 1
            """
            cursor.execute(query_reactivar_shop)

            logging.info("✅ Se ha asegurado available_for_order = 1 para productos con al menos un atributo activo y con stock.")
            logger_funciones_especificas.info("✅ Se ha asegurado available_for_order = 1 para productos con al menos un atributo activo y con stock.")
        except Exception as e:
            logging.error(f"❌ Error al asegurar available_for_order = 1 para productos activos con stock: {e}")
            logger_funciones_especificas.error(f"❌ Error al asegurar available_for_order = 1 para productos activos con stock: {e}")

        connection.commit()

    except Exception as e:
        logging.error(f"Error durante la actualización de available_for_order: {e}")
        logger_funciones_especificas.error(f"Error durante la actualización de available_for_order: {e}")

    finally:
        cursor.close()

# Función para desactivar los atributos de supplier.
def update_id_shop_in_attribute_shop_supplier(connection, dataframe, batch_size=500):
    cursor = connection.cursor()

    # Definir la consulta para verificar si la referencia está en ps_product_attribute
    query_is_attribute = """
        SELECT COUNT(*)
        FROM ps_product_attribute pa
        INNER JOIN ps_product_supplier ps ON pa.id_product_attribute = ps.id_product_attribute
        WHERE ps.product_supplier_reference = %s
    """

    try:
        # Filtrar el DataFrame para obtener solo las referencias de la tabla "ps_product_supplier"
        ps_product_supplier_df = dataframe[dataframe['table'] == 'ps_product_supplier']

        # Dividir las referencias y el stock en lotes de tamaño especificado
        batches = [ps_product_supplier_df[i:i + batch_size] for i in range(0, len(ps_product_supplier_df), batch_size)]

        for batch in batches:
            refs_with_stock = []
            refs_without_stock = []

            for index, row in batch.iterrows():
                supplier_reference = row['reference']
                combined_stock = row['stock_combinado']

                # Verificar si la referencia está en ps_product_attribute
                cursor.execute(query_is_attribute, (supplier_reference,))
                is_attribute = cursor.fetchone()[0] > 0

                if is_attribute:
                    if combined_stock > 0:
                        refs_with_stock.append(supplier_reference)
                    else:
                        refs_without_stock.append(supplier_reference)

            # Imprimir las referencias en los lotes
            logging.info(f"Referencias en el lote ps_product_supplier con stock: {refs_with_stock}")
            logging.info(f"Referencias en el lote ps_product_supplier sin stock: {refs_without_stock}")
            logger_funciones_especificas.info(f"Referencias en el lote ps_product_supplier con stock: {refs_with_stock}")
            logger_funciones_especificas.info(f"Referencias en el lote ps_product_supplier sin stock: {refs_without_stock}")


            # Actualizar id_shop en ps_product_attribute_shop para referencias con y sin stock
            if refs_with_stock:
                placeholders = ', '.join(['%s'] * len(refs_with_stock))
                cursor.execute("""
                    UPDATE ps_product_attribute_shop
                    SET id_shop = %s
                    WHERE id_product_attribute IN (
                        SELECT id_product_attribute
                        FROM ps_product_supplier
                        WHERE product_supplier_reference IN (%s)
                    )
                """ % (config.etiquetas.activar_atributo, placeholders), tuple(refs_with_stock))

            if refs_without_stock:
                placeholders = ', '.join(['%s'] * len(refs_without_stock))
                cursor.execute("""
                    UPDATE ps_product_attribute_shop
                    SET id_shop = %s
                    WHERE id_product_attribute IN (
                        SELECT id_product_attribute
                        FROM ps_product_supplier
                        WHERE product_supplier_reference IN (%s)
                    )
                """ % (config.etiquetas.desactivar_atributo, placeholders), tuple(refs_without_stock))

            # Registros de acciones realizadas
            for ref in refs_with_stock:
                logging.info(f"Referencia '{ref}' activada. id_shop establecido en {config.etiquetas.activar_atributo}.")
                logger_funciones_especificas.info(f"Referencia '{ref}' activada. id_shop establecido en {config.etiquetas.activar_atributo}.")
            for ref in refs_without_stock:
                logging.info(f"Referencia '{ref}' desactivada. id_shop establecido en {config.etiquetas.desactivar_atributo}.")
                logger_funciones_especificas.info(f"Referencia '{ref}' desactivada. id_shop establecido en {config.etiquetas.desactivar_atributo}.")

            # Realizar commit después de procesar cada lote
            connection.commit()

        logging.info("Proceso de actualización de id_shop en lotes completado.")
        logger_funciones_especificas.info("Proceso de actualización de id_shop en lotes completado.")

    except Exception as e:
        logging.error(f"Error durante la actualización de id_shop en ps_product_attribute_shop: {e}")
        logger_funciones_especificas.error(f"Error durante la actualización de id_shop en ps_product_attribute_shop: {e}")

    finally:
        cursor.close()