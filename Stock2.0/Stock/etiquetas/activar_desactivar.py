import logging
import config.etiquetas
from config.logging import logger_funciones_especificas
import pandas as pd
from config.rendimiento import commit_con_metricas, medir_fase
from procesamiento.reglas import (
    conjunto_identificadores_validos,
    filtrar_candidatos_reactivacion,
    normalizar_identificador,
    normalizar_serie_identificadores,
)

# Funcion para activar productos.
def activate_products(connection, dataframe, batch_size=5000, metricas=None):
    cursor = connection.cursor()

    try:
        # Filtrar solo las referencias de la tabla ps_product
        ps_product_df = dataframe[dataframe['table'] == 'ps_product']

        # Preparación de lotes de referencias para ps_product
        references = [(row['reference'], row['stock_combinado']) for index, row in ps_product_df.iterrows()]
        reference_batches = [references[i:i+batch_size] for i in range(0, len(references), batch_size)]

        for batch in reference_batches:
            # Preparación de referencias para la actualización
            references_to_activate = [
                referencia
                for reference, combined_stock in batch
                if combined_stock > 0
                and (referencia := normalizar_identificador(reference)) is not None
            ]

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

                commit_con_metricas(connection, metricas)

                for reference in references_to_activate:
                    logging.info(f"Productos activados para referencia {reference} con stock disponible.")
                    logger_funciones_especificas.info(f"Productos activados para referencia {reference} con stock disponible.")

    except Exception as e:
        logging.exception("Error durante la activación de productos en lote")
        logger_funciones_especificas.exception("Error durante la activación de productos en lote")
        connection.rollback()
        raise RuntimeError("No se pudieron activar los productos") from e

    finally:
        cursor.close()

# Funcion para activar productos supplier.
def activate_simple_products_from_supplier(
    connection, dataframe, batch_size=5000, metricas=None
):
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
            references_batch = [
                referencia
                for reference, combined_stock in batch
                if combined_stock > 0
                and (referencia := normalizar_identificador(reference)) is not None
            ]

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
                          AND id_product_attribute = 0
                    )
                """
                cursor.execute(query_activate_product_shop, tuple(references_batch))

                commit_con_metricas(connection, metricas)
                for reference in references_batch:
                    logging.info(f"Activando productos ps_product_supplier para referencia {reference} con stock disponible.")
                    logger_funciones_especificas.info(f"Activando productos ps_product_supplier para referencia {reference} con stock disponible.")

    except Exception as e:
        connection.rollback()
        logging.exception("Error durante la activación de productos simples")
        logger_funciones_especificas.exception("Error durante la activación de productos simples")
        raise RuntimeError("No se pudieron activar los productos simples") from e

    finally:
        cursor.close()

# Funcion para desactivar Attributos.
def deactivate_attributes(connection, dataframe, batch_size=500, metricas=None):
    cursor = connection.cursor()
    # Lista para almacenar los id_product únicos afectados
    affected_products = set()
    # Lista para almacenar id_product para actualizar available_for_order
    products_to_update_available = set()

    try:
        ps_product_attribute_df = dataframe[dataframe['table'] == 'ps_product_attribute']
        ps_product_attribute_df = ps_product_attribute_df[ps_product_attribute_df['id_proveedor'].isin([3, 6, 7, 8, 9, 10, 14])]
        ids_productos_ambito = (
            pd.to_numeric(
                ps_product_attribute_df["id_product"],
                errors="coerce",
            )
            .dropna()
            .astype(int)
            .drop_duplicates()
            .tolist()
        )
        if not ids_productos_ambito:
            logging.info(
                "No hay atributos elegibles del proveedor: se omite la "
                "actualización de available_for_order"
            )
            return
        references_and_stock = [(row['reference'], row['stock_combinado']) for index, row in ps_product_attribute_df.iterrows()]
        batches = [references_and_stock[i:i + batch_size] for i in range(0, len(references_and_stock), batch_size)]

        for batch in batches:
            refs_with_stock = [
                referencia
                for ref, stock in batch
                if stock > 0
                and (referencia := normalizar_identificador(ref)) is not None
            ]
            refs_without_stock = [
                referencia
                for ref, stock in batch
                if stock <= 0
                and (referencia := normalizar_identificador(ref)) is not None
            ]

            if refs_without_stock:
                placeholders = ', '.join(['%s'] * len(refs_without_stock))
                query_deactivate = f"""
                    UPDATE ps_product_attribute_shop
                    SET id_shop = %s
                    WHERE id_product_attribute IN (
                        SELECT id_product_attribute
                        FROM ps_product_attribute
                        WHERE reference IN ({placeholders})
                    )
                """
                cursor.execute(
                    query_deactivate,
                    (
                        config.etiquetas.desactivar_atributo,
                        *refs_without_stock,
                    ),
                )

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
                    SET id_shop = %s
                    WHERE id_product_attribute IN (
                        SELECT id_product_attribute
                        FROM ps_product_attribute
                        WHERE reference IN ({placeholders})
                    )
                """
                cursor.execute(
                    query_activate,
                    (
                        config.etiquetas.activar_atributo,
                        *refs_with_stock,
                    ),
                )

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

            commit_con_metricas(connection, metricas)

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
            placeholders_ambito = ", ".join(
                ["%s"] * len(ids_productos_ambito)
            )
            query_reactivar = f"""
                UPDATE ps_product p
                INNER JOIN (
                    SELECT pa.id_product
                    FROM ps_product_attribute_shop pas
                    INNER JOIN ps_product_attribute pa ON pas.id_product_attribute = pa.id_product_attribute
                    INNER JOIN ps_stock_available sa ON sa.id_product_attribute = pa.id_product_attribute AND sa.id_shop = 1
                    WHERE pas.id_shop = 1 AND sa.quantity > 0
                      AND pa.id_product IN ({placeholders_ambito})
                    GROUP BY pa.id_product
                ) activos ON p.id_product = activos.id_product
                SET p.available_for_order = 1
            """
            cursor.execute(query_reactivar, tuple(ids_productos_ambito))

            query_reactivar_shop = f"""
                UPDATE ps_product_shop ps
                INNER JOIN (
                    SELECT pa.id_product
                    FROM ps_product_attribute_shop pas
                    INNER JOIN ps_product_attribute pa ON pas.id_product_attribute = pa.id_product_attribute
                    INNER JOIN ps_stock_available sa ON sa.id_product_attribute = pa.id_product_attribute AND sa.id_shop = 1
                    WHERE pas.id_shop = 1 AND sa.quantity > 0
                      AND pa.id_product IN ({placeholders_ambito})
                    GROUP BY pa.id_product
                ) activos ON ps.id_product = activos.id_product
                SET ps.available_for_order = 1
            """
            cursor.execute(
                query_reactivar_shop,
                tuple(ids_productos_ambito),
            )

            logging.info("✅ Se ha asegurado available_for_order = 1 para productos con al menos un atributo activo y con stock.")
            logger_funciones_especificas.info("✅ Se ha asegurado available_for_order = 1 para productos con al menos un atributo activo y con stock.")
        except Exception as e:
            logging.exception(
                "Error al asegurar available_for_order para productos con stock"
            )
            logger_funciones_especificas.exception(
                "Error al asegurar available_for_order para productos con stock"
            )
            raise

        commit_con_metricas(connection, metricas)

    except Exception as e:
        connection.rollback()
        logging.exception("Error durante la actualización de available_for_order")
        logger_funciones_especificas.exception("Error durante la actualización de available_for_order")
        raise RuntimeError(
            "No se pudieron desactivar o reactivar los atributos"
        ) from e

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
                supplier_reference = normalizar_identificador(row['reference'])
                if supplier_reference is None:
                    continue
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

# Función para desactivar atributos huerfanos.
def desactivar_atributos_huerfanos_filtrando_marca(
    conexion_prestashop,
    conexion_proveedores,
    prestashop_df,
    id_proveedor,
    metricas=None,
):
    cursor = conexion_prestashop.cursor()

    try:
        # 1. Obtener combinaciones con marca y stock desde PrestaShop
        query_prestashop = """
            SELECT
                pa.id_product_attribute,
                pa.reference,
                pa.ean13,
                pa.id_product,
                sa.quantity,
                m.name AS marca
            FROM ps_product_attribute pa
            JOIN ps_stock_available sa ON sa.id_product_attribute = pa.id_product_attribute
            JOIN ps_product p ON pa.id_product = p.id_product
            LEFT JOIN ps_manufacturer m ON p.id_manufacturer = m.id_manufacturer
            WHERE pa.reference IS NOT NULL AND pa.reference <> ''
        """
        with medir_fase(metricas, "Consulta de PrestaShop"):
            atributos_df = pd.read_sql(query_prestashop, conexion_prestashop)
        atributos_df["_reference_normalizada"] = normalizar_serie_identificadores(
            atributos_df["reference"]
        )
        atributos_df["_ean_normalizado"] = normalizar_serie_identificadores(
            atributos_df["ean13"]
        )

        # 2. Obtener referencias y eans del proveedor actual
        query_proveedor = """
            SELECT referencia_producto, ean_producto
            FROM productos_variantes
            WHERE id_proveedor = %s
              AND presente_ultima_ejecucion = 1
        """
        with medir_fase(metricas, "Consulta de proveedores"):
            proveedor_df = pd.read_sql(
                query_proveedor,
                conexion_proveedores,
                params=(id_proveedor,),
            )
        proveedor_df["_referencia_normalizada"] = normalizar_serie_identificadores(
            proveedor_df["referencia_producto"]
        )
        proveedor_df["_ean_normalizado"] = normalizar_serie_identificadores(
            proveedor_df["ean_producto"]
        )

        referencias_proveedor = conjunto_identificadores_validos(
            proveedor_df["_referencia_normalizada"]
        )
        eans_proveedor = conjunto_identificadores_validos(
            proveedor_df["_ean_normalizado"]
        )

        # 3. Obtener marcas sincronizadas con ese proveedor
        query_marcas = """
            SELECT m.nombre_marca
            FROM marcas_proveedores mp
            JOIN marcas m ON mp.id_marca = m.id_marca
            WHERE mp.id_proveedor = %s
        """
        with medir_fase(metricas, "Consulta de proveedores"):
            marcas_df = pd.read_sql(
                query_marcas,
                conexion_proveedores,
                params=(id_proveedor,),
            )
        marcas_sincronizadas = set(marcas_df['nombre_marca'].str.lower())

        # 4. Filtrar atributos sin stock, marca sincronizada, y no presentes en proveedor
        atributos_df = atributos_df[
            (atributos_df['quantity'] <= 0) &
            (atributos_df['marca'].str.lower().isin(marcas_sincronizadas)) &
            (~atributos_df["_reference_normalizada"].isin(referencias_proveedor)) &
            (~atributos_df["_ean_normalizado"].isin(eans_proveedor))
        ]

        if atributos_df.empty:
            logging.info(f"✅ No hay atributos huérfanos a desactivar para proveedor {id_proveedor}.")
            return

        # 5. Filtrar solo los que todavía están activos (id_shop ≠ valor de desactivación)
        ids_posibles = tuple(atributos_df['id_product_attribute'].tolist())
        placeholders = ', '.join(['%s'] * len(ids_posibles))
        query_estado = f"""
            SELECT id_product_attribute
            FROM ps_product_attribute_shop
            WHERE id_product_attribute IN ({placeholders})
            AND id_shop != %s
        """
        cursor.execute(query_estado, ids_posibles + (config.etiquetas.desactivar_atributo,))
        ids_activos_a_desactivar = [row[0] for row in cursor.fetchall()]

        if not ids_activos_a_desactivar:
            logging.info(f"✅ Todos los atributos ya estaban desactivados para proveedor {id_proveedor}.")
            return

        # Filtrar atributos_df con esos ID
        atributos_df = atributos_df[atributos_df['id_product_attribute'].isin(ids_activos_a_desactivar)]
        ids_productos = atributos_df['id_product'].dropna().unique().tolist()

        # 6. Desactivar en ps_product_attribute_shop
        placeholders = ', '.join(['%s'] * len(ids_activos_a_desactivar))
        cursor.execute(f"""
            UPDATE ps_product_attribute_shop
            SET id_shop = %s
            WHERE id_product_attribute IN ({placeholders})
        """, (config.etiquetas.desactivar_atributo, *ids_activos_a_desactivar))

        # 7. Limpiar cache_default_attribute
        if ids_productos:
            placeholders_prod = ', '.join(['%s'] * len(ids_productos))
            cursor.execute(f"""
                UPDATE ps_product_shop
                SET cache_default_attribute = NULL
                WHERE id_product IN ({placeholders_prod})
            """, tuple(ids_productos))

            cursor.execute(f"""
                UPDATE ps_product
                SET cache_default_attribute = NULL
                WHERE id_product IN ({placeholders_prod})
            """, tuple(ids_productos))

        # 🔒 Verificar si algún producto tiene ya todos sus atributos desactivados
        productos_a_ocultar = set()
        for id_producto in ids_productos:
            cursor.execute("""
                SELECT COUNT(*) AS total, 
                       SUM(CASE WHEN id_shop = %s THEN 1 ELSE 0 END) AS total_desactivados
                FROM ps_product_attribute_shop
                WHERE id_product IN (
                    SELECT id_product
                    FROM ps_product_attribute
                    WHERE id_product = %s
                )
            """, (config.etiquetas.desactivar_atributo, id_producto))
            total, total_desactivados = cursor.fetchone()

            if total == total_desactivados:
                productos_a_ocultar.add(id_producto)

        if productos_a_ocultar:
            placeholders_ocultar = ', '.join(['%s'] * len(productos_a_ocultar))
            cursor.execute(f"""
                UPDATE ps_product
                SET available_for_order = 0, visibility = 'none'
                WHERE id_product IN ({placeholders_ocultar})
            """, tuple(productos_a_ocultar))
            cursor.execute(f"""
                UPDATE ps_product_shop
                SET available_for_order = 0, visibility = 'none'
                WHERE id_product IN ({placeholders_ocultar})
            """, tuple(productos_a_ocultar))
            logging.info(f"🔒 {len(productos_a_ocultar)} productos ocultados y bloqueados para compra por no tener atributos activos.")
            for pid in productos_a_ocultar:
                logger_funciones_especificas.info(f"🔒 Producto {pid} ocultado y bloqueado para compra.")

        commit_con_metricas(conexion_prestashop, metricas)

        for ref in atributos_df['reference']:
            logging.info(f"🚫 Atributo desactivado por proveedor {id_proveedor}: {ref}")
            logger_funciones_especificas.info(f"🚫 Atributo desactivado por proveedor {id_proveedor}: {ref}")

        logging.info(f"✅ Se han desactivado {len(ids_activos_a_desactivar)} atributos huérfanos para proveedor {id_proveedor}")

    except Exception as e:
        conexion_prestashop.rollback()
        logging.exception(
            "Error al desactivar atributos huérfanos del proveedor %s",
            id_proveedor,
        )
        logger_funciones_especificas.exception(
            "Error al desactivar atributos huérfanos del proveedor %s",
            id_proveedor,
        )
        raise RuntimeError(
            f"No se pudieron desactivar atributos huérfanos del proveedor {id_proveedor}"
        ) from e
    finally:
        cursor.close()

# Función para activar todos los atributos desactivados como emergencia.
def reactivar_todos_los_atributos_desactivados(conexion_prestashop):
    cursor = conexion_prestashop.cursor()

    try:
        # 1. Obtener atributos actualmente desactivados (id_shop = 99)
        query = """
            SELECT pa.id_product_attribute, pa.reference
            FROM ps_product_attribute_shop pas
            JOIN ps_product_attribute pa ON pas.id_product_attribute = pa.id_product_attribute
            WHERE pas.id_shop = 99
        """
        cursor.execute(query)
        resultados = cursor.fetchall()

        if not resultados:
            logging.info("✅ No hay atributos desactivados con id_shop = 99.")
            return

        ids_atributos = [row[0] for row in resultados]
        referencias = [row[1] for row in resultados]

        # 2. Reactivar atributos: poner id_shop = 1
        placeholders = ', '.join(['%s'] * len(ids_atributos))
        query_update = f"""
            UPDATE ps_product_attribute_shop
            SET id_shop = 1
            WHERE id_product_attribute IN ({placeholders})
        """
        cursor.execute(query_update, tuple(ids_atributos))

        conexion_prestashop.commit()

        for ref in referencias:
            logging.info(f"🔄 Atributo reactivado: {ref}")
            logger_funciones_especificas.info(f"🔄 Atributo reactivado: {ref}")

        logging.info(f"✅ Se han reactivado {len(ids_atributos)} atributos anteriormente desactivados.")
    except Exception as e:
        conexion_prestashop.rollback()
        logging.error(f"❌ Error al reactivar atributos desactivados: {e}")
        logger_funciones_especificas.error(f"❌ Error al reactivar atributos desactivados: {e}")
    finally:
        cursor.close()

# Función para activar atributos que tengan stock.
def reactivar_atributos_con_stock(
    conexion_prestashop,
    conexion_proveedores,
    id_proveedor,
    metricas=None,
):
    cursor = conexion_prestashop.cursor()

    try:
        # 1. Las marcas ya asociadas al proveedor son el ámbito disponible más
        # fiable en el esquema actual. No se inventa una relación id_supplier.
        query_marcas = """
            SELECT DISTINCT m.nombre_marca
            FROM marcas_proveedores mp
            INNER JOIN marcas m ON m.id_marca = mp.id_marca
            WHERE mp.id_proveedor = %s
              AND m.nombre_marca IS NOT NULL
              AND TRIM(m.nombre_marca) <> ''
        """
        with medir_fase(metricas, "Consulta de proveedores"):
            marcas_df = pd.read_sql(
                query_marcas,
                conexion_proveedores,
                params=(id_proveedor,),
            )
        marcas_proveedor = marcas_df["nombre_marca"].dropna().tolist()
        if not marcas_proveedor:
            logging.warning(
                "Proveedor %s sin marcas configuradas: se omite la reactivación",
                id_proveedor,
            )
            return

        # 2. Obtener todos los identificadores del proveedor y distinguir los
        # que realmente indican stock.
        query_productos_proveedor = """
            SELECT referencia_producto, ean_producto, hay_stock_producto
            FROM productos_variantes
            WHERE id_proveedor = %s
              AND presente_ultima_ejecucion = 1
        """
        with medir_fase(metricas, "Consulta de proveedores"):
            df_proveedor = pd.read_sql(
                query_productos_proveedor,
                conexion_proveedores,
                params=(id_proveedor,),
            )
        df_proveedor["_ref"] = normalizar_serie_identificadores(
            df_proveedor["referencia_producto"]
        )
        df_proveedor["_ean"] = normalizar_serie_identificadores(
            df_proveedor["ean_producto"]
        )
        referencias_proveedor = conjunto_identificadores_validos(
            df_proveedor["_ref"]
        )
        eans_proveedor = conjunto_identificadores_validos(df_proveedor["_ean"])
        proveedor_con_stock = df_proveedor[
            pd.to_numeric(
                df_proveedor["hay_stock_producto"], errors="coerce"
            ).fillna(0) > 0
        ]
        referencias_stock = conjunto_identificadores_validos(
            proveedor_con_stock["_ref"]
        )
        eans_stock = conjunto_identificadores_validos(
            proveedor_con_stock["_ean"]
        )

        # 3. Filtrar en SQL por las marcas del proveedor antes de cargar en
        # Pandas. La referencia de ps_product_supplier aporta una validación
        # adicional sin asumir equivalencias nuevas entre proveedores.
        marcas_normalizadas = sorted(
            {str(marca).strip().casefold() for marca in marcas_proveedor}
        )
        placeholders_marcas = ", ".join(["%s"] * len(marcas_normalizadas))
        query_atributos = f"""
            SELECT
                pa.id_product_attribute,
                pa.reference,
                pa.ean13,
                pa.id_product,
                pas.id_shop,
                sa.quantity,
                m.name AS marca,
                ps.product_supplier_reference AS supplier_reference
            FROM ps_product_attribute pa
            INNER JOIN ps_product_attribute_shop pas
                ON pa.id_product_attribute = pas.id_product_attribute
            INNER JOIN ps_product p ON p.id_product = pa.id_product
            INNER JOIN ps_manufacturer m
                ON m.id_manufacturer = p.id_manufacturer
            LEFT JOIN ps_stock_available sa
                ON pa.id_product_attribute = sa.id_product_attribute
               AND sa.id_shop = 1
            LEFT JOIN ps_product_supplier ps
                ON ps.id_product_attribute = pa.id_product_attribute
            WHERE LOWER(TRIM(m.name)) IN ({placeholders_marcas})
        """
        with medir_fase(metricas, "Consulta de PrestaShop"):
            df_atributos = pd.read_sql(
                query_atributos,
                conexion_prestashop,
                params=tuple(marcas_normalizadas),
            )
        logging.info(
            "Proveedor %s: %s candidatos de sus marcas leídos para reactivación",
            id_proveedor,
            len(df_atributos),
        )
        df_filtrado = filtrar_candidatos_reactivacion(
            df_atributos,
            marcas_proveedor=marcas_proveedor,
            referencias_proveedor=referencias_proveedor,
            eans_proveedor=eans_proveedor,
            referencias_con_stock=referencias_stock,
            eans_con_stock=eans_stock,
        ).drop_duplicates(subset=["id_product_attribute", "id_shop"])

        if df_filtrado.empty:
            logging.info("✅ No hay atributos con stock para reactivar ni activar productos padre.")
            return
        logging.info(
            "Proveedor %s: %s candidatos validados y %s desactivados para reactivar",
            id_proveedor,
            len(df_filtrado),
            int((df_filtrado["id_shop"] == 99).sum()),
        )

        # 4. Reactivar atributos desactivados (id_shop = 99 → id_shop = 1)
        df_a_reactivar = df_filtrado[df_filtrado['id_shop'] == 99]
        if not df_a_reactivar.empty:
            ids_atributos = df_a_reactivar['id_product_attribute'].tolist()
            placeholders = ', '.join(['%s'] * len(ids_atributos))
            cursor.execute(f"""
                UPDATE ps_product_attribute_shop
                SET id_shop = 1
                WHERE id_product_attribute IN ({placeholders})
            """, tuple(ids_atributos))

            for ref in df_a_reactivar['reference']:
                logging.info(f"🔄 Atributo reactivado (estaba en id_shop=99): {ref}")
                logger_funciones_especificas.info(f"🔄 Atributo reactivado (estaba en id_shop=99): {ref}")

        # ✅ NUEVO → Filtrar packs en base a referencia padre
        ids_productos_detectados = df_filtrado['id_product'].unique().tolist()

        if ids_productos_detectados:
            placeholders = ', '.join(['%s'] * len(ids_productos_detectados))

            # Traer referencias padre
            query_refs = f"""
                SELECT id_product, reference
                FROM ps_product
                WHERE id_product IN ({placeholders})
            """
            df_refs = pd.read_sql(query_refs, conexion_prestashop, params=tuple(ids_productos_detectados))
            df_refs['reference'] = df_refs['reference'].fillna('').astype(str)

            # Excluir referencias que empiezan por pack_
            df_refs_filtrado = df_refs[~df_refs['reference'].str.startswith('pack_')]

            ids_productos_a_activar = df_refs_filtrado['id_product'].tolist()

            if ids_productos_a_activar:
                placeholders_prod = ', '.join(['%s'] * len(ids_productos_a_activar))
                cursor.execute(f"""
                    UPDATE ps_product
                    SET active = 1, available_for_order = 1
                    WHERE id_product IN ({placeholders_prod})
                """, tuple(ids_productos_a_activar))

                cursor.execute(f"""
                    UPDATE ps_product_shop
                    SET active = 1, available_for_order = 1
                    WHERE id_product IN ({placeholders_prod})
                """, tuple(ids_productos_a_activar))

                for pid in ids_productos_a_activar:
                    logging.info(f"✅ Producto padre activado: id_product = {pid}")
                    logger_funciones_especificas.info(f"✅ Producto padre activado: id_product = {pid}")
            else:
                logging.info("✅ No hay productos padre a activar tras filtrar packs.")

        commit_con_metricas(conexion_prestashop, metricas)

        logging.info(f"✅ Se ha completado la reactivación de atributos y productos padres para proveedor {id_proveedor}.")

    except Exception as e:
        conexion_prestashop.rollback()
        logging.exception("Error al reactivar atributos con stock")
        logger_funciones_especificas.exception("Error al reactivar atributos con stock")
        raise RuntimeError(
            f"No se pudieron reactivar atributos del proveedor {id_proveedor}"
        ) from e
    finally:
        cursor.close()
        
# Función para detectar productos obsoletos y desactivarlos.
def detectar_productos_obsoletos_para_desactivar(
    conexion_prestashop,
    conexion_proveedores,
    metricas=None,
    solo_previsualizar=False,
):
    from datetime import datetime, timedelta

    cursor = None
    try:
        logging.info("🔍 Buscando productos obsoletos para desactivar...")

        # Obtener fecha límite
        fecha_limite = datetime.now() - timedelta(days=20)

        # 1️⃣ Obtener combinaciones de PrestaShop con su producto padre y stock
        query_combinaciones = """
            SELECT
                p.id_product,
                pa.id_product_attribute,
                pa.reference,
                pa.ean13,
                sa.quantity,
                p.reference AS ref_padre
            FROM ps_product_attribute pa
            JOIN ps_product p ON pa.id_product = p.id_product
            JOIN ps_stock_available sa ON sa.id_product_attribute = pa.id_product_attribute AND sa.id_shop = 1
            WHERE pa.reference IS NOT NULL AND pa.reference != ''
        """
        with medir_fase(metricas, "Consulta de PrestaShop"):
            combinaciones_df = pd.read_sql(
                query_combinaciones,
                conexion_prestashop,
            )
        combinaciones_df["_reference_normalizada"] = (
            normalizar_serie_identificadores(combinaciones_df["reference"])
        )
        combinaciones_df["_ean_normalizado"] = (
            normalizar_serie_identificadores(combinaciones_df["ean13"])
        )

        # 2️⃣ Obtener datos del proveedor
        query_proveedor = """
            SELECT referencia_producto, ean_producto, hay_stock_producto, fecha_actualizacion_producto
            FROM productos_variantes
            WHERE presente_ultima_ejecucion = 1
        """
        with medir_fase(metricas, "Consulta de proveedores"):
            proveedor_df = pd.read_sql(query_proveedor, conexion_proveedores)
        proveedor_df["_referencia_normalizada"] = (
            normalizar_serie_identificadores(
                proveedor_df["referencia_producto"]
            )
        )
        proveedor_df["_ean_normalizado"] = normalizar_serie_identificadores(
            proveedor_df["ean_producto"]
        )
        proveedor_df['fecha_actualizacion_producto'] = pd.to_datetime(
            proveedor_df['fecha_actualizacion_producto'], errors='coerce'
        )
        proveedor_df["hay_stock_producto"] = pd.to_numeric(
            proveedor_df["hay_stock_producto"], errors="coerce"
        ).fillna(0)

        # 3️⃣ Agregar antes de mapear evita el producto cartesiano que generaban
        # los dos merges cuando había identificadores duplicados o ausentes.
        proveedor_ref = (
            proveedor_df.dropna(subset=["_referencia_normalizada"])
            .groupby("_referencia_normalizada")
            .agg(
                stock_ref=("hay_stock_producto", "max"),
                fecha_ref=("fecha_actualizacion_producto", "max"),
            )
        )
        proveedor_ean = (
            proveedor_df.dropna(subset=["_ean_normalizado"])
            .groupby("_ean_normalizado")
            .agg(
                stock_ean=("hay_stock_producto", "max"),
                fecha_ean=("fecha_actualizacion_producto", "max"),
            )
        )
        combinaciones_df["stock_ref"] = combinaciones_df[
            "_reference_normalizada"
        ].map(proveedor_ref["stock_ref"])
        combinaciones_df["stock_ean"] = combinaciones_df[
            "_ean_normalizado"
        ].map(proveedor_ean["stock_ean"])
        combinaciones_df["hay_stock"] = (
            combinaciones_df[["stock_ref", "stock_ean"]]
            .max(axis=1)
            .fillna(0)
        )
        combinaciones_df["fecha_ref"] = combinaciones_df[
            "_reference_normalizada"
        ].map(proveedor_ref["fecha_ref"])
        combinaciones_df["fecha_ean"] = combinaciones_df[
            "_ean_normalizado"
        ].map(proveedor_ean["fecha_ean"])
        combinaciones_df["fecha_actualizacion"] = combinaciones_df[
            ["fecha_ref", "fecha_ean"]
        ].max(axis=1)

        # 4️⃣ Filtrar combinaciones sin stock y sin actualizar en más de 20 días
        combinaciones_df['fecha_actualizacion'] = pd.to_datetime(combinaciones_df['fecha_actualizacion'], errors='coerce')
        combinaciones_df['cumple_obsoleto'] = (
            (combinaciones_df['quantity'] <= 0) &
            (combinaciones_df['hay_stock'] == 0) &
            (combinaciones_df['fecha_actualizacion'] < fecha_limite)
        )

        # 5️⃣ Agrupar por producto padre: si todas las combinaciones están obsoletas => desactivar
        resumen = combinaciones_df.groupby('id_product')['cumple_obsoleto'].all().reset_index()
        productos_a_desactivar = resumen[resumen['cumple_obsoleto'] == True]['id_product'].tolist()

        if not productos_a_desactivar:
            logging.info("✅ No hay productos obsoletos a desactivar.")
            return pd.DataFrame()

        # 6️⃣ Confirmar que están activos antes de desactivar
        cursor = conexion_prestashop.cursor()
        placeholders = ','.join(['%s'] * len(productos_a_desactivar))
        query_activos = f"""
            SELECT id_product FROM ps_product
            WHERE id_product IN ({placeholders}) AND active = 1
        """
        cursor.execute(query_activos, productos_a_desactivar)
        activos = [row[0] for row in cursor.fetchall()]

        if not activos:
            logging.info("✅ No hay productos activos que cumplan criterios de obsoletos.")
            return pd.DataFrame()

        candidatos = combinaciones_df[
            combinaciones_df['id_product'].isin(activos)
        ].copy()

        if solo_previsualizar:
            logging.info(
                "Previsualización: %s productos obsoletos activos; "
                "no se realizan cambios",
                len(activos),
            )
            return candidatos

        # 7️⃣ Desactivar productos
        placeholders = ','.join(['%s'] * len(activos))
        cursor.execute(f"UPDATE ps_product SET active = 0 WHERE id_product IN ({placeholders})", activos)
        cursor.execute(f"UPDATE ps_product_shop SET active = 0 WHERE id_product IN ({placeholders})", activos)
        commit_con_metricas(conexion_prestashop, metricas)

        for pid in activos:
            logging.info(f"🚫 Producto desactivado por obsoleto: ID {pid}")
            logger_funciones_especificas.info(f"🚫 Producto desactivado por obsoleto: ID {pid}")

        logging.info(f"📆 Productos obsoletos detectados: {len(activos)}")

        return candidatos

    except Exception as e:
        conexion_prestashop.rollback()
        logging.exception("Error al detectar productos obsoletos")
        raise RuntimeError("No se pudieron detectar productos obsoletos") from e
    finally:
        if cursor is not None:
            cursor.close()


def previsualizar_productos_obsoletos(
    conexion_prestashop,
    conexion_proveedores,
    metricas=None,
):
    """Devuelve exactamente los candidatos obsoletos sin escribir SQL."""

    return detectar_productos_obsoletos_para_desactivar(
        conexion_prestashop,
        conexion_proveedores,
        metricas=metricas,
        solo_previsualizar=True,
    )
