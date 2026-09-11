from config.provider_rules import OPEN_QUANTITY_PROVIDER_ID, FTPS_PROVIDER_ID
import logging
import socket
import time
from config.logging import logger_funciones_especificas
import pandas as pd
from io import BytesIO
from datetime import datetime
from tqdm import tqdm
from ftplib import FTP_TLS, FTP, error_perm, error_temp
import requests
import paramiko
from config.rendimiento import commit_con_metricas, medir_fase
from procesamiento.reglas import (
    conjunto_identificadores_validos,
    normalizar_identificador,
    normalizar_indices_configuracion,
    normalizar_serie_ean,
    normalizar_serie_identificadores,
    normalizar_serie_stock,
    normalizar_stock,
)
from procesamiento.variantes import preparar_variantes_o_fallar

# Función para procesar el archivo y preparar los datos
def check_stock(x):
    """Función para determinar si hay stock basado en valores de diferentes formatos."""
    return normalizar_stock(x)


def preparar_referencias_parts_europe(
    dataframe,
    columna_referencia,
    columna_alias=1,
    columna_marca=5,
):
    """Transporta el alias normalizado sin crear variantes adicionales.

    Compatibilidad para consumidores directos: ``ItemNumber`` conserva la
    identidad y ``VendorNo`` viaja en una columna, sin duplicar ninguna fila.
    """

    resultado = dataframe.copy()
    referencias = normalizar_serie_identificadores(
        resultado.iloc[:, columna_referencia]
    )
    aliases = normalizar_serie_identificadores(
        resultado.iloc[:, columna_alias]
    )
    resultado["referencia_alternativa"] = aliases
    resultado["marca_fuente"] = (
        resultado.iloc[:, columna_marca].astype("string").str.strip()
    )
    estadisticas = {
        "filas_fuente": int(len(resultado)),
        "referencias_primarias": int(referencias.notna().sum()),
        "aliases_candidatos": int(aliases.notna().sum()),
        "aliases_ambiguos": int(
            pd.DataFrame({"referencia": referencias, "alias": aliases})
            .dropna()
            .groupby("alias")["referencia"]
            .nunique()
            .gt(1)
            .sum()
        ),
        "filas_resultado": int(len(resultado)),
    }
    resultado.attrs["estadisticas_aliases_referencia"] = estadisticas
    return resultado

# Función para procesar el archivo y preparar los datos
def procesar_archivo_excel(
    archivo_bytes,
    id_proveedor,
    id_marca,
    conexion_proveedores,
    configuracion_excel,
    metricas=None,
):
    try:
        with medir_fase(metricas, "Consultas SQL"):
            with conexion_proveedores.cursor() as cursor:
                id_configuracion = configuracion_excel.get("id_configuracion")
                if id_configuracion is not None:
                    cursor.execute(
                        "SELECT extension_configuracion, "
                        "col_referencia_configuracion, "
                        "col_referencia_alternativa_configuracion, "
                        "col_ean_configuracion, col_fecha_configuracion "
                        "FROM configuracion_proveedores "
                        "WHERE id_configuracion = %s AND id_proveedor = %s",
                        (id_configuracion, id_proveedor),
                    )
                else:
                    cursor.execute(
                        "SELECT extension_configuracion, "
                        "col_referencia_configuracion, NULL, "
                        "col_ean_configuracion, col_fecha_configuracion "
                        "FROM configuracion_proveedores "
                        "WHERE id_proveedor = %s AND id_marca = %s",
                        (id_proveedor, id_marca),
                    )
                resultado = cursor.fetchone()

        if resultado:
            (
                tipo_archivo,
                col_referencia_configuracion,
                col_referencia_alternativa_configuracion,
                col_ean_configuracion,
                col_fecha_configuracion,
            ) = resultado
            tipo_archivo = str(tipo_archivo).lower()
            configuracion_excel = dict(configuracion_excel)
            configuracion_excel["col_referencia_configuracion"] = col_referencia_configuracion
            configuracion_excel[
                "col_referencia_alternativa_configuracion"
            ] = col_referencia_alternativa_configuracion
            configuracion_excel["col_ean_configuracion"] = col_ean_configuracion
            configuracion_excel["col_fecha_configuracion"] = col_fecha_configuracion
        else:
            raise ValueError("No se pudo obtener la configuración desde la base de datos.")
    except Exception as e:
        logging.exception(
            "Error al obtener la configuración del proveedor %s", id_proveedor
        )
        raise RuntimeError(
            f"No se pudo obtener la configuración del proveedor {id_proveedor}"
        ) from e

    try:
        diagnostico_alt = (
            col_referencia_alternativa_configuracion is not None
        )
        if diagnostico_alt:
            inicio_parseo = time.perf_counter()
            logging.info(
                "Referencia alternativa INICIO etapa=parseo "
                "filas_entrada=%s",
                len(archivo_bytes),
            )
        with medir_fase(metricas, "Lectura del fichero"):
            if tipo_archivo == 'csv':
                df = pd.read_csv(BytesIO(archivo_bytes),
                                 encoding='latin1',
                                 on_bad_lines='skip',
                                 sep=configuracion_excel["separador_csv_configuracion"],
                                 header=None,
                                 skiprows=configuracion_excel["fila_comienzo_configuracion"],
                                 dtype=str)
            elif tipo_archivo in ['xlsx', 'xls']:
                pd.set_option('display.float_format', lambda x: '%.f' % x)
                df = pd.read_excel(BytesIO(archivo_bytes),
                                   skiprows=configuracion_excel["fila_comienzo_configuracion"],
                                   header=None,
                                   usecols=configuracion_excel.get("columnas_utilizadas_configuracion"))
            elif tipo_archivo == 'txt':
                df = pd.read_csv(BytesIO(archivo_bytes),
                                 delimiter=configuracion_excel.get("separador_txt_configuracion", '\t'),
                                 header=None,
                                 skiprows=configuracion_excel["fila_comienzo_configuracion"],
                                 encoding='latin1',
                                 dtype=str)
            else:
                raise ValueError(f"Tipo de archivo no soportado: {tipo_archivo}")
        if diagnostico_alt:
            logging.info(
                "Referencia alternativa FIN etapa=parseo duracion=%.3fs "
                "filas_entrada=%s filas_salida=%s",
                time.perf_counter() - inicio_parseo,
                len(archivo_bytes),
                len(df),
            )

        with medir_fase(metricas, "Normalización"):
            configuracion_excel = normalizar_indices_configuracion(
                configuracion_excel,
                len(df.columns),
                id_proveedor,
            )
            col_referencia_configuracion = configuracion_excel[
                "col_referencia_configuracion"
            ]
            col_referencia_alternativa_configuracion = configuracion_excel[
                "col_referencia_alternativa_configuracion"
            ]
            col_ean_configuracion = configuracion_excel["col_ean_configuracion"]
            col_fecha_configuracion = configuracion_excel["col_fecha_configuracion"]
            df = df.fillna("")

            if col_referencia_alternativa_configuracion is not None:
                inicio_alt = time.perf_counter()
                logging.info(
                    "Referencia alternativa INICIO "
                    "etapa=normalizacion_alternativa_fichero "
                    "filas_entrada=%s",
                    len(df),
                )
                df["_referencia_alternativa_normalizada"] = (
                    normalizar_serie_identificadores(
                        df.iloc[:, col_referencia_alternativa_configuracion]
                    )
                )
                logging.info(
                    "Referencia alternativa FIN "
                    "etapa=normalizacion_alternativa_fichero "
                    "duracion=%.3fs filas_entrada=%s filas_salida=%s",
                    time.perf_counter() - inicio_alt,
                    len(df),
                    int(df["_referencia_alternativa_normalizada"].notna().sum()),
                )

            col_marca_fuente = configuracion_excel.get("col_marca_fuente")
            if col_marca_fuente is not None:
                col_marca_fuente = int(col_marca_fuente)
                if not 0 <= col_marca_fuente < len(df.columns):
                    raise ValueError(
                        "La columna de marca configurada queda fuera del fichero"
                    )
                df["marca_fuente"] = (
                    df.iloc[:, col_marca_fuente]
                    .astype("string")
                    .str.strip()
                )

            # Procesamiento normal. Los índices opcionales se comparan
            # explícitamente con None para aceptar la columna 0.
            if diagnostico_alt:
                inicio_principal = time.perf_counter()
                logging.info(
                    "Referencia alternativa INICIO "
                    "etapa=normalizacion_principal_fichero "
                    "filas_entrada=%s",
                    len(df),
                )
            if col_fecha_configuracion is not None and col_ean_configuracion is None:
                resultado_procesado = procesar_dataframe_referencias_fechas(
                    df, col_referencia_configuracion, col_fecha_configuracion,
                    configuracion_excel
                )
            elif col_fecha_configuracion is not None:
                resultado_procesado = procesar_dataframe_fechas(
                    df, col_referencia_configuracion, col_fecha_configuracion,
                    configuracion_excel
                )
            elif col_ean_configuracion is not None:
                resultado_procesado = procesar_dataframe_ean(
                    df, col_referencia_configuracion, col_ean_configuracion,
                    configuracion_excel, configuracion_excel["col_stock_configuracion"]
                )
            else:
                resultado_procesado = procesar_dataframe_referencias(
                    df, col_referencia_configuracion,
                    configuracion_excel["col_stock_configuracion"]
                )
            if id_proveedor == OPEN_QUANTITY_PROVIDER_ID:
                stock_abierto = (
                    resultado_procesado["stock"]
                    .astype("string")
                    .str.strip()
                    .str.fullmatch(r"[0-9]+(?:[.,][0-9]+)?\+", na=False)
                )
                cantidades_minimas = pd.to_numeric(
                    resultado_procesado.loc[stock_abierto, "stock"]
                    .astype("string")
                    .str.strip()
                    .str.rstrip("+")
                    .str.replace(",", ".", regex=False),
                    errors="coerce",
                )
                resultado_procesado.loc[stock_abierto, "hay_stock"] = (
                    cantidades_minimas > 0
                ).astype("int8")
            if diagnostico_alt:
                logging.info(
                    "Referencia alternativa FIN "
                    "etapa=normalizacion_principal_fichero "
                    "duracion=%.3fs filas_entrada=%s filas_salida=%s",
                    time.perf_counter() - inicio_principal,
                    len(df),
                    len(resultado_procesado),
                )
                inicio_deduplicacion = time.perf_counter()
                logging.info(
                    "Referencia alternativa INICIO etapa=deduplicacion "
                    "filas_entrada=%s",
                    len(resultado_procesado),
                )
            resultado = preparar_variantes_o_fallar(
                resultado_procesado,
                id_proveedor=id_proveedor,
                identificadores_normalizados=True,
            )
            if diagnostico_alt:
                logging.info(
                    "Referencia alternativa FIN etapa=deduplicacion "
                    "duracion=%.3fs filas_entrada=%s filas_salida=%s",
                    time.perf_counter() - inicio_deduplicacion,
                    len(resultado_procesado),
                    len(resultado),
                )
            return resultado

    except Exception as e:
        logging.exception("Error al procesar el archivo del proveedor %s", id_proveedor)
        raise RuntimeError(
            f"No se pudo procesar el archivo del proveedor {id_proveedor}: {e}"
        ) from e

def _seleccionar_filas_por_fecha(df, col_referencia, col_fecha):
    """Devuelve una fila determinista por referencia y su fecha elegida."""

    trabajo = df.copy()
    trabajo["_referencia_normalizada"] = normalizar_serie_identificadores(
        trabajo.iloc[:, col_referencia]
    )
    trabajo["_fecha_parseada"] = pd.to_datetime(
        trabajo.iloc[:, col_fecha], errors="coerce"
    )
    trabajo = trabajo[trabajo["_referencia_normalizada"].notna()].copy()

    if trabajo.empty:
        return pd.DataFrame(columns=[*df.columns, "fecha_mas_cercana"])

    referencias = trabajo["_referencia_normalizada"]
    fechas = trabajo["_fecha_parseada"].dt.normalize()
    hoy = pd.Timestamp.now().normalize()
    fecha_minima = hoy - pd.Timedelta(days=30)
    fecha_valida = fechas.notna() & fechas.ge(fecha_minima)
    stock = pd.to_numeric(trabajo["hay_stock"], errors="coerce").fillna(0)
    valida_con_stock = fecha_valida & stock.gt(0)
    grupo_con_stock = valida_con_stock.groupby(referencias).transform("any")
    elegible = fecha_valida & (~grupo_con_stock | stock.gt(0))

    fechas_elegibles = trabajo.loc[elegible, ["_referencia_normalizada"]].copy()
    fechas_elegibles["_fecha_elegible"] = fechas.loc[elegible]
    fechas_elegibles["_distancia_fecha"] = (
        fechas_elegibles["_fecha_elegible"] - hoy
    ).abs()
    fechas_elegidas = (
        fechas_elegibles.sort_values(
            [
                "_referencia_normalizada",
                "_distancia_fecha",
                "_fecha_elegible",
            ],
            kind="stable",
        )
        .drop_duplicates("_referencia_normalizada", keep="first")
        .set_index("_referencia_normalizada")["_fecha_elegible"]
    )
    trabajo["fecha_mas_cercana"] = referencias.map(fechas_elegidas)

    sin_fecha = trabajo["fecha_mas_cercana"].isna()
    candidatos = trabajo[
        sin_fecha | fechas.eq(trabajo["fecha_mas_cercana"])
    ].copy()
    stock_candidatos = pd.to_numeric(
        candidatos["hay_stock"], errors="coerce"
    ).fillna(0)
    candidato_con_stock = stock_candidatos.gt(0).groupby(
        candidatos["_referencia_normalizada"]
    ).transform("any")
    candidatos = candidatos[
        ~candidato_con_stock | stock_candidatos.gt(0)
    ].copy()

    # Se calcula una sola vez para todo el bloque; antes se reconstruía dentro
    # de cada uno de los miles de grupos. El separador conserva el mismo orden
    # lexicográfico determinista de la implementación anterior.
    columnas_orden = [
        columna
        for columna in trabajo.columns
        if columna != "fecha_mas_cercana"
    ]
    candidatos["_orden_fila"] = (
        candidatos[columnas_orden]
        .astype("string")
        .fillna("")
        .agg("\x1f".join, axis=1)
    )
    seleccionadas = (
        candidatos.sort_values(
            ["_referencia_normalizada", "hay_stock", "_orden_fila"],
            ascending=[True, False, True],
            kind="stable",
        )
        .drop_duplicates("_referencia_normalizada", keep="first")
        .reset_index(drop=True)
    )

    grupos_sin_fecha = int(
        referencias[~referencias.isin(fechas_elegidas.index)].nunique()
    )
    if grupos_sin_fecha:
        logging.warning(
            "%s referencias no tienen una fecha válida en la ventana de 30 días",
            grupos_sin_fecha,
        )
    return seleccionadas[
        [
            *df.columns,
            "_referencia_normalizada",
            "_fecha_parseada",
            "_orden_fila",
            "fecha_mas_cercana",
        ]
    ]


def procesar_dataframe_fechas(df, col_referencia, col_fecha, configuracion_excel):
    col_stock = configuracion_excel["col_stock_configuracion"]
    col_ean = configuracion_excel["col_ean_configuracion"]

    trabajo = df.copy()
    trabajo["hay_stock"] = normalizar_serie_stock(trabajo.iloc[:, col_stock])
    trabajo = _seleccionar_filas_por_fecha(
        trabajo, col_referencia, col_fecha
    )

    columnas = [
        col_referencia, col_ean, col_stock, "hay_stock", "fecha_mas_cercana"
    ]
    if "_referencia_alternativa_normalizada" in trabajo:
        columnas.append("_referencia_alternativa_normalizada")
    df_fechas = trabajo[columnas].copy()
    df_fechas = df_fechas.rename(columns={
        col_referencia: 'referencia',
        col_ean: 'ean',
        col_stock: 'stock',
        'hay_stock': 'hay_stock',
        'fecha_mas_cercana': 'fecha_mas_cercana',
        '_referencia_alternativa_normalizada': 'referencia_alternativa',
    })

    df_fechas["referencia"] = normalizar_serie_identificadores(
        df_fechas["referencia"]
    )
    df_fechas["ean"] = normalizar_serie_ean(df_fechas["ean"])
    df_fechas = df_fechas[df_fechas["referencia"].notna()].copy()

    return df_fechas

def procesar_dataframe_ean(df, col_referencia, col_ean, configuracion_excel, col_stock):
    trabajo = df.copy()
    trabajo.iloc[:, col_stock] = trabajo.iloc[:, col_stock].fillna(0)
    trabajo['Stock_str'] = trabajo.iloc[:, col_stock].astype(str)

    # Aplicamos la función check_stock a la columna de stock
    trabajo['hay_stock'] = normalizar_serie_stock(trabajo['Stock_str'])

    columnas = [col_ean, 'Stock_str', 'hay_stock', col_referencia]
    if "_referencia_alternativa_normalizada" in trabajo:
        columnas.append("_referencia_alternativa_normalizada")
    df_ean = trabajo[columnas].copy()
    df_ean = df_ean.rename(
        columns={
            col_ean: 'ean',
            'Stock_str': 'stock',
            col_referencia: 'referencia',
            '_referencia_alternativa_normalizada': 'referencia_alternativa',
        }
    )

    df_ean["ean"] = normalizar_serie_ean(df_ean["ean"])
    df_ean["referencia"] = normalizar_serie_identificadores(
        df_ean["referencia"]
    )
    # Se conserva una referencia válida aunque el EAN esté ausente, porque el
    # cruce posterior puede usarla como respaldo. Una fila sin referencia no se
    # puede insertar de forma segura en la tabla productos.
    df_ean = df_ean[df_ean["referencia"].notna()].copy()

    return df_ean

def procesar_dataframe_referencias(df, col_referencia, col_stock):
    trabajo = df.copy()
    trabajo['hay_stock'] = normalizar_serie_stock(trabajo.iloc[:, col_stock])

    columnas = [col_referencia, col_stock, 'hay_stock']
    if "_referencia_alternativa_normalizada" in trabajo:
        columnas.append("_referencia_alternativa_normalizada")
    if "marca_fuente" in trabajo.columns:
        columnas.append("marca_fuente")
    df_referencias = trabajo[columnas].copy()
    df_referencias = df_referencias.rename(
        columns={
            col_referencia: 'referencia',
            col_stock: 'stock',
            '_referencia_alternativa_normalizada': 'referencia_alternativa',
        }
    )

    df_referencias["referencia"] = normalizar_serie_identificadores(
        df_referencias["referencia"]
    )
    df_referencias = df_referencias[
        df_referencias["referencia"].notna()
    ].copy()

    return df_referencias

def procesar_dataframe_referencias_fechas(df, col_referencia, col_fecha, configuracion_excel):
    col_stock = configuracion_excel["col_stock_configuracion"]
    trabajo = df.copy()
    trabajo['hay_stock'] = normalizar_serie_stock(trabajo.iloc[:, col_stock])
    trabajo = _seleccionar_filas_por_fecha(
        trabajo, col_referencia, col_fecha
    )

    columnas = [col_referencia, col_stock, 'hay_stock', 'fecha_mas_cercana']
    if "_referencia_alternativa_normalizada" in trabajo:
        columnas.append("_referencia_alternativa_normalizada")
    df_referencias_fechas = trabajo[columnas].copy()

    df_referencias_fechas = df_referencias_fechas.rename(columns={
        col_referencia: 'referencia',
        col_stock: 'stock',
        'hay_stock': 'hay_stock',
        'fecha_mas_cercana': 'fecha_mas_cercana',
        '_referencia_alternativa_normalizada': 'referencia_alternativa',
    })

    df_referencias_fechas["referencia"] = normalizar_serie_identificadores(
        df_referencias_fechas["referencia"]
    )
    df_referencias_fechas = df_referencias_fechas[
        df_referencias_fechas["referencia"].notna()
    ].copy()

    return df_referencias_fechas

# Función para insertar y actualizar en la base de datos
def actualizar_base_datos(
    df,
    id_proveedor,
    id_marca,
    conexion_proveedores,
    conexion_prestashop,
    tamaño_lote=22000,
    metricas=None,
):
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
            sub_df = df.iloc[inicio:fin].copy()

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
                    ref = normalizar_identificador(ref)
                    if ref is None:
                        continue
                    if pd.isna(fecha_disponibilidad):
                        fecha_disponibilidad = None
                    valores.append((id_proveedor, ref, stock, hay_stock, fecha_actualizacion, fecha_disponibilidad, id_marca))
                elif tipo_df == 'fechas':
                    ref, ean, stock, hay_stock, fecha_disponibilidad = row
                    ref = normalizar_identificador(ref)
                    ean = normalizar_identificador(ean)
                    if ref is None:
                        continue
                    if pd.isna(fecha_disponibilidad):
                        fecha_disponibilidad = None
                    valores.append((id_proveedor, ref, ean, stock, hay_stock, fecha_actualizacion, fecha_disponibilidad, id_marca))
                elif tipo_df == 'ean':
                    ean, stock, hay_stock, ref = row
                    ref = normalizar_identificador(ref)
                    ean = normalizar_identificador(ean)
                    if ref is None:
                        logging.warning(
                            "Se omite una fila sin referencia válida"
                        )
                        continue
                    valores.append((id_proveedor, ref, ean, stock, hay_stock, fecha_actualizacion, id_marca))
                else:  # 'referencias'
                    ref, stock, hay_stock = row
                    ref = normalizar_identificador(ref)
                    if ref is None:
                        continue
                    valores.append((id_proveedor, ref, stock, fecha_actualizacion, id_marca, hay_stock))

            # Ejecutar inserciones/actualizaciones en la base de datos
            if not valores:
                logging.warning(
                    "Lote %s sin filas válidas; no se ejecuta SQL",
                    inicio // tamaño_lote + 1,
                )
                pbar.update(len(sub_df))
                continue
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

                commit_con_metricas(conexion_proveedores, metricas)
                print(f"💾 Lote {inicio // tamaño_lote + 1} procesado y guardado.")

            pbar.update(len(sub_df))

        print("✅ Inserciones/actualizaciones completadas.")
        logging.info("Proceso de inserciones/actualizaciones finalizado correctamente.")

    except Exception as e:
        conexion_proveedores.rollback()
        logging.exception("Error al actualizar productos del proveedor %s", id_proveedor)
        raise RuntimeError(
            f"No se pudieron actualizar los productos del proveedor {id_proveedor}"
        ) from e
        
# Función para ver las referencias que no se han actualizado.
def verificar_referencias_no_actualizadas(
    id_proveedor,
    id_marca,
    conexion_proveedores,
    conexion_prestashop,
    prestashop_df,
    proveedor_df,
    metricas=None,
):
    from datetime import datetime

    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    referencias_fichero = conjunto_identificadores_validos(
        proveedor_df["referencia"]
    )
    if "ean" in proveedor_df.columns:
        ean_fichero = conjunto_identificadores_validos(proveedor_df["ean"])
    else:
        ean_fichero = set()
        logging.warning(
            "Columna 'ean' no encontrada en proveedor_df; se usará referencia"
        )

    try:
        # 1️⃣ Obtener referencias y EANs de productos NO actualizados hoy
        with medir_fase(metricas, "Consulta de proveedores"):
            with conexion_proveedores.cursor() as cursor:
                cursor.execute("""
                    SELECT referencia_producto, ean_producto
                    FROM productos
                    WHERE id_proveedor = %s
                      AND id_marca = %s
                      AND DATE(fecha_actualizacion_producto) != %s
                """, (id_proveedor, id_marca, fecha_actual))
                rows = cursor.fetchall()
            referencias_no_actualizadas = [
                (
                    normalizar_identificador(row[0]),
                    normalizar_identificador(row[1]),
                )
                for row in rows
                if normalizar_identificador(row[0]) is not None
            ]

        if not referencias_no_actualizadas:
            logging.info("✅ Todas las referencias están actualizadas hoy.")
        else:
            logging.debug(
                "Referencias no actualizadas hoy (proveedor %s): %s",
                id_proveedor,
                referencias_no_actualizadas,
            )

        logging.debug(f"📄 Referencias en fichero: {referencias_fichero}")
        logging.debug(f"📄 EANs en fichero: {ean_fichero}")

        # 3️⃣ Determinar referencias a poner stock 0
        referencias_a_cero = []

        for ref, ean in referencias_no_actualizadas:
            ref_en_fichero = ref in referencias_fichero
            ean_en_fichero = ean and ean in ean_fichero

            if not ref_en_fichero and not ean_en_fichero:
                referencias_a_cero.append(ref)
                logging.info(f"🔴 {ref} (EAN {ean}) → stock = 0 (no llegó del proveedor y no se actualizó hoy)")

        logging.debug(f"📦 Referencias a poner a 0: {referencias_a_cero}")

        # 4️⃣ Actualizar stock = 0 en tabla productos
        if referencias_a_cero:
            placeholders = ','.join(['%s'] * len(referencias_a_cero))
            query_update = f"""
                UPDATE productos
                SET stock_txt_producto = '0',
                    hay_stock_producto = '0'
                WHERE id_proveedor = %s
                  AND id_marca = %s
                  AND referencia_producto IN ({placeholders})
            """
            with conexion_proveedores.cursor() as cursor:
                logging.debug(f"🚀 Ejecutando UPDATE stock 0 para: {referencias_a_cero}")
                cursor.execute(query_update, (id_proveedor, id_marca, *referencias_a_cero))
                commit_con_metricas(conexion_proveedores, metricas)
                logging.info(f"🔻 {len(referencias_a_cero)} referencias actualizadas a stock = 0")

    except Exception as e:
        conexion_proveedores.rollback()
        logging.exception(
            "Error durante la verificación de referencias del proveedor %s",
            id_proveedor,
        )
        raise RuntimeError(
            f"No se pudieron verificar referencias del proveedor {id_proveedor}"
        ) from e

    # La reactivación global que existía aquí se difiere expresamente a
    # reactivar_atributos_con_stock(), que limita candidatos al proveedor.

    # 7️⃣ Resto de lógica: Desactivar productos simples si no tienen stock
    try:
        productos_simples_sin_stock = prestashop_df[
            (prestashop_df['source'] == 'ps_product') &
            (prestashop_df['quantity'] <= 0)
        ]

        referencias_a_verificar = []
        eans_a_verificar = []
        id_product_map = dict()
        ean_por_referencia = {}

        for _, row in productos_simples_sin_stock.iterrows():
            ref = normalizar_identificador(row['reference'])
            ean = normalizar_identificador(row['ean13'])

            ref_en_fichero = ref is not None and ref in referencias_fichero
            ean_en_fichero = ean is not None and ean in ean_fichero

            if ref is not None and not ref_en_fichero and not ean_en_fichero:
                referencias_a_verificar.append(ref)
                if ean:
                    eans_a_verificar.append(ean)
                    ean_por_referencia[ref] = ean
                id_product_map[ref] = row['id_product']

        productos_a_desactivar = []

        if referencias_a_verificar or eans_a_verificar:
            query_conditions = []
            params = []

            if referencias_a_verificar:
                placeholders_refs = ', '.join(['%s'] * len(referencias_a_verificar))
                query_conditions.append(f"referencia_producto IN ({placeholders_refs})")
                params.extend(referencias_a_verificar)

            if eans_a_verificar:
                placeholders_eans = ', '.join(['%s'] * len(eans_a_verificar))
                query_conditions.append(f"ean_producto IN ({placeholders_eans})")
                params.extend(eans_a_verificar)

            query_stock = f"""
                SELECT referencia_producto, ean_producto, hay_stock_producto
                FROM productos
                WHERE id_proveedor = %s
                  AND ({' OR '.join(query_conditions)})
            """
            params = [id_proveedor] + params

            referencias_existentes = set()
            referencias_con_stock = set()

            eans_existentes = set()
            eans_con_stock = set()

            with conexion_proveedores.cursor() as cursor:
                cursor.execute(query_stock, params)
                rows = cursor.fetchall()
                for ref_db, ean_db, hay_stock in rows:
                    ref_db = normalizar_identificador(ref_db)
                    ean_db = normalizar_identificador(ean_db)
                    if ref_db is not None:
                        referencias_existentes.add(ref_db)
                        if hay_stock and int(hay_stock) > 0:
                            referencias_con_stock.add(ref_db)
                    if ean_db is not None:
                        eans_existentes.add(ean_db)
                        if hay_stock and int(hay_stock) > 0:
                            eans_con_stock.add(ean_db)

            for ref in referencias_a_verificar:
                ean = ean_por_referencia.get(ref)
                existe = (
                    ref in referencias_existentes
                    or (ean is not None and ean in eans_existentes)
                )
                if existe:
                    tiene_stock = (
                        ref in referencias_con_stock
                        or (ean is not None and ean in eans_con_stock)
                    )
                    if not tiene_stock:
                        id_product = id_product_map.get(ref)
                        if id_product:
                            productos_a_desactivar.append(id_product)
                            logging.info(f"🚫 Producto simple {ref} sin stock en proveedor → se va a desactivar.")
                    else:
                        logging.info(f"✅ Producto simple {ref} se mantiene activo porque tiene stock en proveedor.")
                else:
                    logging.info(f"ℹ Producto simple {ref} no existe en la tabla productos del proveedor → NO SE TOCA.")

        if productos_a_desactivar:
            placeholders = ','.join(['%s'] * len(productos_a_desactivar))
            with conexion_prestashop.cursor() as cursor:
                cursor.execute(f"""
                    UPDATE ps_product
                    SET active = 0
                    WHERE id_product IN ({placeholders})
                """, productos_a_desactivar)

                cursor.execute(f"""
                    UPDATE ps_product_shop
                    SET active = 0
                    WHERE id_product IN ({placeholders})
                """, productos_a_desactivar)

                commit_con_metricas(conexion_prestashop, metricas)

            for pid in productos_a_desactivar:
                logging.info(f"🚫 Producto simple desactivado automáticamente: ID {pid}")

    except Exception as e:
        conexion_prestashop.rollback()
        logging.exception(
            "Error al desactivar productos simples del proveedor %s",
            id_proveedor,
        )
        raise RuntimeError(
            f"No se pudieron desactivar productos simples del proveedor {id_proveedor}"
        ) from e

def _cerrar_ftp(ftp):
    if ftp is None:
        return
    try:
        ftp.quit()
    except Exception:
        try:
            ftp.close()
        except Exception:
            pass


def _es_error_ftp_transitorio(error):
    if isinstance(
        error,
        (
            ConnectionRefusedError,
            ConnectionResetError,
            TimeoutError,
            socket.timeout,
            EOFError,
            error_temp,
        ),
    ):
        return True
    return isinstance(error, OSError) and getattr(error, "winerror", None) == 10061


def _servidor_exige_ftps(error):
    mensaje = str(error).casefold()
    return (
        isinstance(error, error_perm)
        and mensaje.lstrip().startswith("550")
        and "ssl/tls required" in mensaje
    )


def _descargar_ftp_estandar(config, intentos=3, pausas=(2, 5)):
    ultimo_error = None
    for intento in range(1, intentos + 1):
        ftp = None
        etapa = "conexión de control"
        print(f"FTP estándar intento {intento}/{intentos}...")
        try:
            ftp = FTP()
            ftp.timeout = 300
            ftp.connect(config["ftp_server"], config["ftp_port"])
            etapa = "autenticación"
            ftp.login(config["ftp_user"], config["ftp_pass"])
            ftp.set_pasv(True)
            etapa = "transferencia"
            with BytesIO() as memory_file:
                ftp.retrbinary(
                    f"RETR {config['fichero_configuracion']}",
                    memory_file.write,
                )
                archivo_bytes = memory_file.getvalue()
            print("Archivo descargado correctamente mediante FTP estándar.")
            return archivo_bytes, intento
        except Exception as error:
            ultimo_error = error
            if _servidor_exige_ftps(error) or not _es_error_ftp_transitorio(error):
                raise
            print(
                f"FTP intento {intento}/{intentos} fallido durante {etapa}: "
                f"{error}"
            )
            logger_funciones_especificas.info(
                "FTP intento %s/%s fallido durante %s: %s",
                intento,
                intentos,
                etapa,
                error,
            )
            if intento < intentos:
                pausa = pausas[intento - 1]
                print(f"Reintentando en {pausa} segundos...")
                time.sleep(pausa)
        finally:
            _cerrar_ftp(ftp)
    raise ultimo_error


def _descargar_ftps(config):
    ftp = None
    try:
        ftp = FTP_TLS()
        ftp.timeout = 300
        ftp.connect(config["ftp_server"], config["ftp_port"])
        ftp.login(config["ftp_user"], config["ftp_pass"])
        ftp.prot_p()
        ftp.set_pasv(True)
        with BytesIO() as memory_file:
            ftp.retrbinary(
                f"RETR {config['fichero_configuracion']}",
                memory_file.write,
            )
            return memory_file.getvalue()
    finally:
        _cerrar_ftp(ftp)


def _descargar_sftp(config):
    ssh_client = None
    sftp = None
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(
            config["ftp_server"],
            config["ftp_port"],
            config["ftp_user"],
            config["ftp_pass"],
        )
        sftp = ssh_client.open_sftp()
        with BytesIO() as memory_file:
            sftp.getfo(config["fichero_configuracion"], memory_file)
            return memory_file.getvalue()
    finally:
        if sftp is not None:
            sftp.close()
        if ssh_client is not None:
            ssh_client.close()


def descargar_y_procesar_archivo(config, excel_config, id_proveedor, conexion_proveedores):
    archivo_bytes = None
    try:
        if "ftp_server" in config and config["ftp_server"] is not None:
            puerto = int(config["ftp_port"])
            if puerto == 22:
                try:
                    archivo_bytes = _descargar_sftp(config)
                    print("Archivo Excel descargado exitosamente desde SFTP.")
                except Exception as sftp_error:
                    print(f"Fallo la descarga SFTP: {sftp_error}")
                    logger_funciones_especificas.info(
                        "Fallo la descarga SFTP: %s", sftp_error
                    )
            elif id_proveedor == FTPS_PROVIDER_ID:
                try:
                    archivo_bytes = _descargar_ftps(config)
                    print("Archivo Excel descargado exitosamente mediante FTPS.")
                except Exception as ftps_error:
                    print(f"Fallo la descarga FTPS: {ftps_error}")
                    logger_funciones_especificas.info(
                        "Fallo la descarga FTPS: %s", ftps_error
                    )
            else:
                try:
                    archivo_bytes, _intentos = _descargar_ftp_estandar(config)
                except Exception as ftp_error:
                    if _servidor_exige_ftps(ftp_error):
                        print(
                            "El servidor exige SSL/TLS; intentando FTPS explícito..."
                        )
                        try:
                            archivo_bytes = _descargar_ftps(config)
                            print(
                                "Archivo Excel descargado exitosamente usando "
                                "FTPS explícito."
                            )
                        except Exception as ftps_error:
                            print(f"Fallo la descarga FTPS: {ftps_error}")
                            logger_funciones_especificas.info(
                                "Fallo la descarga FTPS: %s", ftps_error
                            )
                    else:
                        print(f"Fallo definitivo de la descarga FTP: {ftp_error}")
                        logger_funciones_especificas.info(
                            "Fallo definitivo de la descarga FTP: %s", ftp_error
                        )

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
                response = requests.get(
                    config["http_configuracion"],
                    headers=headers,
                    allow_redirects=True,
                    timeout=300,
                )

                if response.status_code == 200:
                    # Descarga el archivo Excel en memoria
                    archivo_bytes = response.content
                    print(f"Archivo Excel '{nombre_archivo}' descargado exitosamente desde HTTP.")

                    # El procesamiento se realiza una sola vez desde main para
                    # medir por separado descarga, lectura y normalización.
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
