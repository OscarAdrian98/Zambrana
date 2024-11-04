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
                tipo_archivo = tipo_archivo.lower()
            else:
                raise ValueError("No se pudo obtener la configuración desde la base de datos.")
    except Exception as e:
        logging.error("Error al obtener la configuración de la base de datos: %s", e)
        return None

    try:
        if tipo_archivo == 'csv':
            if id_proveedor == 13:  # Condición específica para el proveedor con ID 13
                # Leer el archivo CSV especificando las columnas con usecols
                df = pd.read_csv(BytesIO(archivo_bytes), encoding='latin1', sep=configuracion_excel["separador_csv_configuracion"], header=None, skiprows=configuracion_excel["fila_comienzo_configuracion"], usecols=[0, 1, 2, 3, 4])
            else:
                # Leer el archivo CSV como se hacía anteriormente
                df = pd.read_csv(BytesIO(archivo_bytes), encoding='latin1', sep=configuracion_excel["separador_csv_configuracion"], header=None, skiprows=configuracion_excel["fila_comienzo_configuracion"], dtype={col_referencia_configuracion: str})
        elif tipo_archivo in ['xlsx', 'xls']:
            pd.set_option('display.float_format', lambda x: '%.f' % x)
            df = pd.read_excel(BytesIO(archivo_bytes), skiprows=configuracion_excel["fila_comienzo_configuracion"], header=None, usecols=configuracion_excel.get("columnas_utilizadas_configuracion"))
        else:
            raise ValueError("Tipo de archivo no soportado")

        if col_fecha_configuracion and col_referencia_configuracion and not col_ean_configuracion:
            df_referencias_fechas = procesar_dataframe_referencias_fechas(df, col_referencia_configuracion, col_fecha_configuracion, configuracion_excel)
            #print("DataFrame de Referencias y Fechas:\n", df_referencias_fechas.head())
            #fila_deseada = df_referencias_fechas[df_referencias_fechas['referencia'] == "00050000002"]
            #print(f"Fila deseada:\n{fila_deseada}")
            return df_referencias_fechas
        
        elif col_fecha_configuracion:
            df_fechas = procesar_dataframe_fechas(df, col_referencia_configuracion, col_fecha_configuracion, configuracion_excel)
            print("DataFrame de Fechas:\n", df_fechas.head()) # Imprime el DataFrame de Fechas.
            return df_fechas
        
        elif col_ean_configuracion:
            df_ean = procesar_dataframe_ean(df, col_referencia_configuracion, col_ean_configuracion, configuracion_excel, configuracion_excel["col_stock_configuracion"])
            print("DataFrame de EAN:\n", df_ean.head()) # Imprime el DataFrame de EAN.
            return df_ean
        
        else:
            df_referencias = procesar_dataframe_referencias(df, col_referencia_configuracion, configuracion_excel["col_stock_configuracion"])
            print("DataFrame de Referencias:\n", df_referencias.head()) # Imprime el DataFrame de Referencias.
            return df_referencias

    except Exception as e:
        logging.error("Error al procesar el archivo: %s", e)
        return None

def procesar_dataframe_fechas(df, col_referencia, col_fecha, configuracion_excel):
    col_stock = int(configuracion_excel["col_stock_configuracion"])
    col_ean = int(configuracion_excel["col_ean_configuracion"])
    
    # Convertir la columna de fecha a formato datetime y manejar errores
    df['col_fecha_configuracion'] = pd.to_datetime(df.iloc[:, int(col_fecha)], errors='coerce')
    
    # Determinar si hay stock
    df['hay_stock'] = df.iloc[:, col_stock].apply(lambda x: 1 if x != '0' and x != 0 else 0)

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
    # Rellenar los valores nulos o NaN en la columna de stock con 0 antes de convertir a string
    df.iloc[:, int(col_stock)] = df.iloc[:, int(col_stock)].fillna(0)

    # Convierte la columna de stock a str para asegurar la correcta evaluación de 0 y 0.0
    df['Stock_str'] = df.iloc[:, int(col_stock)].astype(str)

    # Define una función auxiliar para determinar si hay stock
    def check_stock(x):
        try:
            # Intenta convertir el valor a float y verifica si es diferente de 0
            return 1 if float(x) != 0 else 0
        except ValueError:
            # Si la conversión falla, asume que no es un valor numérico y puedes decidir qué hacer
            return 0  # Trata el valor no numérico como si no hubiera stock

    # Aplica la función auxiliar para determinar si hay stock, teniendo en cuenta valores no numéricos
    df['hay_stock'] = df['Stock_str'].apply(check_stock)

    # Selecciona y renombra las columnas necesarias
    df_ean = df[[int(col_ean), 'Stock_str', 'hay_stock', int(col_referencia)]].copy()
    df_ean = df_ean.rename(columns={int(col_ean): 'ean', 'Stock_str': 'stock', int(col_referencia): 'referencia'})

    # Elimina filas con EANs vacíos o inválidos (puedes ajustar la condición según tus necesidades)
    df_ean = df_ean[df_ean['ean'].notnull() & df_ean['ean'].apply(lambda x: str(x).strip() != '')]

    # Elimina los duplicados basándose en la columna 'EAN'
    df_ean = df_ean.drop_duplicates(subset=['ean'], keep='first')

    # Devuelve el DataFrame resultante
    return df_ean

def procesar_dataframe_referencias(df, col_referencia, col_stock):
    # Cambiamos la lógica para tratar específicamente los guiones como 'sin stock'
    df['hay_stock'] = df.iloc[:, int(col_stock)].apply(lambda x: 1 if str(x).strip() not in ['0', '-'] else 0)
    
    # Selecciona las columnas de referencia y stock, y renombra según sea necesario
    df_referencias = df[[int(col_referencia), int(col_stock), 'hay_stock']].copy()
    df_referencias = df_referencias.rename(columns={int(col_referencia): 'referencia', int(col_stock): 'stock'})
    
    # Elimina los duplicados para mantener solo la primera aparición de cada referencia
    df_referencias = df_referencias.drop_duplicates(subset=['referencia'], keep='first')

    return df_referencias

def procesar_dataframe_referencias_fechas(df, col_referencia, col_fecha, configuracion_excel):
    col_stock = int(configuracion_excel["col_stock_configuracion"])
    
    # Convertir la columna de fecha a formato datetime y manejar errores
    df['col_fecha'] = pd.to_datetime(df.iloc[:, int(col_fecha)], errors='coerce')
    
    # Determinar si hay stock
    df['hay_stock'] = df.iloc[:, col_stock].apply(lambda x: 1 if x != '0' and x != 0 else 0)

    fecha_actual = datetime.now().date()
    mes_anterior = fecha_actual - timedelta(days=30)

    # Inicializar la columna 'fecha_mas_cercana' con NaT (Not a Time)
    df['fecha_mas_cercana'] = pd.NaT

    # Iterar sobre cada grupo de referencia
    for referencia, grupo in df.groupby(int(col_referencia)):
        grupo = grupo.sort_values('col_fecha')
        for idx, fila in grupo.iterrows():
            fecha_fila = fila['col_fecha'].date() if fila['col_fecha'] is not pd.NaT else None
            if fecha_fila and fecha_fila >= mes_anterior:
                # Asignar la fecha más cercana con stock si hay stock
                if fila['hay_stock']:
                    df.at[idx, 'fecha_mas_cercana'] = pd.Timestamp(fecha_fila)
                    break  # Romper el bucle después de asignar la primera fecha con stock
                # Asignar la fecha más cercana sin importar el stock si aún no se ha encontrado una con stock
                elif df.at[idx, 'fecha_mas_cercana'] is pd.NaT:
                    df.at[idx, 'fecha_mas_cercana'] = pd.Timestamp(fecha_fila)

    # Seleccionar y renombrar las columnas necesarias
    df_referencias_fechas = df[[col_referencia, col_stock, 'hay_stock', 'fecha_mas_cercana']].copy()

    # Convertir la columna 'fecha_mas_cercana' a tipo object
    df_referencias_fechas['fecha_mas_cercana'] = df_referencias_fechas['fecha_mas_cercana'].astype(object)

    # Reemplazar 'NaT' por cadenas vacías en 'fecha_mas_cercana'
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

        print("DataFrame Identificado:\n", tipo_df) # Imprime el DataFrame Identificado
        #print("TEST\n", df)
        # Consultar referencias existentes en la base de datos al principio
        with conexion_proveedores.cursor() as cursor:
            cursor.execute("SELECT referencia_producto, stock_txt_producto FROM productos WHERE id_proveedor = %s AND id_marca = %s", (id_proveedor, id_marca))
            referencias_existentes = {row[0]: row[1] for row in cursor.fetchall()}

        pbar = tqdm(total=len(df), desc="Procesando", unit="fila")

        for inicio in range(0, len(df), tamaño_lote):
            fin = inicio + tamaño_lote
            sub_df = df.iloc[inicio:fin]

            # Verificar si la columna 'ean' está en el DataFrame antes de intentar procesarla
            if 'ean' in sub_df.columns:
                sub_df['ean'] = sub_df['ean'].astype(str).str.replace('.0', '', regex=False)

            # Inicializar diccionarios de inserción
            insercciones_fechas = []
            insercciones_ean = []
            insercciones_referencias = []
            insercciones_referencias_fechas = []

            for row in sub_df.itertuples(index=False):
                if tipo_df == 'referencias_fechas':
                    ref, stock, hay_stock, fecha_disponibilidad = row
                    ref, fecha_disponibilidad = str(ref), str(fecha_disponibilidad)
                    if ref not in referencias_existentes:
                        insercciones_referencias_fechas.append((id_proveedor, ref, stock, hay_stock, fecha_actualizacion, fecha_disponibilidad, id_marca))
                elif tipo_df == 'fechas':
                    ref, ean, stock, hay_stock, fecha_disponibilidad = row
                    ref, ean, fecha_disponibilidad = str(ref), str(ean), str(fecha_disponibilidad)
                    if ref not in referencias_existentes:
                        insercciones_fechas.append((id_proveedor, ref, ean, stock, hay_stock, fecha_actualizacion, fecha_disponibilidad, id_marca))
                elif tipo_df == 'ean':
                    ean, stock, hay_stock, ref = row
                    ref, ean = str(ref), str(ean)
                    # Añade aquí la validación para 'ref' y 'ean'
                    if ref.lower() == 'nan' or ean.lower() == 'nan':
                        logging.warning(f"Se encontró un valor 'nan' para ref: {ref} o ean: {ean}, se omite la inserción.")
                        continue  # Omite esta inserción
                    if ref not in referencias_existentes:
                        insercciones_ean.append((id_proveedor, ref, ean, stock, hay_stock, fecha_actualizacion, id_marca))
                else:  # 'referencias'
                    ref, stock, hay_stock = row
                    ref = str(ref)
                    if ref not in referencias_existentes:
                        insercciones_referencias.append((id_proveedor, ref, stock, fecha_actualizacion, id_marca, hay_stock))

            with conexion_proveedores.cursor() as cursor:
                # Inserciones específicas según el tipo de DataFrame
                if insercciones_referencias_fechas:
                    cursor.executemany("INSERT INTO productos (id_proveedor, referencia_producto, stock_txt_producto, hay_stock_producto, fecha_actualizacion_producto, fecha_disponibilidad_producto, id_marca) VALUES (%s, %s, %s, %s, %s, %s, %s)", insercciones_referencias_fechas)
                    conexion_proveedores.commit()
                    for _, ref, stock, _, _, _, _ in insercciones_referencias_fechas:
                        logging.info(f"Insertada referencia Fechas: {ref}, Stock: {stock}")
                elif insercciones_fechas:
                    cursor.executemany("INSERT INTO productos (id_proveedor, referencia_producto, ean_producto, stock_txt_producto, hay_stock_producto, fecha_actualizacion_producto, fecha_disponibilidad_producto, id_marca) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", insercciones_fechas)
                    conexion_proveedores.commit()
                    for _, ref, ean, stock, _, _, _, _ in insercciones_fechas:
                        logging.info(f"Insertada referencia Fechas: {ref}, EAN: {ean}, Stock: {stock}")
                elif insercciones_ean:
                    cursor.executemany("INSERT INTO productos (id_proveedor, referencia_producto, ean_producto, stock_txt_producto, hay_stock_producto, fecha_actualizacion_producto, id_marca) VALUES (%s, %s, %s, %s, %s, %s, %s)", insercciones_ean)
                    conexion_proveedores.commit()
                    for _, ref, ean, stock, _, _, _ in insercciones_ean:
                        logging.info(f"Insertada referencia REF: {ref}, EAN: {ean}, Stock: {stock}")
                elif insercciones_referencias:
                    cursor.executemany("INSERT INTO productos (id_proveedor, referencia_producto, stock_txt_producto, fecha_actualizacion_producto, id_marca, hay_stock_producto) VALUES (%s, %s, %s, %s, %s, %s)", insercciones_referencias)
                    conexion_proveedores.commit()
                    for _, ref, stock, _, _, _ in insercciones_referencias:
                        logging.info(f"Insertada referencia: {ref}, Stock: {stock}")

            pbar.update(len(sub_df))

        # Obtener referencias y EAN existentes en PrestaShop
        df_referencias_stock = obtener_referencias_y_stock(conexion_prestashop, id_proveedor, id_marca)
        print("DataFrame de PrestaShop cargado.")

        # Filtrar el DataFrame por id_proveedor e id_marca
        df_filtrado_prestashop = df_referencias_stock[(df_referencias_stock['id_proveedor'] == id_proveedor) & (df_referencias_stock['id_marca'] == id_marca)].copy()
        #print("DataFrame BaseDatos: ", df_filtrado_prestashop)
        logging.info(f"DataFrame de PrestaShop filtrado para el proveedor {id_proveedor} y la marca {id_marca}.")
        logger_funciones_especificas.info(f"DataFrame de PrestaShop filtrado para el proveedor {id_proveedor} y la marca {id_marca}.")

        # Comprobar si la columna 'ean' está presente en el DataFrame
        ean_presente = 'ean' in df.columns
        print(f"La columna 'ean' {'está' if ean_presente else 'no está'} presente en el DataFrame.")

        # Paso de diagnóstico antes de la fusión
        print("\n--- Diagnóstico Pre-Fusión ---")
        if ean_presente:
            print(f"Valores únicos en 'ean' del df: {df['ean'].nunique()}, Nulos: {df['ean'].isnull().sum()}")
            print(f"Valores únicos en 'ean_producto' del df_filtrado_prestashop: {df_filtrado_prestashop['ean_producto'].nunique()}, Nulos: {df_filtrado_prestashop['ean_producto'].isnull().sum()}")
        else:
            print(f"Valores únicos en 'referencia' del df: {df['referencia'].nunique()}, Nulos: {df['referencia'].isnull().sum()}")
            print(f"Valores únicos en 'reference' del df_filtrado_prestashop: {df_filtrado_prestashop['reference'].nunique()}, Nulos: {df_filtrado_prestashop['reference'].isnull().sum()}")

        # Fusionar basado en 'ean' si está presente, de lo contrario, en 'referencia'
        if ean_presente:
            df['ean'] = df['ean'].astype(str)
            df_filtrado_prestashop['ean_producto'] = df_filtrado_prestashop['ean_producto'].astype(str)
            df_fusionado = pd.merge(df, df_filtrado_prestashop, left_on='ean', right_on='ean_producto', how='inner', suffixes=('', '_presta'))
            print("DataFrames fusionados en base a 'ean'.")
        else:
            df['referencia'] = df['referencia'].astype(str)  # Asegurarse de que 'referencia' es de tipo string
            df_filtrado_prestashop['reference'] = df_filtrado_prestashop['reference'].astype(str)  # Asegurarse de que 'reference' en PrestaShop es de tipo string
            df_fusionado = pd.merge(df, df_filtrado_prestashop, left_on='referencia', right_on='reference', how='inner', suffixes=('', '_presta'))
            print("DataFrames fusionados en base a 'referencia'.")

        # Paso de diagnóstico después de la fusión
        print("\n--- Diagnóstico Post-Fusión ---")
        print(f"Filas en el DataFrame fusionado: {df_fusionado.shape[0]}")

        #print("DataFrame fusionado:")
        #print(df_fusionado)

        # Comprobar si la columna 'fecha_mas_cercana' está presente en el DataFrame

        # Preparar las listas para las actualizaciones
        actualizaciones_referencias_fechas = []
        actualizaciones_referencias = []

        # Iterar sobre el DataFrame fusionado para preparar las actualizaciones
        for index, row in df_fusionado.iterrows():
            referencia = row['referencia']
            stock = row['stock']
            hay_stock = row['hay_stock']
            fecha_disponibilidad = row.get('fecha_mas_cercana', None)

            if fecha_disponibilidad == '':
                fecha_disponibilidad = None  # Convertir cadena vacía en 'None' para insertar como NULL en la base de datos

            # Imprimir los detalles de la referencia que se va a actualizar
            #logging.info(f"Referencia: {referencia}, Stock: {stock}, Hay stock: {hay_stock}, Fecha disponibilidad: {fecha_disponibilidad}")

            # Preparar la actualización según el tipo de DataFrame
            if 'fecha_mas_cercana' in df.columns:
                actualizaciones_referencias_fechas.append((stock, hay_stock, fecha_actualizacion, fecha_disponibilidad, id_proveedor, referencia, id_marca))
            else:
                actualizaciones_referencias.append((stock, fecha_actualizacion, hay_stock, id_proveedor, referencia, id_marca))

        # Ejecutar las actualizaciones
        with conexion_proveedores.cursor() as cursor:
            if actualizaciones_referencias_fechas:
                cursor.executemany("UPDATE productos SET stock_txt_producto = %s, hay_stock_producto = %s, fecha_actualizacion_producto = %s, fecha_disponibilidad_producto = %s WHERE id_proveedor = %s AND referencia_producto = %s AND id_marca = %s", actualizaciones_referencias_fechas)
                logging.info(f"Actualizadas {len(actualizaciones_referencias_fechas)} referencias con fechas.")
                # Imprimir detalles de las actualizaciones para referencias con fechas
                for actualizacion in actualizaciones_referencias_fechas:
                    logging.info(f"Referencia con fecha actualizada: {actualizacion[5]}, Stock: {actualizacion[0]}, Hay stock: {actualizacion[1]}, Fecha disponibilidad: {actualizacion[3]}")
            
            if actualizaciones_referencias:
                cursor.executemany("UPDATE productos SET stock_txt_producto = %s, fecha_actualizacion_producto = %s, hay_stock_producto = %s WHERE id_proveedor = %s AND referencia_producto = %s AND id_marca = %s", actualizaciones_referencias)
                logging.info(f"Actualizadas {len(actualizaciones_referencias)} referencias sin fechas.")
                # Imprimir detalles de las actualizaciones para referencias sin fechas
                for actualizacion in actualizaciones_referencias:
                    logging.info(f"Referencia sin fecha actualizada: {actualizacion[4]}, Stock: {actualizacion[0]}, Hay stock: {actualizacion[2]}")

            conexion_proveedores.commit()

    except Exception as e:
        conexion_proveedores.rollback()
        logging.error(f"Error al procesar el contenido del archivo Excel: {e}")
        raise e
        
# Funcion para ver las referencias que no se han actualizado.   
def verificar_referencias_no_actualizadas(id_proveedor, id_marca, conexion_proveedores, conexion_prestashop):
    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    referencias_no_actualizadas = []

    try:
        with conexion_proveedores.cursor() as cursor:
            consulta_no_actualizadas_hoy = (
                "SELECT referencia_producto, hay_stock_producto "
                "FROM productos "
                "WHERE id_proveedor = %s AND id_marca = %s AND DATE(fecha_actualizacion_producto) != %s"
            )
            cursor.execute(consulta_no_actualizadas_hoy, (id_proveedor, id_marca, fecha_actual))
            referencias_no_actualizadas = cursor.fetchall()  # Ahora obtenemos una lista de tuplas (referencia_producto, hay_stock_producto)

        if not referencias_no_actualizadas:
            logging.info("Todas las referencias para id_proveedor y id_marca se han actualizado hoy.")
            logger_funciones_especificas.info("Todas las referencias para id_proveedor y id_marca se han actualizado hoy.")
            return

    except Exception as e:
        conexion_proveedores.rollback()
        logging.error(f"Error: {e}")
        logger_funciones_especificas.error(f"Error: {e}")
        return

    try:
        df_referencias_stock = obtener_referencias_y_stock(conexion_prestashop, id_proveedor, id_marca)
        referencias_en_prestashop = df_referencias_stock['reference'].tolist()
        referencias_no_actualizadas_y_en_prestashop = [(ref, stock) for ref, stock in referencias_no_actualizadas if ref in referencias_en_prestashop]

        if referencias_no_actualizadas_y_en_prestashop:
            with conexion_proveedores.cursor() as cursor:
                for referencia, _ in referencias_no_actualizadas_y_en_prestashop:
                    cursor.execute(
                        "UPDATE productos SET stock_txt_producto = '0', hay_stock_producto = '0' "
                        "WHERE id_proveedor = %s AND id_marca = %s AND referencia_producto = %s",
                        (id_proveedor, id_marca, referencia)
                    )
                conexion_proveedores.commit()

            for referencia, stock_proveedor in referencias_no_actualizadas_y_en_prestashop:
                # Suponemos que df_referencias_stock ya contiene la columna 'quantity' que representa el stock en PrestaShop
                stock_prestashop = df_referencias_stock[df_referencias_stock['reference'] == referencia]['quantity'].iloc[0]
                mensaje_log = (f"**** Referencia no actualizada y presente en PrestaShop: {referencia}, "
                               f"Stock en PrestaShop: {stock_prestashop}, Stock del proveedor actualizado a '0', "
                               f"id_proveedor: {id_proveedor}, id_marca: {id_marca} ****")
                logger_funciones_especificas.info(mensaje_log)
        else:
            logging.info("No hay referencias no actualizadas presentes en PrestaShop.")
            logger_funciones_especificas.info("No hay referencias no actualizadas presentes en PrestaShop.")

    except Exception as e:
        conexion_proveedores.rollback()
        logging.error(f"Error al comparar referencias y stock: {e}")
        logger_funciones_especificas.error(f"Error al comparar referencias y stock: {e}")

# Función para descargar y procesar un archivo desde un servidor FTP o una URL HTTP
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
                print(f"Fallo la descarga FTP/FTPS: {ftp_error}, intentando SFTP...")
                logger_funciones_especificas.info(f"Fallo la descarga FTP/FTPS: {ftp_error}, intentando SFTP...")

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

# Función para obtener un DataFrame de las refe, stock y tabla.
def obtener_referencias_y_stock(conexion_prestashop, id_proveedor, id_marca):
    try:
        query = f"""
        SELECT
            tb_prestashop.reference,
            tb_prestashop.ean13,
            tb_prestashop.quantity,
            tb_proveedores.id_proveedor,
            tb_proveedores.id_marca,
            tb_proveedores.stock_txt_producto,
            tb_proveedores.hay_stock_producto,
            tb_proveedores.ean_producto,
            tb_proveedores.fecha_disponibilidad_producto,
            tb_prestashop.table_name
        FROM
            (
                SELECT
                    p.id_product,
                    p.reference,
                    p.ean13,
                    sa.quantity,
                    'ps_product' AS table_name
                FROM
                    ps_product p
                    JOIN ps_stock_available sa ON 
                        p.id_product = sa.id_product AND sa.id_product_attribute = 0
                WHERE
                    p.reference IS NOT NULL AND p.reference <> ''

                UNION ALL

                SELECT
                    pa.id_product,
                    pa.reference,
                    pa.ean13,
                    sa.quantity,
                    'ps_product_attribute' AS table_name
                FROM
                    ps_product_attribute pa
                    JOIN ps_stock_available sa ON 
                        pa.id_product_attribute = sa.id_product_attribute
                WHERE
                    pa.reference IS NOT NULL AND pa.reference <> ''

                UNION ALL

                SELECT
                    ps.id_product,
                    ps.product_supplier_reference AS reference,
                    '' AS ean13,
                    sa.quantity,
                    'ps_product_supplier' AS table_name
                FROM
                    ps_product_supplier ps
                    JOIN ps_stock_available sa ON 
                        ps.id_product = sa.id_product AND sa.id_product_attribute = 0
                WHERE
                    ps.product_supplier_reference IS NOT NULL AND ps.product_supplier_reference <> ''
            ) AS tb_prestashop
        JOIN 
            stock_proveedores.productos AS tb_proveedores ON tb_proveedores.referencia_producto = tb_prestashop.reference
        WHERE
            tb_proveedores.id_proveedor = {id_proveedor} AND tb_proveedores.id_marca = {id_marca}

        UNION

        SELECT
            tb_prestashop.reference,
            tb_prestashop.ean13,
            tb_prestashop.quantity,
            tb_proveedores.id_proveedor,
            tb_proveedores.id_marca,
            tb_proveedores.stock_txt_producto,
            tb_proveedores.hay_stock_producto,
            tb_proveedores.ean_producto,
            tb_proveedores.fecha_disponibilidad_producto,
            tb_prestashop.table_name
        FROM
            (
                SELECT
                    p.id_product,
                    p.reference,
                    p.ean13,
                    sa.quantity,
                    'ps_product' AS table_name
                FROM
                    ps_product p
                    JOIN ps_stock_available sa ON 
                        p.id_product = sa.id_product AND sa.id_product_attribute = 0
                WHERE
                    p.reference IS NOT NULL AND p.reference <> ''

                UNION ALL

                SELECT
                    pa.id_product,
                    pa.reference,
                    pa.ean13,
                    sa.quantity,
                    'ps_product_attribute' AS table_name
                FROM
                    ps_product_attribute pa
                    JOIN ps_stock_available sa ON 
                        pa.id_product_attribute = sa.id_product_attribute
                WHERE
                    pa.reference IS NOT NULL AND pa.reference <> ''

                UNION ALL

                SELECT
                    ps.id_product,
                    ps.product_supplier_reference AS reference,
                    '' AS ean13,
                    sa.quantity,
                    'ps_product_supplier' AS table_name
                FROM
                    ps_product_supplier ps
                    JOIN ps_stock_available sa ON 
                        ps.id_product = sa.id_product AND sa.id_product_attribute = 0
                WHERE
                    ps.product_supplier_reference IS NOT NULL AND ps.product_supplier_reference <> ''
            ) AS tb_prestashop
        JOIN 
            stock_proveedores.productos AS tb_proveedores ON tb_proveedores.ean_producto = tb_prestashop.ean13
        WHERE
            tb_proveedores.id_proveedor = {id_proveedor} AND tb_proveedores.id_marca = {id_marca}
        """

        with conexion_prestashop.cursor() as cursor_prestashop:
            cursor_prestashop.execute(query)
            resultados = cursor_prestashop.fetchall()

        df_referencias_stock = pd.DataFrame(resultados, columns=['reference', 'ean13', 'quantity', 'id_proveedor', 'id_marca', 'stock_txt_producto', 'hay_stock_producto', 'ean_producto', 'fecha_disponibilidad_producto', 'table'])

        return df_referencias_stock

    except pymysql.Error as e:
        logging.error(f"Error al obtener referencias y stock: {e}")
        return pd.DataFrame()