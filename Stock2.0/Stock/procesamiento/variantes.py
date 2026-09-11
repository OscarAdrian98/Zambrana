"""Normalización y persistencia transaccional de variantes de proveedor."""

from __future__ import annotations
from config.provider_rules import OPEN_QUANTITY_PROVIDER_ID, FTPS_PROVIDER_ID

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import pandas as pd

from config.bd import (
    BASE_PROVEEDORES_ACTIVA,
    TIPO_PROVEEDORES,
    validar_conexion_configurada,
)
from procesamiento.reglas import (
    normalizar_ean,
    normalizar_identificador,
    normalizar_serie_ean,
    normalizar_serie_identificadores,
    normalizar_serie_stock,
)


TAMANO_LOTE_VARIANTES = 1000


@dataclass(frozen=True)
class EstadisticasPreparacionVariantes:
    filas_fuente: int
    filas_validas: int
    variantes: int
    duplicados_exactos: int
    referencias_invalidas: int
    ean_ausentes: int
    conflictos: int


@dataclass
class ResultadoPreparacionVariantes:
    dataframe: pd.DataFrame
    estadisticas: EstadisticasPreparacionVariantes
    conflictos: pd.DataFrame = field(default_factory=pd.DataFrame)
    descartadas: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass(frozen=True)
class ResultadoPersistenciaVariantes:
    ejecucion_id: str
    variantes_recibidas: int
    variantes_insertadas: int
    variantes_actualizadas_funcionales: int
    variantes_actualizadas_metadatos: int
    variantes_sin_cambio_funcional: int
    variantes_marcadas_ausentes: int
    resumenes_insertados: int
    resumenes_actualizados_funcionales: int
    resumenes_sin_cambio_funcional: int
    sentencias_sql: int
    commits: int
    tamano_lote: int
    duraciones: dict[str, float]

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResultadoBackfillVariantes:
    ejecucion_id: str
    filas_leidas: int
    filas_validas: int
    insertadas: int
    ya_existentes: int
    actualizadas_funcionales: int
    conflictos: int
    descartadas: int
    sentencias_sql: int
    commits: int
    duracion_segundos: float

    def como_dict(self) -> dict:
        return asdict(self)


class ConflictoVariantesError(ValueError):
    """Indica que una identidad de variante tiene datos incompatibles."""

    def __init__(self, conflictos: pd.DataFrame):
        self.conflictos = conflictos.copy()
        referencias = (
            conflictos["referencia"].dropna().astype(str).drop_duplicates()
            if "referencia" in conflictos
            else pd.Series(dtype=str)
        )
        muestra = ", ".join(referencias.head(10))
        super().__init__(
            f"{len(conflictos)} filas conflictivas de variantes"
            + (f": {muestra}" if muestra else "")
        )


def construir_clave_variante(referencia, ean) -> str:
    referencia_normalizada = normalizar_identificador(referencia)
    if referencia_normalizada is None:
        raise ValueError("No se puede crear una variante sin referencia")
    ean_normalizado = normalizar_ean(ean)
    if ean_normalizado is not None:
        return f"EAN:{ean_normalizado}"
    return f"REF:{referencia_normalizada}"


def _normalizar_fecha(valor):
    fecha = pd.to_datetime(valor, errors="coerce")
    if pd.isna(fecha):
        return pd.NaT
    return pd.Timestamp(fecha).normalize()


def _normalizar_stock_texto(valor) -> str:
    if valor is None or bool(pd.isna(valor)):
        return ""
    return str(valor).strip()


def _cantidad_decimal(
    valor,
    *,
    permitir_cantidad_abierta: bool = False,
) -> Optional[Decimal]:
    texto = _normalizar_stock_texto(valor).replace(",", ".")
    if not texto:
        return None
    if permitir_cantidad_abierta and texto.endswith("+"):
        texto = texto[:-1].strip()
    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    if not numero.is_finite():
        return None
    return numero.quantize(Decimal("0.001"))


def preparar_variantes(
    dataframe: pd.DataFrame,
    *,
    id_proveedor: Optional[int] = None,
    identificadores_normalizados: bool = False,
) -> ResultadoPreparacionVariantes:
    """Normaliza, deduplica y detecta conflictos sin depender del orden."""

    if "referencia" not in dataframe.columns:
        raise ValueError("El fichero no contiene la columna 'referencia'")

    inicio = time.perf_counter()
    trabajo = dataframe.copy()
    filas_fuente = len(trabajo)
    if identificadores_normalizados:
        trabajo["referencia"] = trabajo["referencia"].astype("string")
    else:
        trabajo["referencia"] = normalizar_serie_identificadores(
            trabajo["referencia"]
        )
    if "ean" not in trabajo.columns:
        trabajo["ean"] = pd.Series(pd.NA, index=trabajo.index, dtype="string")
    else:
        trabajo["ean"] = (
            trabajo["ean"].astype("string")
            if identificadores_normalizados
            else normalizar_serie_ean(trabajo["ean"])
        )
    if "referencia_alternativa" in trabajo.columns:
        trabajo["referencia_alternativa"] = (
            trabajo["referencia_alternativa"].astype("string")
            if identificadores_normalizados
            else normalizar_serie_identificadores(
                trabajo["referencia_alternativa"]
            )
        )
    if "stock" not in trabajo.columns:
        trabajo["stock"] = ""
    trabajo["stock"] = trabajo["stock"].astype("string").fillna("").str.strip()
    disponibilidad_stock = normalizar_serie_stock(trabajo["stock"])
    if "hay_stock" in trabajo.columns:
        disponibilidad_declarada = pd.to_numeric(
            trabajo["hay_stock"],
            errors="coerce",
        )
        trabajo["hay_stock"] = (
            disponibilidad_declarada.fillna(disponibilidad_stock) > 0
        ).astype("int8")
    else:
        trabajo["hay_stock"] = disponibilidad_stock.astype("int8")

    columna_fecha = (
        "fecha_mas_cercana"
        if "fecha_mas_cercana" in trabajo.columns
        else None
    )
    if columna_fecha:
        trabajo[columna_fecha] = pd.to_datetime(
            trabajo[columna_fecha], errors="coerce"
        ).dt.normalize()
        trabajo["fecha_disponibilidad_producto"] = trabajo[columna_fecha]
    else:
        trabajo["fecha_disponibilidad_producto"] = pd.NaT

    mascara_invalida = trabajo["referencia"].isna()
    descartadas = trabajo[mascara_invalida].copy()
    trabajo = trabajo[~mascara_invalida].copy()
    trabajo["clave_variante"] = (
        "EAN:" + trabajo["ean"]
    ).where(
        trabajo["ean"].notna(),
        "REF:" + trabajo["referencia"],
    ).astype("string")
    trabajo["stock_cantidad_producto"] = trabajo["stock"].map(
        lambda valor: _cantidad_decimal(
            valor,
            permitir_cantidad_abierta=id_proveedor == OPEN_QUANTITY_PROVIDER_ID,
        )
    )

    columnas_identidad = ["referencia", "clave_variante"]
    columnas_negocio = [
        "ean",
        "stock",
        "hay_stock",
        "fecha_disponibilidad_producto",
    ]
    if "id_marca" in trabajo.columns:
        columnas_negocio.append("id_marca")
    if "referencia_alternativa" in trabajo.columns:
        columnas_negocio.append("referencia_alternativa")
    antes_deduplicar = len(trabajo)
    trabajo = trabajo.drop_duplicates(
        subset=[*columnas_identidad, *columnas_negocio],
        keep="first",
    ).copy()
    duplicados_exactos = antes_deduplicar - len(trabajo)

    mascara_conflicto = trabajo.duplicated(
        subset=columnas_identidad,
        keep=False,
    )
    if mascara_conflicto.any():
        conflictos = trabajo.loc[mascara_conflicto].copy()
        conflictos["motivo_conflicto"] = "identidad_con_datos_incompatibles"
        validas = trabajo.loc[~mascara_conflicto].copy()
    else:
        conflictos = pd.DataFrame(columns=[*trabajo.columns, "motivo_conflicto"])
        validas = trabajo

    validas.sort_values(
        ["referencia", "clave_variante"],
        kind="stable",
        inplace=True,
    )
    validas.reset_index(drop=True, inplace=True)
    estadisticas = EstadisticasPreparacionVariantes(
        filas_fuente=filas_fuente,
        filas_validas=len(trabajo),
        variantes=len(validas),
        duplicados_exactos=duplicados_exactos,
        referencias_invalidas=len(descartadas),
        ean_ausentes=int(validas["ean"].isna().sum()),
        conflictos=len(conflictos),
    )
    validas.attrs["estadisticas_variantes"] = asdict(estadisticas)
    validas.attrs["duracion_preparacion_segundos"] = (
        time.perf_counter() - inicio
    )
    return ResultadoPreparacionVariantes(
        dataframe=validas,
        estadisticas=estadisticas,
        conflictos=conflictos,
        descartadas=descartadas,
    )


def preparar_variantes_o_fallar(
    dataframe: pd.DataFrame,
    *,
    id_proveedor: Optional[int] = None,
    identificadores_normalizados: bool = False,
) -> pd.DataFrame:
    resultado = preparar_variantes(
        dataframe,
        id_proveedor=id_proveedor,
        identificadores_normalizados=identificadores_normalizados,
    )
    if not resultado.conflictos.empty:
        contexto = (
            f" del proveedor {id_proveedor}"
            if id_proveedor is not None
            else ""
        )
        logging.error(
            "Conflictos de variantes%s: %s filas",
            contexto,
            len(resultado.conflictos),
        )
        raise ConflictoVariantesError(resultado.conflictos)
    return resultado.dataframe


def generar_resumen_variantes(
    variantes: pd.DataFrame,
    *,
    hoy: Optional[date] = None,
) -> pd.DataFrame:
    """Genera una fila determinista de `productos` por referencia."""

    hoy = hoy or datetime.now().date()
    if variantes.empty:
        return pd.DataFrame(
            columns=[
                "id_proveedor",
                "id_marca",
                "referencia_producto",
                "ean_producto",
                "stock_cantidad_producto",
                "stock_txt_producto",
                "hay_stock_producto",
                "fecha_disponibilidad_producto",
                "fecha_actualizacion_producto",
            ]
        )

    trabajo = variantes.copy()
    if "presente_ultima_ejecucion" not in trabajo:
        trabajo["presente_ultima_ejecucion"] = 1
    trabajo["presente_ultima_ejecucion"] = pd.to_numeric(
        trabajo["presente_ultima_ejecucion"], errors="coerce"
    ).fillna(0)
    trabajo["hay_stock_producto"] = pd.to_numeric(
        trabajo.get("hay_stock_producto", trabajo.get("hay_stock", 0)),
        errors="coerce",
    ).fillna(0)
    if "referencia_producto" not in trabajo:
        trabajo["referencia_producto"] = trabajo["referencia"]
    if "ean_producto" not in trabajo:
        trabajo["ean_producto"] = trabajo.get("ean")
    if "fecha_disponibilidad_producto" not in trabajo:
        trabajo["fecha_disponibilidad_producto"] = trabajo.get(
            "fecha_mas_cercana"
        )

    claves = ["id_proveedor", "referencia_producto"]
    presentes = trabajo["presente_ultima_ejecucion"].gt(0)
    grupo_presente = presentes.groupby(
        [trabajo[columna] for columna in claves]
    ).transform("any")
    base_identidad = presentes | ~grupo_presente

    grupos = (
        trabajo[claves]
        .drop_duplicates()
        .sort_values(claves, kind="stable")
        .reset_index(drop=True)
    )
    indice_grupos = pd.MultiIndex.from_frame(grupos[claves])

    marcas = pd.to_numeric(
        trabajo.get("id_marca", pd.Series(pd.NA, index=trabajo.index)),
        errors="coerce",
    ).where(base_identidad)
    marcas_validas = trabajo.loc[marcas.notna(), claves].copy()
    marcas_validas["_marca"] = marcas.dropna().astype("int64")
    agregadas_marca = marcas_validas.groupby(claves)["_marca"].agg(
        ["nunique", "first"]
    )
    marca_unica = agregadas_marca["first"].where(
        agregadas_marca["nunique"].eq(1)
    ).reindex(indice_grupos)

    eans = normalizar_serie_ean(
        trabajo.get("ean_producto", pd.Series(pd.NA, index=trabajo.index))
    ).where(presentes)
    eans_validos = trabajo.loc[eans.notna(), claves].copy()
    eans_validos["_ean"] = eans.dropna()
    agregados_ean = eans_validos.groupby(claves)["_ean"].agg(
        ["nunique", "first"]
    )
    ean_unico = agregados_ean["first"].where(
        agregados_ean["nunique"].eq(1)
    ).reindex(indice_grupos)

    disponibilidad_fila = presentes & trabajo["hay_stock_producto"].gt(0)
    disponibilidad = disponibilidad_fila.groupby(
        [trabajo[columna] for columna in claves]
    ).max().astype("int8").reindex(indice_grupos, fill_value=0)

    fechas = pd.to_datetime(
        trabajo.get(
            "fecha_disponibilidad_producto",
            pd.Series(pd.NaT, index=trabajo.index),
        ),
        errors="coerce",
    ).dt.normalize()
    hoy_timestamp = pd.Timestamp(hoy)
    fecha_valida = presentes & fechas.notna() & fechas.ge(
        hoy_timestamp - pd.Timedelta(days=30)
    )
    valida_con_stock = fecha_valida & trabajo["hay_stock_producto"].gt(0)
    grupo_fecha_con_stock = valida_con_stock.groupby(
        [trabajo[columna] for columna in claves]
    ).transform("any")
    elegible = fecha_valida & (
        ~grupo_fecha_con_stock | trabajo["hay_stock_producto"].gt(0)
    )
    fechas_elegibles = trabajo.loc[elegible, claves].copy()
    fechas_elegibles["_fecha"] = fechas.loc[elegible]
    fechas_elegibles["_distancia"] = (
        fechas_elegibles["_fecha"] - hoy_timestamp
    ).abs()
    fecha_elegida = (
        fechas_elegibles.sort_values(
            [*claves, "_distancia", "_fecha"], kind="stable"
        )
        .drop_duplicates(claves, keep="first")
        .set_index(claves)["_fecha"]
        .reindex(indice_grupos)
    )

    resultado = grupos.copy()
    resultado["id_proveedor"] = resultado["id_proveedor"].astype("int64")
    resultado["id_marca"] = (
        marca_unica.astype(object).where(marca_unica.notna(), None).to_numpy()
    )
    resultado["ean_producto"] = (
        ean_unico.astype(object).where(ean_unico.notna(), None).to_numpy()
    )
    resultado["stock_cantidad_producto"] = None
    resultado["stock_txt_producto"] = disponibilidad.map({0: "0", 1: "1"}).array
    resultado["hay_stock_producto"] = disponibilidad.array
    fechas_resultado = fecha_elegida.dt.date.astype(object)
    resultado["fecha_disponibilidad_producto"] = (
        fechas_resultado.where(fecha_elegida.notna(), None).to_numpy()
    )
    resultado["fecha_actualizacion_producto"] = hoy
    return resultado[
        [
            "id_proveedor",
            "id_marca",
            "referencia_producto",
            "ean_producto",
            "stock_cantidad_producto",
            "stock_txt_producto",
            "hay_stock_producto",
            "fecha_disponibilidad_producto",
            "fecha_actualizacion_producto",
        ]
    ]


def _en_lotes(valores, tamano):
    for inicio in range(0, len(valores), tamano):
        yield valores[inicio : inicio + tamano]


def _fecha_sql(valor):
    fecha = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(fecha) else pd.Timestamp(fecha).date()


def _valor_sql(valor):
    if valor is None:
        return None
    try:
        if bool(pd.isna(valor)):
            return None
    except (TypeError, ValueError):
        pass
    return valor


def _tupla_funcional_variante(fila) -> tuple:
    return (
        _valor_sql(fila.get("id_marca")),
        _valor_sql(fila.get("id_configuracion_origen")),
        str(fila.get("estado_clasificacion_marca") or "monomarca"),
        str(fila.get("metodo_resolucion_marca") or "monomarca"),
        normalizar_ean(fila.get("ean_producto")),
        _valor_sql(fila.get("stock_cantidad_producto")),
        _valor_sql(fila.get("stock_txt_producto")),
        int(fila.get("hay_stock_producto") or 0),
        _fecha_sql(fila.get("fecha_disponibilidad_producto")),
        int(fila.get("presente_ultima_ejecucion", 1) or 0),
    )


def _preparar_filas_sql(
    dataframe: pd.DataFrame,
    *,
    id_proveedor: int,
    id_marca: Optional[int],
    ejecucion_id: str,
    hoy: date,
) -> list[tuple]:
    trabajo = dataframe.copy()
    valores_por_defecto = {
        "id_marca": id_marca,
        "id_configuracion_origen": None,
        "estado_clasificacion_marca": "monomarca",
        "metodo_resolucion_marca": "monomarca",
        "ean": pd.NA,
        "stock_cantidad_producto": None,
        "stock": "",
        "hay_stock": 0,
        "fecha_disponibilidad_producto": pd.NaT,
    }
    for columna, valor in valores_por_defecto.items():
        if columna not in trabajo:
            trabajo[columna] = valor
    if id_marca is not None:
        trabajo["id_marca"] = trabajo["id_marca"].fillna(id_marca)
    trabajo["estado_clasificacion_marca"] = (
        trabajo["estado_clasificacion_marca"].fillna("monomarca").astype(str)
    )
    trabajo["metodo_resolucion_marca"] = (
        trabajo["metodo_resolucion_marca"].fillna("monomarca").astype(str)
    )
    fechas = pd.to_datetime(
        trabajo["fecha_disponibilidad_producto"], errors="coerce"
    ).dt.date
    columnas = [
        "id_marca",
        "id_configuracion_origen",
        "estado_clasificacion_marca",
        "metodo_resolucion_marca",
        "referencia",
        "ean",
        "clave_variante",
        "stock_cantidad_producto",
        "stock",
        "hay_stock",
    ]
    filas = []
    for indice, fila in enumerate(
        trabajo[columnas].itertuples(index=False, name=None)
    ):
        marca, configuracion, estado, metodo, referencia, ean, clave, cantidad, stock, hay_stock = fila
        filas.append(
            (
                id_proveedor,
                None if pd.isna(marca) else int(marca),
                _valor_sql(configuracion),
                estado,
                metodo,
                referencia,
                None if pd.isna(ean) else ean,
                clave,
                _valor_sql(cantidad),
                stock,
                int(hay_stock),
                None if pd.isna(fechas.iloc[indice]) else fechas.iloc[indice],
                hoy,
                ejecucion_id,
                1,
            )
        )
    return filas


SQL_UPSERT_VARIANTES = """
    INSERT INTO productos_variantes (
        id_proveedor,
        id_marca,
        id_configuracion_origen,
        estado_clasificacion_marca,
        metodo_resolucion_marca,
        referencia_producto,
        ean_producto,
        clave_variante,
        stock_cantidad_producto,
        stock_txt_producto,
        hay_stock_producto,
        fecha_disponibilidad_producto,
        fecha_actualizacion_producto,
        ultima_ejecucion_id,
        presente_ultima_ejecucion
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        id_marca = VALUES(id_marca),
        id_configuracion_origen = VALUES(id_configuracion_origen),
        estado_clasificacion_marca = VALUES(estado_clasificacion_marca),
        metodo_resolucion_marca = VALUES(metodo_resolucion_marca),
        ean_producto = VALUES(ean_producto),
        stock_cantidad_producto = VALUES(stock_cantidad_producto),
        stock_txt_producto = VALUES(stock_txt_producto),
        hay_stock_producto = VALUES(hay_stock_producto),
        fecha_disponibilidad_producto =
            VALUES(fecha_disponibilidad_producto),
        fecha_actualizacion_producto =
            VALUES(fecha_actualizacion_producto),
        ultima_ejecucion_id = VALUES(ultima_ejecucion_id),
        presente_ultima_ejecucion =
            VALUES(presente_ultima_ejecucion)
"""


SQL_UPSERT_RESUMEN = """
    INSERT INTO productos (
        id_proveedor,
        id_marca,
        referencia_producto,
        ean_producto,
        stock_cantidad_producto,
        stock_txt_producto,
        hay_stock_producto,
        fecha_disponibilidad_producto,
        fecha_actualizacion_producto
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        id_marca = VALUES(id_marca),
        ean_producto = VALUES(ean_producto),
        stock_cantidad_producto = VALUES(stock_cantidad_producto),
        stock_txt_producto = VALUES(stock_txt_producto),
        hay_stock_producto = VALUES(hay_stock_producto),
        fecha_disponibilidad_producto =
            VALUES(fecha_disponibilidad_producto),
        fecha_actualizacion_producto =
            VALUES(fecha_actualizacion_producto)
"""


SQL_MARCAR_VARIANTES_AUSENTES_LOTE = """
    UPDATE productos_variantes
    SET
        presente_ultima_ejecucion = 0,
        hay_stock_producto = 0,
        stock_cantidad_producto = 0,
        stock_txt_producto = '0',
        fecha_actualizacion_producto = %s,
        ultima_ejecucion_id = %s
    WHERE id_proveedor = %s
      AND presente_ultima_ejecucion = 1
      AND (referencia_producto, clave_variante) IN ({claves})
"""


def _marcar_variantes_ausentes_lote(
    cursor,
    claves,
    *,
    hoy,
    ejecucion_id,
    id_proveedor,
):
    """Marca un lote con un solo UPDATE por conjuntos."""

    if not claves:
        return
    placeholders = ", ".join(["(%s, %s)"] * len(claves))
    sql = SQL_MARCAR_VARIANTES_AUSENTES_LOTE.format(claves=placeholders)
    parametros = [hoy, ejecucion_id, id_proveedor]
    for referencia, clave in claves:
        parametros.extend((referencia, clave))
    cursor.execute(sql, tuple(parametros))


def _inicio_persistencia(id_proveedor, etapa, filas):
    logging.info(
        "Persistencia proveedor %s INICIO etapa=%s filas_entrada=%s",
        id_proveedor,
        etapa,
        filas,
    )
    return time.perf_counter()


def _fin_persistencia(id_proveedor, etapa, inicio, filas):
    duracion = time.perf_counter() - inicio
    logging.info(
        "Persistencia proveedor %s FIN etapa=%s duracion=%.3fs "
        "filas_salida=%s",
        id_proveedor,
        etapa,
        duracion,
        filas,
    )
    return duracion


def persistir_variantes_y_resumen(
    conexion,
    dataframe: pd.DataFrame,
    *,
    id_proveedor: int,
    id_marca: Optional[int],
    ejecucion_id: Optional[str] = None,
    tamano_lote: int = TAMANO_LOTE_VARIANTES,
    hoy: Optional[date] = None,
) -> ResultadoPersistenciaVariantes:
    """Persiste variantes y resumen con un único commit por proveedor."""

    validar_conexion_configurada(
        conexion,
        BASE_PROVEEDORES_ACTIVA,
        tipo_conexion=TIPO_PROVEEDORES,
    )
    if dataframe.empty:
        raise ValueError("No se persiste un fichero de variantes vacío")
    if tamano_lote <= 0:
        raise ValueError("El tamaño de lote debe ser positivo")
    ejecucion_id = ejecucion_id or str(uuid.uuid4())
    if len(ejecucion_id) != 36:
        raise ValueError("ejecucion_id debe ser un UUID textual de 36 caracteres")
    hoy = hoy or datetime.now().date()
    duraciones = {}
    sentencias = 0
    commits = 0

    inicio = _inicio_persistencia(
        id_proveedor, "normalizacion_sql", len(dataframe)
    )
    filas_sql = _preparar_filas_sql(
        dataframe,
        id_proveedor=id_proveedor,
        id_marca=id_marca,
        ejecucion_id=ejecucion_id,
        hoy=hoy,
    )
    duraciones["normalizacion_sql"] = _fin_persistencia(
        id_proveedor, "normalizacion_sql", inicio, len(filas_sql)
    )

    try:
        conexion.rollback()
        conexion.begin()
        with conexion.cursor() as cursor:
            inicio = _inicio_persistencia(
                id_proveedor, "deteccion_cambios", len(filas_sql)
            )
            cursor.execute(
                """
                SELECT
                    referencia_producto,
                    clave_variante,
                    id_marca,
                    id_configuracion_origen,
                    estado_clasificacion_marca,
                    metodo_resolucion_marca,
                    ean_producto,
                    stock_cantidad_producto,
                    stock_txt_producto,
                    hay_stock_producto,
                    fecha_disponibilidad_producto,
                    presente_ultima_ejecucion
                FROM productos_variantes
                WHERE id_proveedor = %s
                """,
                (id_proveedor,),
            )
            sentencias += 1
            existentes = {}
            for fila in cursor.fetchall():
                datos = {
                    "id_marca": fila[2],
                    "id_configuracion_origen": fila[3],
                    "estado_clasificacion_marca": fila[4],
                    "metodo_resolucion_marca": fila[5],
                    "ean_producto": fila[6],
                    "stock_cantidad_producto": fila[7],
                    "stock_txt_producto": fila[8],
                    "hay_stock_producto": fila[9],
                    "fecha_disponibilidad_producto": fila[10],
                    "presente_ultima_ejecucion": fila[11],
                }
                existentes[(str(fila[0]), str(fila[1]))] = (
                    _tupla_funcional_variante(datos)
                )

            insertadas = 0
            actualizadas_funcionales = 0
            sin_cambio_funcional = 0
            filas_cambiadas = []
            claves_actuales = set()
            for fila in filas_sql:
                clave = (str(fila[5]), str(fila[7]))
                claves_actuales.add(clave)
                funcional = (
                    fila[1],
                    fila[2],
                    fila[3],
                    fila[4],
                    fila[6],
                    fila[8],
                    fila[9],
                    fila[10],
                    fila[11],
                    fila[14],
                )
                if clave not in existentes:
                    insertadas += 1
                    filas_cambiadas.append(fila)
                elif existentes[clave] != funcional:
                    actualizadas_funcionales += 1
                    filas_cambiadas.append(fila)
                else:
                    sin_cambio_funcional += 1
            duraciones["deteccion_cambios"] = _fin_persistencia(
                id_proveedor,
                "deteccion_cambios",
                inicio,
                len(filas_cambiadas),
            )

            inicio = _inicio_persistencia(
                id_proveedor, "upsert_variantes", len(filas_cambiadas)
            )
            for lote in _en_lotes(filas_cambiadas, tamano_lote):
                cursor.executemany(SQL_UPSERT_VARIANTES, lote)
                sentencias += 1
            duraciones["upsert_variantes"] = _fin_persistencia(
                id_proveedor,
                "upsert_variantes",
                inicio,
                len(filas_cambiadas),
            )

            inicio = _inicio_persistencia(
                id_proveedor, "marcado_ausentes", len(existentes)
            )
            claves_ausentes = [
                clave
                for clave, funcional in existentes.items()
                if clave not in claves_actuales
                and funcional[-1] == 1
                and (id_marca is None or funcional[0] == id_marca)
            ]
            for lote in _en_lotes(claves_ausentes, tamano_lote):
                _marcar_variantes_ausentes_lote(
                    cursor,
                    lote,
                    hoy=hoy,
                    ejecucion_id=ejecucion_id,
                    id_proveedor=id_proveedor,
                )
                sentencias += 1
            ausentes = len(claves_ausentes)
            duraciones["marcado_ausentes"] = _fin_persistencia(
                id_proveedor, "marcado_ausentes", inicio, ausentes
            )

            inicio = _inicio_persistencia(
                id_proveedor, "generacion_resumenes", len(existentes)
            )
            cursor.execute(
                """
                SELECT
                    id_proveedor,
                    id_marca,
                    referencia_producto,
                    ean_producto,
                    stock_cantidad_producto,
                    stock_txt_producto,
                    hay_stock_producto,
                    fecha_disponibilidad_producto,
                    presente_ultima_ejecucion
                FROM productos_variantes
                WHERE id_proveedor = %s
                ORDER BY referencia_producto, clave_variante
                """,
                (id_proveedor,),
            )
            sentencias += 1
            columnas = [
                "id_proveedor",
                "id_marca",
                "referencia_producto",
                "ean_producto",
                "stock_cantidad_producto",
                "stock_txt_producto",
                "hay_stock_producto",
                "fecha_disponibilidad_producto",
                "presente_ultima_ejecucion",
            ]
            variantes_db = pd.DataFrame(cursor.fetchall(), columns=columnas)
            resumenes = generar_resumen_variantes(variantes_db, hoy=hoy)
            duraciones["generacion_resumenes"] = _fin_persistencia(
                id_proveedor,
                "generacion_resumenes",
                inicio,
                len(resumenes),
            )

            inicio = _inicio_persistencia(
                id_proveedor, "upsert_resumenes", len(resumenes)
            )
            cursor.execute(
                """
                SELECT
                    id_proveedor,
                    id_marca,
                    referencia_producto,
                    ean_producto,
                    stock_cantidad_producto,
                    stock_txt_producto,
                    hay_stock_producto,
                    fecha_disponibilidad_producto,
                    fecha_actualizacion_producto
                FROM productos
                WHERE id_proveedor = %s
                """,
                (id_proveedor,),
            )
            sentencias += 1
            resumen_existente = {
                str(fila[2]): tuple(fila) for fila in cursor.fetchall()
            }
            filas_resumen = [
                tuple(_valor_sql(valor) for valor in fila)
                for fila in resumenes[
                    [
                        "id_proveedor",
                        "id_marca",
                        "referencia_producto",
                        "ean_producto",
                        "stock_cantidad_producto",
                        "stock_txt_producto",
                        "hay_stock_producto",
                        "fecha_disponibilidad_producto",
                        "fecha_actualizacion_producto",
                    ]
                ].itertuples(index=False, name=None)
            ]
            resumen_insertado = 0
            resumen_actualizado = 0
            resumen_sin_cambio = 0
            filas_resumen_cambiadas = []
            for fila in filas_resumen:
                existente = resumen_existente.get(str(fila[2]))
                if existente is None:
                    resumen_insertado += 1
                    filas_resumen_cambiadas.append(fila)
                elif existente[:8] != fila[:8]:
                    resumen_actualizado += 1
                    filas_resumen_cambiadas.append(fila)
                else:
                    resumen_sin_cambio += 1
            for lote in _en_lotes(filas_resumen_cambiadas, tamano_lote):
                cursor.executemany(SQL_UPSERT_RESUMEN, lote)
                sentencias += 1
            duraciones["upsert_resumenes"] = _fin_persistencia(
                id_proveedor,
                "upsert_resumenes",
                inicio,
                len(filas_resumen_cambiadas),
            )

        conexion.commit()
        commits = 1
    except Exception:
        conexion.rollback()
        raise

    return ResultadoPersistenciaVariantes(
        ejecucion_id=ejecucion_id,
        variantes_recibidas=len(filas_sql),
        variantes_insertadas=insertadas,
        variantes_actualizadas_funcionales=actualizadas_funcionales,
        variantes_actualizadas_metadatos=0,
        variantes_sin_cambio_funcional=sin_cambio_funcional,
        variantes_marcadas_ausentes=ausentes,
        resumenes_insertados=resumen_insertado,
        resumenes_actualizados_funcionales=resumen_actualizado,
        resumenes_sin_cambio_funcional=resumen_sin_cambio,
        sentencias_sql=sentencias,
        commits=commits,
        tamano_lote=tamano_lote,
        duraciones=duraciones,
    )


def ejecutar_backfill_productos(
    conexion,
    *,
    id_proveedor: int,
    tamano_lote: int = TAMANO_LOTE_VARIANTES,
    ejecucion_id: Optional[str] = None,
) -> ResultadoBackfillVariantes:
    """Copia el resumen histórico a variantes sin modificar `productos`."""

    validar_conexion_configurada(
        conexion,
        BASE_PROVEEDORES_ACTIVA,
        tipo_conexion=TIPO_PROVEEDORES,
    )
    inicio_total = time.perf_counter()
    ejecucion_id = ejecucion_id or str(uuid.uuid4())
    hoy = datetime.now().date()
    sentencias = 0
    try:
        conexion.rollback()
        conexion.begin()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id_proveedor,
                    id_marca,
                    referencia_producto,
                    ean_producto,
                    stock_cantidad_producto,
                    stock_txt_producto,
                    hay_stock_producto,
                    fecha_disponibilidad_producto
                FROM productos
                WHERE id_proveedor = %s
                ORDER BY id_producto
                """,
                (id_proveedor,),
            )
            sentencias += 1
            columnas = [
                "id_proveedor",
                "id_marca",
                "referencia",
                "ean",
                "stock_cantidad_producto",
                "stock",
                "hay_stock",
                "fecha_mas_cercana",
            ]
            historico = pd.DataFrame(cursor.fetchall(), columns=columnas)
            preparacion = preparar_variantes(
                historico,
                id_proveedor=id_proveedor,
            )
            if not preparacion.conflictos.empty:
                raise ConflictoVariantesError(preparacion.conflictos)
            preparado = preparacion.dataframe.copy()

            cursor.execute(
                """
                SELECT referencia_producto, clave_variante,
                       id_marca, id_configuracion_origen,
                       estado_clasificacion_marca,
                       metodo_resolucion_marca,
                       ean_producto, stock_cantidad_producto,
                       stock_txt_producto, hay_stock_producto,
                       fecha_disponibilidad_producto,
                       presente_ultima_ejecucion
                FROM productos_variantes
                WHERE id_proveedor = %s
                """,
                (id_proveedor,),
            )
            sentencias += 1
            existentes = {
                (str(fila[0]), str(fila[1])): _tupla_funcional_variante(
                    {
                        "id_marca": fila[2],
                        "id_configuracion_origen": fila[3],
                        "estado_clasificacion_marca": fila[4],
                        "metodo_resolucion_marca": fila[5],
                        "ean_producto": fila[6],
                        "stock_cantidad_producto": fila[7],
                        "stock_txt_producto": fila[8],
                        "hay_stock_producto": fila[9],
                        "fecha_disponibilidad_producto": fila[10],
                        "presente_ultima_ejecucion": fila[11],
                    }
                )
                for fila in cursor.fetchall()
            }
            filas_sql = _preparar_filas_sql(
                preparado,
                id_proveedor=id_proveedor,
                id_marca=None,
                ejecucion_id=ejecucion_id,
                hoy=hoy,
            )
            insertadas = 0
            actualizadas = 0
            ya_existentes = 0
            for fila in filas_sql:
                clave = (str(fila[5]), str(fila[7]))
                funcional = (
                    fila[1],
                    fila[2],
                    fila[3],
                    fila[4],
                    fila[6],
                    fila[8],
                    fila[9],
                    fila[10],
                    fila[11],
                    fila[14],
                )
                if clave not in existentes:
                    insertadas += 1
                elif existentes[clave] != funcional:
                    actualizadas += 1
                else:
                    ya_existentes += 1
            for lote in _en_lotes(filas_sql, tamano_lote):
                cursor.executemany(SQL_UPSERT_VARIANTES, lote)
                sentencias += 1
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    return ResultadoBackfillVariantes(
        ejecucion_id=ejecucion_id,
        filas_leidas=len(historico),
        filas_validas=len(preparado),
        insertadas=insertadas,
        ya_existentes=ya_existentes,
        actualizadas_funcionales=actualizadas,
        conflictos=len(preparacion.conflictos),
        descartadas=len(preparacion.descartadas),
        sentencias_sql=sentencias,
        commits=1,
        duracion_segundos=time.perf_counter() - inicio_total,
    )
