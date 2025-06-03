import pymysql
import logging
from config.logging import logger_funciones_especificas
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
from tqdm import tqdm
from ftplib import FTP_TLS, FTP
import requests
from pymysql.err import IntegrityError
import paramiko
from config.bd import ejecutar_query_con_reintentos, reconectar_bd_si_necesario

# Función para procesar el archivo y preparar los datos
def check_stock(x):
    """Función para determinar si hay stock basado en valores de diferentes formatos."""
    try:
        x_str = str(x).strip().lower()
        if x_str in ['yes', 'si', 'sí', 'y', 'true', 'mas de 3 uds', '9+', 'mas de 5', '5 o menos', ' 5 o menos', '10+', 'Mas de 5']:
            return 1
        elif x_str in ['no', 'n', 'false', '-', '0', 'sin stock']:
            return 0
        # Si no es texto, intentamos convertir a número
        return 1 if float(str(x).replace(',', '.')) != 0 else 0
    except ValueError:
        return 0  # Trata el valor no numérico como si no hubiera stock

# Función para procesar el archivo y preparar los datos
def procesar_archivo_excel(archivo_bytes, id_proveedor, id_marca, conexion_proveedores, configuracion_excel):
    try:
        with conexion_proveedores.cursor() as cursor:
            cursor.execute(
                "SELECT extension_configuracion, col_referencia_configuracion, col_ean_configuracion, col_fecha_configuracion FROM configuracion_proveedores WHERE id_proveedor = %s AND id_marca = %s",
                (id_proveedor, id_marca))
            resultado = cursor.fetchone()

            if resultado:
                tipo_archivo, col_referencia_configuracion, col_ean_configuracion, col_fecha_configuracion = resultado
                tipo_archivo = str(tipo_archivo).lower()
            else:
                raise ValueError("No se pudo obtener la configuración desde la base de datos.")
    except Exception as e:
        logging.error("Error al obtener la configuración de la base de datos: %s", e)
        return None

    try:
        if tipo_archivo == 'csv':
            # Procesar archivo CSV
            df = pd.read_csv(BytesIO(archivo_bytes), 
                             encoding='latin1', 
                             on_bad_lines='skip',  # Saltar líneas problemáticas
                             sep=configuracion_excel["separador_csv_configuracion"], 
                             header=None, 
                             skiprows=configuracion_excel["fila_comienzo_configuracion"], 
                             dtype=str)  # Asegura que todo es texto
        elif tipo_archivo in ['xlsx', 'xls']:
            # Procesar archivo Excel
            pd.set_option('display.float_format', lambda x: '%.f' % x)
            df = pd.read_excel(BytesIO(archivo_bytes), 
                               skiprows=configuracion_excel["fila_comienzo_configuracion"], 
                               header=None, 
                               usecols=configuracion_excel.get("columnas_utilizadas_configuracion"))
        elif tipo_archivo == 'txt':
            # Procesar archivo TXT como delimitado por tabulaciones u otro delimitador
            df = pd.read_csv(BytesIO(archivo_bytes), 
                             delimiter=configuracion_excel.get("separador_txt_configuracion", '\t'), 
                             header=None, 
                             skiprows=configuracion_excel["fila_comienzo_configuracion"], 
                             encoding='latin1', 
                             dtype={col_referencia_configuracion: str})
        else:
            raise ValueError("Tipo de archivo no soportado")
        
        # Reemplazar NaN con cadenas vacías y convertir todo a texto
        df = df.fillna('').astype(str)

        # Procesamiento según las columnas configuradas
        if col_fecha_configuracion and col_referencia_configuracion and not col_ean_configuracion:
            df_referencias_fechas = procesar_dataframe_referencias_fechas(df, col_referencia_configuracion, col_fecha_configuracion, configuracion_excel)
            return df_referencias_fechas
        elif col_fecha_configuracion:
            df_fechas = procesar_dataframe_fechas(df, col_referencia_configuracion, col_fecha_configuracion, configuracion_excel)
            return df_fechas
        elif col_ean_configuracion:
            df_ean = procesar_dataframe_ean(df, col_referencia_configuracion, col_ean_configuracion, configuracion_excel, configuracion_excel["col_stock_configuracion"])
            return df_ean
        else:
            df_referencias = procesar_dataframe_referencias(df, col_referencia_configuracion, configuracion_excel["col_stock_configuracion"])
            return df_referencias

    except Exception as e:
        logging.error("Error al procesar el archivo: %s", e)
        return None

def procesar_dataframe_fechas(df, col_referencia, col_fecha, configuracion_excel):
    col_stock = int(configuracion_excel["col_stock_configuracion"])
    col_ean = int(configuracion_excel["col_ean_configuracion"])

    # Convertir la columna de fecha a formato datetime y manejar errores
    df['col_fecha_configuracion'] = pd.to_datetime(df.iloc[:, int(col_fecha)], errors='coerce')

    # Determinar si hay stock utilizando la función check_stock
    df['hay_stock'] = df.iloc[:, col_stock].apply(check_stock)

    fecha_actual = datetime.now().date()
    mes_anterior = fecha_actual - timedelta(days=30)

    # Inicializar la columna 'fecha_mas_cercana' con NaT (Not a Time)
    df['fecha_mas_cercana'] = pd.NaT

    # Iterar sobre cada grupo de referencia
    for referencia, grupo in df.groupby(int(col_referencia)):
        grupo = grupo.sort_values('col_fecha_configuracion')
        fecha_mas_cercana_con_stock = None
        fecha_mas_cercana_sin_stock = None

        for idx, fila in grupo.iterrows():
            fecha_fila = fila['col_fecha_configuracion'].date() if fila['col_fecha_configuracion'] is not pd.NaT else None
            if fecha_fila and fecha_fila >= mes_anterior:
                if fila['hay_stock'] and fecha_mas_cercana_con_stock is None:
                    fecha_mas_cercana_con_stock = fecha_fila
                    idx_con_stock = idx
                if fecha_mas_cercana_sin_stock is None:
                    fecha_mas_cercana_sin_stock = fecha_fila
                    idx_sin_stock = idx

        # Asignar la fecha más cercana con stock si existe, de lo contrario la fecha más cercana disponible
        if fecha_mas_cercana_con_stock:
            df.at[idx_con_stock, 'fecha_mas_cercana'] = pd.Timestamp(fecha_mas_cercana_con_stock)
        else:
            df.at[idx_sin_stock, 'fecha_mas_cercana'] = pd.Timestamp(fecha_mas_cercana_sin_stock)

    # Eliminar las filas donde 'fecha_mas_cercana' es NaT
    df = df.dropna(subset=['fecha_mas_cercana'])

    # Seleccionar y renombrar las columnas necesarias
    df_fechas = df[[col_referencia, col_ean, col_stock, 'hay_stock', 'fecha_mas_cercana']].copy()
    df_fechas = df_fechas.rename(columns={
        col_referencia: 'referencia',
        col_ean: 'ean',
        col_stock: 'stock',
        'hay_stock': 'hay_stock',
        'fecha_mas_cercana': 'fecha_mas_cercana'
    })

    df_fechas = df_fechas.drop_duplicates(subset=['referencia', 'ean'], keep='first')

    return df_fechas

def procesar_dataframe_ean(df, col_referencia, col_ean, configuracion_excel, col_stock):
    df.iloc[:, int(col_stock)] = df.iloc[:, int(col_stock)].fillna(0)
    df['Stock_str'] = df.iloc[:, int(col_stock)].astype(str)

    # Aplicamos la función check_stock a la columna de stock
    df['hay_stock'] = df['Stock_str'].apply(check_stock)

    df_ean = df[[int(col_ean), 'Stock_str', 'hay_stock', int(col_referencia)]].copy()
    df_ean = df_ean.rename(columns={int(col_ean): 'ean', 'Stock_str': 'stock', int(col_referencia): 'referencia'})

    df_ean = df_ean[df_ean['ean'].notnull() & df_ean['ean'].apply(lambda x: str(x).strip() != '')]
    df_ean = df_ean.drop_duplicates(subset=['ean'], keep='first')

    return df_ean

def procesar_dataframe_referencias(df, col_referencia, col_stock):
    df['hay_stock'] = df.iloc[:, int(col_stock)].apply(check_stock)

    df_referencias = df[[int(col_referencia), int(col_stock), 'hay_stock']].copy()
    df_referencias = df_referencias.rename(columns={int(col_referencia): 'referencia', int(col_stock): 'stock'})

    df_referencias = df_referencias.drop_duplicates(subset=['referencia'], keep='first')

    return df_referencias

def procesar_dataframe_referencias_fechas(df, col_referencia, col_fecha, configuracion_excel):
    col_stock = int(configuracion_excel["col_stock_configuracion"])

    df['col_fecha'] = pd.to_datetime(df.iloc[:, int(col_fecha)], errors='coerce')
    df['hay_stock'] = df.iloc[:, col_stock].apply(check_stock)  # Aquí usamos la función generalizada

    fecha_actual = datetime.now().date()
    mes_anterior = fecha_actual - timedelta(days=30)

    df['fecha_mas_cercana'] = pd.NaT

    for referencia, grupo in df.groupby(int(col_referencia)):
        grupo = grupo.sort_values('col_fecha')
        for idx, fila in grupo.iterrows():
            fecha_fila = fila['col_fecha'].date() if fila['col_fecha'] is not pd.NaT else None
            if fecha_fila and fecha_fila >= mes_anterior:
                if fila['hay_stock']:
                    df.at[idx, 'fecha_mas_cercana'] = pd.Timestamp(fecha_fila)
                    break
                elif df.at[idx, 'fecha_mas_cercana'] is pd.NaT:
                    df.at[idx, 'fecha_mas_cercana'] = pd.Timestamp(fecha_fila)

    df_referencias_fechas = df[[col_referencia, col_stock, 'hay_stock', 'fecha_mas_cercana']].copy()
    df_referencias_fechas['fecha_mas_cercana'] = df_referencias_fechas['fecha_mas_cercana'].astype(object)
    df_referencias_fechas['fecha_mas_cercana'] = df_referencias_fechas['fecha_mas_cercana'].fillna('')

    df_referencias_fechas = df_referencias_fechas.rename(columns={
        col_referencia: 'referencia',
        col_stock: 'stock',
        'hay_stock': 'hay_stock',
        'fecha_mas_cercana': 'fecha_mas_cercana'
    })

    df_referencias_fechas = df_referencias_fechas.drop_duplicates(subset=['referencia'], keep='first')

    return df_referencias_fechas

# Función para insertar y actualizar en la base de datos
def actualizar_base_datos(df, id_proveedor, id_marca, conexion_proveedores, conexion_prestashop, tamaño_lote=22000):
    logging.info("Actualizando o Insertando en la base de datos")
    try:
        fecha_actualizacion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Identificar el tipo de DataFrame
        columnas_df = df.columns.tolist()
        if 'fecha_mas_cercana' in columnas_df and 'ean' not in columnas_df:
            tipo_df = 'referencias_fechas'
        elif 'fecha_mas_cercana' in columnas_df:
            tipo_df = 'fechas'
        elif 'ean' in columnas_df:
            tipo_df = 'ean'
        else:
            tipo_df = 'referencias'

        print("DataFrame Identificado:\n", tipo_df)

        pbar = tqdm(total=len(df), desc="Procesando", unit="fila")

        # 🔄 Inserciones y actualizaciones por lotes
        for inicio in range(0, len(df), tamaño_lote):
            fin = inicio + tamaño_lote
            sub_df = df.iloc[inicio:fin]

            # 📊 Diagnóstico: Muestra el tamaño del lote antes de la inserción
            print(f"🔎 Lote {inicio // tamaño_lote + 1}:")
            print(f"  Filas a insertar: {len(sub_df)}")
            print(f"  Tamaño del lote: {sub_df.memory_usage(deep=True).sum() / (1024 * 1024):.2f} MB")

            if 'ean' in sub_df.columns:
                sub_df['ean'] = sub_df['ean'].astype(str).str.replace('.0', '', regex=False)

            valores = []

            for row in sub_df.itertuples(index=False):
                if tipo_df == 'referencias_fechas':
                    ref, stock, hay_stock, fecha_disponibilidad = row
                    valores.append((id_proveedor, ref, stock, hay_stock, fecha_actualizacion, fecha_disponibilidad, id_marca))
                elif tipo_df == 'fechas':
                    ref, ean, stock, hay_stock, fecha_disponibilidad = row
                    valores.append((id_proveedor, ref, ean, stock, hay_stock, fecha_actualizacion, fecha_disponibilidad, id_marca))
                elif tipo_df == 'ean':
                    ean, stock, hay_stock, ref = row
                    if ref.lower() == 'nan' or ean.lower() == 'nan':
                        logging.warning(f"Se encontró un valor 'nan' para ref: {ref} o ean: {ean}, se omite la inserción.")
                        continue
                    valores.append((id_proveedor, ref, ean, stock, hay_stock, fecha_actualizacion, id_marca))
                else:  # 'referencias'
                    ref, stock, hay_stock = row
                    valores.append((id_proveedor, ref, stock, fecha_actualizacion, id_marca, hay_stock))

            # Ejecutar inserciones/actualizaciones en la base de datos
            with conexion_proveedores.cursor() as cursor:
                if tipo_df == 'referencias_fechas':
                    cursor.executemany("""
                        INSERT INTO productos (id_proveedor, referencia_producto, stock_txt_producto, hay_stock_producto,
                                               fecha_actualizacion_producto, fecha_disponibilidad_producto, id_marca)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            stock_txt_producto = VALUES(stock_txt_producto),
                            hay_stock_producto = VALUES(hay_stock_producto),
                            fecha_actualizacion_producto = VALUES(fecha_actualizacion_producto),
                            fecha_disponibilidad_producto = VALUES(fecha_disponibilidad_producto)
                    """, valores)

                elif tipo_df == 'fechas':
                    cursor.executemany("""
                        INSERT INTO productos (id_proveedor, referencia_producto, ean_producto, stock_txt_producto,
                                               hay_stock_producto, fecha_actualizacion_producto, fecha_disponibilidad_producto, id_marca)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            ean_producto = VALUES(ean_producto),
                            stock_txt_producto = VALUES(stock_txt_producto),
                            hay_stock_producto = VALUES(hay_stock_producto),
                            fecha_actualizacion_producto = VALUES(fecha_actualizacion_producto),
                            fecha_disponibilidad_producto = VALUES(fecha_disponibilidad_producto)
                    """, valores)

                elif tipo_df == 'ean':
                    cursor.executemany("""
                        INSERT INTO productos (id_proveedor, referencia_producto, ean_producto, stock_txt_producto,
                                               hay_stock_producto, fecha_actualizacion_producto, id_marca)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            ean_producto = VALUES(ean_producto),
                            stock_txt_producto = VALUES(stock_txt_producto),
                            hay_stock_producto = VALUES(hay_stock_producto),
                            fecha_actualizacion_producto = VALUES(fecha_actualizacion_producto)
                    """, valores)

                else:  # 'referencias'
                    cursor.executemany("""
                        INSERT INTO productos (id_proveedor, referencia_producto, stock_txt_producto,
                                               fecha_actualizacion_producto, id_marca, hay_stock_producto)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            stock_txt_producto = VALUES(stock_txt_producto),
                            hay_stock_producto = VALUES(hay_stock_producto),
                            fecha_actualizacion_producto = VALUES(fecha_actualizacion_producto)
                    """, valores)

                conexion_proveedores.commit()
                print(f"💾 Lote {inicio // tamaño_lote + 1} procesado y guardado.")

            pbar.update(len(sub_df))

        print("✅ Inserciones/actualizaciones completadas.")
        logging.info("Proceso de inserciones/actualizaciones finalizado correctamente.")

    except Exception as e:
        conexion_proveedores.rollback()
        logging.error(f"❌ Error al procesar el contenido: {e}")
        raise e
        
# Función para ver las referencias que no se han actualizado.
def verificar_referencias_no_actualizadas(id_proveedor, id_marca, conexion_proveedores, conexion_prestashop, prestashop_df, proveedor_df):
    from datetime import datetime
    fecha_actual = datetime.now().strftime("%Y-%m-%d")

    try:
        # 1️⃣ Obtener referencias no actualizadas hoy
        with conexion_proveedores.cursor() as cursor:
            cursor.execute("""
                SELECT referencia_producto
                FROM productos
                WHERE id_proveedor = %s AND id_marca = %s AND DATE(fecha_actualizacion_producto) != %s
            """, (id_proveedor, id_marca, fecha_actual))
            referencias_no_actualizadas = [str(row[0]) for row in cursor.fetchall()]

        if not referencias_no_actualizadas:
            logging.info("✅ Todas las referencias están actualizadas hoy.")
            return

        # 2️⃣ Convertir a sets y filtrar
        referencias_no_hoy = set(referencias_no_actualizadas)
        referencias_fichero = set(proveedor_df['referencia'].astype(str))
        referencias_prestashop_sin_stock = set(
            prestashop_df[prestashop_df['quantity'] <= 0]['reference'].astype(str)
        )

        # 3️⃣ Criterio final: no actualizada hoy + no está en fichero + sin stock en PrestaShop
        referencias_a_cero = list(
            (referencias_no_hoy - referencias_fichero) & referencias_prestashop_sin_stock
        )

        for ref in referencias_a_cero:
            logging.info(f"🔴 {ref} → stock = 0 (no llegó del proveedor, no se actualizó hoy y sin stock en PrestaShop)")

        # 4️⃣ Actualizar stock = 0 en la base de datos del proveedor
        if referencias_a_cero:
            placeholders = ','.join(['%s'] * len(referencias_a_cero))
            query_update = f"""
                UPDATE productos
                SET stock_txt_producto = '0', hay_stock_producto = '0'
                WHERE id_proveedor = %s AND id_marca = %s AND referencia_producto IN ({placeholders})
            """
            with conexion_proveedores.cursor() as cursor:
                cursor.execute(query_update, (id_proveedor, id_marca, *referencias_a_cero))
                conexion_proveedores.commit()
                logging.info(f"🔻 {len(referencias_a_cero)} referencias actualizadas a stock = 0")

            # 5️⃣ Desactivar atributos en PrestaShop si aún están activos y no tienen stock
            query_get_ids = f"""
                SELECT pa.id_product_attribute, pa.reference, pa.id_product
                FROM ps_product_attribute pa
                JOIN ps_stock_available sa ON sa.id_product_attribute = pa.id_product_attribute AND sa.id_shop = 1
                JOIN ps_product_attribute_shop pas ON pa.id_product_attribute = pas.id_product_attribute
                WHERE pa.reference IN ({placeholders}) AND sa.quantity <= 0 AND pas.id_shop != 99
            """
            with conexion_prestashop.cursor() as cursor:
                cursor.execute(query_get_ids, referencias_a_cero)
                atributos_a_desactivar = cursor.fetchall()

            if atributos_a_desactivar:
                ids_a_desactivar = [row[0] for row in atributos_a_desactivar]
                ids_productos_afectados = list(set(row[2] for row in atributos_a_desactivar))

                logging.info(f"🚫 Desactivando {len(ids_a_desactivar)} atributos en PrestaShop por no actualizarse y sin stock")

                placeholders_ids = ','.join(['%s'] * len(ids_a_desactivar))
                with conexion_prestashop.cursor() as cursor:
                    cursor.execute(f"""
                        UPDATE ps_product_attribute_shop
                        SET id_shop = 99
                        WHERE id_product_attribute IN ({placeholders_ids})
                    """, ids_a_desactivar)

                    if ids_productos_afectados:
                        placeholders_prod = ','.join(['%s'] * len(ids_productos_afectados))
                        cursor.execute(f"""
                            UPDATE ps_product
                            SET cache_default_attribute = NULL
                            WHERE id_product IN ({placeholders_prod})
                        """, ids_productos_afectados)
                        cursor.execute(f"""
                            UPDATE ps_product_shop
                            SET cache_default_attribute = NULL
                            WHERE id_product IN ({placeholders_prod})
                        """, ids_productos_afectados)

                    conexion_prestashop.commit()

                for row in atributos_a_desactivar:
                    logging.info(f"❌ Atributo {row[1]} desactivado automáticamente.")

    except Exception as e:
        conexion_proveedores.rollback()
        logging.error(f"❌ Error durante verificación de referencias: {e}")

    # 6️⃣ Reactivar atributos con stock si están en id_shop = 99
    try:
        with conexion_prestashop.cursor() as cursor:
            query_reactivar = """
                SELECT pas.id_product_attribute, pa.reference
                FROM ps_product_attribute_shop pas
                INNER JOIN ps_product_attribute pa ON pas.id_product_attribute = pa.id_product_attribute
                INNER JOIN ps_stock_available sa 
                    ON pa.id_product_attribute = sa.id_product_attribute AND sa.id_shop = 1
                WHERE sa.quantity > 0 AND pas.id_shop = 99
            """
            cursor.execute(query_reactivar)
            atributos = cursor.fetchall()

            if atributos:
                ids = [str(row[0]) for row in atributos]
                logging.info(f"🔄 Reactivando {len(ids)} atributos con stock en PrestaShop")
                for row in atributos:
                    logging.info(f"✔️ Atributo {row[0]} ({row[1]}) pasa a id_shop = 1")

                placeholders = ','.join(['%s'] * len(ids))
                query_update = f"""
                    UPDATE ps_product_attribute_shop
                    SET id_shop = 1
                    WHERE id_product_attribute IN ({placeholders}) AND id_shop = 99
                """
                cursor.execute(query_update, ids)
                conexion_prestashop.commit()
            else:
                logging.info("✅ No hay atributos con stock e id_shop = 99 para reactivar.")

    except Exception as e:
        conexion_prestashop.rollback()
        logging.error(f"❌ Error al reactivar atributos con stock en PrestaShop: {e}")

def descargar_y_procesar_archivo(config, excel_config, id_proveedor, conexion_proveedores):
    archivo_bytes = None
    try:
        if "ftp_server" in config and config["ftp_server"] is not None:
            try:
                if id_proveedor == 14:
                    # Conexión segura FTPS en lugar de FTP para el proveedor 14
                    ftp = FTP_TLS()
                    ftp.timeout = 300  # Ajusta el valor según sea necesario
                    ftp.connect(config["ftp_server"], config["ftp_port"])
                    ftp.login(config["ftp_user"], config["ftp_pass"])
                    ftp.set_pasv(True)  # Establecer modo pasivo
                    ftp.prot_p()  # Activar protección de datos
                    print("Usando FTPS para el proveedor 14.")
                else:
                    # Conexión FTP estándar para otros proveedores
                    ftp = FTP()
                    ftp.timeout = 300  # Ajusta el valor según sea necesario
                    ftp.connect(config["ftp_server"], config["ftp_port"])
                    ftp.login(config["ftp_user"], config["ftp_pass"])
                    print("Usando FTP estándar.")

                # Descarga el archivo Excel en memoria
                with BytesIO() as memory_file:
                    ftp.retrbinary(f"RETR {config['fichero_configuracion']}", memory_file.write)
                    memory_file.seek(0)
                    archivo_bytes = memory_file.read()

                ftp.quit()
                print("Archivo Excel descargado exitosamente desde FTP o FTPS.")
            except Exception as ftp_error:
                print(f"Fallo la descarga FTP/FTPS: {ftp_error}, intentando FTPS...")
                logger_funciones_especificas.info(f"Fallo la descarga FTP/FTPS: {ftp_error}, intentando FTPS...")

                try:
                    # Conexión segura FTPS adicional (protocolo explícito)
                    ftp = FTP_TLS()
                    ftp.timeout = 300
                    ftp.connect(config["ftp_server"], config["ftp_port"])
                    ftp.login(config["ftp_user"], config["ftp_pass"])
                    ftp.prot_p()
                    ftp.set_pasv(True)

                    # Descarga el archivo Excel en memoria
                    with BytesIO() as memory_file:
                        ftp.retrbinary(f"RETR {config['fichero_configuracion']}", memory_file.write)
                        memory_file.seek(0)
                        archivo_bytes = memory_file.read()

                    ftp.quit()
                    print("Archivo Excel descargado exitosamente usando FTPS explícito.")
                except Exception as ftps_error:
                    print(f"Fallo la descarga FTPS explícito: {ftps_error}, intentando SFTP...")
                    logger_funciones_especificas.info(f"Fallo la descarga FTPS explícito: {ftps_error}, intentando SFTP...")

                    try:
                        # Establecer conexión SSH usando SSHClient
                        ssh_client = paramiko.SSHClient()
                        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                        ssh_client.connect(config["ftp_server"], config["ftp_port"], config["ftp_user"], config["ftp_pass"])

                        # Iniciar cliente SFTP
                        sftp = ssh_client.open_sftp()

                        # Descarga del archivo en memoria
                        with BytesIO() as memory_file:
                            sftp.getfo(config['fichero_configuracion'], memory_file)
                            memory_file.seek(0)
                            archivo_bytes = memory_file.read()

                        # Cerrar conexiones SFTP y SSH
                        sftp.close()
                        ssh_client.close()
                        print("Archivo Excel descargado exitosamente desde SFTP.")
                        logger_funciones_especificas.info("Archivo Excel descargado exitosamente desde SFTP.")

                    except Exception as sftp_error:
                        print(f"Fallo la descarga SFTP: {sftp_error}")
                        logger_funciones_especificas.info(f"Fallo la descarga SFTP: {sftp_error}")

        elif "http_configuracion" in config and config["http_configuracion"] is not None:
            # Configuración de HTTP proporcionada, intenta la descarga desde HTTP
            cursor = conexion_proveedores.cursor()
            consulta_nombre_archivo = "SELECT fichero_configuracion FROM configuracion_proveedores WHERE id_proveedor = %s"
            cursor.execute(consulta_nombre_archivo, (id_proveedor,))
            resultado_nombre_archivo = cursor.fetchone()

            if resultado_nombre_archivo:
                nombre_archivo = resultado_nombre_archivo[0]

                # Añade un encabezado de User-Agent para simular una solicitud de navegador
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
                }

                # Realiza la solicitud HTTP para descargar el archivo Excel
                response = requests.get(config["http_configuracion"], headers=headers, allow_redirects=True)

                if response.status_code == 200:
                    # Descarga el archivo Excel en memoria
                    archivo_bytes = response.content
                    print(f"Archivo Excel '{nombre_archivo}' descargado exitosamente desde HTTP.")

                    # Procesa el contenido del archivo Excel
                    id_marca = excel_config.get('id_marca')
                    procesar_archivo_excel(archivo_bytes, id_proveedor, id_marca, conexion_proveedores, excel_config)
                    print("Archivo HTTP procesado con éxito")
                    logger_funciones_especificas.info("Archivo HTTP procesado con éxito")
                else:
                    print(f"Error al descargar el archivo HTTP. Código de estado: {response.status_code}")
                    logger_funciones_especificas.info(f"Error al descargar el archivo HTTP. Código de estado: {response.status_code}")
            else:
                print("No se pudo obtener el nombre del archivo desde la base de datos.")
                logger_funciones_especificas.info("No se pudo obtener el nombre del archivo desde la base de datos.")
        else:
            print("Error: Configuración no válida para FTP ni para HTTP.")
            logger_funciones_especificas.info("Error: Configuración no válida para FTP ni para HTTP.")
    except Exception as e:
        print(f"Error al descargar y procesar el archivo: {e}")
        logger_funciones_especificas.info(f"Error al descargar y procesar el archivo: {e}")
    finally:
        if "cursor" in locals() and 'cursor' in vars():
            cursor.close()
    print("Función descargar_y_procesar_archivo ha terminado de ejecutarse.")
    logger_funciones_especificas.info("Función descargar_y_procesar_archivo ha terminado de ejecutarse.")
    return archivo_bytes, excel_config