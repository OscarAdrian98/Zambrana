import logging
from config.configuracion_proveedor import comparar_bases_de_datos
import config.etiquetas
from config.logging import logger_funciones_especificas
from datetime import timedelta, datetime
import pandas as pd

# Función para actualizar las etiquetas de disponibilidad y transporte.
def update_labels(connection, df, conexion_proveedores, id_proveedor, batch_size=5000):
    logging.info("Iniciando la actualización de etiquetas en lotes")
    logger_funciones_especificas.info("Iniciando la actualización de etiquetas en lotes")

    # Obtener configuraciones iniciales
    plazo_entrega_query = f"SELECT plazo_entrega_proveedor FROM proveedores WHERE id_proveedor = {id_proveedor}"
    conexion_proveedores_cursor = conexion_proveedores.cursor()
    conexion_proveedores_cursor.execute(plazo_entrega_query)
    plazo_entrega_resultado = conexion_proveedores_cursor.fetchone()

    if plazo_entrega_resultado: 
        plazo_entrega_proveedor = plazo_entrega_resultado[0] # Etiqueta del proveedor
    else:
        plazo_entrega_proveedor = config.etiquetas.entrega_proveedor_predeterminado

    delivery_in_stock_label = config.etiquetas.etiqueta_stock
    delivery_out_stock_label_default = config.etiquetas.etiqueta_no_stock

    references_with_stock = {}
    references_without_stock = {}

    # Verificar si la columna 'fecha_mas_cercana' está presente en el DataFrame
    if 'fecha_mas_cercana' in df.columns:
        fecha_column_present = True
    else:
        fecha_column_present = False
        
    # Crear un cursor a partir de la conexión a la base de datos
    cursor = connection.cursor()
    
    if fecha_column_present:
        for table in df['table'].unique():
            table_updates = df[df['table'] == table]

            if table == 'ps_product':
                refs_with_date_and_stock, refs_without_date_with_stock, refs_without_date_without_stock = [], [], []

                for index, row in table_updates.iterrows():
                    fecha = row['fecha_mas_cercana']
                    stock = row['stock_combinado']
                    has_valid_date = fecha not in [None, '', pd.NaT, '0000-00-00 00:00:00']

                    if has_valid_date and stock > 0:
                        refs_with_date_and_stock.append((row['reference'], fecha))
                    elif not has_valid_date and stock > 0:
                        refs_without_date_with_stock.append(row['reference'])
                    elif not has_valid_date and stock <= 0:
                        refs_without_date_without_stock.append(row['reference'])

                # Procesar actualizaciones en lotes para referencias con fecha y stock
                for ref, date in refs_with_date_and_stock:
                    if isinstance(date, pd.Timestamp):
                        fecha_modificada = date + timedelta(days=5)
                    else:
                        fecha_modificada = datetime.strptime(date, "%Y-%m-%d %H:%M:%S") + timedelta(days=5)
                    formatted_fecha = fecha_modificada.strftime("%d-%m-%Y")

                    update_query_with_date = f"""
                        UPDATE ps_product_lang pl
                        JOIN ps_product p ON pl.id_product = p.id_product
                        SET pl.delivery_in_stock = '{config.etiquetas.etiqueta_stock}', pl.delivery_out_stock = 'Envío el {formatted_fecha}'
                        WHERE p.reference = %s
                    """
                    cursor.execute(update_query_with_date, (ref,))
                    logging.info(f"Actualizando etiquetas para ps_product. Referencia: {ref}, Stock: con, delivery_in_stock_label = '{config.etiquetas.etiqueta_stock}', delivery_out_stock_label = 'Envío el {formatted_fecha}'")
                    logger_funciones_especificas.info(f"Actualizando etiquetas para ps_product. Referencia: {ref}, Stock: con, delivery_in_stock_label = '{config.etiquetas.etiqueta_stock}', delivery_out_stock_label = 'Envío el {formatted_fecha}'")

                # Procesar actualizaciones en lotes para referencias sin fecha y con stock
                for ref in refs_without_date_with_stock:
                    update_query_without_date_with_stock = f"""
                        UPDATE ps_product_lang pl
                        JOIN ps_product p ON pl.id_product = p.id_product
                        SET pl.delivery_in_stock = '{config.etiquetas.etiqueta_stock}', pl.delivery_out_stock = '{plazo_entrega_proveedor}'
                        WHERE p.reference = %s
                    """
                    cursor.execute(update_query_without_date_with_stock, (ref,))
                    logging.info(f"Actualizando etiquetas para ps_product. Referencia: {ref}, Stock: con, delivery_in_stock_label = '{config.etiquetas.etiqueta_stock}', delivery_out_stock_label = '{plazo_entrega_proveedor}'")
                    logger_funciones_especificas.info(f"Actualizando etiquetas para ps_product. Referencia: {ref}, Stock: con, delivery_in_stock_label = '{config.etiquetas.etiqueta_stock}', delivery_out_stock_label = '{plazo_entrega_proveedor}'")

                # Procesar actualizaciones en lotes para referencias sin fecha y sin stock
                for ref in refs_without_date_without_stock:
                    update_query_without_date_without_stock = f"""
                        UPDATE ps_product_lang pl
                        JOIN ps_product p ON pl.id_product = p.id_product
                        SET pl.delivery_in_stock = '{config.etiquetas.etiqueta_stock}', pl.delivery_out_stock = '{config.etiquetas.etiqueta_no_stock}'
                        WHERE p.reference = %s
                    """
                    cursor.execute(update_query_without_date_without_stock, (ref,))
                    logging.info(f"Actualizando etiquetas para ps_product. Referencia: {ref}, Stock: sin, delivery_in_stock_label = '{config.etiquetas.etiqueta_stock}', delivery_out_stock_label_default = '{config.etiquetas.etiqueta_no_stock}'")
                    logger_funciones_especificas.info(f"Actualizando etiquetas para ps_product. Referencia: {ref}, Stock: sin, delivery_in_stock_label = '{config.etiquetas.etiqueta_stock}', delivery_out_stock_label_default = '{config.etiquetas.etiqueta_no_stock}'")

                connection.commit()
                logging.info("Actualizaciones en lotes completadas para 'ps_product'")
                logger_funciones_especificas.info("Actualizaciones en lotes completadas para 'ps_product'")

            elif table == 'ps_product_attribute':
                # Obtener todas las referencias y dividirlas en lotes
                all_references = table_updates[['reference', 'stock_combinado']].values.tolist()
                batches = [all_references[i:i + batch_size] for i in range(0, len(all_references), batch_size)]

                for batch in batches:
                    # Preparar listas para las consultas
                    references_with_stock = []
                    references_without_stock = []

                    # Clasificar las referencias en con stock y sin stock
                    for reference, stock_combinado in batch:
                        if stock_combinado > 0:
                            references_with_stock.append(reference)
                        else:
                            references_without_stock.append(reference)

                    # Actualizar referencias con stock
                    if references_with_stock:
                        placeholders_with_stock = ', '.join(['%s'] * len(references_with_stock))
                        update_query_with_stock = f"""
                            UPDATE ps_product_lang pl
                            JOIN ps_product_attribute p ON pl.id_product = p.id_product
                            SET pl.delivery_in_stock = '{config.etiquetas.etiqueta_stock}', pl.delivery_out_stock = '{config.etiquetas.etiqueta_proveedor_attribute}'
                            WHERE p.reference IN ({placeholders_with_stock})
                        """
                        cursor.execute(update_query_with_stock, references_with_stock)
                        for reference in references_with_stock:
                            logging.info(f"Actualizando etiquetas para ps_product_attribute. Referencia: {reference}, Stock: con, delivery_in_stock_label = '{config.etiquetas.etiqueta_stock}', delivery_out_stock_label = '{config.etiquetas.etiqueta_proveedor_attribute}'")
                            logger_funciones_especificas.info(f"Actualizando etiquetas para ps_product_attribute. Referencia: {reference}, Stock: con, delivery_in_stock_label = '{config.etiquetas.etiqueta_stock}', delivery_out_stock_label = '{config.etiquetas.etiqueta_proveedor_attribute}'")

                    # Actualizar referencias sin stock
                    if references_without_stock:
                        placeholders_without_stock = ', '.join(['%s'] * len(references_without_stock))
                        update_query_without_stock = f"""
                            UPDATE ps_product_lang pl
                            JOIN ps_product_attribute p ON pl.id_product = p.id_product
                            SET pl.delivery_in_stock = '{config.etiquetas.etiqueta_stock}', pl.delivery_out_stock = '{config.etiquetas.etiqueta_proveedor_attribute}'
                            WHERE p.reference IN ({placeholders_without_stock})
                        """
                        cursor.execute(update_query_without_stock, references_without_stock)
                        for reference in references_without_stock:
                            logging.info(f"Actualizando etiquetas para ps_product_attribute. Referencia: {reference}, Stock: sin, delivery_in_stock_label = '{config.etiquetas.etiqueta_stock}', delivery_out_stock_label_default = '{config.etiquetas.etiqueta_proveedor_attribute}'")
                            logger_funciones_especificas.info(f"Actualizando etiquetas para ps_product_attribute. Referencia: {reference}, Stock: sin, delivery_in_stock_label = '{config.etiquetas.etiqueta_stock}', delivery_out_stock_label_default = '{config.etiquetas.etiqueta_proveedor_attribute}'")

                # Confirmar las actualizaciones después de procesar todos los lotes
                connection.commit()
                logging.info("Actualizaciones en lotes completadas para 'ps_product_attribute'")
                logger_funciones_especificas.info("Actualizaciones en lotes completadas para 'ps_product_attribute'")

    if not fecha_column_present:
        for index, row in df.iterrows():
            reference = row['reference']
            table = row['table']
            combined_stock = row['stock_combinado']

            if combined_stock > 0:
                if table not in references_with_stock:
                    references_with_stock[table] = []
                references_with_stock[table].append((reference, combined_stock))
            else:
                if table not in references_without_stock:
                    references_without_stock[table] = []
                references_without_stock[table].append((reference, combined_stock))

    try:
        # Crear un cursor a partir de la conexión a la base de datos
        cursor = connection.cursor()

        if not fecha_column_present:
            # Procesar referencias sin stock
            for table, references in references_without_stock.items():
                batches = [references[i:i+batch_size] for i in range(0, len(references), batch_size)]
                for batch in batches:
                    placeholders = ', '.join(['%s'] * len(batch))
                    query_values = [delivery_in_stock_label, delivery_out_stock_label_default] + [ref[0] for ref in batch]

                    if table == 'ps_product_attribute':
                        query = f"""
                            UPDATE ps_product_lang
                            SET delivery_in_stock = %s, delivery_out_stock = %s
                            WHERE id_product IN (SELECT id_product FROM ps_product_attribute WHERE reference IN ({placeholders}))
                        """
                    elif table == 'ps_product':
                        query = f"""
                            UPDATE ps_product_lang
                            SET delivery_in_stock = %s, delivery_out_stock = %s
                            WHERE id_product IN (SELECT id_product FROM ps_product WHERE reference IN ({placeholders}))
                        """
                    elif table == 'ps_product_supplier':
                        query = f"""
                            UPDATE ps_product_lang
                            SET delivery_in_stock = %s, delivery_out_stock = %s
                            WHERE id_product IN (SELECT id_product FROM ps_product_supplier WHERE product_supplier_reference IN ({placeholders}))
                        """

                    #print(f"Consulta SQL: {query}")
                    #print(f"Valores de consulta: {query_values}")

                    cursor.execute(query, query_values)

                    for reference, stock in batch:
                        logging.info(f"Actualizando etiquetas en lote para la tabla {table}. Referencia: {reference}, Stock: {stock}, delivery_in_stock_label: {delivery_in_stock_label}, delivery_out_stock_label: {delivery_out_stock_label_default}")
                        logger_funciones_especificas.info(f"Actualizando etiquetas en lote para la tabla {table}. Referencia: {reference}, Stock: {stock}, delivery_in_stock_label: {delivery_in_stock_label}, delivery_out_stock_label: {delivery_out_stock_label_default}")


            # Procesar referencias con stock
            for table, references in references_with_stock.items():
                batches = [references[i:i+batch_size] for i in range(0, len(references), batch_size)]
                for batch in batches:
                    placeholders = ', '.join(['%s'] * len(batch))
                    query_values = [delivery_in_stock_label, plazo_entrega_proveedor] + [ref[0] for ref in batch]

                    if table == 'ps_product_attribute':
                        query = f"""
                            UPDATE ps_product_lang
                            SET delivery_in_stock = %s, delivery_out_stock = %s
                            WHERE id_product IN (SELECT id_product FROM ps_product_attribute WHERE reference IN ({placeholders}))
                        """
                    elif table == 'ps_product':
                        query = f"""
                            UPDATE ps_product_lang
                            SET delivery_in_stock = %s, delivery_out_stock = %s
                            WHERE id_product IN (SELECT id_product FROM ps_product WHERE reference IN ({placeholders}))
                        """
                    elif table == 'ps_product_supplier':
                        query = f"""
                            UPDATE ps_product_lang
                            SET delivery_in_stock = %s, delivery_out_stock = %s
                            WHERE id_product IN (SELECT id_product FROM ps_product_supplier WHERE product_supplier_reference IN ({placeholders}))
                        """

                    #print(f"Consulta SQL: {query}")
                    #print(f"Valores de consulta: {query_values}")

                    cursor.execute(query, query_values)

                    for reference, stock in batch:
                        logging.info(f"Actualizando etiquetas en lote para la tabla {table}. Referencia: {reference}, Stock: {stock}, delivery_in_stock_label: {delivery_in_stock_label}, delivery_out_stock_label: {plazo_entrega_proveedor}")
                        logger_funciones_especificas.info(f"Actualizando etiquetas en lote para la tabla {table}. Referencia: {reference}, Stock: {stock}, delivery_in_stock_label: {delivery_in_stock_label}, delivery_out_stock_label: {plazo_entrega_proveedor}")

        connection.commit()
        logging.info("Actualizaciones en lotes completadas")
        logger_funciones_especificas.info("Actualizaciones en lotes completadas")

    except Exception as e:
        logging.error(f"Error en actualizaciones en lotes: {e}")
        logger_funciones_especificas.error(f"Error en actualizaciones en lotes: {e}")
        connection.rollback()

    finally:
        cursor.close()
        conexion_proveedores_cursor.close()

# Función para actualizar las etiquetas de permitir y denegar pedido.
def update_product_labels(connection, dataframe, batch_size=5000):
    cursor = connection.cursor()

    # Definir la función is_attribute
    def is_attribute(reference):
        query = """
            SELECT COUNT(*)
            FROM ps_product_attribute pa
            INNER JOIN ps_product_supplier ps ON pa.id_product_attribute = ps.id_product_attribute
            WHERE ps.product_supplier_reference = %s
        """
        cursor.execute(query, (reference,))
        count = cursor.fetchone()[0]
        return count > 0

    try:

        # Diccionarios y listas para manejar las diferentes condiciones
        references_ps_product_with_date_no_stock = []
        references_ps_product_with_date_with_stock = []
        references_no_date_no_stock = {'ps_product': [], 'ps_product_supplier': []}
        references_no_date_with_stock = {'ps_product': [], 'ps_product_supplier': []}
        references_ps_product_attribute = []

        # Nuevos diccionarios para ps_product_supplier "product" con stock y sin stock
        references_ps_product_supplier_product_with_stock = []
        references_ps_product_supplier_product_no_stock = []

        # Lista para almacenar referencias de ps_product_supplier y su tipo (product o attribute)
        references_ps_product_supplier = []

        # Verifica si 'fecha_mas_cercana' está en el DataFrame antes de iniciar el bucle
        fecha_mas_cercana_presente = 'fecha_mas_cercana' in dataframe.columns

        # Llenar las listas y diccionarios basados en las condiciones
        for index, row in dataframe.iterrows():
            table = row['table']
            reference = row['reference']
            stock_combinado = row['stock_combinado']
            fecha_disponibilidad = row['fecha_mas_cercana'] if fecha_mas_cercana_presente else None

            if table == 'ps_product':
                if fecha_mas_cercana_presente and fecha_disponibilidad:
                    if stock_combinado <= 0:
                        references_ps_product_with_date_no_stock.append((reference, stock_combinado))
                    else:
                        references_ps_product_with_date_with_stock.append((reference, stock_combinado))
                elif not fecha_mas_cercana_presente:
                    if stock_combinado <= 0:
                        # Para ps_product sin 'fecha_mas_cercana' y sin stock, usar config.etiquetas.denegar_pedido
                        references_no_date_no_stock[table].append((reference, stock_combinado))
                    else:
                        references_ps_product_with_date_with_stock.append((reference, stock_combinado))
            elif table == 'ps_product_attribute':
                references_ps_product_attribute.append((reference, stock_combinado))
            elif table == 'ps_product_supplier':
                # Clasificar referencias de ps_product_supplier por tipo (product o attribute)
                if is_attribute(reference):
                    references_ps_product_supplier.append((reference, stock_combinado, 'attribute'))
                else:
                    if stock_combinado > 0:
                        references_ps_product_supplier.append((reference, stock_combinado, 'product_con_stock'))
                    else:
                        references_ps_product_supplier.append((reference, stock_combinado, 'product_no_stock'))
            else:
                if stock_combinado <= 0:
                    references_no_date_no_stock[table].append((reference, stock_combinado))
                else:
                    references_no_date_with_stock[table].append((reference, stock_combinado))

        # Función para ejecutar actualizaciones por lotes
        def execute_update(references, out_of_stock_value, table, ref_type=None):
            for i in range(0, len(references), batch_size):
                batch = references[i:i + batch_size]
                references_only = [ref[0] for ref in batch]
                placeholders = ', '.join(['%s'] * len(references_only))
                column_name = 'reference' if table != 'ps_product_supplier' else 'product_supplier_reference'
                query = f"""
                    UPDATE ps_stock_available
                    SET out_of_stock = {out_of_stock_value}
                    WHERE id_product IN (
                        SELECT id_product FROM {table} WHERE {column_name} IN ({placeholders})
                    )
                """
                cursor.execute(query, tuple(references_only))

                # Log each update including stock and type
                for ref_data in batch:
                    reference, stock = ref_data[:2]  # Siempre estarán presentes
                    ref_type_list = ref_data[2:]  # Puede estar vacía si no hay tercer elemento
                    ref_type = ref_type_list[0] if ref_type_list else None  # Asigna None si ref_type_list está vacía
                    type_message = f" ({ref_type})" if ref_type else ""
                    logging.info(f"Actualizando etiquetas para {table}{type_message}. Referencia: {reference}, out_of_stock: {out_of_stock_value}, stock: {stock}")
                    logger_funciones_especificas.info(f"Actualizando etiquetas para {table}{type_message}. Referencia: {reference}, out_of_stock: {out_of_stock_value}, stock: {stock}")

        # Ejecutar actualizaciones en lotes para referencias de atributos y productos en ps_product_supplier
        for ref_type in ['attribute', 'product_con_stock']:
            references = [ref_data for ref_data in references_ps_product_supplier if ref_data[2] == ref_type]
            if references:
                execute_update(references, 2, 'ps_product_supplier', ref_type)

        # Ejecutar actualizaciones en lotes para referencias "product_no_stock" en ps_product_supplier
        product_no_stock_references = [ref_data for ref_data in references_ps_product_supplier if ref_data[2] == 'product_no_stock']
        if product_no_stock_references:
            execute_update(product_no_stock_references, config.etiquetas.denegar_pedido, 'ps_product_supplier', 'product_no_stock')

        # Ejecutar actualizaciones para ps_product con y sin fecha_disponibilidad_producto
        execute_update(references_ps_product_with_date_no_stock, 0, 'ps_product')
        execute_update(references_ps_product_with_date_with_stock, 2, 'ps_product')

        # Ejecutar actualizaciones para ps_product_attribute siempre con out_of_stock = 2
        execute_update(references_ps_product_attribute, 2, 'ps_product_attribute')

        # Ejecutar actualizaciones para referencias sin fecha_disponibilidad_producto en ps_product y ps_product_supplier
        for table, refs in references_no_date_no_stock.items():
            if refs:
                execute_update(refs, config.etiquetas.denegar_pedido, table)
        for table, refs in references_no_date_with_stock.items():
            if refs:
                execute_update(refs, 2, table)

        connection.commit()

    except Exception as e:
        logging.error(f"Error durante la actualización por lotes: {e}")
    finally:
        cursor.close()

# Función para actualizar la columna additional_delivery_times en ps_product
def update_additional_delivery_times(connection, dataframe, batch_size=5000):
    cursor = connection.cursor()

    try:
        # Crear un diccionario para almacenar las referencias y su stock de la tabla "ps_product"
        references_by_table = {"ps_product": []}

        # Llenar el diccionario con las referencias correspondientes
        for index, row in dataframe.iterrows():
            table = row['table']
            if table == 'ps_product':
                references_by_table["ps_product"].append((row['reference'], row['stock_combinado']))

        # Consulta para actualizar additional_delivery_times en ps_product
        query_update_additional_delivery_times = "UPDATE ps_product SET additional_delivery_times = 2 WHERE reference IN %s"

        for table, references_stock in references_by_table.items():
            references_for_table = [ref[0] for ref in references_stock]

            # Dividir las referencias en lotes de tamaño especificado
            references_batches = [references_for_table[i:i+batch_size] for i in range(0, len(references_for_table), batch_size)]

            for references_batch in references_batches:
                try:
                    # Ejecutar la consulta para actualizar additional_delivery_times en ps_product
                    cursor.execute(query_update_additional_delivery_times, (tuple(references_batch),))

                    # Registra cada actualización en el registro de logging
                    for reference in references_batch:
                        logging.info(f"Actualizando additional_delivery_times en ps_product para referencia {reference}")

                except Exception as e:
                    #print(f"Error durante la actualización de additional_delivery_times: {e}")
                    logging.error(f"Error durante la actualización de additional_delivery_times para referencia {reference}: {e}")

        connection.commit()

        logging.info("Actualizaciones de additional_delivery_times en ps_product completadas")

    except Exception as e:
        #print(f"Error general durante la actualización de additional_delivery_times en ps_product: {e}")
        logging.error(f"Error general durante la actualización de additional_delivery_times en ps_product: {e}")

    finally:
        cursor.close()

# Función para actualizar la columna additional_delivery_times en ps_product_attribute
def update_additional_delivery_times_attribute(connection, dataframe, batch_size=5000):
    cursor = connection.cursor()

    try:
        # Crear un diccionario para almacenar las referencias y su stock de la tabla "ps_product_attribute"
        references_by_table = {"ps_product_attribute": []}

        # Llenar el diccionario con las referencias correspondientes
        for index, row in dataframe.iterrows():
            table = row['table']
            if table == 'ps_product_attribute':
                references_by_table["ps_product_attribute"].append((row['reference'], row['stock_combinado']))

        # Consulta para actualizar additional_delivery_times en ps_product_attribute
        query_update_additional_delivery_times_attribute = """
            UPDATE ps_product_attribute pa
            INNER JOIN ps_product pp ON pa.id_product = pp.id_product
            SET pp.additional_delivery_times = 2
            WHERE pa.reference IN %s
        """

        for table, references_stock in references_by_table.items():
            references_for_table = [ref[0] for ref in references_stock]

            # Dividir las referencias en lotes de tamaño especificado
            references_batches = [references_for_table[i:i+batch_size] for i in range(0, len(references_for_table), batch_size)]

            for references_batch in references_batches:
                try:
                    # Ejecutar la consulta para actualizar additional_delivery_times en ps_product_attribute
                    cursor.execute(query_update_additional_delivery_times_attribute, (tuple(references_batch),))

                    # Registra cada actualización en el registro de logging
                    for reference in references_batch:
                        logging.info(f"Actualizando additional_delivery_times en ps_product_attribute para referencia {reference}")

                except Exception as e:
                    print(f"Error durante la actualización de additional_delivery_times en ps_product_attribute: {e}")
                    logging.error(f"Error durante la actualización de additional_delivery_times en ps_product_attribute: {e}")

        connection.commit()

        logging.info("Actualizaciones de additional_delivery_times en ps_product_attribute completadas")

    except Exception as e:
        #print(f"Error general durante la actualización de additional_delivery_times en ps_product_attribute: {e}")
        logging.error(f"Error general durante la actualización de additional_delivery_times en ps_product_attribute: {e}")

    finally:
        cursor.close()

# Función para actualizar la columna additional_delivery_times en ps_product_supplier
def update_additional_delivery_times_supplier(connection, dataframe, batch_size=500):
    cursor = connection.cursor()

    try:
        # Filtrar el DataFrame para obtener solo las referencias de la tabla "ps_product_supplier"
        filtered_dataframe = dataframe[dataframe['table'] == 'ps_product_supplier']

        # Crear una lista de referencias de proveedor a partir del dataframe filtrado
        supplier_references = filtered_dataframe['reference'].tolist()

        # Consulta para actualizar additional_delivery_times en ps_product_supplier por lotes
        query_update_additional_delivery_times_supplier = """
            UPDATE ps_product_supplier ps
            INNER JOIN ps_product pp ON ps.id_product = pp.id_product
            SET pp.additional_delivery_times = 2
            WHERE ps.product_supplier_reference IN %s
        """

        # Dividir las referencias en lotes de tamaño especificado
        batches = [supplier_references[i:i+batch_size] for i in range(0, len(supplier_references), batch_size)]

        for batch in batches:
            try:
                # Ejecutar la consulta para actualizar additional_delivery_times en ps_product_supplier por lote
                cursor.execute(query_update_additional_delivery_times_supplier, (tuple(batch),))

                # Registra cada actualización en el registro de logging
                for reference in batch:
                    logging.info(f"Actualizando additional_delivery_times en ps_product_supplier para referencia {reference}")

            except Exception as e:
                print(f"Error durante la actualización de additional_delivery_times en ps_product_supplier: {e}")
                logging.error(f"Error durante la actualización de additional_delivery_times en ps_product_supplier: {e}")

        connection.commit()

        logging.info("Actualizaciones de additional_delivery_times en ps_product_supplier completadas")

    except Exception as e:
        #print(f"Error general durante la actualización de additional_delivery_times en ps_product_supplier: {e}")
        logging.error(f"Error general durante la actualización de additional_delivery_times en ps_product_supplier: {e}")

    finally:
        cursor.close()

# Función para actualizar la fecha de disponibilidad de los productos que tengan.
def actualizar_fecha_disponibilidad(conexion, dataframe, batch_size=5000):
    #print("DATAFRAME FECHA: ", dataframe)
    if 'fecha_mas_cercana' not in dataframe.columns:
        logging.info("El DataFrame no contiene la columna 'fecha_mas_cercana'. No se realizarán actualizaciones.")
        logger_funciones_especificas.info("El DataFrame no contiene la columna 'fecha_mas_cercana'. No se realizarán actualizaciones.")
        return

    # Filtrar el DataFrame para excluir filas donde 'fecha_mas_cercana' es NaN, una cadena vacía, o '0000-00-00'
    df_filtrado = dataframe[dataframe['fecha_mas_cercana'].notna() & 
                            (dataframe['fecha_mas_cercana'] != '') & 
                            (dataframe['fecha_mas_cercana'] != '0000-00-00')]
    #print(f"DataFrame Filtrado:\n{df_filtrado}")

    # Preparación de datos para actualización en lote
    datos_ps_product_attribute = [(row['fecha_mas_cercana'], row['reference']) for index, row in df_filtrado[df_filtrado['table'] == 'ps_product_attribute'].iterrows()]
    datos_ps_product = df_filtrado[df_filtrado['table'] == 'ps_product'][['fecha_mas_cercana', 'reference']].values.tolist()
    datos_ps_product_attribute_shop = [(row['fecha_mas_cercana'], row['reference']) for index, row in df_filtrado[df_filtrado['table'] == 'ps_product_attribute'].iterrows()]
    datos_ps_product_shop = df_filtrado[df_filtrado['table'] == 'ps_product'][['fecha_mas_cercana', 'reference']].values.tolist()

    # Consultas SQL
    query_ps_product_attribute = "UPDATE ps_product_attribute SET available_date = %s WHERE reference = %s"
    query_ps_product = "UPDATE ps_product SET available_date = %s WHERE reference = %s"
    query_ps_product_attribute_shop = """
        UPDATE ps_product_attribute_shop SET available_date = %s 
        WHERE id_product_attribute IN (SELECT id_product_attribute FROM ps_product_attribute WHERE reference = %s)
    """
    query_ps_product_shop = """
        UPDATE ps_product_shop SET available_date = %s 
        WHERE id_product IN (SELECT id_product FROM ps_product WHERE reference = %s)
    """

    cursor = conexion.cursor()

    try:
        # Actualizamos ps_product_attribute en lotes
        for i in range(0, len(datos_ps_product_attribute), batch_size):
            batch = datos_ps_product_attribute[i:i + batch_size]
            cursor.executemany(query_ps_product_attribute, batch)
            conexion.commit()
            for fecha, ref in batch:
                logging.info(f"Actualizada ps_product_attribute, referencia: {ref}, fecha: {fecha}")
                logger_funciones_especificas.info(f"Actualizada ps_product_attribute, referencia: {ref}, fecha: {fecha}")

        # Actualizamos ps_product en lotes
        for i in range(0, len(datos_ps_product), batch_size):
            batch = datos_ps_product[i:i + batch_size]
            cursor.executemany(query_ps_product, batch)
            conexion.commit()
            for fecha, ref in batch:
                logging.info(f"Actualizada ps_product, referencia: {ref}, fecha: {fecha}")
                logger_funciones_especificas.info(f"Actualizada ps_product, referencia: {ref}, fecha: {fecha}")

        # Actualizamos ps_product_attribute_shop en lotes
        for i in range(0, len(datos_ps_product_attribute_shop), batch_size):
            batch = datos_ps_product_attribute_shop[i:i + batch_size]
            cursor.executemany(query_ps_product_attribute_shop, batch)
            conexion.commit()
            for fecha, ref in batch:
                logging.info(f"Actualizada ps_product_attribute_shop, referencia: {ref}, fecha: {fecha}")
                logger_funciones_especificas.info(f"Actualizada ps_product_attribute_shop, referencia: {ref}, fecha: {fecha}")

        # Actualizamos ps_product_shop en lotes
        for i in range(0, len(datos_ps_product_shop), batch_size):
            batch = datos_ps_product_shop[i:i + batch_size]
            cursor.executemany(query_ps_product_shop, batch)
            conexion.commit()
            for fecha, ref in batch:
                logging.info(f"Actualizada ps_product_shop, referencia: {ref}, fecha: {fecha}")
                logger_funciones_especificas.info(f"Actualizada ps_product_shop, referencia: {ref}, fecha: {fecha}")

        logging.info("Actualización de fechas completada.")
        logger_funciones_especificas.info("Actualización de fechas completada.")

    except Exception as e:
        logging.error(f"Error al actualizar fechas de disponibilidad: {e}")
        logger_funciones_especificas.error(f"Error al actualizar fechas de disponibilidad: {e}")
        conexion.rollback()
    finally:
        cursor.close()
