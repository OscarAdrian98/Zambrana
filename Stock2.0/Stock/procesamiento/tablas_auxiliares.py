import pandas as pd
import gc

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
