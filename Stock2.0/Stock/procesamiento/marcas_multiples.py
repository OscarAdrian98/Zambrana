"""Resolución determinista de marca para configuraciones multipmarca."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd

from procesamiento.reglas import (
    cruzar_catalogos,
    normalizar_ean,
    normalizar_identificador,
)


ESTADO_RESUELTA = "resuelta"
ESTADO_PENDIENTE = "pendiente"
METODO_EAN = "ean"
METODO_REFERENCIA = "referencia"
METODO_REFERENCIA_PRINCIPAL = "referencia_principal"
METODO_REFERENCIA_ALTERNATIVA = "referencia_alternativa"
METODO_HISTORICO = "historico"
METODO_PENDIENTE = "pendiente"


@dataclass(frozen=True)
class EstadisticasResolucionMarcas:
    filas: int
    resueltas_ean: int
    resueltas_referencia: int
    resueltas_historico: int
    pendientes: int
    conflictos: int
    fuera_marcas_permitidas: int
    ean_duplicados: int
    referencias_duplicadas: int
    marcas_fuente_no_coincidentes: int

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EstadisticasResolucionMarcasAlternativa(EstadisticasResolucionMarcas):
    resueltas_referencia_alternativa: int = 0
    sin_coincidencia: int = 0
    referencias_alternativas_ambiguas: int = 0
    conflictos_identificadores: int = 0


@dataclass
class ResultadoResolucionMarcas:
    dataframe: pd.DataFrame
    coincidencias: pd.DataFrame
    auditoria: pd.DataFrame
    conflictos: pd.DataFrame
    fuera_marcas_permitidas: pd.DataFrame
    pendientes: pd.DataFrame
    estadisticas: EstadisticasResolucionMarcas


class ResolucionMarcaInseguraError(ValueError):
    """Bloquea cualquier persistencia si la resolución no es inequívoca."""

    def __init__(self, resultado: ResultadoResolucionMarcas):
        self.resultado = resultado
        super().__init__(
            "Resolución multipmarca insegura: "
            f"conflictos={len(resultado.conflictos)}, "
            "fuera_marcas_permitidas="
            f"{len(resultado.fuera_marcas_permitidas)}"
        )


def _texto_exacto(valor):
    if normalizar_identificador(valor) is None:
        return None
    return str(valor).strip().casefold()


def _destino(fila) -> tuple[int, int]:
    return (
        int(fila["id_product"]),
        int(fila.get("id_product_attribute") or 0),
    )


def _prioridad_origen(fila) -> tuple:
    orden = {
        "ps_product_attribute": 0,
        "ps_product": 1,
        "ps_product_supplier": 2,
    }
    return (
        orden.get(str(fila.get("source")), 99),
        int(fila.get("_orden_prestashop", 0)),
    )


def _indice_destinos(prestashop: pd.DataFrame, columna: str) -> dict:
    indice = {}
    for fila in prestashop.to_dict("records"):
        identificador = fila.get(columna)
        if identificador is None or pd.isna(identificador):
            continue
        destinos = indice.setdefault(identificador, {})
        clave = (_destino(fila), _texto_exacto(fila.get("marca")))
        anterior = destinos.get(clave)
        if anterior is None or _prioridad_origen(fila) < _prioridad_origen(
            anterior
        ):
            destinos[clave] = fila
    return {
        identificador: list(destinos.values())
        for identificador, destinos in indice.items()
    }


def _indice_historico(
    historico: pd.DataFrame | None,
    marcas_permitidas: set[int],
) -> dict:
    if historico is None or historico.empty:
        return {}
    trabajo = historico.copy()
    trabajo["_ref"] = trabajo.get("referencia_producto").map(
        normalizar_identificador
    )
    trabajo["_ean"] = trabajo.get("ean_producto").map(normalizar_ean)
    trabajo["id_marca"] = pd.to_numeric(
        trabajo.get("id_marca"), errors="coerce"
    )
    trabajo = trabajo[
        trabajo["_ref"].notna()
        & trabajo["id_marca"].isin(marcas_permitidas)
    ]
    if "estado_clasificacion_marca" in trabajo:
        trabajo = trabajo[
            trabajo["estado_clasificacion_marca"].fillna("") != ESTADO_PENDIENTE
        ]
    trabajo["_clave_historica"] = list(
        zip(trabajo["_ref"], trabajo["_ean"].fillna(""))
    )
    marcas = trabajo.groupby("_clave_historica", sort=False)["id_marca"].agg(
        ["nunique", "first"]
    )
    unicas = marcas[marcas["nunique"] == 1]["first"].astype(int)
    return dict(unicas.items())


def _combinar_coincidencia(fila_fuente: dict, fila_ps: dict, metodo: str) -> dict:
    resultado = dict(fila_fuente)
    for clave, valor in fila_ps.items():
        if clave.startswith("_"):
            continue
        destino = clave if clave not in resultado else f"{clave}_prestashop"
        resultado[destino] = valor
    resultado["tipo_coincidencia"] = metodo
    return resultado


def _resolver_con_referencia_alternativa(
    proveedor_df,
    prestashop_df,
    *,
    alias_a_marca,
    ids_permitidos,
    id_marca_pendiente,
    id_configuracion,
    historico_df,
):
    """Aplica el cruce de tres identificadores antes de clasificar la marca."""

    atributos = dict(proveedor_df.attrs)
    fuente = proveedor_df.copy().reset_index(drop=True)
    fuente["fila_origen_resolucion"] = fuente.index
    fuente["_ref_normalizada"] = fuente["referencia"].map(
        normalizar_identificador
    )
    fuente["_alt_normalizada"] = fuente["referencia_alternativa"].map(
        normalizar_identificador
    )
    fuente["_ean_normalizado"] = fuente.get(
        "ean", pd.Series(pd.NA, index=fuente.index)
    ).map(normalizar_ean)
    historico = _indice_historico(historico_df, ids_permitidos)
    cruce = cruzar_catalogos(fuente, prestashop_df)
    coincidencias_por_fila = {
        int(fila["fila_origen_resolucion"]): fila
        for fila in cruce.coincidencias.to_dict("records")
    }
    conflictos_por_fila = {
        int(fila["fila_origen_resolucion"]): fila
        for fila in cruce.conflictos.to_dict("records")
    }

    auditoria = []
    coincidencias = []
    conflictos = []
    fuera = []
    pendientes = []
    marcas_resultado = []
    estados = []
    metodos = []
    marcas_fuente_no_coincidentes = 0

    for fila in fuente.to_dict("records"):
        indice = int(fila["fila_origen_resolucion"])
        destino = coincidencias_por_fila.get(indice)
        conflicto = conflictos_por_fila.get(indice)
        motivo = conflicto.get("motivo_conflicto") if conflicto else None
        metodo = destino.get("match_method") if destino else None
        destino_auditoria = destino
        id_marca = None

        if conflicto is not None:
            conflictos.append({**fila, "motivo_resolucion": motivo})

        if destino is not None:
            marca_fuente = _texto_exacto(fila.get("marca_fuente"))
            marca_destino = _texto_exacto(destino.get("marca"))
            if marca_fuente is not None and marca_fuente != marca_destino:
                motivo = "marca_fuente_no_coincide"
                marcas_fuente_no_coincidentes += 1
                pendientes.append({
                    **fila,
                    "marca_prestashop": destino.get("marca"),
                    "motivo_resolucion": motivo,
                })
                destino = None
                metodo = None

        if motivo is None and destino is not None:
            id_marca = alias_a_marca.get(_texto_exacto(destino.get("marca")))
            if id_marca is None:
                motivo = "fabricante_fuera_de_marcas_permitidas"
                fuera.append({
                    **fila,
                    "marca_prestashop": destino.get("marca"),
                    "motivo_resolucion": motivo,
                })
            else:
                coincidencia = dict(destino)
                coincidencia.pop("fila_origen_resolucion", None)
                coincidencia["id_marca"] = id_marca
                coincidencia["id_configuracion_origen"] = int(id_configuracion)
                coincidencia["estado_clasificacion_marca"] = ESTADO_RESUELTA
                coincidencia["metodo_resolucion_marca"] = metodo
                coincidencias.append(coincidencia)

        if motivo is not None:
            marcas_resultado.append(id_marca_pendiente)
            estados.append(ESTADO_PENDIENTE)
            metodos.append(METODO_PENDIENTE)
        elif destino is not None:
            marcas_resultado.append(id_marca)
            estados.append(ESTADO_RESUELTA)
            metodos.append(metodo)
        else:
            clave_historica = (
                fila["_ref_normalizada"],
                fila["_ean_normalizado"] or "",
            )
            id_historico = historico.get(clave_historica)
            if id_historico is not None:
                id_marca = id_historico
                estado = ESTADO_RESUELTA
                metodo = METODO_HISTORICO
            else:
                id_marca = id_marca_pendiente
                estado = ESTADO_PENDIENTE
                metodo = METODO_PENDIENTE
                motivo = "sin_correspondencia"
                pendientes.append({**fila, "motivo_resolucion": motivo})
            marcas_resultado.append(id_marca)
            estados.append(estado)
            metodos.append(metodo)

        auditoria.append({
            "fila_fuente": indice,
            "referencia": fila["_ref_normalizada"],
            "referencia_alternativa": fila["_alt_normalizada"],
            "ean": fila["_ean_normalizado"],
            "id_marca": marcas_resultado[-1],
            "estado": estados[-1],
            "metodo": metodos[-1],
            "match_method": (
                destino_auditoria.get("match_method")
                if destino_auditoria else None
            ),
            "match_value": (
                destino_auditoria.get("match_value")
                if destino_auditoria else None
            ),
            "marca_prestashop": (
                destino_auditoria.get("marca")
                if destino_auditoria else None
            ),
            "id_product": (
                destino_auditoria.get("id_product")
                if destino_auditoria else None
            ),
            "id_product_attribute": (
                destino_auditoria.get("id_product_attribute")
                if destino_auditoria else None
            ),
            "motivo": motivo,
        })

    fuente["id_marca"] = marcas_resultado
    fuente["id_configuracion_origen"] = int(id_configuracion)
    fuente["estado_clasificacion_marca"] = estados
    fuente["metodo_resolucion_marca"] = metodos
    fuente.drop(
        columns=[
            "fila_origen_resolucion",
            "_ref_normalizada",
            "_alt_normalizada",
            "_ean_normalizado",
        ],
        inplace=True,
    )
    fuente.attrs.update(atributos)
    estadisticas_cruce = cruce.estadisticas
    estadisticas = EstadisticasResolucionMarcasAlternativa(
        filas=len(fuente),
        resueltas_ean=metodos.count(METODO_EAN),
        resueltas_referencia=metodos.count(METODO_REFERENCIA_PRINCIPAL),
        resueltas_historico=metodos.count(METODO_HISTORICO),
        pendientes=len(pendientes),
        conflictos=len(conflictos),
        fuera_marcas_permitidas=len(fuera),
        ean_duplicados=estadisticas_cruce.ean_duplicados,
        referencias_duplicadas=estadisticas_cruce.referencias_duplicadas,
        marcas_fuente_no_coincidentes=marcas_fuente_no_coincidentes,
        resueltas_referencia_alternativa=metodos.count(
            METODO_REFERENCIA_ALTERNATIVA
        ),
        sin_coincidencia=estadisticas_cruce.sin_coincidencia,
        referencias_alternativas_ambiguas=(
            estadisticas_cruce.referencias_alternativas_ambiguas
        ),
        conflictos_identificadores=(
            estadisticas_cruce.conflictos_identificadores
        ),
    )
    return ResultadoResolucionMarcas(
        dataframe=fuente,
        coincidencias=pd.DataFrame(coincidencias),
        auditoria=pd.DataFrame(auditoria),
        conflictos=pd.DataFrame(conflictos),
        fuera_marcas_permitidas=pd.DataFrame(fuera),
        pendientes=pd.DataFrame(pendientes),
        estadisticas=estadisticas,
    )


def resolver_marcas_multiples(
    proveedor_df: pd.DataFrame,
    prestashop_df: pd.DataFrame,
    *,
    marcas_permitidas: Iterable[dict],
    id_marca_pendiente: int,
    id_configuracion: int,
    historico_df: pd.DataFrame | None = None,
) -> ResultadoResolucionMarcas:
    """Clasifica cada fila sin aproximaciones ni selección de destinos."""

    permitidas = list(marcas_permitidas)
    if not permitidas:
        raise ValueError("Una configuración multipmarca exige marcas permitidas")
    alias_a_marca = {}
    for marca in permitidas:
        alias = _texto_exacto(marca.get("nombre_marca_prestashop"))
        if alias is None:
            raise ValueError("Toda marca permitida necesita un alias exacto")
        id_marca = int(marca["id_marca"])
        anterior = alias_a_marca.setdefault(alias, id_marca)
        if anterior != id_marca:
            raise ValueError("Un alias PrestaShop apunta a varias marcas")
    ids_permitidos = set(alias_a_marca.values())

    if "referencia_alternativa" in proveedor_df.columns:
        return _resolver_con_referencia_alternativa(
            proveedor_df,
            prestashop_df,
            alias_a_marca=alias_a_marca,
            ids_permitidos=ids_permitidos,
            id_marca_pendiente=id_marca_pendiente,
            id_configuracion=id_configuracion,
            historico_df=historico_df,
        )

    fuente = proveedor_df.copy().reset_index(drop=True)
    atributos = dict(proveedor_df.attrs)
    fuente["_fila_fuente"] = fuente.index
    fuente["_ref_normalizada"] = fuente.get("referencia").map(
        normalizar_identificador
    )
    fuente["_ean_normalizado"] = fuente.get(
        "ean", pd.Series(pd.NA, index=fuente.index)
    ).map(normalizar_ean)
    conteo_ean_fuente = fuente["_ean_normalizado"].value_counts()
    conteo_ref_fuente = fuente["_ref_normalizada"].value_counts()

    ps = prestashop_df.copy().reset_index(drop=True)
    ps["_orden_prestashop"] = ps.index
    ps["_ref_normalizada"] = ps.get("reference").map(
        normalizar_identificador
    )
    ps["_ean_normalizado"] = ps.get(
        "ean13", pd.Series(pd.NA, index=ps.index)
    ).map(normalizar_ean)
    indice_ean = _indice_destinos(ps, "_ean_normalizado")
    indice_ref = _indice_destinos(ps, "_ref_normalizada")
    indice_historico = _indice_historico(historico_df, ids_permitidos)

    auditoria = []
    coincidencias = []
    conflictos = []
    fuera = []
    pendientes = []
    marcas_resultado = []
    estados = []
    metodos = []
    ean_duplicados = 0
    referencias_duplicadas = 0
    marcas_fuente_no_coincidentes = 0

    for fila in fuente.to_dict("records"):
        candidatos_ean = (
            indice_ean.get(fila["_ean_normalizado"], [])
            if fila["_ean_normalizado"] is not None
            else []
        )
        candidatos_ref = (
            indice_ref.get(fila["_ref_normalizada"], [])
            if fila["_ref_normalizada"] is not None
            else []
        )
        ean_ambiguo = bool(candidatos_ean) and (
            len(candidatos_ean) != 1
            or conteo_ean_fuente.get(fila["_ean_normalizado"], 0) != 1
        )
        referencia_ambigua = bool(candidatos_ref) and (
            len(candidatos_ref) != 1
            or conteo_ref_fuente.get(fila["_ref_normalizada"], 0) != 1
        )
        if ean_ambiguo:
            ean_duplicados += 1
        if referencia_ambigua:
            referencias_duplicadas += 1
        por_ean = (
            candidatos_ean[0]
            if len(candidatos_ean) == 1 and not ean_ambiguo
            else None
        )
        por_ref = (
            candidatos_ref[0]
            if len(candidatos_ref) == 1 and not referencia_ambigua
            else None
        )

        motivo = None
        destino = None
        destino_auditoria = None
        metodo = None
        if ean_ambiguo:
            motivo = "ean_duplicado_sin_destino_unico"
            conflictos.append({**fila, "motivo_resolucion": motivo})
        elif not candidatos_ean and referencia_ambigua:
            motivo = "referencia_duplicada_sin_destino_unico"
            conflictos.append({**fila, "motivo_resolucion": motivo})
        elif por_ean is not None and por_ref is not None:
            if (
                _destino(por_ean) != _destino(por_ref)
                or _texto_exacto(por_ean.get("marca"))
                != _texto_exacto(por_ref.get("marca"))
            ):
                motivo = "ean_referencia_destinos_distintos"
                conflictos.append({**fila, "motivo_resolucion": motivo})
            else:
                destino = por_ean
                metodo = METODO_EAN
        elif por_ean is not None:
            destino = por_ean
            metodo = METODO_EAN
        elif por_ref is not None:
            destino = por_ref
            metodo = METODO_REFERENCIA

        if destino is not None:
            destino_auditoria = destino
            marca_fuente = _texto_exacto(fila.get("marca_fuente"))
            marca_destino = _texto_exacto(destino.get("marca"))
            if marca_fuente is not None and marca_fuente != marca_destino:
                motivo = "marca_fuente_no_coincide"
                marcas_fuente_no_coincidentes += 1
                pendientes.append({
                    **fila,
                    "marca_prestashop": destino.get("marca"),
                    "motivo_resolucion": motivo,
                })
                destino = None
                metodo = None

        id_marca = None
        if motivo is None and destino is not None:
            alias = _texto_exacto(destino.get("marca"))
            id_marca = alias_a_marca.get(alias)
            if id_marca is None:
                motivo = "fabricante_fuera_de_marcas_permitidas"
                fuera.append({
                    **fila,
                    "marca_prestashop": destino.get("marca"),
                    "motivo_resolucion": motivo,
                })
            else:
                coincidencia = _combinar_coincidencia(fila, destino, metodo)
                coincidencia["id_marca"] = id_marca
                coincidencia["id_configuracion_origen"] = int(id_configuracion)
                coincidencia["estado_clasificacion_marca"] = ESTADO_RESUELTA
                coincidencia["metodo_resolucion_marca"] = metodo
                coincidencias.append(coincidencia)

        if motivo is not None:
            marcas_resultado.append(id_marca_pendiente)
            estados.append(ESTADO_PENDIENTE)
            metodos.append(METODO_PENDIENTE)
        elif destino is not None:
            marcas_resultado.append(id_marca)
            estados.append(ESTADO_RESUELTA)
            metodos.append(metodo)
        else:
            clave_historica = (
                fila["_ref_normalizada"],
                fila["_ean_normalizado"] or "",
            )
            id_historico = indice_historico.get(clave_historica)
            if id_historico is not None:
                id_marca = id_historico
                estado = ESTADO_RESUELTA
                metodo = METODO_HISTORICO
            else:
                id_marca = id_marca_pendiente
                estado = ESTADO_PENDIENTE
                metodo = METODO_PENDIENTE
                motivo = (
                    "identificador_duplicado_sin_destino_unico"
                    if len(candidatos_ean) > 1 or len(candidatos_ref) > 1
                    else "sin_correspondencia"
                )
                pendientes.append({**fila, "motivo_resolucion": motivo})
            marcas_resultado.append(id_marca)
            estados.append(estado)
            metodos.append(metodo)

        auditoria.append({
            "fila_fuente": int(fila["_fila_fuente"]),
            "referencia": fila["_ref_normalizada"],
            "ean": fila["_ean_normalizado"],
            "id_marca": marcas_resultado[-1],
            "estado": estados[-1],
            "metodo": metodos[-1],
            "marca_prestashop": (
                destino_auditoria.get("marca")
                if destino_auditoria else None
            ),
            "id_product": (
                destino_auditoria.get("id_product")
                if destino_auditoria else None
            ),
            "id_product_attribute": (
                destino_auditoria.get("id_product_attribute")
                if destino_auditoria else None
            ),
            "motivo": motivo,
        })

    fuente["id_marca"] = marcas_resultado
    fuente["id_configuracion_origen"] = int(id_configuracion)
    fuente["estado_clasificacion_marca"] = estados
    fuente["metodo_resolucion_marca"] = metodos
    fuente.drop(
        columns=["_fila_fuente", "_ref_normalizada", "_ean_normalizado"],
        inplace=True,
    )
    fuente.attrs.update(atributos)
    auditoria_df = pd.DataFrame(auditoria)
    estadisticas = EstadisticasResolucionMarcas(
        filas=len(fuente),
        resueltas_ean=metodos.count(METODO_EAN),
        resueltas_referencia=metodos.count(METODO_REFERENCIA),
        resueltas_historico=metodos.count(METODO_HISTORICO),
        pendientes=len(pendientes),
        conflictos=len(conflictos),
        fuera_marcas_permitidas=len(fuera),
        ean_duplicados=ean_duplicados,
        referencias_duplicadas=referencias_duplicadas,
        marcas_fuente_no_coincidentes=marcas_fuente_no_coincidentes,
    )
    return ResultadoResolucionMarcas(
        dataframe=fuente,
        coincidencias=pd.DataFrame(coincidencias),
        auditoria=auditoria_df,
        conflictos=pd.DataFrame(conflictos),
        fuera_marcas_permitidas=pd.DataFrame(fuera),
        pendientes=pd.DataFrame(pendientes),
        estadisticas=estadisticas,
    )
