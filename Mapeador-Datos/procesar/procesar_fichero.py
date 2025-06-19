import pandas as pd
from io import BytesIO
import openpyxl
from deep_translator import GoogleTranslator
from bd.bd import DatabaseConnector
import logging
from functools import lru_cache

# Configuración de logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
file_handler = logging.FileHandler('servidor.log', encoding='utf-8')
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(file_handler)
logger = logging.getLogger(__name__)


def letra_a_numero(letra):
    """Convierte una letra de columna Excel (A, B, C, etc.) a su índice numérico (0, 1, 2, etc.)"""
    resultado = 0
    for i, c in enumerate(reversed(letra.upper())):
        resultado += (ord(c) - ord('A') + 1) * (26 ** i)
    return resultado - 1

# Definir la función global decorada con @lru_cache
@lru_cache(maxsize=1000)
def traducir_texto_con_cache(texto_str):
    """
    Traduce el texto usando Google Translator con caché global.
    """
    try:
        translator = GoogleTranslator(source='auto', target='es')
        return translator.translate(texto_str)
    except Exception as e:
        logger.warning(f"Error al traducir '{texto_str}': {str(e)}")
        return texto_str  # Devuelve el texto original en caso de error
    
# Ver el uso de la caché
logger.info(f"Caché hits: {traducir_texto_con_cache.cache_info().hits}")
logger.info(f"Caché misses: {traducir_texto_con_cache.cache_info().misses}")

# Definir diccionario de plantillas
plantillas = {
    'POLISPORT': {
        'REF': 'B',           # Part Number
        'NOMBRE': 'F',        # Description
        'COLOR': 'G',         # Color
        'CATEGORIA': 'C',     # Item Group
        'EAN': 'L',          # EAN
        'P.COMPRA': 'H',     # Your price
        'PVP S/IVA': 'J',    # MSRP Without VAT
        'PVP +IVA': 'K',     # MSRP With VAT
        'PESO': 'M',         # Weight
        'COD NC': 'V',       # HS Code
        'ANCHURA': 'P',      # Packaging Width
        'ALTURA': 'Q',       # Packaging Height
        'PROFUNDIDAD': 'O',  # Packaging Length
        'IMG': 'S'           # Photo
    },
    'FOX': {
        'REF MADRE': 'B',
        'NOMBRE': 'C',
        'COLOR': 'H',
        'CATEGORIA': 'F',
        'EAN': 'I',
        'P.COMPRA': 'N',
        'PVP +IVA': 'O',
        'TALLA': 'J'
    },
    'ACERBIS': {
        'REF MADRE': 'A',
        'REF': 'A',
        'NOMBRE': 'D',
        'PVP S/IVA': 'B',
        'PVP +IVA': 'C',
        'EAN': 'E'
    },
    'FXR': {
        'REF MADRE': 'C',
        'GENERO': 'Q',
        'TALLA': 'G',
        'REF': 'D',
        'P.COMPRA': 'I',
        'PVP S/IVA': 'J',
        'CATEGORIA': 'N',
        'NOMBRE': 'A'
    },
    'PROX': {
        'REF MADRE': 'B',
        'REF': 'B',
        'NOMBRE': 'C',
        'PVP S/IVA': 'F',
        'P.COMPRA': 'H',
        'CATEGORIA': 'E'
    },
    'UFO': {
        'REF': 'A',
        'EAN': 'B',
        'CATEGORIA': 'C',
        'NOMBRE': 'D',
        'GAMA': 'D',
        'COLOR': 'E',
        'TALLA': 'F',
        'P.COMPRA': 'G',
        'PVP S/IVA': 'H',
        'PVP +IVA': 'I'
    },
    'UFO PLASTICS': {
        'REF': 'A',
        'NOMBRE': 'H',
        'TIPO PRODUCT': 'G',
        'MARCA MOTO': 'C',
        'PVP S/IVA': 'K',
        'PVP +IVA': 'L',
        'COLOR': 'I',
        'EAN': 'B',
        'AÑO DESDE': 'E',
        'AÑO HASTA': 'F',
        'MODELO': 'D'
    }
}

def procesar_referencias_no_encontradas(df_mapeado, referencias_no_encontradas, plantilla_seleccionada):
    """
    Procesa las referencias no encontradas y las retorna en la plantilla provisional.
    """
    try:
        # Inicializar traductor
        translator = GoogleTranslator(source='auto', target='es')

        # Función para formatear precios
        def formatear_precio(precio):
            if precio is not None and str(precio).strip() and str(precio).strip().lower() != 'nan':
                try:
                    precio_limpio = str(precio).replace('€', '').replace(',', '.').strip()
                    return str(round(float(precio_limpio), 2)).replace('.', ',')
                except ValueError as e:
                    logger.warning(f"Error al formatear precio '{precio}': {str(e)}")
                    return ''
            return ''

        def traducir_seguro(texto):
            """
            Traduce el texto usando traducir_texto_con_cache para manejar valores nulos o vacíos.
            """
            if pd.isna(texto) or str(texto).strip() == '':
                return texto

            texto_str = str(texto).strip()
            return traducir_texto_con_cache(texto_str)

        # Verificar si la plantilla seleccionada tiene los campos para concatenar
        campos_para_concatenar = ['MARCA MOTO', 'MODELO', 'AÑO DESDE', 'AÑO HASTA']
        concatenar_nombre = all(campo in plantillas[plantilla_seleccionada] for campo in campos_para_concatenar)

        # Crear DataFrame con columnas de la plantilla provisional
        columnas_provisional = [
            'REF MADRE', 'REF', 'EAN', 'NOMBRE', 'TIPO PRODUCT', 'P.COMPRA', 
            'PVP S/IVA', 'PVP +IVA', 'COLOR', 'CATEGORIA', 'PESO', 'COD NC', 
            'ANCHURA', 'ALTURA', 'PROFUNDIDAD', 'GENERO', 'EDAD', 'TALLA', 
            'TEMPORADA', 'GAMA', 'MARCA', 'IMG'
        ]
        df_provisional = pd.DataFrame(columns=columnas_provisional)

        # Filtrar referencias no encontradas
        df_no_encontradas = df_mapeado[df_mapeado['REF'].isin(referencias_no_encontradas)].copy()

        if not df_no_encontradas.empty:
            # Procesar cada fila
            for _, fila in df_no_encontradas.iterrows():
                nueva_fila = pd.Series('', index=columnas_provisional)

                # Copiar datos básicos
                for columna in columnas_provisional:
                    if columna in fila:
                        nueva_fila[columna] = fila[columna]

                # Concatenar "MARCA MOTO", "MODELO", "AÑO DESDE", "AÑO HASTA" en NOMBRE si aplica
                if concatenar_nombre:
                    partes = []
                    for campo in ['NOMBRE', 'MARCA MOTO', 'MODELO']:
                        valor = fila.get(campo)
                        if pd.notna(valor) and valor != '':
                            partes.append(str(valor).strip())

                    # Concatenar años solo si ambos existen
                    ano_desde = fila.get('AÑO DESDE')
                    ano_hasta = fila.get('AÑO HASTA')
                    if pd.notna(ano_desde) and pd.notna(ano_hasta) and ano_desde != '' and ano_hasta != '':
                        partes.append(f"{str(ano_desde).strip()}-{str(ano_hasta).strip()}")

                    # Construir el nombre concatenado
                    nueva_fila['NOMBRE'] = ' '.join(partes)

                # Traducir las columnas especificadas
                columnas_a_traducir = ['NOMBRE', 'TIPO PRODUCT', 'COLOR', 'CATEGORIA']
                for columna in columnas_a_traducir:
                    if columna in nueva_fila and pd.notna(nueva_fila[columna]):
                        nueva_fila[columna] = traducir_seguro(nueva_fila[columna])

                # Formatear precios
                nueva_fila['P.COMPRA'] = formatear_precio(fila.get('P.COMPRA', ''))
                nueva_fila['PVP S/IVA'] = formatear_precio(fila.get('PVP S/IVA', ''))
                nueva_fila['PVP +IVA'] = formatear_precio(fila.get('PVP +IVA', ''))

                # Añadir la nueva fila al DataFrame provisional
                df_provisional = pd.concat([df_provisional, nueva_fila.to_frame().T], ignore_index=True)

        return df_provisional if not df_provisional.empty else None

    except Exception as e:
        logger.error(f"Error procesando referencias no encontradas: {str(e)}")
        raise

def consultar_ambar(datos_mapeados_stream):
    """
    Consulta las bases de datos con los datos mapeados.
    """
    try:
        def formatear_precio(precio):
            if precio is not None and str(precio).strip() and str(precio).strip().lower() != 'nan':
                return str(round(float(str(precio).replace(',', '.')), 2)).replace('.', ',')
            return ''
            
        # Leer DataFrame mapeado
        df_mapeado = pd.read_excel(datos_mapeados_stream, dtype=str)
        
        # Obtener referencias y EANs
        referencias_originales = []
        if 'REF' in df_mapeado.columns and not df_mapeado['REF'].isna().all():
            referencias_originales = df_mapeado['REF'].dropna().tolist()
            referencias_originales = [str(ref).strip() for ref in referencias_originales]
        elif 'REF MADRE' in df_mapeado.columns and not df_mapeado['REF MADRE'].isna().all():
            referencias_originales = df_mapeado['REF MADRE'].dropna().tolist()
            referencias_originales = [str(ref).strip() for ref in referencias_originales]

        eans_originales = df_mapeado['EAN'].dropna().tolist() if 'EAN' in df_mapeado.columns else []
        eans_originales = [str(ean).strip() for ean in eans_originales]
        
        # Definir columnas finales
        columnas_finales = [
            'REF MADRE', 'EAN PRODUCT', 'NOMBRE (SIN TALLA)', 'MARCA', 'PVP S/IVA', 
            'ID IVA', 'PRODUCT CATEGORIA', 'CATEGORIAS', 'CARACTERISTICAS', 'GAMA',
            'FILTROS', 'PRODUCT', 'META-DESCRIPCION', 'URL IMGs', 'ELIMINAR IMG',
            'DESCRIPCION LARGA', 'ANCHURA', 'ALTURA', 'PROFUNDIDAD', 'PESO PRODUCT',
            'ID DISPONIBILIDAD', 'ACTIVO', 'DISP. PEDIDOS', 'TEMPORADA',
            'TALLAS', 'GENERO', 'EDAD', 'COLOR', 'REF MADRE COMBI', 'REF COMBI',
            'EAN COMBI', 'NOMBRE COMBI:TIPO', '|', 'REF', 'NOMBRE', 'PROVEEDOR', 'FAMILIA',
            'SUBFAMILIA', 'P.COMPRA', 'PVP (+IVA)', 'EAN', 'ALT 1', 'ALT 2', 'ALT 3',
            'UNIDAD', 'LOTE', 'PESO', 'CODNC', 'LIBRE1=MARCA', 'LIBRE2=TEMPORADA',
            'LIBRE3=PRODUCTO', 'LIBRE4=GAMA/MODELO', 'LIBRE5=GRUPO', 'LIBRE6=EDAD',
            'P.COMPRA (Excel)', 'PVP S/IVA (Excel)', 'PVP (+IVA) (Excel)'
        ]
        
        todas_filas = []  
        referencias_encontradas = {}
        referencias_no_encontradas = []
        resultados_dict = {}
        mapeo_referencias = {}
        
        # Conectar a base de datos Ambar
        db = DatabaseConnector()
        ambar_conn = db.connect_to_ambar()
        
        if ambar_conn:
            cursor = ambar_conn.cursor()
            
            # Buscar por referencias
            if referencias_originales:
                referencias_str = "','".join(referencias_originales)
                query = f"""
                    SELECT Artículo, [Descripción], Familia, Proveedor, PVPGralSinIVAEu, 
                           PVPGralConIVAEu, PrecioUltCompraEu, [CódigoBarras], PesoBruto, 
                           SubFamilia, CodigoNC, Libre1, Libre2, Libre3, Libre4, Libre5, Libre6
                    FROM [Artículos] 
                    WHERE [Artículo] IN ('{referencias_str}')
                """
                cursor.execute(query)
                resultados = cursor.fetchall()
                
                for resultado in resultados:
                    ref_ambar = str(resultado[0])
                    resultados_dict[ref_ambar] = resultado
                    referencias_encontradas[ref_ambar] = ref_ambar

                referencias_no_encontradas = [ref for ref in referencias_originales if ref not in referencias_encontradas]
            
            # Buscar por EAN si es necesario
            if (not referencias_originales or referencias_no_encontradas) and eans_originales:
                eans_str = "','".join(eans_originales)
                query_ean = f"""
                    SELECT Artículo, [Descripción], Familia, Proveedor, PVPGralSinIVAEu, 
                           PVPGralConIVAEu, PrecioUltCompraEu, [CódigoBarras], PesoBruto, 
                           SubFamilia, CodigoNC, Libre1, Libre2, Libre3, Libre4, Libre5, Libre6
                    FROM [Artículos] 
                    WHERE [CódigoBarras] IN ('{eans_str}')
                """
                cursor.execute(query_ean)
                resultados_ean = cursor.fetchall()
                
                for resultado in resultados_ean:
                    ref_ambar = str(resultado[0])
                    ean_ambar = str(resultado[7])
                    
                    if ref_ambar not in resultados_dict:
                        resultados_dict[ref_ambar] = resultado
                    
                    filas_con_ean = df_mapeado[df_mapeado['EAN'] == ean_ambar]
                    for _, fila in filas_con_ean.iterrows():
                        ref_original = fila.get('REF MADRE' if 'REF MADRE' in df_mapeado.columns else 'REF', '')
                        if ref_original and ref_original in referencias_no_encontradas:
                            referencias_encontradas[ref_original] = ref_ambar
                            referencias_no_encontradas.remove(ref_original)
                        elif not ref_original:
                            referencias_encontradas[ean_ambar] = ref_ambar
            
            mapeo_referencias.update(referencias_encontradas)
            cursor.close()
        
        # Conectar a Prestashop y obtener información adicional
        prestashop_conn = db.connect_to_prestashop()
        resultados_product = {}
        resultados_attribute = {}
        resultados_features = {}
        
        if prestashop_conn and mapeo_referencias:
            cursor_ps = prestashop_conn.cursor()
            referencias_str = "','".join(mapeo_referencias.values())
            
            # Consultar productos
            query_product = f"""
                SELECT p.reference, p.ean13, pl.name AS product_name,
                       m.name AS brand_name, p.price
                FROM ps_product p
                LEFT JOIN ps_product_lang pl ON p.id_product = pl.id_product
                LEFT JOIN ps_manufacturer m ON p.id_manufacturer = m.id_manufacturer
                WHERE p.reference IN ('{referencias_str}')
                AND pl.id_lang = 1
            """
            cursor_ps.execute(query_product)
            resultados_product = {row[0]: {
                'ean': str(row[1]),
                'nombre': str(row[2]),
                'marca': str(row[3]),
                'precio': row[4]
            } for row in cursor_ps.fetchall()}
            
            # Consultar atributos
            query_attribute = f"""
                SELECT pa.reference, pa.ean13, pl.name AS product_name,
                       m.name AS brand_name, p.reference AS ref_madre,
                       p.price + IFNULL(pa.price, 0) as price
                FROM ps_product_attribute pa
                JOIN ps_product p ON pa.id_product = p.id_product
                LEFT JOIN ps_product_lang pl ON p.id_product = pl.id_product
                LEFT JOIN ps_manufacturer m ON p.id_manufacturer = m.id_manufacturer
                WHERE pa.reference IN ('{referencias_str}')
                AND pl.id_lang = 1
            """
            cursor_ps.execute(query_attribute)
            resultados_attribute = {row[0]: {
                'ean': str(row[1]),
                'nombre': str(row[2]),
                'marca': str(row[3]),
                'ref_madre': str(row[4]),
                'precio': row[5]
            } for row in cursor_ps.fetchall()}
            
            # Consultar características
            query_features = f"""
                SELECT COALESCE(pa.reference, p.reference) as reference,
                       fvl.value AS feature_value
                FROM ps_product p
                LEFT JOIN ps_product_attribute pa ON p.id_product = pa.id_product
                JOIN ps_feature_product fp ON p.id_product = fp.id_product
                JOIN ps_feature_lang fl ON fp.id_feature = fl.id_feature
                JOIN ps_feature_value_lang fvl ON fp.id_feature_value = fvl.id_feature_value
                WHERE fl.name = 'Productos'
                AND fl.id_lang = 1 
                AND fvl.id_lang = 1
                AND (p.reference IN ('{referencias_str}') OR pa.reference IN ('{referencias_str}'))
            """
            cursor_ps.execute(query_features)
            resultados_features = {str(row[0]): str(row[1]) for row in cursor_ps.fetchall()}
            
            cursor_ps.close()

        # Procesar referencias encontradas
        referencias_a_procesar = referencias_originales if referencias_originales else eans_originales
        
        for ref_original in referencias_a_procesar:
            if ref_original in referencias_encontradas:
                nueva_fila = {col: '' for col in columnas_finales}
                ref_busqueda = mapeo_referencias.get(ref_original, ref_original)
                datos_excel = None
                
                # Obtener datos del Excel original
                if 'REF MADRE' in df_mapeado.columns:
                    datos_excel = df_mapeado[df_mapeado['REF MADRE'] == ref_original].iloc[0] if any(df_mapeado['REF MADRE'] == ref_original) else None
                else:
                    datos_excel = df_mapeado[df_mapeado['REF'] == ref_original].iloc[0] if any(df_mapeado['REF'] == ref_original) else None
                    
                # Procesar datos de Ambar
                datos_ambar = resultados_dict.get(ref_busqueda) if ref_busqueda in resultados_dict else None

                if datos_ambar:
                    #logger.debug(f"Datos Ambar para {ref_busqueda}: {datos_ambar}")

                    nueva_fila['REF'] = str(ref_busqueda)

                    # ---------------------------------------------------
                    # 1) Valores que llegan en el Excel (si los hay)
                    # ---------------------------------------------------
                    p_compra_excel    = formatear_precio(datos_excel.get('P.COMPRA', ''))    if datos_excel is not None else ''
                    pvp_sin_iva_excel = formatear_precio(datos_excel.get('PVP S/IVA', ''))   if datos_excel is not None else ''
                    pvp_con_iva_excel = formatear_precio(datos_excel.get('PVP +IVA', ''))    if datos_excel is not None else ''

                    # ---------------------------------------------------
                    # 2) Guardar valores del Excel en columnas informativas
                    # ---------------------------------------------------
                    nueva_fila['P.COMPRA (Excel)']     = p_compra_excel
                    nueva_fila['PVP S/IVA (Excel)']    = pvp_sin_iva_excel
                    nueva_fila['PVP (+IVA) (Excel)']   = pvp_con_iva_excel

                    # ---------------------------------------------------
                    # 3) SIEMPRE escribir los precios de Ambar en columnas principales
                    # ---------------------------------------------------
                    nueva_fila['P.COMPRA']    = formatear_precio(datos_ambar[6])  # PrecioUltCompraEu
                    nueva_fila['PVP S/IVA']   = formatear_precio(datos_ambar[4])  # PVPGralSinIVAEu
                    nueva_fila['PVP (+IVA)']  = formatear_precio(datos_ambar[5])  # PVPGralConIVAEu

                    # ---------------------------------------------------
                    # 4) Otros datos de Ambar
                    # ---------------------------------------------------
                    nueva_fila['NOMBRE']             = str(datos_ambar[1])
                    nueva_fila['FAMILIA']            = str(datos_ambar[2])
                    nueva_fila['PROVEEDOR']          = str(datos_ambar[3])
                    nueva_fila['EAN']                = str(datos_ambar[7])
                    nueva_fila['PESO']               = str(datos_ambar[8])
                    nueva_fila['SUBFAMILIA']         = str(datos_ambar[9])
                    nueva_fila['CODNC']              = str(datos_ambar[10]).replace(' ', '')
                    nueva_fila['LIBRE1=MARCA']       = str(datos_ambar[11])
                    nueva_fila['LIBRE2=TEMPORADA']   = str(datos_ambar[12])
                    nueva_fila['LIBRE3=PRODUCTO']    = str(datos_ambar[13])
                    nueva_fila['LIBRE4=GAMA/MODELO'] = str(datos_ambar[14])
                    nueva_fila['LIBRE5=GRUPO']       = str(datos_ambar[15])
                    nueva_fila['LIBRE6=EDAD']        = str(datos_ambar[16])
                
                # Procesar datos de Prestashop
                if ref_busqueda in resultados_product:
                    nueva_fila['REF MADRE'] = str(ref_busqueda)
                    nueva_fila['EAN PRODUCT'] = str(resultados_product[ref_busqueda]['ean'])
                    nueva_fila['NOMBRE (SIN TALLA)'] = str(resultados_product[ref_busqueda]['nombre'])
                    nueva_fila['MARCA'] = str(resultados_product[ref_busqueda]['marca'])
                    nueva_fila['PVP S/IVA'] = formatear_precio(resultados_product[ref_busqueda]['precio'])
                    nueva_fila['|'] = '|'
                elif ref_busqueda in resultados_attribute:
                    nueva_fila['REF COMBI'] = str(ref_busqueda)
                    nueva_fila['EAN COMBI'] = str(resultados_attribute[ref_busqueda]['ean'])
                    nueva_fila['REF MADRE'] = str(resultados_attribute[ref_busqueda]['ref_madre'])
                    nueva_fila['NOMBRE (SIN TALLA)'] = str(resultados_attribute[ref_busqueda]['nombre'])
                    nueva_fila['MARCA'] = str(resultados_attribute[ref_busqueda]['marca'])
                    nueva_fila['PVP S/IVA'] = formatear_precio(resultados_attribute[ref_busqueda]['precio'])
                    nueva_fila['|'] = '|'
                
                # Añadir características de Prestashop
                if ref_busqueda in resultados_features:
                    nueva_fila['PRODUCT'] = str(resultados_features[ref_busqueda])
                
                # Añadir datos del Excel original
                if datos_excel is not None:
                    if pd.notna(datos_excel.get('IMG')):
                        nueva_fila['URL IMGs'] = str(datos_excel['IMG'])
                    if pd.notna(datos_excel.get('ANCHURA')):
                        nueva_fila['ANCHURA'] = str(datos_excel['ANCHURA'])
                    if pd.notna(datos_excel.get('ALTURA')):
                        nueva_fila['ALTURA'] = str(datos_excel['ALTURA'])
                    if pd.notna(datos_excel.get('PROFUNDIDAD')):
                        nueva_fila['PROFUNDIDAD'] = str(datos_excel['PROFUNDIDAD'])
                
                todas_filas.append(nueva_fila)

        # Crear DataFrame con referencias encontradas
        if todas_filas:
            df_final = pd.DataFrame(todas_filas)
            df_final = df_final.reindex(columns=columnas_finales)
            df_final = df_final.fillna('')
            df_final = df_final.replace({'nan': '', 'None': '', None: ''})
            df_final = df_final.astype(str)
            df_final = df_final.replace({'nan': '', 'None': ''})
        else:
            df_final = pd.DataFrame(columns=columnas_finales)

        # Cerrar conexiones
        db.close_connections()

        # Crear BytesIO para el archivo principal
        output_encontradas = BytesIO()
        with pd.ExcelWriter(output_encontradas, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False)
        output_encontradas.seek(0)

        # Procesar referencias no encontradas si existen
        output_no_encontradas = None
        if referencias_no_encontradas:
            df_no_encontradas = procesar_referencias_no_encontradas(df_mapeado, referencias_no_encontradas, plantilla_seleccionada="UFO PLASTICS")
            if df_no_encontradas is not None:
                output_no_encontradas = BytesIO()
                with pd.ExcelWriter(output_no_encontradas, engine='openpyxl') as writer:
                    df_no_encontradas.to_excel(writer, index=False)
                output_no_encontradas.seek(0)

        return {
            'success': True,
            'file_data': output_encontradas,
            'not_found_data': output_no_encontradas
        }

    except Exception as e:
        logger.error(f"Error en consulta_ambar: {str(e)}")
        return {'success': False, 'error': str(e)}

def mapear_excel_a_plantilla(file_stream, nombre_plantilla, mapeo_dict=None):
    """
    Mapea un archivo Excel según la plantilla o el mapeo manual.
    """
    try:
        logger.info(f"Iniciando mapeo - Plantilla: {nombre_plantilla}, ¿Mapeo manual? {bool(mapeo_dict)}")

        if not nombre_plantilla and not mapeo_dict:
            return {'success': False, 'error': 'Se requiere plantilla o mapeo manual'}

        try:
            df_entrada = pd.read_excel(file_stream, dtype=str)
            logger.info("Archivo Excel leído correctamente")
        except Exception as e:
            error_msg = f"Error al leer el archivo Excel: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        datos_salida = {}

        # Si hay mapeo manual, renombrar y usar directamente
        if mapeo_dict:
            try:
                inverso = {v: k for k, v in mapeo_dict.items()}
                df_entrada.rename(columns=inverso, inplace=True)
                logger.info(f"Columnas renombradas con mapeo personalizado: {inverso}")

                for campo in mapeo_dict.keys():
                    try:
                        datos_salida[campo] = df_entrada[campo]
                        logger.debug(f"Campo mapeado: {campo}")
                    except KeyError:
                        logger.warning(f"Columna '{campo}' no encontrada tras renombrar")
                        datos_salida[campo] = pd.Series([''] * len(df_entrada))
            except Exception as e:
                logger.error(f"Error aplicando mapeo manual: {str(e)}")
                return {'success': False, 'error': f'Error en mapeo manual: {str(e)}'}

        # Si no hay mapeo manual, usar plantilla
        elif nombre_plantilla:
            if nombre_plantilla not in plantillas:
                return {'success': False, 'error': f"Plantilla '{nombre_plantilla}' no encontrada"}
            mapeo_columnas = plantillas[nombre_plantilla]
            logger.debug(f"Usando plantilla: {mapeo_columnas}")

            for columna_destino, letra_columna in mapeo_columnas.items():
                try:
                    indice = letra_a_numero(letra_columna)
                    if indice < len(df_entrada.columns):
                        datos_salida[columna_destino] = df_entrada.iloc[:, indice]
                        logger.debug(f"Mapeada columna {letra_columna} a {columna_destino}")
                    else:
                        logger.warning(f"Columna '{letra_columna}' fuera de rango")
                        datos_salida[columna_destino] = pd.Series([''] * len(df_entrada))
                except Exception as e:
                    logger.error(f"Error al mapear columna {columna_destino}: {str(e)}")
                    datos_salida[columna_destino] = pd.Series([''] * len(df_entrada))

        # Crear DataFrame con los datos mapeados
        df_salida = pd.DataFrame(datos_salida)

        # Exportar a BytesIO
        datos_mapeados = BytesIO()
        with pd.ExcelWriter(datos_mapeados, engine='openpyxl') as writer:
            df_salida.to_excel(writer, index=False)
        datos_mapeados.seek(0)

        # Llamar a consulta Ambar
        try:
            logger.info("Iniciando consulta a Ambar...")
            resultado = consultar_ambar(datos_mapeados)

            if resultado['success']:
                logger.info("Proceso completado exitosamente")
                return resultado
            else:
                logger.error(f"Error en consulta_ambar: {resultado.get('error')}")
                return resultado

        except Exception as e:
            error_msg = f"Error en la consulta a Ambar: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

    except Exception as e:
        error_msg = f"Error general en el procesamiento: {str(e)}"
        logger.error(error_msg)
        return {'success': False, 'error': error_msg}

if __name__ == "__main__":
    logger.info("Este script debe ser importado como módulo")