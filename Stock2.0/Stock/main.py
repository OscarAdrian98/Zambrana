import logging
from config.bd import conectar_bd, cerrar_conexion, prestashop_config, proveedores_config
from config.email import enviar_correo
from config.configuracion_proveedor import obtener_configuraciones_proveedor, comparar_bases_de_datos
from procesamiento.procesar_contenido import descargar_y_procesar_archivo, procesar_archivo_excel, actualizar_base_datos, verificar_referencias_no_actualizadas, obtener_referencias_y_stock
from etiquetas.etiquetas import update_labels, update_additional_delivery_times_supplier, update_product_labels, update_additional_delivery_times, update_additional_delivery_times_attribute, actualizar_fecha_disponibilidad
from etiquetas.activar_desactivar import activate_products, activate_simple_products_from_supplier, deactivate_attributes, update_id_shop_in_attribute_shop_supplier
from tqdm import tqdm
from config.logging import borrar_archivo_log, logger_funciones_especificas
import pandas as pd

# Lista de Proveedores:
# Parts Europe: 5
# Acerbis: 7
# Fox: 8
# Pruebas: 9
# FXR: 10
# Tridegar: 11
# Torino: 12
# Italkit: 13
# Husqvarna: 14
# Totimport: 15
# Mots: 16
# MMK: 17

# Función principal.
def main():
    id_proveedores = [5, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17]  # Ajusta la lista según tus necesidades
    conexiones = []
    error_occurred = False

    try:
        for id_proveedor in id_proveedores:
            conexion_proveedores = conectar_bd(proveedores_config)
            conexion_prestashop = conectar_bd(prestashop_config)
            conexiones.extend([conexion_proveedores, conexion_prestashop])

            logging.info(f"Procesando proveedor con ID: {id_proveedor}")
            logger_funciones_especificas.info(f"Procesando proveedor con ID: {id_proveedor}")
            configuraciones_proveedor = obtener_configuraciones_proveedor(id_proveedor, conexion_proveedores)

            for configuracion_proveedor in configuraciones_proveedor:
                if len(configuracion_proveedor) >= 5:
                    logging.info(f"Configuración del proveedor obtenida para ID: {id_proveedor}")
                    # Configuración para Excel y descarga
                    excel_config = {
                        "col_referencia_configuracion": configuracion_proveedor[6],
                        "col_ean_configuracion": configuracion_proveedor[13],
                        "col_fecha_configuracion": configuracion_proveedor[14],
                        "col_stock_configuracion": configuracion_proveedor[7],
                        "fila_comienzo_configuracion": configuracion_proveedor[8],
                        "separador_csv_configuracion": configuracion_proveedor[9],
                        "id_marca": configuracion_proveedor[10],
                    }
                    config_descarga = {
                        "ftp_server": configuracion_proveedor[0],
                        "ftp_port": configuracion_proveedor[1],
                        "ftp_user": configuracion_proveedor[2],
                        "ftp_pass": configuracion_proveedor[3],
                        "fichero_configuracion": configuracion_proveedor[4],
                        "http_configuracion": configuracion_proveedor[11],
                    }

                    # Descargar y procesar cada archivo
                    archivo_bytes, configuracion_excel = descargar_y_procesar_archivo(config_descarga, excel_config, id_proveedor, conexion_proveedores)

                    if archivo_bytes is not None:
                        df_procesado = procesar_archivo_excel(archivo_bytes, id_proveedor, configuracion_excel['id_marca'], conexion_proveedores, configuracion_excel)

                        if df_procesado is not None:
                            #print("DATAFRAME MAIN: ", df_procesado)
                            actualizar_base_datos(df_procesado, id_proveedor, configuracion_excel['id_marca'], conexion_proveedores, conexion_prestashop)                            

                        # Verificar referencias no actualizadas
                        verificar_referencias_no_actualizadas(id_proveedor, configuracion_excel['id_marca'], conexion_proveedores, conexion_prestashop)
                        
                        # Nueva sección para obtener referencias y stock y realizar actualizaciones en lotes
                        logging.info("Obteniendo referencias y stock")
                        # Pasamos los parámetros id_proveedor e id_marca a la función
                        id_marca_especifica = configuracion_proveedor[10]
                        df_referencias_stock = obtener_referencias_y_stock(conexion_prestashop, id_proveedor, id_marca_especifica)
                        #print("DATAFRAME MAIN: ", df_referencias_stock)
                        # Crear una nueva columna 'stock_combinado'
                        df_referencias_stock['stock_combinado'] = df_referencias_stock['quantity'] + df_referencias_stock['hay_stock_producto']

                        # Ya no necesitamos filtrar el DataFrame según el id_proveedor y id_marca porque la función ya realiza este filtro
                        # Sin embargo, para mantener la impresión, creamos un df_filtrado idéntico a df_referencias_stock
                        df_filtrado = df_referencias_stock.copy()
                        #print("DATAFRAME FILTRADO: ", df_filtrado)
                        
                        if df_procesado is not None and 'fecha_mas_cercana' in df_procesado.columns and 'ean' in df_procesado.columns:
                            # Asegurar que las columnas de unión sean de tipo string
                            df_procesado['ean'] = df_procesado['ean'].astype(str)
                            df_filtrado['ean_producto'] = df_filtrado['ean_producto'].astype(str)

                            # Unir df_filtrado con df_procesado basándose en las columnas correspondientes
                            df_filtrado = pd.merge(df_filtrado, df_procesado[['ean', 'fecha_mas_cercana']],
                                                left_on='ean_producto', 
                                                right_on='ean', 
                                                how='left').drop(columns=['ean'])

                            # Limpieza final del DataFrame
                            if 'fecha_mas_cercana' in df_filtrado.columns:
                                df_filtrado = df_filtrado.dropna(subset=['fecha_mas_cercana'])

                        elif df_procesado is not None and 'fecha_mas_cercana' in df_procesado.columns:
                            # Asegúrate primero que las columnas clave están en el mismo formato de datos
                            df_procesado['referencia'] = df_procesado['referencia'].astype(str)
                            df_filtrado['reference'] = df_filtrado['reference'].astype(str)

                            # Realiza una unión (merge) para añadir 'fecha_mas_cercana' de df_procesado a df_filtrado
                            df_filtrado = pd.merge(df_filtrado, df_procesado[['referencia', 'fecha_mas_cercana']],
                                                left_on='reference', right_on='referencia', 
                                                how='left').drop(columns=['referencia'])
                            # Limpieza final del DataFrame
                            if 'fecha_mas_cercana' in df_filtrado.columns:
                                df_filtrado = df_filtrado.dropna(subset=['fecha_mas_cercana'])

                        #print("DATAFRAME FINAL: ", df_filtrado) # Imprime el DataFrame Final.

                        logging.info("Actualizando etiquetas en lotes")
                        with tqdm(total=df_filtrado.shape[0], desc="Actualizando etiquetas") as pbar:
                            update_labels(conexion_prestashop, df_filtrado, conexion_proveedores, id_proveedor, batch_size=5000)
                            update_product_labels(conexion_prestashop, df_filtrado, batch_size=5000)
                            update_additional_delivery_times(conexion_prestashop, df_filtrado, batch_size=5000)
                            update_additional_delivery_times_attribute(conexion_prestashop, df_filtrado, batch_size=5000)
                            update_additional_delivery_times_supplier(conexion_prestashop, df_filtrado, batch_size=5000)
                            activate_products(conexion_prestashop, df_filtrado, batch_size=5000)
                            activate_simple_products_from_supplier(conexion_prestashop, df_filtrado, batch_size=5000)
                            actualizar_fecha_disponibilidad(conexion_prestashop, df_filtrado, batch_size=5000)
                            # FUNCION PARA DESACTIVAR/ACTIVAR ATTRIBUTOS
                            deactivate_attributes(conexion_prestashop, df_filtrado, batch_size=5000) # Comentar si no se quiere desactivar
                            # FUNCION PARA DESACTIVAR/ACTIVAR ATTRIBUTES DE SUPPLIER
                            #update_id_shop_in_attribute_shop_supplier(conexion_prestashop, df_filtrado, batch_size=5000) # Comentar si no se quiere desactivar
                    else:
                        logging.info(f"No se pudo procesar el archivo para el proveedor {id_proveedor}")
                        logger_funciones_especificas.info(f"No se pudo procesar el archivo para el proveedor {id_proveedor}")
                else:
                    logging.warning(f"Configuración insuficiente para el proveedor {id_proveedor}")
                    logger_funciones_especificas.warning(f"Configuración insuficiente para el proveedor {id_proveedor}")

    except Exception as e:
        error_occurred = True
        logging.error(f"Error general en main: {e}")
        enviar_correo(asunto='Error en Procesamiento', cuerpo=f'Se ha producido un error: {e}')

    finally:
        logging.info("Cerrando conexiones a bases de datos")
        for conexion in conexiones:
            cerrar_conexion(conexion)
        if not error_occurred:
            enviar_correo(asunto='Proceso Completado Stock', cuerpo='El proceso se ha completado exitosamente Stock.')

if __name__ == "__main__":
    main()
    borrar_archivo_log()  # Borrar el archivo de registro después de ejecutar main