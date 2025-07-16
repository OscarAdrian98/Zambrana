import logging
from config.bd import conectar_bd, cerrar_conexion, prestashop_config, proveedores_config
from config.email import enviar_correo
from config.configuracion_proveedor import obtener_configuraciones_proveedor
from procesamiento.procesar_contenido import descargar_y_procesar_archivo, procesar_archivo_excel, actualizar_base_datos, verificar_referencias_no_actualizadas
from procesamiento.tablas_auxiliares import crear_tabla_aux_prestashop, crear_tabla_aux_proveedor, comparar_tablas_auxiliares, eliminar_tablas_auxiliares, detectar_referencias_huerfanas_para_desactivar
from etiquetas.etiquetas import update_labels, update_additional_delivery_times_supplier, update_product_labels, update_additional_delivery_times, update_additional_delivery_times_attribute, actualizar_fecha_disponibilidad
from etiquetas.activar_desactivar import activate_products, activate_simple_products_from_supplier, deactivate_attributes, desactivar_atributos_huerfanos_filtrando_marca, reactivar_todos_los_atributos_desactivados, reactivar_atributos_con_stock, detectar_productos_obsoletos_para_desactivar
from tqdm import tqdm
from config.logging import borrar_archivo_log, logger_funciones_especificas
import time
import pandas as pd

# Lista de Proveedores:
# Corver: 2
# Mundo Talio: 3
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
# Prox: 18
# X-grip: 19
# Racing: 20
# Technical: 21
# Polisport: 22

def main():
    start_time = time.time()
    id_proveedores = [2, 3, 5, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]  # Ajusta la lista según tus necesidades
    conexiones = []
    error_occurred = False
    proveedores_fallidos = set()

    try:
        # Conectar a las bases de datos una sola vez
        conexion_proveedores = conectar_bd(proveedores_config)
        conexion_prestashop = conectar_bd(prestashop_config)
        conexiones.extend([conexion_proveedores, conexion_prestashop])

        # ✅ Crear la tabla auxiliar de PrestaShop solo una vez antes de procesar los proveedores
        prestashop_df = crear_tabla_aux_prestashop(conexion_prestashop)

        for id_proveedor in id_proveedores:
            try:
                logging.info(f"Procesando proveedor con ID: {id_proveedor}")
                logger_funciones_especificas.info(f"Procesando proveedor con ID: {id_proveedor}")

                configuraciones_proveedor = obtener_configuraciones_proveedor(id_proveedor, conexion_proveedores)

                for configuracion_proveedor in configuraciones_proveedor:
                    try:
                        if len(configuracion_proveedor) >= 5:
                            logging.info(f"Configuración del proveedor obtenida para ID: {id_proveedor}")

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

                            archivo_bytes, configuracion_excel = descargar_y_procesar_archivo(
                                config_descarga, excel_config, id_proveedor, conexion_proveedores
                            )

                            if archivo_bytes is not None:
                                df_procesado = procesar_archivo_excel(
                                    archivo_bytes, id_proveedor, configuracion_excel['id_marca'],
                                    conexion_proveedores, configuracion_excel
                                )

                                if df_procesado is not None:
                                    actualizar_base_datos(
                                        df_procesado, id_proveedor, configuracion_excel['id_marca'],
                                        conexion_proveedores, conexion_prestashop
                                    )

                                    proveedor_df = crear_tabla_aux_proveedor(df_procesado)

                                    verificar_referencias_no_actualizadas(
                                        id_proveedor=id_proveedor,
                                        id_marca=configuracion_excel['id_marca'],
                                        conexion_proveedores=conexion_proveedores,
                                        conexion_prestashop=conexion_prestashop,
                                        prestashop_df=prestashop_df,
                                        proveedor_df=proveedor_df
                                    )

                                    df_fusionado = comparar_tablas_auxiliares(prestashop_df, proveedor_df)

                                    if df_fusionado is not None and not df_fusionado.empty:
                                        df_fusionado.rename(columns={'source': 'table'}, inplace=True)
                                        df_fusionado['id_proveedor'] = id_proveedor

                                        if 'quantity' in df_fusionado.columns and 'hay_stock' in df_fusionado.columns:
                                            df_fusionado['quantity'] = pd.to_numeric(df_fusionado['quantity'], errors='coerce').fillna(0)
                                            df_fusionado['hay_stock'] = pd.to_numeric(df_fusionado['hay_stock'], errors='coerce').fillna(0)
                                            df_fusionado['stock_combinado'] = df_fusionado['quantity'] + df_fusionado['hay_stock']

                                        with tqdm(total=df_fusionado.shape[0], desc="Actualizando etiquetas") as pbar:
                                            update_labels(conexion_prestashop, df_fusionado, conexion_proveedores, id_proveedor, batch_size=5000)
                                            update_product_labels(conexion_prestashop, df_fusionado, batch_size=5000)
                                            update_additional_delivery_times(conexion_prestashop, df_fusionado, batch_size=5000)
                                            update_additional_delivery_times_attribute(conexion_prestashop, df_fusionado, batch_size=5000)
                                            update_additional_delivery_times_supplier(conexion_prestashop, df_fusionado, batch_size=5000)
                                            activate_products(conexion_prestashop, df_fusionado, batch_size=5000)
                                            activate_simple_products_from_supplier(conexion_prestashop, df_fusionado, batch_size=5000)
                                            actualizar_fecha_disponibilidad(conexion_prestashop, df_fusionado, batch_size=5000)
                                            deactivate_attributes(conexion_prestashop, df_fusionado, batch_size=5000)
                                            if id_proveedor in [8, 9, 10]:
                                                desactivar_atributos_huerfanos_filtrando_marca(
                                                    conexion_prestashop, conexion_proveedores, prestashop_df, id_proveedor
                                                )
                                            reactivar_atributos_con_stock(
                                                conexion_prestashop, conexion_proveedores, id_proveedor
                                            )
                                            pbar.update(df_fusionado.shape[0])

                                    else:
                                        logging.warning(f"No se pudo obtener un DataFrame fusionado para proveedor {id_proveedor}")

                                    eliminar_tablas_auxiliares(conexion_proveedores, 'tabla_aux_proveedor')

                                else:
                                    logging.warning(f"No se pudo procesar el archivo para proveedor {id_proveedor}")
                            else:
                                logging.warning(f"No se pudo descargar archivo para proveedor {id_proveedor}")
                        else:
                            logging.warning(f"Configuración insuficiente para proveedor {id_proveedor}")

                    except Exception as e:
                        logging.error(f"❌ Error interno al procesar configuración de proveedor {id_proveedor}: {e}")
                        proveedores_fallidos.add(id_proveedor)

            except Exception as e:
                logging.error(f"❌ Error general al procesar proveedor {id_proveedor}: {e}")
                proveedores_fallidos.add(id_proveedor)

        # ✅ Detectar y desactivar productos antiguos que ya no están ni en ficheros ni en la base de datos del proveedor
        try:
            df_huerfanas = detectar_referencias_huerfanas_para_desactivar(conexion_prestashop, conexion_proveedores)

            if df_huerfanas.empty:
                logging.info("✅ No se encontraron productos huérfanos a desactivar.")
                logger_funciones_especificas.info("✅ No se encontraron productos huérfanos a desactivar.")
            else:
                logging.info(f"✅ Proceso de detección y desactivación de {df_huerfanas.shape[0]} productos huérfanos completado.")
                logger_funciones_especificas.info(f"✅ Proceso de detección y desactivación de {df_huerfanas.shape[0]} productos huérfanos completado.")
        except Exception as e:
            logging.error(f"❌ Error al detectar/desactivar productos huérfanos: {e}")
            logger_funciones_especificas.error(f"❌ Error al detectar/desactivar productos huérfanos: {e}")

        # ✅ Detectar y desactivar productos obsoletos (sin stock, sin stock en proveedor y sin actualizar en 20 días)
        try:
            df_obsoletos = detectar_productos_obsoletos_para_desactivar(conexion_prestashop, conexion_proveedores)

            if df_obsoletos.empty:
                logging.info("✅ No se encontraron productos obsoletos a desactivar.")
                logger_funciones_especificas.info("✅ No se encontraron productos obsoletos a desactivar.")
            else:
                productos_unicos = df_obsoletos['id_product'].nunique()
                logging.info(f"✅ Se han desactivado {productos_unicos} productos obsoletos.")
                logger_funciones_especificas.info(f"✅ Se han desactivado {productos_unicos} productos obsoletos.")
        except Exception as e:
            logging.error(f"❌ Error al detectar/desactivar productos obsoletos: {e}")
            logger_funciones_especificas.error(f"❌ Error al detectar/desactivar productos obsoletos: {e}")

        # Reactivar todos los atributos desactivados (solo usar cuando sea necesario)
        # Descomenta la línea siguiente SOLO cuando quieras reactivar todos los atributos
        #reactivar_todos_los_atributos_desactivados(conexion_prestashop)

        # ✅ Eliminar la tabla auxiliar de PrestaShop después de terminar con todos los proveedores
        eliminar_tablas_auxiliares(conexion_prestashop, 'tabla_aux_prestashop')

    except Exception as e:
        error_occurred = True
        logging.error(f"Error general en main: {e}")
        enviar_correo(asunto='Error en Procesamiento', cuerpo=f'Se ha producido un error: {e}')

    finally:
        logging.info("Cerrando conexiones a bases de datos")
        for conexion in conexiones:
            cerrar_conexion(conexion)

        tiempo_total = time.time() - start_time
        logging.info(f"⏱️ Tiempo total de ejecución: {tiempo_total:.2f} segundos")

        if not error_occurred and not proveedores_fallidos:
            enviar_correo(asunto='Proceso Completado', cuerpo='El proceso se ha completado exitosamente.')
        elif proveedores_fallidos:
            enviar_correo(
                asunto='⚠️ Proveedores con errores',
                cuerpo=f'Fallaron los siguientes proveedores: {", ".join(map(str, sorted(proveedores_fallidos)))}'
            )

if __name__ == "__main__":
    main()
    borrar_archivo_log()