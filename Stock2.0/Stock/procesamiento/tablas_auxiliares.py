import pandas as pd
import gc
import logging
from dataclasses import asdict
from config.logging import logger_funciones_especificas
from config.lote_validacion import PROVEEDORES_OPERATIVOS_VALIDACION
from config.rendimiento import commit_con_metricas, medir_fase
from procesamiento.reglas import (
    conjunto_identificadores_validos,
    cruzar_catalogos,
    normalizar_ean,
    normalizar_identificador,
    normalizar_serie_identificadores,
)
from procesamiento.huerfanos import (
    DECISION_SEGURO,
    clasificar_evidencias_huerfanos,
    identificador_flexible,
)

def crear_tabla_aux_prestashop(conexion_prestashop):
    query = """
        SELECT
            p.id_product,
            0 AS id_product_attribute,
            p.reference,
            p.ean13,
            sa.quantity,
            'ps_product' AS source,
            m.name AS marca
        FROM ps_product p
        JOIN ps_stock_available sa
          ON p.id_product = sa.id_product
         AND sa.id_product_attribute = 0
         AND sa.id_shop = 1
        LEFT JOIN ps_manufacturer m
          ON m.id_manufacturer = p.id_manufacturer
        WHERE (
            (p.reference IS NOT NULL AND p.reference <> '')
            OR (p.ean13 IS NOT NULL AND p.ean13 <> '')
        )

        UNION ALL

        SELECT
            pa.id_product,
            pa.id_product_attribute,
            pa.reference,
            pa.ean13,
            sa.quantity,
            'ps_product_attribute' AS source,
            m.name AS marca
        FROM ps_product_attribute pa
        JOIN ps_stock_available sa
          ON pa.id_product_attribute = sa.id_product_attribute
         AND sa.id_shop = 1
        JOIN ps_product p ON p.id_product = pa.id_product
        LEFT JOIN ps_manufacturer m
          ON m.id_manufacturer = p.id_manufacturer
        WHERE (
            (pa.reference IS NOT NULL AND pa.reference <> '')
            OR (pa.ean13 IS NOT NULL AND pa.ean13 <> '')
        )

        UNION ALL

        SELECT
            ps.id_product,
            ps.id_product_attribute,
            ps.product_supplier_reference AS reference,
            '' AS ean13,
            sa.quantity,
            'ps_product_supplier' AS source,
            m.name AS marca
        FROM ps_product_supplier ps
        JOIN ps_stock_available sa
          ON ps.id_product = sa.id_product
         AND sa.id_product_attribute = ps.id_product_attribute
         AND sa.id_shop = 1
        JOIN ps_product p ON p.id_product = ps.id_product
        LEFT JOIN ps_manufacturer m
          ON m.id_manufacturer = p.id_manufacturer
        WHERE ps.product_supplier_reference IS NOT NULL AND ps.product_supplier_reference <> ''
    """
    prestashop_df = pd.read_sql(query, conexion_prestashop)
    print(
        "Tabla auxiliar PrestaShop creada: "
        f"{prestashop_df.shape[0]} filas."
    )
    return prestashop_df


def crear_tabla_aux_proveedor(df_proveedor):
    print(
        "Tabla auxiliar proveedor creada: "
        f"{df_proveedor.shape[0]} filas."
    )
    return df_proveedor.copy()


def comparar_tablas_auxiliares(
    prestashop_df,
    proveedor_df,
    id_proveedor=None,
    marcas_permitidas=None,
    metricas=None,
):
    """Cruza por EAN válido y usa la referencia única como respaldo."""

    prestashop_ambito = prestashop_df
    if marcas_permitidas:
        marcas = {
            str(marca).strip().casefold()
            for marca in marcas_permitidas
            if pd.notna(marca) and str(marca).strip()
        }
        prestashop_ambito = prestashop_df[
            prestashop_df["marca"].map(
                lambda valor: (
                    str(valor).strip().casefold()
                    if pd.notna(valor)
                    else None
                )
            ).isin(marcas)
        ].copy()

    with medir_fase(metricas, "Cruces de DataFrames"):
        resultado = cruzar_catalogos(
            proveedor_df,
            prestashop_ambito,
            id_proveedor=id_proveedor,
        )

    estadisticas = resultado.estadisticas
    if "referencia_alternativa" in proveedor_df.columns:
        logging.info(
            "Cruce proveedor %s: referencia_principal=%s, "
            "referencia_alternativa=%s, EAN=%s, sin_coincidencia=%s, "
            "ambiguas_alt=%s, conflictos=%s",
            id_proveedor,
            estadisticas.matches_referencia_principal,
            estadisticas.matches_referencia_alternativa,
            estadisticas.matches_ean,
            estadisticas.sin_coincidencia,
            estadisticas.referencias_alternativas_ambiguas,
            estadisticas.conflictos_identificadores,
        )
    else:
        logging.info(
            "Cruce proveedor %s: EAN=%s, referencia=%s, "
            "sin coincidencia=%s, EAN duplicados=%s, "
            "referencias duplicadas=%s, conflictos=%s",
            id_proveedor,
            estadisticas.coincidencias_ean,
            estadisticas.coincidencias_referencia,
            estadisticas.sin_coincidencia,
            estadisticas.ean_duplicados,
            estadisticas.referencias_duplicadas,
            estadisticas.conflictos,
        )
    if estadisticas.conflictos:
        logging.warning(
            "Se excluyeron %s conflictos EAN/referencia del proveedor %s",
            estadisticas.conflictos,
            id_proveedor,
        )
    coincidencias = resultado.coincidencias
    coincidencias.attrs["estadisticas_cruce"] = asdict(estadisticas)
    return coincidencias

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
def _lista_normalizada(valores, normalizador=normalizar_identificador):
    return {
        normalizado
        for valor in valores
        if (normalizado := normalizador(valor)) is not None
    }


def _consultar_catalogo_por_identificadores(
    conexion,
    tabla,
    referencias,
    eans,
    flexibles,
):
    columnas = (
        "id_proveedor, id_marca, referencia_producto, ean_producto, "
        "hay_stock_producto, fecha_actualizacion_producto"
    )
    if tabla == "productos_variantes":
        columnas += (
            ", presente_ultima_ejecucion, ultima_ejecucion_id, "
            "fecha_creacion, fecha_modificacion"
        )
    condiciones = []
    parametros = []
    if referencias:
        condiciones.append(
            "TRIM(referencia_producto) IN ("
            + ",".join(["%s"] * len(referencias))
            + ")"
        )
        parametros.extend(sorted(referencias))
    if eans:
        condiciones.append(
            "TRIM(ean_producto) IN (" + ",".join(["%s"] * len(eans)) + ")"
        )
        parametros.extend(sorted(eans))
    if flexibles:
        placeholders = ",".join(["%s"] * len(flexibles))
        condiciones.extend(
            [
                "REGEXP_REPLACE(LOWER(TRIM(COALESCE(referencia_producto,''))), "
                f"'[^0-9a-z]', '') IN ({placeholders})",
                "REGEXP_REPLACE(LOWER(TRIM(COALESCE(ean_producto,''))), "
                f"'[^0-9a-z]', '') IN ({placeholders})",
            ]
        )
        parametros.extend(sorted(flexibles))
        parametros.extend(sorted(flexibles))
    if not condiciones:
        return pd.DataFrame()
    return pd.read_sql(
        f"SELECT {columnas} FROM {tabla} WHERE " + " OR ".join(condiciones),
        conexion,
        params=parametros,
    )


def _agrupar_listas(dataframe, clave, valor):
    if dataframe.empty:
        return {}
    return (
        dataframe.dropna(subset=[clave, valor])
        .groupby(clave)[valor]
        .agg(lambda serie: sorted(set(serie)))
        .to_dict()
    )


def previsualizar_huerfanos(
    conexion_prestashop,
    conexion_proveedores,
    metricas=None,
):
    """Clasifica huérfanos con todas sus evidencias sin realizar escrituras."""

    query_prestashop = """
        SELECT
            p.id_product,
            p.reference,
            p.ean13,
            sa.quantity AS stock_ps,
            sa.out_of_stock,
            m.name AS fabricante,
            NULL AS id_product_attribute,
            'ps_product' AS source,
            p.active,
            p.visibility,
            p.available_date,
            p.date_add,
            p.date_upd
        FROM ps_product p
        JOIN ps_stock_available sa
          ON p.id_product = sa.id_product
         AND sa.id_product_attribute = 0
         AND sa.id_shop = 1
        LEFT JOIN ps_manufacturer m
          ON p.id_manufacturer = m.id_manufacturer
        WHERE p.reference IS NOT NULL AND p.reference <> ''

        UNION ALL

        SELECT
            pa.id_product,
            pa.reference,
            pa.ean13,
            sa.quantity AS stock_ps,
            sa.out_of_stock,
            m.name AS fabricante,
            pa.id_product_attribute,
            'ps_product_attribute' AS source,
            p.active,
            p.visibility,
            p.available_date,
            p.date_add,
            p.date_upd
        FROM ps_product_attribute pa
        JOIN ps_product p ON pa.id_product = p.id_product
        JOIN ps_stock_available sa
          ON pa.id_product_attribute = sa.id_product_attribute
         AND sa.id_shop = 1
        LEFT JOIN ps_manufacturer m
          ON p.id_manufacturer = m.id_manufacturer
        WHERE pa.reference IS NOT NULL AND pa.reference <> ''
    """
    query_variantes_presentes = """
        SELECT
            id_proveedor,
            id_marca,
            referencia_producto,
            ean_producto,
            hay_stock_producto
        FROM productos_variantes
        WHERE presente_ultima_ejecucion = 1
    """
    query_marcas = """
        SELECT
            m.nombre_marca,
            mp.id_proveedor,
            p.nombre_proveedor
        FROM marcas_proveedores mp
        JOIN marcas m ON m.id_marca = mp.id_marca
        JOIN proveedores p ON p.id_proveedor = mp.id_proveedor
    """
    query_combinaciones = """
        SELECT
            pa.id_product,
            pa.id_product_attribute,
            pa.reference,
            pa.ean13,
            COALESCE(sa.quantity, 0) AS quantity
        FROM ps_product_attribute pa
        LEFT JOIN ps_stock_available sa
          ON sa.id_product_attribute = pa.id_product_attribute
         AND sa.id_shop = 1
    """
    query_asociaciones = """
        SELECT
            ps.id_product,
            ps.id_product_attribute,
            ps.id_supplier,
            s.name AS supplier_name,
            ps.product_supplier_reference
        FROM ps_product_supplier ps
        JOIN ps_supplier s ON s.id_supplier = ps.id_supplier
    """
    with medir_fase(metricas, "Consulta de PrestaShop"):
        prestashop_df = pd.read_sql(query_prestashop, conexion_prestashop)
        combinaciones_df = pd.read_sql(query_combinaciones, conexion_prestashop)
        asociaciones_df = pd.read_sql(query_asociaciones, conexion_prestashop)
    with medir_fase(metricas, "Consulta de proveedores"):
        presentes_df = pd.read_sql(
            query_variantes_presentes,
            conexion_proveedores,
        )
        marcas_df = pd.read_sql(query_marcas, conexion_proveedores)

    for dataframe, referencia, ean in (
        (prestashop_df, "reference", "ean13"),
        (combinaciones_df, "reference", "ean13"),
        (presentes_df, "referencia_producto", "ean_producto"),
    ):
        dataframe["_ref"] = dataframe[referencia].map(normalizar_identificador)
        dataframe["_ean"] = dataframe[ean].map(normalizar_ean)

    refs_presentes = _lista_normalizada(presentes_df["referencia_producto"])
    eans_presentes = _lista_normalizada(
        presentes_df["ean_producto"],
        normalizador=normalizar_ean,
    )
    marcas_configuradas = set(marcas_df["nombre_marca"].dropna())
    candidatos = prestashop_df[
        prestashop_df["source"].eq("ps_product")
        & prestashop_df["fabricante"].isin(marcas_configuradas)
        & pd.to_numeric(
            prestashop_df["active"], errors="coerce"
        ).fillna(0).eq(1)
        & ~prestashop_df["_ref"].isin(refs_presentes)
        & ~prestashop_df["_ean"].isin(eans_presentes)
        & pd.to_numeric(prestashop_df["stock_ps"], errors="coerce").fillna(0).le(0)
    ].copy()
    if candidatos.empty:
        return clasificar_evidencias_huerfanos(candidatos)

    refs_stock = _lista_normalizada(
        presentes_df.loc[
            pd.to_numeric(
                presentes_df["hay_stock_producto"], errors="coerce"
            ).fillna(0).gt(0),
            "referencia_producto",
        ]
    )
    eans_stock = _lista_normalizada(
        presentes_df.loc[
            pd.to_numeric(
                presentes_df["hay_stock_producto"], errors="coerce"
            ).fillna(0).gt(0),
            "ean_producto",
        ],
        normalizador=normalizar_ean,
    )
    combinaciones_df["stock_proveedor"] = (
        combinaciones_df["_ref"].isin(refs_stock)
        | combinaciones_df["_ean"].isin(eans_stock)
    )
    combinaciones_df["combinacion_con_stock_ps"] = pd.to_numeric(
        combinaciones_df["quantity"], errors="coerce"
    ).fillna(0).gt(0)
    resumen_combinaciones = combinaciones_df.groupby("id_product").agg(
        numero_combinaciones=("id_product_attribute", "nunique"),
        stock_total_combinaciones=("quantity", "sum"),
        combinacion_con_stock_ps=("combinacion_con_stock_ps", "any"),
        combinacion_con_stock_proveedor=("stock_proveedor", "any"),
    )
    candidatos = candidatos.merge(
        resumen_combinaciones,
        on="id_product",
        how="left",
    )
    candidatos["numero_combinaciones"] = candidatos[
        "numero_combinaciones"
    ].fillna(0).astype(int)
    candidatos["stock_total_combinaciones"] = pd.to_numeric(
        candidatos["stock_total_combinaciones"], errors="coerce"
    ).fillna(0)
    candidatos["combinacion_con_stock_ps"] = candidatos[
        "combinacion_con_stock_ps"
    ].fillna(False)
    candidatos["combinacion_con_stock_proveedor"] = candidatos[
        "combinacion_con_stock_proveedor"
    ].fillna(False)
    candidatos = candidatos[
        ~candidatos["combinacion_con_stock_proveedor"]
    ].drop_duplicates("id_product").copy()

    ids = set(pd.to_numeric(candidatos["id_product"]).astype(int))
    asociaciones_df = asociaciones_df[asociaciones_df["id_product"].isin(ids)].copy()
    asociaciones_df["_supplier_ref"] = asociaciones_df[
        "product_supplier_reference"
    ].map(normalizar_identificador)
    referencias = _lista_normalizada(candidatos["reference"])
    eans = _lista_normalizada(
        candidatos["ean13"],
        normalizador=normalizar_ean,
    )
    supplier_refs = _lista_normalizada(
        asociaciones_df["product_supplier_reference"]
    )
    flexibles = {
        valor
        for valor in (
            identificador_flexible(v)
            for v in list(candidatos["reference"]) + list(candidatos["ean13"])
        )
        if valor is not None
    }
    with medir_fase(metricas, "Consulta de proveedores"):
        productos_df = _consultar_catalogo_por_identificadores(
            conexion_proveedores,
            "productos",
            referencias | supplier_refs,
            eans,
            flexibles,
        )
        variantes_df = _consultar_catalogo_por_identificadores(
            conexion_proveedores,
            "productos_variantes",
            referencias | supplier_refs,
            eans,
            flexibles,
        )
        proveedores_df = pd.read_sql(
            "SELECT id_proveedor, nombre_proveedor FROM proveedores",
            conexion_proveedores,
        )

    catalogos = []
    for nombre, dataframe in (
        ("productos", productos_df),
        ("productos_variantes", variantes_df),
    ):
        if dataframe.empty:
            continue
        copia = dataframe.copy()
        copia["tabla_origen"] = nombre
        copia["_ref"] = copia["referencia_producto"].map(
            normalizar_identificador
        )
        copia["_ean"] = copia["ean_producto"].map(normalizar_ean)
        copia["_ref_flexible"] = copia["referencia_producto"].map(
            identificador_flexible
        )
        copia["_ean_flexible"] = copia["ean_producto"].map(
            identificador_flexible
        )
        catalogos.append(copia)
    catalogo_df = (
        pd.concat(catalogos, ignore_index=True, sort=False)
        if catalogos
        else pd.DataFrame()
    )

    nombres_proveedores = {
        int(fila.id_proveedor): str(fila.nombre_proveedor)
        for fila in proveedores_df.itertuples(index=False)
    }
    ids_por_nombre = {}
    for proveedor_id, nombre in nombres_proveedores.items():
        ids_por_nombre.setdefault(identificador_flexible(nombre), set()).add(
            proveedor_id
        )
    marcas_df["_marca"] = marcas_df["nombre_marca"].map(
        lambda valor: str(valor).strip().casefold()
        if pd.notna(valor)
        else None
    )
    proveedores_marca = _agrupar_listas(marcas_df, "_marca", "id_proveedor")
    referencias_presentes_globales = refs_presentes
    referencias_productos_globales = _lista_normalizada(
        productos_df.get("referencia_producto", pd.Series(dtype=object))
    )

    conteos_ref_ps = prestashop_df["_ref"].value_counts()
    conteos_ean_ps = prestashop_df["_ean"].value_counts()
    filas = []
    for candidato in candidatos.to_dict("records"):
        product_id = int(candidato["id_product"])
        ref = normalizar_identificador(candidato.get("reference"))
        ean = normalizar_ean(candidato.get("ean13"))
        ref_flexible = identificador_flexible(candidato.get("reference"))
        ean_flexible = identificador_flexible(candidato.get("ean13"))
        if catalogo_df.empty:
            relacionados = catalogo_df
        else:
            relacionados = catalogo_df[
                catalogo_df["_ref"].eq(ref)
                | (ean is not None and catalogo_df["_ean"].eq(ean))
            ]
        relacionados_flexibles = (
            catalogo_df[
                catalogo_df["_ref_flexible"].isin(
                    {ref_flexible, ean_flexible} - {None}
                )
                | catalogo_df["_ean_flexible"].isin(
                    {ref_flexible, ean_flexible} - {None}
                )
            ]
            if not catalogo_df.empty
            else catalogo_df
        )
        coincidencia_flexible = len(
            relacionados_flexibles.drop(relacionados.index, errors="ignore")
        )
        productos_rel = relacionados[
            relacionados["tabla_origen"].eq("productos")
        ]
        variantes_rel = relacionados[
            relacionados["tabla_origen"].eq("productos_variantes")
        ]
        presentes_rel = variantes_rel[
            pd.to_numeric(
                variantes_rel.get(
                    "presente_ultima_ejecucion",
                    pd.Series(index=variantes_rel.index, dtype=float),
                ),
                errors="coerce",
            ).fillna(0).gt(0)
        ]
        asociaciones = asociaciones_df[
            asociaciones_df["id_product"].eq(product_id)
        ]
        supplier_ids = set()
        no_mapeadas = 0
        for nombre in asociaciones["supplier_name"].dropna().unique():
            encontrados = ids_por_nombre.get(identificador_flexible(nombre), set())
            if encontrados:
                supplier_ids.update(encontrados)
            else:
                no_mapeadas += 1
        refs_supplier = _lista_normalizada(
            asociaciones["product_supplier_reference"]
        )
        refs_supplier_presentes = refs_supplier & (
            referencias_presentes_globales | referencias_productos_globales
        )
        marca_clave = (
            str(candidato.get("fabricante")).strip().casefold()
            if pd.notna(candidato.get("fabricante"))
            else None
        )
        ids_marca = {
            int(valor) for valor in proveedores_marca.get(marca_clave, [])
        }
        ultima_producto = pd.to_datetime(
            productos_rel.get(
                "fecha_actualizacion_producto", pd.Series(dtype=object)
            ),
            errors="coerce",
        ).max()
        ultima_variante = pd.to_datetime(
            variantes_rel.get("fecha_modificacion", pd.Series(dtype=object)),
            errors="coerce",
        ).max()
        ids_historicos = set(
            pd.to_numeric(
                relacionados.get("id_proveedor", pd.Series(dtype=float)),
                errors="coerce",
            ).dropna().astype(int)
        )
        candidato.update(
            {
                "tiene_combinaciones": int(candidato["numero_combinaciones"] > 0),
                "asociaciones_supplier": len(asociaciones),
                "referencias_supplier": "|".join(sorted(refs_supplier)),
                "proveedores_supplier_ids": sorted(supplier_ids),
                "proveedores_supplier_fuera_lote_ids": sorted(
                    supplier_ids - set(PROVEEDORES_OPERATIVOS_VALIDACION)
                ),
                "asociaciones_supplier_no_mapeadas": no_mapeadas,
                "referencias_supplier_presentes": len(refs_supplier_presentes),
                "proveedores_marca_ids": sorted(ids_marca),
                "proveedores_marca": "|".join(
                    nombres_proveedores.get(i, str(i)) for i in sorted(ids_marca)
                ),
                "marca_compartida": int(len(ids_marca) > 1),
                "productos_actuales": len(productos_rel),
                "variantes_historicas": len(variantes_rel),
                "variantes_presentes": len(presentes_rel),
                "proveedores_historicos_ids": sorted(ids_historicos),
                "proveedores_historicos_fuera_lote_ids": sorted(
                    ids_historicos - set(PROVEEDORES_OPERATIVOS_VALIDACION)
                ),
                "ultima_fecha_productos": (
                    None if pd.isna(ultima_producto) else ultima_producto
                ),
                "ultima_fecha_variantes": (
                    None if pd.isna(ultima_variante) else ultima_variante
                ),
                "coincidencia_flexible_proveedor": coincidencia_flexible,
                "conflicto_identidad_ps": int(
                    (ref is not None and conteos_ref_ps.get(ref, 0) > 1)
                    or (ean is not None and conteos_ean_ps.get(ean, 0) > 1)
                ),
            }
        )
        filas.append(candidato)

    resultado = clasificar_evidencias_huerfanos(pd.DataFrame(filas))
    logging.info(
        "Previsualización segura de huérfanos: %s candidatos; %s seguros",
        len(resultado),
        int(resultado["decision"].eq(DECISION_SEGURO).sum()),
    )
    return resultado.sort_values("id_product").reset_index(drop=True)


def detectar_referencias_huerfanas_para_desactivar(
    conexion_prestashop,
    conexion_proveedores,
    metricas=None,
    solo_previsualizar=False,
):
    """Aplica únicamente el mismo conjunto seguro que devuelve el preview."""

    previsualizacion = previsualizar_huerfanos(
        conexion_prestashop,
        conexion_proveedores,
        metricas=metricas,
    )
    seguros = previsualizacion[
        previsualizacion["decision"].eq(DECISION_SEGURO)
    ]
    ids_desactivar = seguros["id_product"].astype(int).drop_duplicates().tolist()
    if solo_previsualizar or not ids_desactivar:
        return previsualizacion

    placeholders = ",".join(["%s"] * len(ids_desactivar))
    try:
        with conexion_prestashop.cursor() as cursor:
            cursor.execute(
                f"UPDATE ps_product SET active=0 WHERE active=1 "
                f"AND id_product IN ({placeholders})",
                tuple(ids_desactivar),
            )
            cursor.execute(
                f"UPDATE ps_product_shop SET active=0 WHERE active=1 "
                f"AND id_product IN ({placeholders})",
                tuple(ids_desactivar),
            )
        commit_con_metricas(conexion_prestashop, metricas)
    except Exception as error:
        conexion_prestashop.rollback()
        logging.exception("Error desactivando productos huérfanos seguros")
        raise RuntimeError(
            "No se pudieron desactivar los productos huérfanos seguros"
        ) from error
    return previsualizacion


def previsualizar_referencias_huerfanas(
    conexion_prestashop,
    conexion_proveedores,
    metricas=None,
):
    """Alias compatible de :func:`previsualizar_huerfanos`."""

    return previsualizar_huerfanos(
        conexion_prestashop,
        conexion_proveedores,
        metricas=metricas,
    )

def añadir_referencias_colgadas(df_fusionado, conexion_prestashop, conexion_proveedores, id_proveedor):
    """
    Añade al df_fusionado todas las combinaciones de productos en PrestaShop
    que tengan alguna referencia en la BD del proveedor (productos) aunque no estén en el fichero.
    """
    import pandas as pd
    import logging

    try:
        # 1️⃣ Obtener todas las referencias en la BD del proveedor para ese proveedor
        with conexion_proveedores.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT referencia_producto
                FROM productos_variantes
                WHERE id_proveedor = %s
                  AND presente_ultima_ejecucion = 1
            """, (id_proveedor,))
            refs_proveedor = list(
                conjunto_identificadores_validos(
                    row[0] for row in cursor.fetchall()
                )
            )

        if not refs_proveedor:
            logging.info(f"🔍 No se encontraron referencias en BD proveedor {id_proveedor}")
            return df_fusionado

        # 2️⃣ Buscar sus id_product en PrestaShop
        placeholders = ','.join(['%s'] * len(refs_proveedor))
        query = f"""
            SELECT DISTINCT pa.id_product
            FROM ps_product_attribute pa
            WHERE pa.reference IN ({placeholders})
        """
        with conexion_prestashop.cursor() as cursor:
            cursor.execute(query, tuple(refs_proveedor))
            id_products = [row[0] for row in cursor.fetchall()]

        if not id_products:
            logging.info(f"🔍 No se encontraron id_product en PrestaShop para referencias de proveedor {id_proveedor}")
            return df_fusionado

        # 3️⃣ Obtener todas las combinaciones (incluso las no presentes en fichero)
        placeholders = ','.join(['%s'] * len(id_products))
        query_attrs = f"""
            SELECT pa.id_product, pa.id_product_attribute, pa.reference, sa.quantity
            FROM ps_product_attribute pa
            INNER JOIN ps_stock_available sa ON sa.id_product_attribute = pa.id_product_attribute AND sa.id_shop = 1
            WHERE pa.id_product IN ({placeholders})
        """
        with conexion_prestashop.cursor() as cursor:
            cursor.execute(query_attrs, tuple(id_products))
            rows = cursor.fetchall()

        extra_df = pd.DataFrame(rows, columns=['id_product','id_product_attribute','reference','quantity'])
        extra_df["reference"] = normalizar_serie_identificadores(
            extra_df["reference"]
        )
        extra_df = extra_df[extra_df["reference"].notna()].copy()
        extra_df['table'] = 'ps_product_attribute'
        extra_df['id_proveedor'] = id_proveedor
        extra_df['hay_stock'] = 0
        extra_df["disponible"] = (
            pd.to_numeric(extra_df["quantity"], errors="coerce").fillna(0) > 0
        ).astype("int8")
        extra_df['stock_combinado'] = extra_df["disponible"]

        # Filtrar combinaciones ya presentes
        ids_atributos_existentes = set(
            pd.to_numeric(
                df_fusionado.get("id_product_attribute"),
                errors="coerce",
            ).dropna().astype(int)
        )
        extra_df = extra_df[
            ~extra_df["id_product_attribute"].isin(ids_atributos_existentes)
        ]

        df_fusionado = pd.concat([df_fusionado, extra_df], ignore_index=True)
        df_fusionado = df_fusionado.drop_duplicates(
            subset=["id_product", "id_product_attribute", "table"],
            keep="first",
        )

        logging.info(f"🟡 Añadidas {len(extra_df)} combinaciones desde BD del proveedor {id_proveedor} por coincidencia con id_product en PrestaShop.")

        return df_fusionado

    except Exception as e:
        logging.exception(
            "Error al añadir referencias relacionadas del proveedor %s",
            id_proveedor,
        )
        raise RuntimeError(
            f"No se pudieron añadir referencias relacionadas del proveedor {id_proveedor}"
        ) from e

def previsualizar_visibilidad_productos_ocultos(
    conexion_prestashop,
    metricas=None,
):
    """Lista productos que corregiría visibilidad, sin escribir en la BD."""

    consulta = """
        SELECT
            p.id_product,
            p.reference,
            p.ean13,
            m.name AS marca,
            p.active,
            p.visibility AS visibility_product,
            MAX(s.quantity) AS quantity_max,
            GROUP_CONCAT(
                DISTINCT CONCAT(ps.id_shop, ':', ps.visibility)
                ORDER BY ps.id_shop SEPARATOR ','
            ) AS visibility_shops
        FROM ps_product p
        INNER JOIN ps_stock_available s
            ON s.id_product = p.id_product
            AND s.id_product_attribute = 0
        LEFT JOIN ps_product_shop ps
            ON ps.id_product = p.id_product
        LEFT JOIN ps_manufacturer m
            ON m.id_manufacturer = p.id_manufacturer
        WHERE p.active = 1
          AND p.visibility = 'none'
        GROUP BY
            p.id_product,
            p.reference,
            p.ean13,
            m.name,
            p.active,
            p.visibility
        HAVING MAX(s.quantity) > 0
        ORDER BY p.id_product
    """
    with medir_fase(metricas, "Consulta de PrestaShop"):
        candidatos = pd.read_sql(consulta, conexion_prestashop)
    logging.info(
        "Previsualización de visibilidad: %s candidatos",
        len(candidatos),
    )
    return candidatos


# Corrección de visibilidad de productos ocultos con stock
def corregir_visibilidad_productos_ocultos(
    conexion_prestashop,
    metricas=None,
    solo_previsualizar=False,
):
    """
    Corrige la visibilidad de los productos activos que tienen stock pero están ocultos (visibility = 'none').

    Actualiza tanto ps_product como ps_product_shop a visibility = 'both'
    Solo afecta a productos con stock > 0 y active = 1
    Registra en log cuántos productos fueron corregidos
    """
    try:
        candidatos = previsualizar_visibilidad_productos_ocultos(
            conexion_prestashop,
            metricas=metricas,
        )
        ids_ocultos = (
            pd.to_numeric(candidatos["id_product"], errors="coerce")
            .dropna()
            .astype(int)
            .drop_duplicates()
            .tolist()
            if not candidatos.empty
            else []
        )
        if solo_previsualizar:
            logging.info(
                "Visibilidad en report-only: %s candidatos; 0 escrituras",
                len(ids_ocultos),
            )
            return candidatos
        with conexion_prestashop.cursor() as cursor:
            if not ids_ocultos:
                logging.info("✅ No se encontraron productos con stock y visibilidad 'none'.")
                return candidatos

            logging.info(f"🔄 Corrigiendo visibilidad de {len(ids_ocultos)} productos ocultos con stock...")

            placeholders = ','.join(['%s'] * len(ids_ocultos))

            # Actualizar visibilidad en ps_product
            update_product = f"""
                UPDATE ps_product
                SET visibility = 'both'
                WHERE id_product IN ({placeholders})
            """
            cursor.execute(update_product, ids_ocultos)

            # Actualizar visibilidad en ps_product_shop (para todas las tiendas registradas)
            update_product_shop = f"""
                UPDATE ps_product_shop
                SET visibility = 'both'
                WHERE id_product IN ({placeholders})
            """
            cursor.execute(update_product_shop, ids_ocultos)

            commit_con_metricas(conexion_prestashop, metricas)

            logging.info(f"✅ Visibilidad corregida para {len(ids_ocultos)} productos.")

        return candidatos

    except Exception as e:
        conexion_prestashop.rollback()
        logging.exception("Error al corregir visibilidad de productos ocultos")
        raise RuntimeError(
            "No se pudo corregir la visibilidad de productos ocultos"
        ) from e
