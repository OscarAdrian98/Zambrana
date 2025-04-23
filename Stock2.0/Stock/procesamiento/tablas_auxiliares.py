import pandas as pd
import gc
import logging
from config.logging import logger_funciones_especificas

def crear_tabla_aux_prestashop(conexion_prestashop):
    query = """
        SELECT p.id_product, p.reference, p.ean13, sa.quantity, 'ps_product' AS source
        FROM ps_product p
        JOIN ps_stock_available sa ON p.id_product = sa.id_product AND sa.id_product_attribute = 0
        WHERE p.reference IS NOT NULL AND p.reference <> ''

        UNION ALL

        SELECT pa.id_product, pa.reference, pa.ean13, sa.quantity, 'ps_product_attribute' AS source
        FROM ps_product_attribute pa
        JOIN ps_stock_available sa ON pa.id_product_attribute = sa.id_product_attribute
        WHERE pa.reference IS NOT NULL AND pa.reference <> ''

        UNION ALL

        SELECT ps.id_product, ps.product_supplier_reference AS reference, '' AS ean13, sa.quantity, 'ps_product_supplier' AS source
        FROM ps_product_supplier ps
        JOIN ps_stock_available sa ON ps.id_product = sa.id_product AND sa.id_product_attribute = 0
        WHERE ps.product_supplier_reference IS NOT NULL AND ps.product_supplier_reference <> ''
    """
    prestashop_df = pd.read_sql(query, conexion_prestashop)
    print(f"✅ Tabla auxiliar PrestaShop creada: {prestashop_df.shape[0]} filas.")
    return prestashop_df


def crear_tabla_aux_proveedor(df_proveedor):
    print(f"✅ Tabla auxiliar proveedor creada: {df_proveedor.shape[0]} filas.")
    return df_proveedor.copy()


def comparar_tablas_auxiliares(prestashop_df, proveedor_df):
    # Verificamos si la columna 'ean' existe para decidir cómo comparar
    usar_ean = 'ean' in proveedor_df.columns and 'ean13' in prestashop_df.columns

    if usar_ean:
        prestashop_df['ean13'] = prestashop_df['ean13'].astype(str)
        proveedor_df['ean'] = proveedor_df['ean'].astype(str)

        df_fusionado = pd.merge(
            proveedor_df, prestashop_df, 
            left_on='ean', right_on='ean13', how='inner'
        )
        print(f"🔎 Comparación por EAN: {df_fusionado.shape[0]} coincidencias.")
    else:
        prestashop_df['reference'] = prestashop_df['reference'].astype(str)
        proveedor_df['referencia'] = proveedor_df['referencia'].astype(str)

        df_fusionado = pd.merge(
            proveedor_df, prestashop_df, 
            left_on='referencia', right_on='reference', how='inner'
        )
        print(f"🔎 Comparación por referencia: {df_fusionado.shape[0]} coincidencias.")

    return df_fusionado

# Eliminar tablas auxiliares de memoria
def eliminar_tablas_auxiliares(*tablas):
    """
    Elimina los DataFrames auxiliares de memoria para liberar recursos.
    
    Args:
        *tablas: Pasar las variables de los DataFrames a eliminar.
    """
    for tabla in tablas:
        del tabla
    gc.collect()  # Recolector de basura para liberar la memoria inmediatamente
    print("🗑️ Tablas auxiliares eliminadas de la memoria.")

# Detectar referencias huérfanas para desactivar
def detectar_referencias_huerfanas_para_desactivar(conexion_prestashop, conexion_proveedores):
    
    # 1. Consulta al PrestaShop para obtener referencias + marca
    query_prestashop = """
        -- Productos simples
        SELECT
            p.id_product,
            p.reference,
            p.ean13,
            sa.quantity,
            m.name AS marca,
            NULL AS id_product_attribute,
            'ps_product' AS source
        FROM ps_product p
        JOIN ps_stock_available sa ON p.id_product = sa.id_product AND sa.id_product_attribute = 0
        LEFT JOIN ps_manufacturer m ON p.id_manufacturer = m.id_manufacturer
        WHERE p.reference IS NOT NULL AND p.reference <> ''

        UNION

        -- Combinaciones (atributos)
        SELECT
            pa.id_product,
            pa.reference,
            pa.ean13,
            sa.quantity,
            m.name AS marca,
            pa.id_product_attribute,
            'ps_product_attribute' AS source
        FROM ps_product_attribute pa
        JOIN ps_product p ON pa.id_product = p.id_product
        JOIN ps_stock_available sa ON pa.id_product_attribute = sa.id_product_attribute
        LEFT JOIN ps_manufacturer m ON p.id_manufacturer = m.id_manufacturer
        WHERE pa.reference IS NOT NULL AND pa.reference <> ''
    """
    prestashop_df = pd.read_sql(query_prestashop, conexion_prestashop)
    prestashop_df['reference'] = prestashop_df['reference'].astype(str)
    prestashop_df['ean13'] = prestashop_df['ean13'].astype(str)
    logging.info(f"📦 PrestaShop: {prestashop_df.shape[0]} productos cargados")

    # 2. Consulta a base de datos del proveedor
    query_proveedor = """
        SELECT id_proveedor, id_marca, referencia_producto, ean_producto, stock_txt_producto, hay_stock_producto
        FROM productos
    """
    proveedor_df = pd.read_sql(query_proveedor, conexion_proveedores)
    proveedor_df['referencia_producto'] = proveedor_df['referencia_producto'].astype(str)
    proveedor_df['ean_producto'] = proveedor_df['ean_producto'].astype(str)
    logging.info(f"📡 Proveedor: {proveedor_df.shape[0]} productos cargados")

    # 3. Comparar referencias y EANs
    referencias_proveedor = set(proveedor_df['referencia_producto'])
    eans_proveedor = set(proveedor_df['ean_producto'])

    df_huerfanas = prestashop_df[
        ~prestashop_df['reference'].isin(referencias_proveedor) &
        ~prestashop_df['ean13'].isin(eans_proveedor) &
        (prestashop_df['quantity'] <= 0)
    ].copy()
    logging.info(f"🕵️ Referencias/EAN huérfanas sin stock detectadas: {df_huerfanas.shape[0]}")

    if df_huerfanas.empty:
        return pd.DataFrame()

    # 4. Obtener mapeo marca ↔ id_proveedor desde la base del proveedor
    query_marca_proveedor = """
        SELECT mp.id_marca, mp.id_proveedor, m.nombre_marca
        FROM marcas_proveedores mp
        JOIN marcas m ON mp.id_marca = m.id_marca
    """
    marcas_df = pd.read_sql(query_marca_proveedor, conexion_proveedores)

    # 5. Verificar si la marca del producto en PrestaShop está vinculada a algún proveedor
    df_huerfanas = pd.merge(
        df_huerfanas, marcas_df,
        left_on='marca', right_on='nombre_marca',
        how='left'
    )

    # 6. Filtrar las que tienen marca con proveedor conocido
    df_a_desactivar = df_huerfanas[df_huerfanas['id_proveedor'].notnull()].copy()
    logging.info(f"📛 Referencias candidatas a desactivar (marca sincronizada): {df_a_desactivar.shape[0]}")

    # 7. Desactivar solo los que sean de tipo 'ps_product'
    df_ps_product = df_a_desactivar[df_a_desactivar['source'] == 'ps_product'].copy()

    # 8. Traer todas las combinaciones de una sola vez
    query_combinaciones = """
        SELECT id_product, reference
        FROM ps_product_attribute
        WHERE reference IS NOT NULL AND reference <> ''
    """
    combinaciones_df = pd.read_sql(query_combinaciones, conexion_prestashop)
    combinaciones_df['reference'] = combinaciones_df['reference'].astype(str)

    # 9. Comprobar si alguna combinación tiene stock en proveedor
    combinaciones_df['tiene_stock'] = combinaciones_df['reference'].isin(
        proveedor_df[proveedor_df['hay_stock_producto'] == 1]['referencia_producto']
    )

    stock_por_padre = combinaciones_df.groupby('id_product')['tiene_stock'].any().reset_index()
    stock_por_padre.rename(columns={'tiene_stock': 'tiene_stock_combinaciones'}, inplace=True)

    df_ps_product = df_ps_product.merge(stock_por_padre, on='id_product', how='left')
    df_ps_product['tiene_stock_combinaciones'] = df_ps_product['tiene_stock_combinaciones'].fillna(False)

    # 10. Filtrar solo los que NO tienen combinaciones con stock
    df_ps_product = df_ps_product[df_ps_product['tiene_stock_combinaciones'] == False]

    # 11. Realizar desactivación solo si están activos
    referencias_desactivar = df_ps_product['reference'].dropna().unique().tolist()

    cursor = conexion_prestashop.cursor()

    if referencias_desactivar:
        placeholders = ', '.join(['%s'] * len(referencias_desactivar))
        query_activos = f"""
            SELECT reference
            FROM ps_product
            WHERE reference IN ({placeholders}) AND active = 1
        """
        cursor.execute(query_activos, tuple(referencias_desactivar))
        referencias_activas = [row[0] for row in cursor.fetchall()]

        referencias_desactivar = referencias_activas

        if referencias_desactivar:
            placeholders = ', '.join(['%s'] * len(referencias_desactivar))
            try:
                query_update_product = f"UPDATE ps_product SET active = 0 WHERE reference IN ({placeholders})"
                query_update_product_shop = f"""
                    UPDATE ps_product_shop
                    SET active = 0
                    WHERE id_product IN (
                        SELECT id_product FROM ps_product WHERE reference IN ({placeholders})
                    )
                """

                cursor.execute(query_update_product, tuple(referencias_desactivar))
                cursor.execute(query_update_product_shop, tuple(referencias_desactivar))
                conexion_prestashop.commit()

                for ref in referencias_desactivar:
                    logging.info(f"🚫 Producto desactivado: {ref}")
                    logger_funciones_especificas.info(f"🚫 Producto desactivado: {ref}")

                logging.info(f"✅ Se han desactivado {len(referencias_desactivar)} productos huérfanos tipo ps_product.")
            except Exception as e:
                conexion_prestashop.rollback()
                logging.error(f"❌ Error desactivando productos: {e}")
                logger_funciones_especificas.error(f"❌ Error desactivando productos: {e}")
        else:
            logging.info("✅ No hay productos activos que desactivar.")
    else:
        logging.info("✅ No hay productos de tipo ps_product a desactivar.")

    cursor.close()

    return df_a_desactivar