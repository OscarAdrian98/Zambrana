import pandas as pd
from io import BytesIO
import openpyxl
from deep_translator import GoogleTranslator
from bd.bd import DatabaseConnector
import logging

# Configuración de logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def letra_a_numero(letra):
    """Convierte una letra de columna Excel (A, B, C, etc.) a su índice numérico (0, 1, 2, etc.)"""
    resultado = 0
    for i, c in enumerate(reversed(letra.upper())):
        resultado += (ord(c) - ord('A') + 1) * (26 ** i)
    return resultado - 1

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
    }
}

def procesar_referencias_no_encontradas(df_mapeado, referencias_no_encontradas):
    """
    Procesa las referencias no encontradas y las retorna en un DataFrame separado.
    """
    try:
        
        # Función para formatear precios
        def formatear_precio(precio):
            if precio is not None and str(precio).strip() and str(precio).strip().lower() != 'nan':
                try:
                    # Eliminar símbolos de moneda y espacios
                    precio_limpio = str(precio).replace('€', '').replace(',', '.').strip()
                    return str(round(float(precio_limpio), 2)).replace('.', ',')
                except ValueError as e:
                    logger.warning(f"Error al formatear precio '{precio}': {str(e)}")
                    return ''  # Retornar cadena vacía si no se puede formatear
            return ''
        
        # Inicializar el traductor
        translator = GoogleTranslator(source='auto', target='es')
        
        # Filtrar referencias no encontradas
        df_no_encontradas = df_mapeado[df_mapeado['REF'].isin(referencias_no_encontradas)].copy()
        
        if not df_no_encontradas.empty:
            # Función para traducir texto de manera segura
            def traducir_seguro(texto):
                if pd.isna(texto) or str(texto).strip() == '':
                    return texto
                try:
                    texto_str = str(texto).strip()
                    traduccion = translator.translate(texto_str)
                    return traduccion
                except Exception as e:
                    logger.warning(f"Error al traducir '{texto}': {str(e)}")
                    return texto
            
            # Traducir columnas especificadas
            columnas_a_traducir = ['NOMBRE', 'COLOR', 'CATEGORIA']
            for columna in columnas_a_traducir:
                if columna in df_no_encontradas.columns:
                    logger.info(f"Traduciendo columna: {columna}")
                    df_no_encontradas[columna] = df_no_encontradas[columna].apply(traducir_seguro)
            
            # Crear DataFrame con las mismas columnas que el original
            columnas_finales = [
                'REF MADRE', 'EAN PRODUCT', 'NOMBRE (SIN TALLA)', 'MARCA', 'PVP +IVA', 
                'ID IVA', 'PRODUCT CATEGORIA', 'CATEGORIAS', 'CARACTERISTICAS', 'GAMA',
                'FILTROS', 'PRODUCT', 'META-DESCRIPCION', 'URL IMGs', 'ELIMINAR IMG',
                'DESCRIPCION LARGA', 'ANCHURA', 'ALTURA', 'PROFUNDIDAD', 'PESO PRODUCT',
                'ID DISPONIBILIDAD', 'ACTIVO', 'DISP. PEDIDOS', 'TEMPORADA',
                'TALLAS', 'GENERO', 'EDAD', 'COLOR', 'REF MADRE COMBI', 'REF COMBI',
                'EAN COMBI', 'NOMBRE COMBI:TIPO', '|', 'REF', 'NOMBRE', 'PROVEEDOR', 'FAMILIA',
                'SUBFAMILIA', 'P.COMPRA', 'PVP (+IVA)', 'EAN', 'ALT 1', 'ALT 2', 'ALT 3',
                'UNIDAD', 'LOTE', 'PESO', 'CODNC', 'LIBRE1=MARCA', 'LIBRE2=TEMPORADA',
                'LIBRE3=PRODUCTO', 'LIBRE4=GAMA/MODELO', 'LIBRE5=GRUPO'
            ]
            
            df_resultado = pd.DataFrame(columns=columnas_finales)
            
            # Mapear los datos de las referencias no encontradas
            for _, fila in df_no_encontradas.iterrows():
                nueva_fila = pd.Series('', index=columnas_finales)
                nueva_fila['REF'] = fila['REF']
                nueva_fila['NOMBRE'] = fila['NOMBRE'] if 'NOMBRE' in fila else ''
                nueva_fila['COLOR'] = fila['COLOR'] if 'COLOR' in fila else ''
                nueva_fila['PRODUCT CATEGORIA'] = fila['CATEGORIA'] if 'CATEGORIA' in fila else ''
                nueva_fila['EAN'] = fila['EAN'] if 'EAN' in fila else ''
                
                # Formatear precios
                nueva_fila['P.COMPRA'] = formatear_precio(fila['P.COMPRA']) if 'P.COMPRA' in fila else ''
                nueva_fila['PVP S/IVA'] = formatear_precio(fila['PVP S/IVA']) if 'PVP S/IVA' in fila else ''
                nueva_fila['PVP (+IVA)'] = formatear_precio(fila['PVP +IVA']) if 'PVP +IVA' in fila else ''
                
                nueva_fila['PESO'] = fila['PESO'] if 'PESO' in fila else ''
                nueva_fila['CODNC'] = fila['COD NC'] if 'COD NC' in fila else ''
                nueva_fila['ANCHURA'] = fila['ANCHURA'] if 'ANCHURA' in fila else ''
                nueva_fila['ALTURA'] = fila['ALTURA'] if 'ALTURA' in fila else ''
                nueva_fila['PROFUNDIDAD'] = fila['PROFUNDIDAD'] if 'PROFUNDIDAD' in fila else ''
                nueva_fila['URL IMGs'] = fila['IMG'] if 'IMG' in fila else ''
                
                df_resultado = pd.concat([df_resultado, nueva_fila.to_frame().T], ignore_index=True)
            
            return df_resultado
            
        return None
            
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
            'REF MADRE', 'EAN PRODUCT', 'NOMBRE (SIN TALLA)', 'MARCA', 'PVP +IVA', 
            'ID IVA', 'PRODUCT CATEGORIA', 'CATEGORIAS', 'CARACTERISTICAS', 'GAMA',
            'FILTROS', 'PRODUCT', 'META-DESCRIPCION', 'URL IMGs', 'ELIMINAR IMG',
            'DESCRIPCION LARGA', 'ANCHURA', 'ALTURA', 'PROFUNDIDAD', 'PESO PRODUCT',
            'ID DISPONIBILIDAD', 'ACTIVO', 'DISP. PEDIDOS', 'TEMPORADA',
            'TALLAS', 'GENERO', 'EDAD', 'COLOR', 'REF MADRE COMBI', 'REF COMBI',
            'EAN COMBI', 'NOMBRE COMBI:TIPO', '|', 'REF', 'NOMBRE', 'PROVEEDOR', 'FAMILIA',
            'SUBFAMILIA', 'P.COMPRA', 'PVP (+IVA)', 'EAN', 'ALT 1', 'ALT 2', 'ALT 3',
            'UNIDAD', 'LOTE', 'PESO', 'CODNC', 'LIBRE1=MARCA', 'LIBRE2=TEMPORADA',
            'LIBRE3=PRODUCTO', 'LIBRE4=GAMA/MODELO', 'LIBRE5=GRUPO'
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
                           SubFamilia, CodigoNC, Libre1, Libre2, Libre3, Libre4, Libre5 
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
                           SubFamilia, CodigoNC, Libre1, Libre2, Libre3, Libre4, Libre5 
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
                    nueva_fila['REF'] = str(ref_busqueda)
                    # Solo usar precios de Ambar si no hay precios en Excel
                    if datos_excel is not None:
                        # Verificar P.COMPRA del Excel
                        if pd.notna(datos_excel.get('P.COMPRA')) and str(datos_excel.get('P.COMPRA')).strip():
                            nueva_fila['P.COMPRA'] = formatear_precio(datos_excel['P.COMPRA'])
                        else:
                            nueva_fila['P.COMPRA'] = formatear_precio(datos_ambar[6])
                        
                        # Verificar PVP S/IVA del Excel
                        if pd.notna(datos_excel.get('PVP S/IVA')) and str(datos_excel.get('PVP S/IVA')).strip():
                            nueva_fila['PVP S/IVA'] = formatear_precio(datos_excel['PVP S/IVA'])
                        else:
                            nueva_fila['PVP S/IVA'] = formatear_precio(datos_ambar[4])
                            
                        # Verificar PVP +IVA del Excel
                        if pd.notna(datos_excel.get('PVP +IVA')) and str(datos_excel.get('PVP +IVA')).strip():
                            nueva_fila['PVP (+IVA)'] = formatear_precio(datos_excel['PVP +IVA'])
                        else:
                            nueva_fila['PVP (+IVA)'] = formatear_precio(datos_ambar[5])
                    else:
                        # Si no hay datos en Excel, usar precios de Ambar
                        nueva_fila['P.COMPRA'] = formatear_precio(datos_ambar[6])
                        nueva_fila['PVP S/IVA'] = formatear_precio(datos_ambar[4])
                        nueva_fila['PVP (+IVA)'] = formatear_precio(datos_ambar[5])
                    
                    nueva_fila['NOMBRE'] = str(datos_ambar[1])
                    nueva_fila['FAMILIA'] = str(datos_ambar[2])
                    nueva_fila['PROVEEDOR'] = str(datos_ambar[3])
                    nueva_fila['EAN'] = str(datos_ambar[7])
                    nueva_fila['PESO'] = str(datos_ambar[8])
                    nueva_fila['SUBFAMILIA'] = str(datos_ambar[9])
                    nueva_fila['CODNC'] = str(datos_ambar[10]).replace(' ', '')
                    nueva_fila['LIBRE1=MARCA'] = str(datos_ambar[11])
                    nueva_fila['LIBRE2=TEMPORADA'] = str(datos_ambar[12])
                    nueva_fila['LIBRE3=PRODUCTO'] = str(datos_ambar[13])
                    nueva_fila['LIBRE4=GAMA/MODELO'] = str(datos_ambar[14])
                    nueva_fila['LIBRE5=GRUPO'] = str(datos_ambar[15])
                
                # Procesar datos de Prestashop
                if ref_busqueda in resultados_product:
                    nueva_fila['REF MADRE'] = str(ref_busqueda)
                    nueva_fila['EAN PRODUCT'] = str(resultados_product[ref_busqueda]['ean'])
                    nueva_fila['NOMBRE (SIN TALLA)'] = str(resultados_product[ref_busqueda]['nombre'])
                    nueva_fila['MARCA'] = str(resultados_product[ref_busqueda]['marca'])
                    nueva_fila['PVP +IVA'] = formatear_precio(resultados_product[ref_busqueda]['precio'])
                    nueva_fila['|'] = '|'
                elif ref_busqueda in resultados_attribute:
                    nueva_fila['REF COMBI'] = str(ref_busqueda)
                    nueva_fila['EAN COMBI'] = str(resultados_attribute[ref_busqueda]['ean'])
                    nueva_fila['REF MADRE'] = str(resultados_attribute[ref_busqueda]['ref_madre'])
                    nueva_fila['NOMBRE (SIN TALLA)'] = str(resultados_attribute[ref_busqueda]['nombre'])
                    nueva_fila['MARCA'] = str(resultados_attribute[ref_busqueda]['marca'])
                    nueva_fila['PVP +IVA'] = formatear_precio(resultados_attribute[ref_busqueda]['precio'])
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
                    if pd.notna(datos_excel.get('P.COMPRA')):
                        nueva_fila['P.COMPRA'] = formatear_precio(datos_excel['P.COMPRA'])
                
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
            df_no_encontradas = procesar_referencias_no_encontradas(df_mapeado, referencias_no_encontradas)
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

def mapear_excel_a_plantilla(file_stream, nombre_plantilla):
    """
    Mapea un archivo Excel según la plantilla seleccionada.
    """
    try:
        logger.info(f"Iniciando mapeo con plantilla: {nombre_plantilla}")
        
        # Verificar que la plantilla existe
        if nombre_plantilla not in plantillas:
            error_msg = f"Plantilla '{nombre_plantilla}' no encontrada"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        
        # Obtener el mapeo de columnas
        mapeo_columnas = plantillas[nombre_plantilla]
        logger.debug(f"Usando mapeo de columnas: {mapeo_columnas}")
        
        try:
            df_entrada = pd.read_excel(file_stream)
            logger.info("Archivo Excel leído correctamente")
        except Exception as e:
            error_msg = f"Error al leer el archivo Excel: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        
        # Realizar el mapeo de columnas
        datos_salida = {}
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
        
        # Crear BytesIO para datos mapeados
        datos_mapeados = BytesIO()
        with pd.ExcelWriter(datos_mapeados, engine='openpyxl') as writer:
            df_salida.to_excel(writer, index=False)
        
        datos_mapeados.seek(0)
        
        # Consultar Ambar y procesar resultados
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