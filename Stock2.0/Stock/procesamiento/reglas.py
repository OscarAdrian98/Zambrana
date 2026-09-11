"""Reglas puras compartidas por el procesamiento de stock.

Este módulo no accede a bases de datos ni a servicios externos. Centraliza las
normalizaciones que deben comportarse igual en todos los flujos.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Optional

import pandas as pd


IDENTIFICADORES_AUSENTES = {
    "",
    "none",
    "nan",
    "nat",
    "null",
    "<na>",
}

TEXTOS_CON_STOCK = {
    "yes",
    "si",
    "sí",
    "y",
    "true",
    "mas de 3 uds",
    "9+",
    "mas de 5",
    "5 o menos",
    "10+",
}

TEXTOS_SIN_STOCK = {
    "no",
    "n",
    "false",
    "-",
    "sin stock",
}


def normalizar_identificador(valor) -> Optional[str]:
    """Devuelve un identificador canónico o ``None`` si no es válido.

    Las cadenas conservan sus ceros iniciales. Los números enteros que Pandas
    haya leído como ``float`` pierden únicamente el sufijo artificial ``.0``.
    """

    if valor is None:
        return None

    try:
        ausente = pd.isna(valor)
        if isinstance(ausente, bool) and ausente:
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(valor, bool):
        texto = str(valor)
    elif isinstance(valor, int):
        texto = str(valor)
    elif isinstance(valor, (float, Decimal)):
        numero = float(valor)
        if numero != numero:
            return None
        texto = str(int(numero)) if numero.is_integer() else str(valor)
    else:
        texto = str(valor).strip()

    texto = texto.strip()
    if texto.casefold() in IDENTIFICADORES_AUSENTES:
        return None
    return texto


def normalizar_serie_identificadores(serie: pd.Series) -> pd.Series:
    """Normaliza una serie dejando ``pd.NA`` en identificadores ausentes."""

    # Los lectores CSV/TXT entregan columnas homogéneas de texto. En esa ruta
    # habitual podemos conservar exactamente la semántica escalar sin entrar
    # una vez por celda en Python. Los tipos mixtos (incluidos float/Decimal,
    # cuyo tratamiento de ``.0`` es deliberado) mantienen la ruta escalar.
    tipo_inferido = pd.api.types.infer_dtype(serie, skipna=True)
    if tipo_inferido in {"string", "empty"}:
        resultado = serie.astype("string").str.strip()
        ausentes = resultado.str.casefold().isin(IDENTIFICADORES_AUSENTES)
        return resultado.mask(ausentes, pd.NA)
    return serie.map(normalizar_identificador).astype("string")


def normalizar_ean(valor) -> Optional[str]:
    """Normaliza un EAN/GTIN y descarta marcadores textuales del proveedor."""

    normalizado = normalizar_identificador(valor)
    if (
        normalizado is None
        or not normalizado.isascii()
        or not normalizado.isdigit()
    ):
        return None
    return normalizado


def normalizar_serie_ean(serie: pd.Series) -> pd.Series:
    """Normaliza una serie de EAN conservando ceros iniciales."""

    normalizados = normalizar_serie_identificadores(serie)
    validos = normalizados.str.fullmatch(r"[0-9]+", na=False)
    return normalizados.where(validos, pd.NA).astype("string")


def normalizar_serie_stock(serie: pd.Series) -> pd.Series:
    """Versión vectorizada de :func:`normalizar_stock`."""

    textos = serie.astype("string").str.strip().str.casefold()
    resultado = pd.Series(0, index=serie.index, dtype="int8")
    resultado.loc[textos.isin(TEXTOS_CON_STOCK)] = 1
    pendientes = ~(
        textos.isin(TEXTOS_CON_STOCK)
        | textos.isin(TEXTOS_SIN_STOCK)
        | textos.isin(IDENTIFICADORES_AUSENTES)
        | textos.isna()
    )
    if pendientes.any():
        numeros = pd.to_numeric(
            textos.loc[pendientes].str.replace(",", ".", regex=False),
            errors="coerce",
        )
        resultado.loc[pendientes] = (
            (numeros > 0).fillna(False).astype("int8")
        )
    return resultado


def conjunto_eans_validos(valores: Iterable) -> set[str]:
    """Construye un conjunto que excluye EAN vacíos o textuales."""

    return {
        normalizado
        for valor in valores
        if (normalizado := normalizar_ean(valor)) is not None
    }


def conjunto_identificadores_validos(valores: Iterable) -> set[str]:
    """Construye un conjunto sin permitir identificadores ausentes."""

    resultado = set()
    for valor in valores:
        normalizado = normalizar_identificador(valor)
        if normalizado is not None:
            resultado.add(normalizado)
    return resultado


def normalizar_stock(valor) -> int:
    """Normaliza textos y cantidades a disponibilidad binaria.

    Una cantidad numérica solo está disponible cuando es estrictamente mayor
    que cero.
    """

    if valor is None:
        return 0
    try:
        if bool(pd.isna(valor)):
            return 0
    except (TypeError, ValueError):
        return 0

    texto = str(valor).strip().casefold()
    if texto in TEXTOS_CON_STOCK:
        return 1
    if texto in TEXTOS_SIN_STOCK or texto in IDENTIFICADORES_AUSENTES:
        return 0

    try:
        numero = float(texto.replace(",", "."))
    except (TypeError, ValueError):
        return 0
    return int(numero > 0)


def calcular_disponibilidad(cantidad_prestashop, stock_proveedor) -> int:
    """Aplica la regla: PrestaShop > 0 O proveedor disponible."""

    try:
        cantidad = float(cantidad_prestashop)
        prestashop_disponible = cantidad > 0
    except (TypeError, ValueError):
        prestashop_disponible = False
    return int(prestashop_disponible or normalizar_stock(stock_proveedor) > 0)


def calcular_disponibilidad_series(
    cantidades_prestashop: pd.Series,
    stock_proveedor: pd.Series,
) -> pd.Series:
    """Versión vectorizada de :func:`calcular_disponibilidad`."""

    cantidad = pd.to_numeric(cantidades_prestashop, errors="coerce").fillna(0)
    proveedor = pd.to_numeric(stock_proveedor, errors="coerce").fillna(0)
    return ((cantidad > 0) | (proveedor > 0)).astype("int8")


def valor_configurado(valor) -> bool:
    """Indica si un valor opcional de configuración está presente."""

    return normalizar_identificador(valor) is not None


def normalizar_indice_columna(
    valor,
    campo: str,
    numero_columnas: Optional[int],
    *,
    id_proveedor=None,
    opcional: bool = False,
) -> Optional[int]:
    """Valida un índice posicional y devuelve un entero.

    ``numero_columnas`` puede ser ``None`` durante la lectura inicial, cuando
    todavía no se conoce la anchura del fichero.
    """

    contexto = f" para proveedor {id_proveedor}" if id_proveedor is not None else ""
    columnas_disponibles = (
        f"; el fichero tiene {numero_columnas} columnas"
        if numero_columnas is not None
        else ""
    )
    if not valor_configurado(valor):
        if opcional:
            return None
        raise ValueError(
            f"Configuración inválida{contexto}: {campo} está ausente"
            f"{columnas_disponibles}"
        )

    if isinstance(valor, bool):
        raise ValueError(
            f"Configuración inválida{contexto}: {campo}={valor!r} no es un índice entero"
            f"{columnas_disponibles}"
        )

    texto = str(valor).strip()
    try:
        indice = int(texto)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Configuración inválida{contexto}: {campo}={valor!r} no es un índice entero"
            f"{columnas_disponibles}"
        ) from exc

    if texto not in {str(indice), f"+{indice}"}:
        raise ValueError(
            f"Configuración inválida{contexto}: {campo}={valor!r} no es un índice entero"
            f"{columnas_disponibles}"
        )
    if indice < 0:
        raise ValueError(
            f"Configuración inválida{contexto}: {campo}={indice} no puede ser negativo"
            f"{columnas_disponibles}"
        )
    if numero_columnas is not None and indice >= numero_columnas:
        raise ValueError(
            f"Configuración inválida{contexto}: {campo}={indice}; "
            f"el fichero tiene {numero_columnas} columnas"
        )
    return indice


def normalizar_indices_configuracion(
    configuracion: dict,
    numero_columnas: int,
    id_proveedor,
) -> dict:
    """Devuelve una copia con los cuatro índices de fichero validados."""

    resultado = dict(configuracion)
    campos = {
        "col_referencia_configuracion": False,
        "col_referencia_alternativa_configuracion": True,
        "col_stock_configuracion": False,
        "col_ean_configuracion": True,
        "col_fecha_configuracion": True,
    }
    for campo, opcional in campos.items():
        resultado[campo] = normalizar_indice_columna(
            resultado.get(campo),
            campo,
            numero_columnas,
            id_proveedor=id_proveedor,
            opcional=opcional,
        )
    return resultado


def validar_duplicados_proveedor(
    dataframe: pd.DataFrame,
    *,
    id_proveedor=None,
) -> pd.DataFrame:
    """Elimina duplicados idénticos y rechaza referencias contradictorias."""

    if "referencia" not in dataframe.columns:
        raise ValueError("El DataFrame del proveedor no contiene 'referencia'")

    resultado = dataframe.copy()
    resultado["referencia"] = normalizar_serie_identificadores(
        resultado["referencia"]
    )
    resultado = resultado[resultado["referencia"].notna()].copy()
    duplicadas = resultado[
        resultado["referencia"].duplicated(keep=False)
    ]
    if duplicadas.empty:
        return resultado

    columnas_comparacion = [
        columna
        for columna in resultado.columns
        if columna != "referencia"
    ]
    conflictos = []
    for referencia, grupo in duplicadas.groupby("referencia", sort=True):
        variantes = grupo[columnas_comparacion].astype("string").fillna("<NA>")
        if len(variantes.drop_duplicates()) > 1:
            conflictos.append(referencia)

    if conflictos:
        contexto = (
            f" del proveedor {id_proveedor}"
            if id_proveedor is not None
            else ""
        )
        muestra = ", ".join(conflictos[:10])
        raise ValueError(
            f"Referencias duplicadas con datos contradictorios{contexto}: {muestra}"
        )
    return resultado.drop_duplicates(subset=["referencia"], keep="first")


def elegir_fecha_disponibilidad(
    fechas: Iterable,
    disponibilidades: Iterable,
    *,
    hoy: Optional[date] = None,
) -> pd.Timestamp:
    """Elige de forma determinista la fecha válida más cercana.

    Conserva la ventana histórica existente de 30 días. Se priorizan filas con
    stock; dentro del grupo elegido se usa la menor distancia a hoy y, en caso
    de empate, la fecha anterior.
    """

    hoy = hoy or datetime.now().date()
    fecha_minima = hoy - timedelta(days=30)
    candidatos = []

    for fecha, disponible in zip(fechas, disponibilidades):
        fecha_parseada = pd.to_datetime(fecha, errors="coerce")
        if pd.isna(fecha_parseada):
            continue
        fecha_normalizada = pd.Timestamp(fecha_parseada).normalize()
        if fecha_normalizada.date() < fecha_minima:
            continue
        candidatos.append((fecha_normalizada, normalizar_stock(disponible)))

    if not candidatos:
        return pd.NaT

    con_stock = [item for item in candidatos if item[1] > 0]
    elegibles = con_stock or candidatos
    elegibles.sort(
        key=lambda item: (
            abs((item[0].date() - hoy).days),
            item[0],
        )
    )
    return elegibles[0][0]


@dataclass(frozen=True)
class EstadisticasCruce:
    coincidencias_ean: int = 0
    coincidencias_referencia: int = 0
    sin_coincidencia: int = 0
    ean_duplicados: int = 0
    referencias_duplicadas: int = 0
    conflictos: int = 0


@dataclass(frozen=True)
class EstadisticasCruceAlternativa(EstadisticasCruce):
    matches_referencia_principal: int = 0
    matches_referencia_alternativa: int = 0
    matches_ean: int = 0
    referencias_alternativas_ambiguas: int = 0
    conflictos_identificadores: int = 0


@dataclass
class ResultadoCruce:
    coincidencias: pd.DataFrame
    sin_coincidencia: pd.DataFrame
    conflictos: pd.DataFrame
    estadisticas: EstadisticasCruce


def _numero_valores_duplicados(serie: pd.Series) -> int:
    conteos = serie.dropna().value_counts()
    return int((conteos > 1).sum())


def _cruzar_catalogos_sin_alternativa(
    proveedor_df: pd.DataFrame,
    prestashop_df: pd.DataFrame,
    *,
    id_proveedor=None,
) -> ResultadoCruce:
    """Cruza primero por EAN único y después por referencia única.

    Los identificadores ausentes y los valores duplicados nunca producen una
    coincidencia automática.
    """

    proveedor = proveedor_df.copy().reset_index(drop=True)
    prestashop = prestashop_df.copy().reset_index(drop=True)

    if id_proveedor is not None and "id_proveedor" in proveedor.columns:
        proveedor = proveedor[proveedor["id_proveedor"] == id_proveedor].copy()

    proveedor["_fila_proveedor"] = range(len(proveedor))
    prestashop["_fila_prestashop"] = range(len(prestashop))
    proveedor["_ref_normalizada"] = normalizar_serie_identificadores(
        proveedor.get("referencia", pd.Series(pd.NA, index=proveedor.index))
    )
    prestashop["_ref_normalizada"] = normalizar_serie_identificadores(
        prestashop.get("reference", pd.Series(pd.NA, index=prestashop.index))
    )
    proveedor["_ean_normalizado"] = normalizar_serie_ean(
        proveedor.get("ean", pd.Series(pd.NA, index=proveedor.index))
    )
    prestashop["_ean_normalizado"] = normalizar_serie_ean(
        prestashop.get("ean13", pd.Series(pd.NA, index=prestashop.index))
    )

    ean_duplicados = (
        _numero_valores_duplicados(proveedor["_ean_normalizado"])
        + _numero_valores_duplicados(prestashop["_ean_normalizado"])
    )
    referencias_duplicadas = (
        _numero_valores_duplicados(proveedor["_ref_normalizada"])
        + _numero_valores_duplicados(prestashop["_ref_normalizada"])
    )

    conteo_ean_proveedor = proveedor["_ean_normalizado"].value_counts()
    conteo_ean_prestashop = prestashop["_ean_normalizado"].value_counts()
    ean_presentes_en_ambos = set(conteo_ean_proveedor.index) & set(
        conteo_ean_prestashop.index
    )
    ean_ambiguos = {
        ean
        for ean in ean_presentes_en_ambos
        if conteo_ean_proveedor[ean] != 1
        or conteo_ean_prestashop[ean] != 1
    }
    conflictos_ean_ambiguo = proveedor[
        proveedor["_ean_normalizado"].isin(ean_ambiguos)
    ].copy()
    conflictos_ean_ambiguo["motivo_conflicto"] = "ean_duplicado_ambiguo"
    ean_unicos_proveedor = set(conteo_ean_proveedor[conteo_ean_proveedor == 1].index)
    ean_unicos_prestashop = set(conteo_ean_prestashop[conteo_ean_prestashop == 1].index)
    ean_comunes = ean_unicos_proveedor & ean_unicos_prestashop

    coincidencias_ean = proveedor[
        proveedor["_ean_normalizado"].isin(ean_comunes)
    ].merge(
        prestashop[prestashop["_ean_normalizado"].isin(ean_comunes)],
        on="_ean_normalizado",
        how="inner",
        suffixes=("", "_prestashop"),
        validate="one_to_one",
    )

    mapa_ref_prestashop = (
        prestashop.dropna(subset=["_ref_normalizada"])
        .groupby("_ref_normalizada")["_fila_prestashop"]
        .agg(list)
    )
    if coincidencias_ean.empty:
        conflicto_mask = pd.Series(False, index=coincidencias_ean.index, dtype=bool)
    else:
        conflicto_mask = coincidencias_ean.apply(
            lambda fila: (
                pd.notna(fila.get("_ref_normalizada"))
                and fila.get("_ref_normalizada") in mapa_ref_prestashop
                and len(mapa_ref_prestashop[fila.get("_ref_normalizada")]) == 1
                and mapa_ref_prestashop[fila.get("_ref_normalizada")][0]
                != fila["_fila_prestashop"]
            ),
            axis=1,
        ).astype(bool)
    conflictos_identidad = coincidencias_ean[conflicto_mask].copy()
    conflictos_identidad["motivo_conflicto"] = (
        "ean_referencia_destinos_distintos"
    )
    coincidencias_ean = coincidencias_ean[~conflicto_mask].copy()
    coincidencias_ean["tipo_coincidencia"] = "ean"

    conflictos = pd.concat(
        [conflictos_ean_ambiguo, conflictos_identidad],
        ignore_index=True,
        sort=False,
    )
    filas_proveedor_en_conflicto = set(conflictos["_fila_proveedor"])
    filas_proveedor_usadas = (
        set(coincidencias_ean["_fila_proveedor"]) | filas_proveedor_en_conflicto
    )
    filas_prestashop_usadas = set(coincidencias_ean["_fila_prestashop"])
    proveedor_restante = proveedor[
        ~proveedor["_fila_proveedor"].isin(filas_proveedor_usadas)
    ]
    prestashop_restante = prestashop[
        ~prestashop["_fila_prestashop"].isin(filas_prestashop_usadas)
    ]

    conteo_ref_proveedor = proveedor["_ref_normalizada"].value_counts()
    conteo_ref_prestashop = prestashop["_ref_normalizada"].value_counts()
    referencias_presentes_en_ambos = set(conteo_ref_proveedor.index) & set(
        conteo_ref_prestashop.index
    )
    referencias_ambiguas = {
        referencia
        for referencia in referencias_presentes_en_ambos
        if conteo_ref_proveedor[referencia] != 1
        or conteo_ref_prestashop[referencia] != 1
    }
    conflictos_referencia = proveedor_restante[
        proveedor_restante["_ref_normalizada"].isin(referencias_ambiguas)
    ].copy()
    conflictos_referencia["motivo_conflicto"] = (
        "referencia_duplicada_ambigua"
    )
    if not conflictos_referencia.empty:
        filas_nuevas_en_conflicto = set(
            conflictos_referencia["_fila_proveedor"]
        )
        filas_proveedor_en_conflicto.update(filas_nuevas_en_conflicto)
        proveedor_restante = proveedor_restante[
            ~proveedor_restante["_fila_proveedor"].isin(
                filas_nuevas_en_conflicto
            )
        ]
        conflictos = pd.concat(
            [conflictos, conflictos_referencia],
            ignore_index=True,
            sort=False,
        )
    referencias_comunes = (
        set(conteo_ref_proveedor[conteo_ref_proveedor == 1].index)
        & set(conteo_ref_prestashop[conteo_ref_prestashop == 1].index)
    )

    coincidencias_ref = proveedor_restante[
        proveedor_restante["_ref_normalizada"].isin(referencias_comunes)
    ].merge(
        prestashop_restante[
            prestashop_restante["_ref_normalizada"].isin(referencias_comunes)
        ],
        on="_ref_normalizada",
        how="inner",
        suffixes=("", "_prestashop"),
        validate="one_to_one",
    )
    coincidencias_ref["tipo_coincidencia"] = "referencia"

    coincidencias = pd.concat(
        [coincidencias_ean, coincidencias_ref],
        ignore_index=True,
        sort=False,
    )
    filas_proveedor_emparejadas = (
        set(coincidencias["_fila_proveedor"]) | filas_proveedor_en_conflicto
    )
    sin_coincidencia = proveedor[
        ~proveedor["_fila_proveedor"].isin(filas_proveedor_emparejadas)
    ].copy()

    columnas_auxiliares = {
        "_fila_proveedor",
        "_fila_prestashop",
        "_ref_normalizada",
        "_ref_normalizada_prestashop",
        "_ean_normalizado",
        "_ean_normalizado_prestashop",
    }
    coincidencias.drop(
        columns=[c for c in columnas_auxiliares if c in coincidencias.columns],
        inplace=True,
    )
    sin_coincidencia.drop(
        columns=[c for c in columnas_auxiliares if c in sin_coincidencia.columns],
        inplace=True,
    )

    estadisticas = EstadisticasCruce(
        coincidencias_ean=len(coincidencias_ean),
        coincidencias_referencia=len(coincidencias_ref),
        sin_coincidencia=len(sin_coincidencia),
        ean_duplicados=ean_duplicados,
        referencias_duplicadas=referencias_duplicadas,
        conflictos=len(conflictos),
    )
    return ResultadoCruce(
        coincidencias=coincidencias,
        sin_coincidencia=sin_coincidencia,
        conflictos=conflictos,
        estadisticas=estadisticas,
    )


def _clave_destino(fila: dict) -> tuple[int, int]:
    atributo = fila.get("id_product_attribute")
    return (
        int(fila["id_product"]),
        0 if atributo is None or pd.isna(atributo) else int(atributo),
    )


def _prioridad_fila_prestashop(fila: dict) -> tuple[int, int]:
    prioridad = {
        "ps_product_attribute": 0,
        "ps_product": 1,
        "ps_product_supplier": 2,
    }
    return (
        prioridad.get(str(fila.get("source")), 99),
        int(fila.get("_fila_prestashop", 0)),
    )


def _indexar_destinos_exactos(
    prestashop: pd.DataFrame,
    columna: str,
) -> dict[str, dict[tuple[int, int], dict]]:
    """Agrupa coincidencias exactas por destino, no por fila SQL."""

    indice = {}
    # ``groupby`` seguido de ``to_dict`` por grupo crea un DataFrame y una
    # lista por cada referencia. En el catalogo real eso suponia unas 92 000
    # materializaciones. Un unico recorrido conserva exactamente la misma
    # agrupacion y prioridad con coste lineal.
    for fila in prestashop.to_dict("records"):
        identificador = fila.get(columna)
        if identificador is None or pd.isna(identificador):
            continue
        destinos = indice.setdefault(identificador, {})
        clave = _clave_destino(fila)
        anterior = destinos.get(clave)
        if anterior is None or _prioridad_fila_prestashop(
            fila
        ) < _prioridad_fila_prestashop(anterior):
            destinos[clave] = fila
    return indice


def _registrar_etapa_alt(nombre, inicio, filas_entrada, filas_salida):
    logging.info(
        "Referencia alternativa FIN etapa=%s duracion=%.3fs "
        "filas_entrada=%s filas_salida=%s",
        nombre,
        time.perf_counter() - inicio,
        filas_entrada,
        filas_salida,
    )


def _iniciar_etapa_alt(nombre, filas_entrada):
    logging.info(
        "Referencia alternativa INICIO etapa=%s filas_entrada=%s",
        nombre,
        filas_entrada,
    )
    return time.perf_counter()


def _combinar_fila_destino(fuente: dict, destino: dict) -> dict:
    resultado = {
        clave: valor
        for clave, valor in fuente.items()
        if not clave.startswith("_")
    }
    for clave, valor in destino.items():
        if clave.startswith("_"):
            continue
        nombre = clave if clave not in resultado else f"{clave}_prestashop"
        resultado[nombre] = valor
    return resultado


def _cruzar_catalogos_con_alternativa(
    proveedor_df: pd.DataFrame,
    prestashop_df: pd.DataFrame,
    *,
    id_proveedor=None,
) -> ResultadoCruce:
    """Resuelve principal, alternativa y EAN sin ocultar contradicciones."""

    proveedor = proveedor_df.copy().reset_index(drop=True)
    prestashop = prestashop_df.copy().reset_index(drop=True)
    if id_proveedor is not None and "id_proveedor" in proveedor.columns:
        proveedor = proveedor[proveedor["id_proveedor"] == id_proveedor].copy()
        proveedor.reset_index(drop=True, inplace=True)

    proveedor["_fila_proveedor"] = range(len(proveedor))
    prestashop["_fila_prestashop"] = range(len(prestashop))
    inicio = _iniciar_etapa_alt("normalizacion_principal", len(proveedor))
    proveedor["_ref_normalizada"] = normalizar_serie_identificadores(
        proveedor.get("referencia", pd.Series(pd.NA, index=proveedor.index))
    )
    _registrar_etapa_alt(
        "normalizacion_principal",
        inicio,
        len(proveedor),
        int(proveedor["_ref_normalizada"].notna().sum()),
    )
    inicio = _iniciar_etapa_alt("normalizacion_alternativa", len(proveedor))
    proveedor["_alt_normalizada"] = normalizar_serie_identificadores(
        proveedor.get(
            "referencia_alternativa",
            pd.Series(pd.NA, index=proveedor.index),
        )
    )
    _registrar_etapa_alt(
        "normalizacion_alternativa",
        inicio,
        len(proveedor),
        int(proveedor["_alt_normalizada"].notna().sum()),
    )
    inicio = _iniciar_etapa_alt("normalizacion_ean", len(proveedor))
    proveedor["_ean_normalizado"] = normalizar_serie_ean(
        proveedor.get("ean", pd.Series(pd.NA, index=proveedor.index))
    )
    prestashop["_ref_normalizada"] = normalizar_serie_identificadores(
        prestashop.get("reference", pd.Series(pd.NA, index=prestashop.index))
    )
    prestashop["_ean_normalizado"] = normalizar_serie_ean(
        prestashop.get("ean13", pd.Series(pd.NA, index=prestashop.index))
    )
    _registrar_etapa_alt(
        "normalizacion_ean",
        inicio,
        len(proveedor) + len(prestashop),
        int(proveedor["_ean_normalizado"].notna().sum())
        + int(prestashop["_ean_normalizado"].notna().sum()),
    )

    inicio = _iniciar_etapa_alt("indices_prestashop", len(prestashop))
    indice_ref = _indexar_destinos_exactos(prestashop, "_ref_normalizada")
    indice_ean = _indexar_destinos_exactos(prestashop, "_ean_normalizado")
    _registrar_etapa_alt(
        "indices_prestashop",
        inicio,
        len(prestashop),
        len(indice_ref) + len(indice_ean),
    )
    inicio = _iniciar_etapa_alt("deteccion_ambiguos", len(proveedor))
    identidades_por_alt = (
        proveedor.dropna(subset=["_alt_normalizada", "_ref_normalizada"])
        .groupby("_alt_normalizada")["_ref_normalizada"]
        .nunique()
    )
    alternativas_ambiguas = set(
        identidades_por_alt[identidades_por_alt > 1].index
    )
    conteo_ean_fuente = proveedor.groupby("_ean_normalizado", dropna=True)[
        "_ref_normalizada"
    ].nunique()
    _registrar_etapa_alt(
        "deteccion_ambiguos",
        inicio,
        len(proveedor),
        len(alternativas_ambiguas),
    )

    coincidencias = []
    conflictos = []
    conteos = {
        "referencia_principal": 0,
        "referencia_alternativa": 0,
        "ean": 0,
    }

    def buscar(metodo, valor, indice, *, ambiguo_fuente=False):
        if valor is None:
            return None, None
        if ambiguo_fuente:
            if valor in indice:
                motivo = (
                    "referencia_alternativa_ambigua_en_proveedor"
                    if metodo == "referencia_alternativa"
                    else "ean_duplicado_ambiguo"
                )
                return None, motivo
            return None, None
        destinos = indice.get(valor, {})
        if len(destinos) > 1:
            return None, f"{metodo}_ambiguo_en_prestashop"
        if len(destinos) == 1:
            clave, destino = next(iter(destinos.items()))
            return (metodo, valor, clave, destino), None
        return None, None

    referencias = proveedor["_ref_normalizada"].astype(object).where(
        proveedor["_ref_normalizada"].notna(), None
    ).tolist()
    alternativas = proveedor["_alt_normalizada"].astype(object).where(
        proveedor["_alt_normalizada"].notna(), None
    ).tolist()
    eans = proveedor["_ean_normalizado"].astype(object).where(
        proveedor["_ean_normalizado"].notna(), None
    ).tolist()

    inicio = _iniciar_etapa_alt("matching_principal", len(proveedor))
    candidatos_principal = [
        buscar("referencia_principal", valor, indice_ref)
        for valor in referencias
    ]
    _registrar_etapa_alt(
        "matching_principal", inicio, len(proveedor),
        sum(candidato is not None for candidato, _ in candidatos_principal),
    )
    inicio = _iniciar_etapa_alt("matching_alternativa", len(proveedor))
    candidatos_alternativa = [
        (None, None)
        if valor == principal
        else buscar(
            "referencia_alternativa",
            valor,
            indice_ref,
            ambiguo_fuente=valor in alternativas_ambiguas,
        )
        for principal, valor in zip(referencias, alternativas)
    ]
    _registrar_etapa_alt(
        "matching_alternativa", inicio, len(proveedor),
        sum(candidato is not None for candidato, _ in candidatos_alternativa),
    )
    inicio = _iniciar_etapa_alt("matching_ean", len(proveedor))
    candidatos_ean = [
        buscar(
            "ean",
            valor,
            indice_ean,
            ambiguo_fuente=(
                valor is not None and int(conteo_ean_fuente.get(valor, 0)) > 1
            ),
        )
        for valor in eans
    ]
    _registrar_etapa_alt(
        "matching_ean", inicio, len(proveedor),
        sum(candidato is not None for candidato, _ in candidatos_ean),
    )

    columnas_visibles = [
        columna for columna in proveedor.columns if not columna.startswith("_")
    ]
    sin_coincidencia_indices = []
    for posicion, resultados in enumerate(zip(
        candidatos_principal,
        candidatos_alternativa,
        candidatos_ean,
    )):
        destinos_por_metodo = [
            candidato for candidato, _motivo in resultados
            if candidato is not None
        ]
        motivos = [
            motivo for _candidato, motivo in resultados if motivo is not None
        ]
        fila = None
        if motivos or destinos_por_metodo:
            fila = proveedor.iloc[posicion].to_dict()
        if motivos or len({elemento[2] for elemento in destinos_por_metodo}) > 1:
            claves = {elemento[2] for elemento in destinos_por_metodo}
            conflicto = {
                clave: valor
                for clave, valor in fila.items()
                if not clave.startswith("_")
            }
            conflicto["motivo_conflicto"] = (
                motivos[0]
                if motivos
                else "identificadores_exactos_destinos_distintos"
            )
            conflicto["destinos_candidatos"] = tuple(sorted(claves))
            conflictos.append(conflicto)
            continue
        if not destinos_por_metodo:
            sin_coincidencia_indices.append(posicion)
            continue

        metodo, valor, _clave, destino = destinos_por_metodo[0]
        coincidencia = _combinar_fila_destino(fila, destino)
        coincidencia["tipo_coincidencia"] = metodo
        coincidencia["match_method"] = metodo
        coincidencia["match_value"] = valor
        coincidencias.append(coincidencia)
        conteos[metodo] += 1

    coincidencias_df = pd.DataFrame(coincidencias)
    sin_coincidencia_df = proveedor.loc[
        sin_coincidencia_indices, columnas_visibles
    ].reset_index(drop=True).copy()
    conflictos_df = pd.DataFrame(conflictos)
    estadisticas = EstadisticasCruceAlternativa(
        coincidencias_ean=conteos["ean"],
        coincidencias_referencia=(
            conteos["referencia_principal"]
            + conteos["referencia_alternativa"]
        ),
        sin_coincidencia=len(sin_coincidencia_df),
        ean_duplicados=int((conteo_ean_fuente > 1).sum()),
        referencias_duplicadas=_numero_valores_duplicados(
            proveedor["_ref_normalizada"]
        ),
        conflictos=len(conflictos_df),
        matches_referencia_principal=conteos["referencia_principal"],
        matches_referencia_alternativa=conteos["referencia_alternativa"],
        matches_ean=conteos["ean"],
        referencias_alternativas_ambiguas=len(alternativas_ambiguas),
        conflictos_identificadores=len(conflictos_df),
    )
    return ResultadoCruce(
        coincidencias=coincidencias_df,
        sin_coincidencia=sin_coincidencia_df,
        conflictos=conflictos_df,
        estadisticas=estadisticas,
    )


def cruzar_catalogos(
    proveedor_df: pd.DataFrame,
    prestashop_df: pd.DataFrame,
    *,
    id_proveedor=None,
) -> ResultadoCruce:
    """Conserva el cruce histÃ³rico salvo cuando existe la alternativa."""

    if "referencia_alternativa" not in proveedor_df.columns:
        return _cruzar_catalogos_sin_alternativa(
            proveedor_df,
            prestashop_df,
            id_proveedor=id_proveedor,
        )
    return _cruzar_catalogos_con_alternativa(
        proveedor_df,
        prestashop_df,
        id_proveedor=id_proveedor,
    )


def filtrar_candidatos_reactivacion(
    candidatos: pd.DataFrame,
    *,
    marcas_proveedor: Iterable,
    referencias_proveedor: Iterable,
    eans_proveedor: Iterable,
    referencias_con_stock: Iterable,
    eans_con_stock: Iterable,
) -> pd.DataFrame:
    """Filtra candidatos por marca, pertenencia y disponibilidad."""

    df = candidatos.copy()
    marcas = {
        str(marca).strip().casefold()
        for marca in marcas_proveedor
        if normalizar_identificador(marca) is not None
    }
    refs = conjunto_identificadores_validos(referencias_proveedor)
    eans = conjunto_eans_validos(eans_proveedor)
    refs_stock = conjunto_identificadores_validos(referencias_con_stock)
    eans_stock = conjunto_eans_validos(eans_con_stock)

    df["_marca"] = df.get("marca", pd.Series(pd.NA, index=df.index)).map(
        lambda valor: str(valor).strip().casefold()
        if normalizar_identificador(valor) is not None
        else None
    )
    df["_ref"] = normalizar_serie_identificadores(
        df.get("reference", pd.Series(pd.NA, index=df.index))
    )
    df["_ean"] = normalizar_serie_ean(
        df.get("ean13", pd.Series(pd.NA, index=df.index))
    )
    df["_ref_supplier"] = normalizar_serie_identificadores(
        df.get("supplier_reference", pd.Series(pd.NA, index=df.index))
    )

    pertenece = (
        df["_ref"].isin(refs)
        | df["_ean"].isin(eans)
        | df["_ref_supplier"].isin(refs)
    )
    proveedor_con_stock = (
        df["_ref"].isin(refs_stock)
        | df["_ean"].isin(eans_stock)
        | df["_ref_supplier"].isin(refs_stock)
    )
    cantidad_local = pd.to_numeric(
        df.get("quantity", pd.Series(0, index=df.index)), errors="coerce"
    ).fillna(0)
    resultado = df[
        df["_marca"].isin(marcas)
        & pertenece
        & ((cantidad_local > 0) | proveedor_con_stock)
    ].copy()
    return resultado.drop(
        columns=["_marca", "_ref", "_ean", "_ref_supplier"],
        errors="ignore",
    )
