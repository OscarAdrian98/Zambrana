"""Plan global, determinista e independiente del orden de proveedores.

Los cruces exactos producen intenciones durante la fase de proveedores. Este
módulo las agrega en memoria, lee el estado actual por lotes y construye el
único plan que comparten report-only y apply.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Optional

import pandas as pd

import config.etiquetas
from config.bd import (
    BASE_PRESTASHOP_ACTIVA,
    BASE_PROVEEDORES_ACTIVA,
    TIPO_PRESTASHOP,
    TIPO_PROVEEDORES,
    validar_conexion_configurada,
)
from config.lote_validacion import PROVEEDORES_GESTION_ID_SHOP
from procesamiento.reglas import elegir_fecha_disponibilidad


@dataclass(frozen=True)
class PlanGlobalPrestaShop:
    """Plan inmutable en su interfaz y aplicable sin recalcular decisiones."""

    objetivos: pd.DataFrame = field(repr=False)
    padres: pd.DataFrame = field(repr=False)
    actualizaciones: dict[str, tuple] = field(repr=False)
    metricas: dict
    colisiones_tienda: tuple[int, ...] = ()
    aplica_cambios: bool = False
    ids_packs_excluidos: tuple[int, ...] = ()
    id_product_por_atributo: dict[int, int] = field(
        default_factory=dict,
        repr=False,
    )
    acciones_detalladas: tuple[dict, ...] = field(default_factory=tuple)

    def como_dict(self) -> dict:
        resultado = dict(self.metricas)
        resultado.update(
            {
                "aplica_cambios": self.aplica_cambios,
                "colisiones_tienda": self.colisiones_tienda,
                "actualizaciones": {
                    nombre: len(filas)
                    for nombre, filas in self.actualizaciones.items()
                },
                "acciones_detalladas": len(self.acciones_detalladas),
            }
        )
        return resultado

    @property
    def candidatos_reactivacion(self) -> tuple[int, ...]:
        return tuple(fila[0] for fila in self.actualizaciones["reactivar_atributo"])

    @property
    def candidatos_desactivacion_simple(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                {fila[2] for fila in self.actualizaciones["estado_producto"] if fila[:2] == (0, 0)}
            )
        )

    @property
    def candidatos_activacion_producto(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                {fila[2] for fila in self.actualizaciones["estado_producto"] if fila[:2] == (1, 1)}
            )
        )


@dataclass(frozen=True)
class ResultadoAplicacionPlanGlobal:
    metricas_plan: dict
    filas_modificadas: int
    sentencias_sql: int
    lotes_update: int
    commits: int = 1
    aplica_cambios: bool = True

    def como_dict(self) -> dict:
        resultado = dict(self.metricas_plan)
        resultado.update(asdict(self))
        resultado["cambios_funcionales"] = self.filas_modificadas
        return resultado

    @property
    def atributos_reactivados(self) -> int:
        return int(self.metricas_plan.get("reactivaciones_id_shop_autorizadas", 0))

    @property
    def productos_activados(self) -> int:
        return int(self.metricas_plan.get("activaciones", 0))

    @property
    def productos_simples_desactivados(self) -> int:
        return int(self.metricas_plan.get("desactivaciones", 0))


def _en_lotes(valores, tamano):
    for inicio in range(0, len(valores), tamano):
        yield valores[inicio : inicio + tamano]


def _seleccionar_por_ids(cursor, sql, ids, tamano_lote):
    filas = []
    consultas = 0
    for lote in _en_lotes(ids, tamano_lote):
        if not lote:
            continue
        placeholders = ", ".join(["%s"] * len(lote))
        cursor.execute(sql.format(placeholders=placeholders), tuple(lote))
        filas.extend(cursor.fetchall())
        consultas += 1
    return filas, consultas


def _fecha_sql(valor):
    fecha = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(fecha) else pd.Timestamp(fecha).date()


def _fecha_bd(valor):
    if valor in (None, ""):
        return None
    if str(valor) == "0000-00-00":
        return "0000-00-00"
    return _fecha_sql(valor)


def _es_referencia_pack(valor) -> bool:
    """Reconoce un Advanced Pack por la referencia real de PrestaShop."""

    return str(valor or "").strip().casefold().startswith("pack_")


_INDICE_ID_PRODUCT = {
    "cache_producto": 0,
    "cache_producto_shop": 0,
    "etiquetas": 2,
    "fecha_producto": 1,
    "fecha_producto_shop": 1,
    "estado_producto": 2,
    "estado_producto_shop": 2,
    "out_of_stock": 1,
    "visibilidad_producto": 0,
    "visibilidad_producto_shop": 0,
}
_INDICE_ID_ATRIBUTO = {
    "reactivar_atributo": 0,
    "desactivar_atributo": 0,
    "fecha_atributo": 1,
    "fecha_atributo_shop": 1,
}


def _excluir_acciones_pack(
    actualizaciones,
    ids_packs,
    id_product_por_atributo,
):
    """Defensa final: elimina cualquier SQL dirigido a un padre ``pack_``."""

    ids_packs = set(ids_packs)
    filtradas = {}
    descartadas = 0
    for nombre, filas in actualizaciones.items():
        conservadas = []
        for fila in filas:
            id_product = None
            if nombre in _INDICE_ID_PRODUCT:
                id_product = int(fila[_INDICE_ID_PRODUCT[nombre]])
            elif nombre in _INDICE_ID_ATRIBUTO:
                id_atributo = int(fila[_INDICE_ID_ATRIBUTO[nombre]])
                id_product = id_product_por_atributo.get(id_atributo)
            else:
                raise RuntimeError(
                    f"Ruta SQL sin protección de packs: {nombre}"
                )
            if id_product in ids_packs:
                descartadas += 1
                continue
            conservadas.append(fila)
        filtradas[nombre] = tuple(conservadas)
    return filtradas, descartadas


def _destinos_de_actualizaciones(actualizaciones, id_product_por_atributo):
    ids_productos = set()
    ids_atributos = set()
    for nombre, filas in actualizaciones.items():
        if nombre in _INDICE_ID_PRODUCT:
            ids_productos.update(
                int(fila[_INDICE_ID_PRODUCT[nombre]]) for fila in filas
            )
        elif nombre in _INDICE_ID_ATRIBUTO:
            ids_atributos.update(
                int(fila[_INDICE_ID_ATRIBUTO[nombre]]) for fila in filas
            )
        elif filas:
            raise RuntimeError(f"Ruta SQL sin protección de packs: {nombre}")
    ids_productos.update(
        id_product_por_atributo[id_atributo]
        for id_atributo in ids_atributos
        if id_atributo in id_product_por_atributo
    )
    return ids_productos, ids_atributos


def _valor_auditable(valor):
    """Convierte valores de pandas/fechas a tipos seguros para JSON."""

    if valor is None:
        return None
    if isinstance(valor, (date, pd.Timestamp)):
        return valor.isoformat()
    if isinstance(valor, tuple):
        return [_valor_auditable(elemento) for elemento in valor]
    if isinstance(valor, list):
        return [_valor_auditable(elemento) for elemento in valor]
    if isinstance(valor, dict):
        return {
            str(clave): _valor_auditable(elemento)
            for clave, elemento in valor.items()
        }
    if pd.isna(valor):
        return None
    if hasattr(valor, "item"):
        return valor.item()
    return valor


def _accion_auditoria(
    tipo_accion,
    tabla,
    id_product,
    *,
    id_product_attribute=None,
    referencia="",
    ean=None,
    valor_anterior=None,
    valor_deseado=None,
    proveedores=(),
    motivo="",
    tipo_producto="simple",
    aplicable=True,
    estado="APLICABLE",
    sql=None,
    acciones_descartadas=None,
    match_method=None,
    match_value=None,
    matches=(),
):
    accion = {
        "tipo_accion": tipo_accion,
        "tabla": tabla,
        "id_product": int(id_product),
        "id_product_attribute": (
            int(id_product_attribute) if id_product_attribute else None
        ),
        "referencia": str(referencia or ""),
        "ean": None if ean in (None, "") else str(ean),
        "valor_anterior": _valor_auditable(valor_anterior),
        "valor_deseado": _valor_auditable(valor_deseado),
        "proveedores": [int(valor) for valor in proveedores],
        "motivo": motivo,
        "tipo_producto": tipo_producto,
        "aplicable": bool(aplicable),
        "estado": estado,
        "sql": sql if aplicable else None,
    }
    if acciones_descartadas is not None:
        accion["acciones_descartadas"] = list(acciones_descartadas)
    if match_method is not None:
        accion["match_method"] = str(match_method)
        accion["match_value"] = (
            None if match_value is None else str(match_value)
        )
    if matches:
        accion["matches"] = _valor_auditable(tuple(matches))
    return accion


def _construir_acciones_detalladas(
    actualizaciones,
    objetivos_originales,
    padres_originales,
    estados_padre,
    *,
    ids_packs,
    metadatos_atributo=None,
    fechas_atributo=None,
    fechas_tienda_atributo=None,
    tiendas_atributo=None,
    etiquetas_actuales=None,
    fuera_stock_actual=None,
    metadatos_visibilidad=None,
    packs_visibilidad=None,
):
    """Materializa la auditoria desde el mismo plan, sin nuevas decisiones."""

    metadatos_atributo = metadatos_atributo or {}
    fechas_atributo = fechas_atributo or {}
    fechas_tienda_atributo = fechas_tienda_atributo or {}
    tiendas_atributo = tiendas_atributo or {}
    etiquetas_actuales = etiquetas_actuales or {}
    fuera_stock_actual = fuera_stock_actual or {}
    metadatos_visibilidad = metadatos_visibilidad or {}
    packs_visibilidad = packs_visibilidad or ()
    objetivos_por_destino = {
        (int(f.id_product), int(f.id_product_attribute)): f
        for f in objetivos_originales.itertuples(index=False)
    }
    proveedores_padre = {}
    for objetivo in objetivos_originales.itertuples(index=False):
        proveedores_padre.setdefault(int(objetivo.id_product), set()).update(
            int(valor) for valor in objetivo.proveedores
        )
    tipo_por_padre = {
        int(f.id_product): (
            "con_combinaciones" if bool(f.tiene_atributos) else "simple"
        )
        for f in padres_originales.itertuples(index=False)
    }
    matches_por_padre = {
        int(f.id_product): tuple(f.matches)
        for f in padres_originales.itertuples(index=False)
        if hasattr(f, "matches")
    }

    def contexto(id_product, id_atributo=0):
        estado = estados_padre.get(
            int(id_product),
            ("", 0, 0, None, 0, False, 0, 0, None, None, None, None),
        )
        objetivo = objetivos_por_destino.get(
            (int(id_product), int(id_atributo))
        )
        meta_atributo = metadatos_atributo.get(int(id_atributo), {})
        meta_visibilidad = metadatos_visibilidad.get(int(id_product), {})
        matches = (
            tuple(objetivo.matches)
            if objetivo is not None and hasattr(objetivo, "matches")
            else matches_por_padre.get(int(id_product), ())
        )
        match_unico = matches[0] if len(matches) == 1 else {}
        return {
            "referencia": (
                meta_atributo.get("referencia")
                or estado[0]
                or meta_visibilidad.get("referencia", "")
            ),
            "ean": (
                meta_atributo.get("ean")
                or estado[9]
                or meta_visibilidad.get("ean")
            ),
            "proveedores": (
                tuple(objetivo.proveedores)
                if objetivo is not None
                else tuple(sorted(proveedores_padre.get(int(id_product), ())))
            ),
            "tipo_producto": tipo_por_padre.get(
                int(id_product),
                (
                    "con_combinaciones"
                    if meta_visibilidad.get("tiene_atributos")
                    else "simple"
                ),
            ),
            "objetivo": objetivo,
            "estado_padre": estado,
            "matches": matches,
            "match_method": match_unico.get("match_method"),
            "match_value": match_unico.get("match_value"),
        }

    acciones = []
    for objetivo in objetivos_originales.itertuples(index=False):
        id_product = int(objetivo.id_product)
        id_atributo = int(objetivo.id_product_attribute)
        ctx = contexto(id_product, id_atributo)
        if id_product in ids_packs:
            descartadas = [
                (
                    "SINCRONIZAR_COMBINACION_DISPONIBLE"
                    if bool(objetivo.disponible)
                    else "SINCRONIZAR_COMBINACION_SIN_STOCK"
                )
                if id_atributo
                else (
                    "ACTIVAR_PRODUCTO"
                    if bool(objetivo.disponible)
                    else "DESACTIVAR_PRODUCTO"
                )
            ]
            acciones.append(
                _accion_auditoria(
                    "EXCLUIDO_PACK",
                    "ninguna",
                    id_product,
                    id_product_attribute=id_atributo,
                    referencia=ctx["referencia"],
                    ean=ctx["ean"],
                    valor_anterior={
                        "active": ctx["estado_padre"][1],
                        "available_for_order": ctx["estado_padre"][2],
                    },
                    valor_deseado={"disponible": int(objetivo.disponible)},
                    proveedores=ctx["proveedores"],
                    motivo="referencia_real_prestashop_empieza_por_pack_",
                    tipo_producto=ctx["tipo_producto"],
                    aplicable=False,
                    estado="EXCLUIDO_PACK",
                    acciones_descartadas=descartadas,
                    match_method=ctx["match_method"],
                    match_value=ctx["match_value"],
                    matches=ctx["matches"],
                )
            )
        elif bool(objetivo.contradictorio):
            acciones.append(
                _accion_auditoria(
                    "CONFLICTO_DESCARTADO",
                    "ninguna",
                    id_product,
                    id_product_attribute=id_atributo,
                    referencia=ctx["referencia"],
                    ean=ctx["ean"],
                    valor_anterior="intenciones_contradictorias",
                    valor_deseado=int(objetivo.disponible),
                    proveedores=ctx["proveedores"],
                    motivo="resolucion_multiproveedor_OR_sin_SQL_propio",
                    tipo_producto=ctx["tipo_producto"],
                    aplicable=False,
                    estado="CONFLICTO_DESCARTADO",
                    acciones_descartadas=["CONFLICTO_MULTIPROVEEDOR"],
                    match_method=ctx["match_method"],
                    match_value=ctx["match_value"],
                    matches=ctx["matches"],
                )
            )

    for pack in packs_visibilidad:
        acciones.append(
            _accion_auditoria(
                "EXCLUIDO_PACK",
                "ninguna",
                pack["id_product"],
                referencia=pack["referencia"],
                ean=pack.get("ean"),
                valor_anterior="none",
                valor_deseado="both",
                proveedores=(),
                motivo="referencia_real_prestashop_empieza_por_pack_",
                tipo_producto=(
                    "con_combinaciones"
                    if pack.get("tiene_atributos") else "simple"
                ),
                aplicable=False,
                estado="EXCLUIDO_PACK",
                acciones_descartadas=["CAMBIAR_VISIBILIDAD"],
            )
        )

    def agregar(
        tipo,
        tabla,
        id_product,
        *,
        id_atributo=0,
        anterior=None,
        deseado=None,
        motivo,
        sql,
    ):
        ctx = contexto(id_product, id_atributo)
        acciones.append(
            _accion_auditoria(
                tipo,
                tabla,
                id_product,
                id_product_attribute=id_atributo,
                referencia=ctx["referencia"],
                ean=ctx["ean"],
                valor_anterior=anterior,
                valor_deseado=deseado,
                proveedores=ctx["proveedores"],
                motivo=motivo,
                tipo_producto=ctx["tipo_producto"],
                sql=sql,
                match_method=ctx["match_method"],
                match_value=ctx["match_value"],
                matches=ctx["matches"],
            )
        )

    for (id_atributo,) in actualizaciones["reactivar_atributo"]:
        id_product = int(metadatos_atributo[id_atributo]["id_product"])
        agregar(
            "REACTIVAR_COMBINACION_99_A_1", "ps_product_attribute_shop",
            id_product, id_atributo=id_atributo, anterior=99, deseado=1,
            motivo="proveedor_autorizado_con_stock", sql="reactivar_atributo",
        )
    for (id_atributo,) in actualizaciones["desactivar_atributo"]:
        id_product = int(metadatos_atributo[id_atributo]["id_product"])
        agregar(
            "DESACTIVAR_COMBINACION_1_A_99", "ps_product_attribute_shop",
            id_product, id_atributo=id_atributo, anterior=1, deseado=99,
            motivo="sin_fuente_disponible_y_proveedor_autorizado",
            sql="desactivar_atributo",
        )
    for nombre, tabla in (
        ("cache_producto", "ps_product"),
        ("cache_producto_shop", "ps_product_shop"),
    ):
        for (id_product,) in actualizaciones[nombre]:
            estado = contexto(id_product)["estado_padre"]
            agregar(
                "LIMPIAR_CACHE_COMBINACION", tabla, id_product,
                anterior=estado[10 if nombre == "cache_producto" else 11],
                deseado=None,
                motivo="recalcular_combinacion_predeterminada", sql=nombre,
            )
    for entrada, salida, id_product in actualizaciones["etiquetas"]:
        agregar(
            "CAMBIAR_DELIVERY_OUT_STOCK", "ps_product_lang", id_product,
            anterior=etiquetas_actuales.get(id_product, []),
            deseado={"delivery_in_stock": entrada, "delivery_out_stock": salida},
            motivo="etiqueta_segun_disponibilidad_y_plazo_proveedor",
            sql="etiquetas",
        )
    for fecha, id_product in actualizaciones["fecha_producto"]:
        estado = contexto(id_product)["estado_padre"]
        if estado[3] != fecha:
            agregar(
                "CAMBIAR_AVAILABLE_DATE", "ps_product", id_product,
                anterior=estado[3], deseado=fecha,
                motivo="fecha_global_segun_fuentes_disponibles",
                sql="fecha_producto",
            )
        if estado[4] != 2:
            agregar(
                "CAMBIAR_ADDITIONAL_DELIVERY_TIMES", "ps_product", id_product,
                anterior=estado[4], deseado=2,
                motivo="politica_de_plazo_de_entrega", sql="fecha_producto",
            )
    for fecha, id_product in actualizaciones["fecha_producto_shop"]:
        estado = contexto(id_product)["estado_padre"]
        agregar(
            "CAMBIAR_AVAILABLE_DATE", "ps_product_shop", id_product,
            anterior=estado[8], deseado=fecha,
            motivo="fecha_global_segun_fuentes_disponibles",
            sql="fecha_producto_shop",
        )
    for nombre, tabla, indices in (
        ("estado_producto", "ps_product", (1, 2)),
        ("estado_producto_shop", "ps_product_shop", (6, 7)),
    ):
        for active, order, id_product in actualizaciones[nombre]:
            estado = contexto(id_product)["estado_padre"]
            if estado[indices[0]] != active:
                agregar(
                    "ACTIVAR_PRODUCTO" if active else "DESACTIVAR_PRODUCTO",
                    tabla, id_product, anterior=estado[indices[0]],
                    deseado=active,
                    motivo=(
                        "fuente_disponible" if active
                        else "sin_fuente_disponible"
                    ), sql=nombre,
                )
            if estado[indices[1]] != order:
                agregar(
                    "ACTIVAR_PEDIDO" if order else "DESACTIVAR_PEDIDO",
                    tabla, id_product, anterior=estado[indices[1]],
                    deseado=order,
                    motivo=(
                        "fuente_disponible" if order
                        else "sin_fuente_disponible"
                    ), sql=nombre,
                )
    for nombre, tabla in (
        ("fecha_atributo", "ps_product_attribute"),
        ("fecha_atributo_shop", "ps_product_attribute_shop"),
    ):
        for fecha, id_atributo in actualizaciones[nombre]:
            meta = metadatos_atributo[id_atributo]
            anterior = (
                fechas_atributo.get(id_atributo)
                if nombre == "fecha_atributo"
                else fechas_tienda_atributo.get(id_atributo, [])
            )
            agregar(
                "CAMBIAR_AVAILABLE_DATE", tabla, meta["id_product"],
                id_atributo=id_atributo, anterior=anterior, deseado=fecha,
                motivo="fecha_global_segun_fuentes_disponibles", sql=nombre,
            )
    for deseado, id_product, id_atributo in actualizaciones["out_of_stock"]:
        agregar(
            "CAMBIAR_OUT_OF_STOCK", "ps_stock_available", id_product,
            id_atributo=id_atributo,
            anterior=fuera_stock_actual.get((id_product, id_atributo)),
            deseado=deseado,
            motivo="politica_pedido_segun_tipo_y_disponibilidad",
            sql="out_of_stock",
        )
    for nombre, tabla in (
        ("visibilidad_producto", "ps_product"),
        ("visibilidad_producto_shop", "ps_product_shop"),
    ):
        for (id_product,) in actualizaciones[nombre]:
            agregar(
                "CAMBIAR_VISIBILIDAD", tabla, id_product,
                anterior="none", deseado="both",
                motivo="producto_activo_con_stock_oculto", sql=nombre,
            )
    return tuple(acciones)


def _metricas_trazabilidad(acciones):
    principales = [
        accion for accion in acciones
        if accion["tabla"] in {"ps_product", "ps_product_attribute_shop"}
    ]
    return {
        "productos_activados_detallados": sum(
            a["tipo_accion"] == "ACTIVAR_PRODUCTO"
            and a["tabla"] == "ps_product" for a in principales
        ),
        "productos_desactivados_detallados": sum(
            a["tipo_accion"] == "DESACTIVAR_PRODUCTO"
            and a["tabla"] == "ps_product" for a in principales
        ),
        "pedidos_habilitados": sum(
            a["tipo_accion"] == "ACTIVAR_PEDIDO"
            and a["tabla"] == "ps_product" for a in principales
        ),
        "pedidos_deshabilitados": sum(
            a["tipo_accion"] == "DESACTIVAR_PEDIDO"
            and a["tabla"] == "ps_product" for a in principales
        ),
        "combinaciones_99_a_1": sum(
            a["tipo_accion"] == "REACTIVAR_COMBINACION_99_A_1"
            for a in principales
        ),
        "combinaciones_1_a_99": sum(
            a["tipo_accion"] == "DESACTIVAR_COMBINACION_1_A_99"
            for a in principales
        ),
        "conflictos_descartados": sum(
            a["tipo_accion"] == "CONFLICTO_DESCARTADO" for a in acciones
        ),
    }


def _fecha_global(grupo: pd.DataFrame, hoy: date):
    """Prioriza suministro actual y evita que una reposición lo eclipse."""

    disponibles = grupo[grupo["disponible"] > 0]
    if not disponibles.empty:
        # Una fuente disponible sin restricción de fecha representa stock
        # actual; no se le impone la fecha futura de otra fuente.
        if disponibles["fecha"].isna().any():
            return None
        elegidas = disponibles
    else:
        elegidas = grupo
    return _fecha_sql(
        elegir_fecha_disponibilidad(
            elegidas["fecha"],
            elegidas["disponible"],
            hoy=hoy,
        )
    )


def _fechas_por_grupo(
    dataframe: pd.DataFrame,
    claves: list[str],
    *,
    hoy: date,
) -> pd.Series:
    """Versión por conjuntos de la selección histórica de fechas."""

    dataframe = dataframe.copy()
    dataframe["fecha"] = pd.to_datetime(dataframe["fecha"], errors="coerce")
    indice = (
        pd.Index(dataframe[claves[0]].drop_duplicates(), name=claves[0])
        if len(claves) == 1
        else pd.MultiIndex.from_frame(dataframe[claves].drop_duplicates())
    )
    resultado = pd.Series(None, index=indice, dtype=object)
    disponibles = dataframe.groupby(claves, sort=False)["disponible"].transform(
        "max"
    ).gt(0)
    # Si existe stock actual sin fecha, esa ausencia de restricción gana.
    stock_sin_fecha = (
        (dataframe["disponible"] > 0) & dataframe["fecha"].isna()
    ).groupby([dataframe[clave] for clave in claves]).transform("max")
    fecha_minima = pd.Timestamp(hoy - timedelta(days=30))
    elegibles = dataframe[
        (~disponibles | dataframe["disponible"].gt(0))
        & dataframe["fecha"].notna()
        & dataframe["fecha"].ge(fecha_minima)
        & ~stock_sin_fecha
    ].copy()
    if elegibles.empty:
        return resultado
    elegibles["_distancia"] = (
        elegibles["fecha"].dt.normalize() - pd.Timestamp(hoy)
    ).abs().dt.days
    elegibles.sort_values(
        [*claves, "_distancia", "fecha"], inplace=True, kind="stable"
    )
    elegidas = elegibles.drop_duplicates(claves, keep="first")
    valores = elegidas.set_index(claves)["fecha"].map(_fecha_sql)
    resultado.loc[valores.index] = valores
    return resultado


def preparar_objetivos_globales(
    intenciones: pd.DataFrame,
    *,
    hoy: Optional[date] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Agrega fuentes exactas por combinación y después por padre."""

    hoy = hoy or date.today()
    requeridas = {"id_product", "id_product_attribute", "stock_combinado"}
    faltan = requeridas - set(intenciones.columns)
    if faltan:
        raise ValueError(
            "Faltan columnas en las intenciones: " + ", ".join(sorted(faltan))
        )
    trabajo = intenciones.copy()
    trabajo["id_product"] = pd.to_numeric(
        trabajo["id_product"], errors="coerce"
    )
    trabajo["id_product_attribute"] = pd.to_numeric(
        trabajo["id_product_attribute"], errors="coerce"
    ).fillna(0)
    trabajo = trabajo[
        trabajo["id_product"].gt(0)
        & trabajo["id_product_attribute"].ge(0)
    ].copy()
    if trabajo.empty:
        return pd.DataFrame(), pd.DataFrame(), {
            "intenciones_proveedor": 0,
            "destinos_unicos": 0,
            "contradicciones": 0,
        }
    trabajo[["id_product", "id_product_attribute"]] = trabajo[
        ["id_product", "id_product_attribute"]
    ].astype(int)
    serie_proveedor = trabajo.get(
        "id_proveedor", pd.Series(0, index=trabajo.index)
    )
    trabajo["id_proveedor"] = pd.to_numeric(
        serie_proveedor, errors="coerce"
    ).fillna(0).astype(int)
    trabajo["es_fuente_catalogo"] = trabajo.get(
        "es_fuente_catalogo", pd.Series(True, index=trabajo.index)
    )
    trabajo["es_fuente_catalogo"] = trabajo["es_fuente_catalogo"].fillna(
        False
    ).astype(bool)
    trabajo["disponible"] = pd.to_numeric(
        trabajo["stock_combinado"], errors="coerce"
    ).fillna(0).gt(0).astype("int8")
    trabajo["fecha"] = pd.to_datetime(
        trabajo.get("fecha_mas_cercana", pd.Series(pd.NaT, index=trabajo.index)),
        errors="coerce",
    )

    claves = ["id_product", "id_product_attribute"]
    grupos = trabajo.groupby(claves, sort=True, observed=True)
    objetivos_df = grupos.agg(
        disponible=("disponible", "max"),
        fuentes_catalogo=("es_fuente_catalogo", "sum"),
    ).reset_index()
    catalogo = trabajo[trabajo["es_fuente_catalogo"]].copy()
    catalogo_matches = catalogo[
        catalogo.get(
            "match_method", pd.Series(pd.NA, index=catalogo.index)
        ).notna()
    ].copy()
    if catalogo_matches.empty:
        matches_por_destino = {}
    else:
        def resumir_matches(grupo):
            unicos = {
                (
                    int(fila.id_proveedor),
                    str(fila.match_method),
                    None if pd.isna(fila.match_value) else str(fila.match_value),
                )
                for fila in grupo[
                    ["id_proveedor", "match_method", "match_value"]
                ].itertuples(index=False)
            }
            return tuple(
                {
                    "id_proveedor": proveedor,
                    "match_method": metodo,
                    "match_value": valor,
                }
                for proveedor, metodo, valor in sorted(unicos)
            )

        matches_por_destino = catalogo_matches.groupby(
            claves,
            sort=False,
            observed=True,
        )[["id_proveedor", "match_method", "match_value"]].apply(
            resumir_matches
        ).to_dict()
    proveedor_destino = catalogo.groupby(
        [*claves, "id_proveedor"], sort=False, observed=True
    )["disponible"].max().reset_index()
    proveedores = proveedor_destino.groupby(claves, sort=False)[
        "id_proveedor"
    ].agg(lambda s: tuple(sorted(set(s) - {0})))
    proveedores_disponibles = proveedor_destino[
        proveedor_destino["disponible"] > 0
    ].groupby(claves, sort=False)["id_proveedor"].agg(
        lambda s: tuple(sorted(set(s) - {0}))
    )
    indice = pd.MultiIndex.from_frame(objetivos_df[claves])
    objetivos_df["matches"] = [
        matches_por_destino.get(tuple(clave), ())
        for clave in objetivos_df[claves].itertuples(index=False, name=None)
    ]
    objetivos_df["proveedores"] = proveedores.reindex(indice).map(
        lambda valor: valor if isinstance(valor, tuple) else ()
    ).to_numpy()
    objetivos_df["proveedores_disponibles"] = (
        proveedores_disponibles.reindex(indice).map(
            lambda valor: valor if isinstance(valor, tuple) else ()
        ).to_numpy()
    )
    objetivos_df["proveedor_etiqueta"] = objetivos_df[
        "proveedores_disponibles"
    ].map(lambda valores: min(valores) if valores else None)
    objetivos_df["autoriza_id_shop"] = objetivos_df["proveedores"].map(
        lambda valores: any(
            proveedor in PROVEEDORES_GESTION_ID_SHOP
            for proveedor in valores
        )
    )
    objetivos_df["autoriza_reactivacion"] = objetivos_df[
        "proveedores_disponibles"
    ].map(
        lambda valores: any(
            proveedor in PROVEEDORES_GESTION_ID_SHOP
            for proveedor in valores
        )
    )
    contradiccion = proveedor_destino.groupby(claves)["disponible"].nunique()
    objetivos_df["contradictorio"] = contradiccion.reindex(indice).fillna(0).gt(
        1
    ).to_numpy()
    fechas = _fechas_por_grupo(trabajo, claves, hoy=hoy)
    objetivos_df["fecha_disponibilidad"] = fechas.reindex(indice).to_numpy()
    objetivos_df["fecha_disponibilidad"] = objetivos_df[
        "fecha_disponibilidad"
    ].map(lambda valor: None if pd.isna(valor) else _fecha_sql(valor))

    objetivos_df["es_combinacion"] = objetivos_df[
        "id_product_attribute"
    ].gt(0)
    padres_con_atributos = set(
        objetivos_df.loc[objetivos_df["es_combinacion"], "id_product"]
    )
    base_padres = objetivos_df[
        objetivos_df["es_combinacion"]
        | ~objetivos_df["id_product"].isin(padres_con_atributos)
    ].copy()
    padres_disponibles = base_padres.groupby("id_product", sort=True)[
        "disponible"
    ].max()
    padres_df = padres_disponibles.rename("disponible").reset_index()
    padres_df["tiene_atributos"] = padres_df["id_product"].isin(
        padres_con_atributos
    )
    matches_padre = {}
    for clave, matches in matches_por_destino.items():
        id_product = int(clave[0])
        acumulados = {
            (
                int(elemento["id_proveedor"]),
                elemento["match_method"],
                elemento["match_value"],
            )
            for elemento in matches_padre.get(id_product, ())
        }
        acumulados.update(
            (
                int(elemento["id_proveedor"]),
                elemento["match_method"],
                elemento["match_value"],
            )
            for elemento in matches
        )
        matches_padre[id_product] = tuple(
            {
                "id_proveedor": proveedor,
                "match_method": metodo,
                "match_value": valor,
            }
            for proveedor, metodo, valor in sorted(acumulados)
        )
    padres_df["matches"] = padres_df["id_product"].map(
        lambda valor: matches_padre.get(int(valor), ())
    )
    proveedores_padre = base_padres.explode("proveedores_disponibles")
    proveedores_padre = proveedores_padre[
        proveedores_padre["proveedores_disponibles"].notna()
    ].groupby("id_product")["proveedores_disponibles"].min()
    padres_df["proveedor_etiqueta"] = padres_df["id_product"].map(
        proveedores_padre
    )
    fechas_padre = _fechas_por_grupo(
        base_padres.rename(columns={"fecha_disponibilidad": "fecha"}),
        ["id_product"],
        hoy=hoy,
    )
    padres_df["fecha_disponibilidad"] = padres_df["id_product"].map(
        fechas_padre
    )
    padres_df["fecha_disponibilidad"] = padres_df[
        "fecha_disponibilidad"
    ].map(lambda valor: None if pd.isna(valor) else _fecha_sql(valor))

    por_proveedor_destino = (
        catalogo.groupby(
            ["id_proveedor", "id_product", "id_product_attribute"],
            sort=False,
        )["disponible"].max().reset_index()
        if not catalogo.empty
        else pd.DataFrame()
    )
    por_proveedor_padre = (
        por_proveedor_destino.groupby(
            ["id_proveedor", "id_product"], sort=False
        )["disponible"].max().reset_index()
        if not por_proveedor_destino.empty
        else pd.DataFrame()
    )
    contradicciones_padre = (
        int(
            por_proveedor_padre.groupby("id_product")["disponible"]
            .nunique().gt(1).sum()
        )
        if not por_proveedor_padre.empty
        else 0
    )
    metricas = {
        "intenciones_proveedor": int(len(por_proveedor_destino)),
        "destinos_unicos": int(len(objetivos_df)),
        "contradicciones": contradicciones_padre,
        "combinaciones_resueltas": int(
            objetivos_df["id_product_attribute"].gt(0).sum()
        ),
        "padres_resueltos": int(len(padres_df)),
        "intenciones_por_proveedor": {
            int(proveedor): int(total)
            for proveedor, total in por_proveedor_destino[
                "id_proveedor"
            ].value_counts().sort_index().items()
        } if not por_proveedor_destino.empty else {},
    }
    return objetivos_df, padres_df, metricas


def _plazos_proveedores(conexion, ids_proveedores):
    plazos = {}
    ids = sorted(set(ids_proveedores) - {0})
    if not ids:
        return plazos
    with conexion.cursor() as cursor:
        for lote in _en_lotes(ids, 1000):
            placeholders = ", ".join(["%s"] * len(lote))
            cursor.execute(
                "SELECT id_proveedor, plazo_entrega_proveedor "
                f"FROM proveedores WHERE id_proveedor IN ({placeholders})",
                tuple(lote),
            )
            for id_proveedor, plazo in cursor.fetchall():
                if plazo:
                    plazos[int(id_proveedor)] = str(plazo)
    return plazos


def construir_plan_global(
    conexion_prestashop,
    conexion_proveedores,
    intenciones: pd.DataFrame,
    *,
    hoy: Optional[date] = None,
    tamano_lote: int = 1000,
    incluir_visibilidad: bool = False,
) -> PlanGlobalPrestaShop:
    """Construye todas las diferencias sin realizar ninguna escritura."""

    hoy = hoy or date.today()
    objetivos, padres, metricas = preparar_objetivos_globales(
        intenciones, hoy=hoy
    )
    objetivos_originales = objetivos.copy()
    padres_originales = padres.copy()
    nombres_actualizaciones = (
        "reactivar_atributo", "desactivar_atributo",
        "cache_producto", "cache_producto_shop", "etiquetas",
        "fecha_producto", "fecha_producto_shop", "estado_producto",
        "estado_producto_shop", "fecha_atributo", "fecha_atributo_shop",
        "out_of_stock",
        "visibilidad_producto", "visibilidad_producto_shop",
    )
    actualizaciones = {nombre: [] for nombre in nombres_actualizaciones}
    if objetivos.empty:
        metricas.update(
            {
                "packs_detectados": 0,
                "packs_excluidos": 0,
                "acciones_pack_descartadas": 0,
                "packs_activados": 0,
                "packs_conservados_inactivos": 0,
                "reactivaciones_id_shop_autorizadas": 0,
                "desactivaciones_id_shop_autorizadas": 0,
                "cambios_finales": 0,
                "cambios_funcionales": 0,
            }
        )
        metricas.update(_metricas_trazabilidad(()))
        return PlanGlobalPrestaShop(
            objetivos, padres, {k: () for k in actualizaciones}, metricas
        )

    validar_conexion_configurada(
        conexion_prestashop,
        BASE_PRESTASHOP_ACTIVA,
        tipo_conexion=TIPO_PRESTASHOP,
    )
    validar_conexion_configurada(
        conexion_proveedores,
        BASE_PROVEEDORES_ACTIVA,
        tipo_conexion=TIPO_PROVEEDORES,
    )

    ids_productos_resueltos = padres["id_product"].astype(int).tolist()
    id_product_por_atributo = {
        int(fila.id_product_attribute): int(fila.id_product)
        for fila in objetivos.itertuples(index=False)
        if int(fila.id_product_attribute) > 0
    }
    consultas = 0
    with conexion_prestashop.cursor() as cursor:
        filas, n = _seleccionar_por_ids(
            cursor,
            """
            SELECT p.id_product, p.reference, p.active,
                   p.available_for_order, p.available_date,
                   p.additional_delivery_times, ps.id_product,
                   ps.active, ps.available_for_order, ps.available_date,
                   p.ean13, p.cache_default_attribute,
                   ps.cache_default_attribute
            FROM ps_product p
            LEFT JOIN ps_product_shop ps
              ON ps.id_product=p.id_product AND ps.id_shop=1
            WHERE p.id_product IN ({placeholders})
            """,
            ids_productos_resueltos,
            tamano_lote,
        )
        consultas += n
        estados_padre = {
            int(f[0]): (
                "" if f[1] is None else str(f[1]), int(f[2] or 0),
                int(f[3] or 0), _fecha_bd(f[4]), int(f[5] or 0),
                f[6] is not None, int(f[7] or 0), int(f[8] or 0),
                _fecha_bd(f[9]), None if f[10] in (None, "") else str(f[10]),
                f[11], f[12],
            ) for f in filas
        }

    # La referencia del proveedor no decide esta protección. Sólo se usa la
    # referencia real de ``ps_product`` una vez resuelto inequívocamente el
    # ``id_product`` de destino.
    ids_packs = {
        id_product
        for id_product, estado in estados_padre.items()
        if _es_referencia_pack(estado[0])
    }
    mascara_pack = objetivos["id_product"].isin(ids_packs)
    destinos_pack_descartados = int(mascara_pack.sum())
    objetivos = objetivos.loc[~mascara_pack].copy()
    padres = padres.loc[~padres["id_product"].isin(ids_packs)].copy()
    metricas.update(
        {
            "packs_detectados": len(ids_packs),
            "packs_excluidos": len(ids_packs),
            # Cada destino agregado se descarta antes de generar acciones de
            # campos, atributos o movimientos id_shop.
            "acciones_pack_descartadas": destinos_pack_descartados,
            "destinos_pack_descartados": destinos_pack_descartados,
        }
    )
    if objetivos.empty and not incluir_visibilidad:
        acciones_detalladas = _construir_acciones_detalladas(
            {k: () for k in actualizaciones},
            objetivos_originales,
            padres_originales,
            estados_padre,
            ids_packs=ids_packs,
        )
        metricas.update(
            {
                "packs_activados": 0,
                "packs_conservados_inactivos": 0,
                "reactivaciones_id_shop_autorizadas": 0,
                "desactivaciones_id_shop_autorizadas": 0,
                "activaciones": 0,
                "desactivaciones": 0,
                "cambios_finales": 0,
                "cambios_funcionales": 0,
                "consultas_select": consultas,
                "visibilidad_productos": 0,
                "proveedores_autorizados_id_shop": tuple(
                    sorted(PROVEEDORES_GESTION_ID_SHOP)
                ),
                **_metricas_trazabilidad(acciones_detalladas),
            }
        )
        return PlanGlobalPrestaShop(
            objetivos=objetivos,
            padres=padres,
            actualizaciones={k: () for k in actualizaciones},
            metricas=metricas,
            ids_packs_excluidos=tuple(sorted(ids_packs)),
            id_product_por_atributo=id_product_por_atributo,
            acciones_detalladas=acciones_detalladas,
        )

    ids_productos = padres["id_product"].astype(int).tolist()
    ids_atributos = sorted(
        objetivos.loc[
            objetivos["id_product_attribute"] > 0,
            "id_product_attribute",
        ].astype(int).unique()
    )
    ids_proveedores = {
        proveedor
        for valores in objetivos["proveedores"]
        for proveedor in valores
    }
    plazos = _plazos_proveedores(conexion_proveedores, ids_proveedores)

    with conexion_prestashop.cursor() as cursor:

        filas, n = _seleccionar_por_ids(
            cursor,
            """SELECT id_product, delivery_in_stock, delivery_out_stock
               FROM ps_product_lang
               WHERE id_product IN ({placeholders}) AND id_shop=1""",
            ids_productos,
            tamano_lote,
        )
        consultas += n
        etiquetas_actuales = {}
        for id_product, entrada, salida in filas:
            etiquetas_actuales.setdefault(int(id_product), []).append(
                (entrada or "", salida or "")
            )

        filas, n = _seleccionar_por_ids(
            cursor,
            """SELECT id_product_attribute, available_date, reference,
                      ean13, id_product
               FROM ps_product_attribute
               WHERE id_product_attribute IN ({placeholders})""",
            ids_atributos,
            tamano_lote,
        )
        consultas += n
        fechas_atributo = {int(f[0]): _fecha_bd(f[1]) for f in filas}
        metadatos_atributo = {
            int(f[0]): {
                "referencia": "" if f[2] is None else str(f[2]),
                "ean": None if f[3] in (None, "") else str(f[3]),
                "id_product": int(f[4]),
            }
            for f in filas
        }

        filas, n = _seleccionar_por_ids(
            cursor,
            """SELECT id_product_attribute, id_shop, available_date
               FROM ps_product_attribute_shop
               WHERE id_product_attribute IN ({placeholders})""",
            ids_atributos,
            tamano_lote,
        )
        consultas += n
        fechas_tienda_atributo = {}
        tiendas_atributo = {}
        for id_atributo, id_shop, fecha in filas:
            id_atributo = int(id_atributo)
            fechas_tienda_atributo.setdefault(id_atributo, []).append(
                _fecha_bd(fecha)
            )
            if int(id_shop) in (1, 99):
                tiendas_atributo.setdefault(id_atributo, set()).add(
                    int(id_shop)
                )

        filas, n = _seleccionar_por_ids(
            cursor,
            """SELECT id_product, id_product_attribute, out_of_stock
               FROM ps_stock_available
               WHERE id_product IN ({placeholders}) AND id_shop=1""",
            ids_productos,
            tamano_lote,
        )
        consultas += n
        fuera_stock_actual = {
            (int(f[0]), int(f[1])): int(f[2]) for f in filas
        }

    colisiones = []
    atributos_desactivados = set()
    for objetivo in objetivos.itertuples(index=False):
        id_atributo = int(objetivo.id_product_attribute)
        if id_atributo <= 0:
            continue
        tiendas = tiendas_atributo.get(id_atributo, set())
        if objetivo.disponible and objetivo.autoriza_reactivacion:
            if {1, 99}.issubset(tiendas):
                colisiones.append(id_atributo)
            elif tiendas == {99}:
                actualizaciones["reactivar_atributo"].append((id_atributo,))
        elif not objetivo.disponible and objetivo.autoriza_id_shop:
            if {1, 99}.issubset(tiendas):
                colisiones.append(id_atributo)
            elif tiendas == {1}:
                actualizaciones["desactivar_atributo"].append((id_atributo,))
                atributos_desactivados.add(int(objetivo.id_product))
    if colisiones:
        raise RuntimeError(
            "Colisión id_shop=1/99 en atributos: "
            + ", ".join(map(str, sorted(set(colisiones))[:20]))
        )
    for id_product in sorted(atributos_desactivados):
        actualizaciones["cache_producto"].append((id_product,))
        actualizaciones["cache_producto_shop"].append((id_product,))

    activaciones = 0
    desactivaciones = 0
    activos_finales = {
        id_product: bool(estado[1])
        for id_product, estado in estados_padre.items()
    }
    for padre in padres.itertuples(index=False):
        id_product = int(padre.id_product)
        actual = estados_padre.get(
            id_product,
            ("", 0, 0, None, 0, False, 0, 0, None, None, None, None),
        )
        fecha = padre.fecha_disponibilidad
        proveedor_etiqueta = padre.proveedor_etiqueta
        if padre.disponible:
            etiqueta_salida = (
                f"Envío el {fecha + timedelta(days=5):%d-%m-%Y}"
                if fecha is not None
                else plazos.get(
                    proveedor_etiqueta,
                    config.etiquetas.entrega_proveedor_predeterminado,
                )
            )
        else:
            etiqueta_salida = config.etiquetas.etiqueta_no_stock
        etiqueta = (config.etiquetas.etiqueta_stock, etiqueta_salida)
        actuales = etiquetas_actuales.get(id_product, [])
        if actuales and any(valor != etiqueta for valor in actuales):
            actualizaciones["etiquetas"].append((*etiqueta, id_product))
        if id_product in estados_padre and (
            actual[3] != fecha or actual[4] != 2
        ):
            actualizaciones["fecha_producto"].append((fecha, id_product))
        if actual[5] and actual[8] != fecha:
            actualizaciones["fecha_producto_shop"].append(
                (fecha, id_product)
            )

        estado_deseado = None
        estado_deseado_shop = None
        if padre.tiene_atributos:
            if padre.disponible:
                estado_deseado = (1, 1)
                estado_deseado_shop = (1, 1)
            else:
                # Históricamente no se desactiva ``active`` del padre por
                # agotar tallas; sí se impide el pedido cuando ninguna queda.
                estado_deseado = (actual[1], 0)
                estado_deseado_shop = (actual[6], 0)
        else:
            estado_deseado = (1, 1) if padre.disponible else (0, 0)
            estado_deseado_shop = estado_deseado
        if estado_deseado is not None:
            activos_finales[id_product] = bool(estado_deseado[0])
            if actual[1:3] != estado_deseado:
                actualizaciones["estado_producto"].append(
                    (*estado_deseado, id_product)
                )
            if actual[5] and actual[6:8] != estado_deseado_shop:
                actualizaciones["estado_producto_shop"].append(
                    (*estado_deseado_shop, id_product)
                )
            if estado_deseado == (1, 1) and (
                actual[1:3] != estado_deseado
                or (actual[5] and actual[6:8] != estado_deseado_shop)
            ):
                activaciones += 1
            if estado_deseado == (0, 0) and (
                actual[1:3] != estado_deseado
                or (actual[5] and actual[6:8] != estado_deseado)
            ):
                desactivaciones += 1

    metadatos_visibilidad = {}
    packs_visibilidad = []
    if incluir_visibilidad:
        # Conserva la regla histórica, pero la evalúa contra ``active`` final
        # para que forme parte del mismo plan y no de una fase recalculada.
        with conexion_prestashop.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.id_product, p.reference, p.active, p.ean13,
                       EXISTS(
                           SELECT 1 FROM ps_product_attribute pa
                           WHERE pa.id_product=p.id_product
                       ) AS tiene_atributos
                FROM ps_product p
                INNER JOIN ps_stock_available s
                  ON s.id_product=p.id_product
                 AND s.id_product_attribute=0
                WHERE p.visibility='none'
                GROUP BY p.id_product, p.active
                HAVING MAX(s.quantity)>0
                """
            )
            candidatos_visibilidad = cursor.fetchall()
        for (
            id_product, referencia, active_actual, ean, tiene_atributos
        ) in candidatos_visibilidad:
            id_product = int(id_product)
            metadatos_visibilidad[id_product] = {
                "referencia": "" if referencia is None else str(referencia),
                "ean": None if ean in (None, "") else str(ean),
                "tiene_atributos": bool(tiene_atributos),
            }
            if _es_referencia_pack(referencia):
                ids_packs.add(id_product)
                if activos_finales.get(id_product, bool(active_actual)):
                    metricas["acciones_pack_descartadas"] += 2
                    packs_visibilidad.append(
                        {
                            "id_product": id_product,
                            "referencia": str(referencia or ""),
                            "ean": None if ean in (None, "") else str(ean),
                            "tiene_atributos": bool(tiene_atributos),
                        }
                    )
                continue
            if activos_finales.get(id_product, bool(active_actual)):
                actualizaciones["visibilidad_producto"].append((id_product,))
                actualizaciones["visibilidad_producto_shop"].append((id_product,))

    for objetivo in objetivos.itertuples(index=False):
        id_product = int(objetivo.id_product)
        id_atributo = int(objetivo.id_product_attribute)
        fecha = objetivo.fecha_disponibilidad
        if id_atributo > 0:
            if fechas_atributo.get(id_atributo) != fecha:
                actualizaciones["fecha_atributo"].append(
                    (fecha, id_atributo)
                )
            fechas_tienda = fechas_tienda_atributo.get(id_atributo, [])
            if fechas_tienda and any(valor != fecha for valor in fechas_tienda):
                actualizaciones["fecha_atributo_shop"].append(
                    (fecha, id_atributo)
                )
        deseado_fuera_stock = (
            2
            if id_atributo > 0 or objetivo.disponible
            else config.etiquetas.denegar_pedido
        )
        clave = (id_product, id_atributo)
        if (
            clave in fuera_stock_actual
            and fuera_stock_actual[clave] != deseado_fuera_stock
        ):
            actualizaciones["out_of_stock"].append(
                (deseado_fuera_stock, id_product, id_atributo)
            )

    actualizaciones, descartadas_finales = _excluir_acciones_pack(
        actualizaciones,
        ids_packs,
        id_product_por_atributo,
    )
    metricas["acciones_pack_descartadas"] += descartadas_finales
    cambios_finales = sum(len(filas) for filas in actualizaciones.values())
    metricas.update(
        {
            "packs_detectados": len(ids_packs),
            "packs_excluidos": len(ids_packs),
            # Se mantienen por compatibilidad; ningún pack llega a estas ramas.
            "packs_activados": 0,
            "packs_conservados_inactivos": 0,
            "reactivaciones_id_shop_autorizadas": len(
                actualizaciones["reactivar_atributo"]
            ),
            "desactivaciones_id_shop_autorizadas": len(
                actualizaciones["desactivar_atributo"]
            ),
            "activaciones": activaciones,
            "desactivaciones": desactivaciones,
            "cambios_finales": cambios_finales,
            "cambios_funcionales": cambios_finales,
            "consultas_select": consultas,
            "visibilidad_productos": len(
                actualizaciones["visibilidad_producto"]
            ),
            "proveedores_autorizados_id_shop": tuple(
                sorted(PROVEEDORES_GESTION_ID_SHOP)
            ),
        }
    )
    acciones_detalladas = _construir_acciones_detalladas(
        actualizaciones,
        objetivos_originales,
        padres_originales,
        estados_padre,
        ids_packs=ids_packs,
        metadatos_atributo=metadatos_atributo,
        fechas_atributo=fechas_atributo,
        fechas_tienda_atributo=fechas_tienda_atributo,
        tiendas_atributo=tiendas_atributo,
        etiquetas_actuales=etiquetas_actuales,
        fuera_stock_actual=fuera_stock_actual,
        metadatos_visibilidad=metadatos_visibilidad,
        packs_visibilidad=packs_visibilidad,
    )
    metricas.update(_metricas_trazabilidad(acciones_detalladas))
    return PlanGlobalPrestaShop(
        objetivos=objetivos,
        padres=padres,
        actualizaciones=actualizaciones,
        metricas=metricas,
        ids_packs_excluidos=tuple(sorted(ids_packs)),
        id_product_por_atributo=id_product_por_atributo,
        acciones_detalladas=acciones_detalladas,
    )


SQL_ACTUALIZACIONES = {
    "reactivar_atributo": """
        UPDATE ps_product_attribute_shop SET id_shop=1
        WHERE id_product_attribute=%s AND id_shop=99
    """,
    "desactivar_atributo": """
        UPDATE ps_product_attribute_shop SET id_shop=99
        WHERE id_product_attribute=%s AND id_shop=1
    """,
    "cache_producto": """
        UPDATE ps_product SET cache_default_attribute=NULL
        WHERE id_product=%s
    """,
    "cache_producto_shop": """
        UPDATE ps_product_shop SET cache_default_attribute=NULL
        WHERE id_product=%s AND id_shop=1
    """,
    "etiquetas": """
        UPDATE ps_product_lang
        SET delivery_in_stock=%s, delivery_out_stock=%s
        WHERE id_product=%s AND id_shop=1
    """,
    "fecha_producto": """
        UPDATE ps_product SET available_date=%s, additional_delivery_times=2
        WHERE id_product=%s
    """,
    "fecha_producto_shop": """
        UPDATE ps_product_shop SET available_date=%s
        WHERE id_product=%s AND id_shop=1
    """,
    "estado_producto": """
        UPDATE ps_product SET active=%s, available_for_order=%s
        WHERE id_product=%s
    """,
    "estado_producto_shop": """
        UPDATE ps_product_shop SET active=%s, available_for_order=%s
        WHERE id_product=%s AND id_shop=1
    """,
    "fecha_atributo": """
        UPDATE ps_product_attribute SET available_date=%s
        WHERE id_product_attribute=%s
    """,
    "fecha_atributo_shop": """
        UPDATE ps_product_attribute_shop SET available_date=%s
        WHERE id_product_attribute=%s
    """,
    "out_of_stock": """
        UPDATE ps_stock_available SET out_of_stock=%s
        WHERE id_product=%s AND id_product_attribute=%s AND id_shop=1
    """,
    "visibilidad_producto": """
        UPDATE ps_product SET visibility='both' WHERE id_product=%s
    """,
    "visibilidad_producto_shop": """
        UPDATE ps_product_shop SET visibility='both'
        WHERE id_product=%s AND id_shop=1
    """,
}


def aplicar_plan_global(
    conexion_prestashop,
    plan: PlanGlobalPrestaShop,
    *,
    tamano_lote: int = 1000,
) -> ResultadoAplicacionPlanGlobal:
    """Aplica el plan tras repetir la exclusión final de padres ``pack_``."""

    validar_conexion_configurada(
        conexion_prestashop,
        BASE_PRESTASHOP_ACTIVA,
        tipo_conexion=TIPO_PRESTASHOP,
    )
    if plan.colisiones_tienda:
        raise RuntimeError("No se aplica un plan con colisiones id_shop")
    ids_productos, ids_atributos = _destinos_de_actualizaciones(
        plan.actualizaciones,
        plan.id_product_por_atributo,
    )
    ids_packs_finales = set(plan.ids_packs_excluidos)
    id_product_por_atributo = dict(plan.id_product_por_atributo)
    consultas_seguridad = 0
    with conexion_prestashop.cursor() as cursor:
        filas, n = _seleccionar_por_ids(
            cursor,
            """SELECT id_product, reference FROM ps_product
               WHERE id_product IN ({placeholders})""",
            sorted(ids_productos),
            tamano_lote,
        )
        consultas_seguridad += n
        ids_packs_finales.update(
            int(id_product)
            for id_product, referencia in filas
            if _es_referencia_pack(referencia)
        )
        filas, n = _seleccionar_por_ids(
            cursor,
            """SELECT pa.id_product_attribute, pa.id_product, p.reference
               FROM ps_product_attribute pa
               INNER JOIN ps_product p ON p.id_product=pa.id_product
               WHERE pa.id_product_attribute IN ({placeholders})""",
            sorted(ids_atributos),
            tamano_lote,
        )
        consultas_seguridad += n
        for id_atributo, id_product, referencia in filas:
            id_product = int(id_product)
            id_product_por_atributo[int(id_atributo)] = id_product
            if _es_referencia_pack(referencia):
                ids_packs_finales.add(id_product)
    actualizaciones, descartadas_finales = _excluir_acciones_pack(
        plan.actualizaciones,
        ids_packs_finales,
        id_product_por_atributo,
    )
    metricas_plan = dict(plan.metricas)
    metricas_plan["packs_detectados"] = len(ids_packs_finales)
    metricas_plan["packs_excluidos"] = len(ids_packs_finales)
    metricas_plan["consultas_select"] = int(
        metricas_plan.get("consultas_select", 0)
    ) + consultas_seguridad
    metricas_plan["acciones_pack_descartadas"] = int(
        metricas_plan.get("acciones_pack_descartadas", 0)
    ) + descartadas_finales
    if descartadas_finales:
        for nombre in ("cambios_finales", "cambios_funcionales"):
            metricas_plan[nombre] = max(
                int(metricas_plan.get(nombre, 0)) - descartadas_finales,
                0,
            )
    sentencias = 0
    lotes = 0
    modificadas = 0
    try:
        conexion_prestashop.rollback()
        conexion_prestashop.begin()
        with conexion_prestashop.cursor() as cursor:
            # El orden respeta primero el estado de combinaciones y después
            # el padre; todas las decisiones ya están cerradas en el plan.
            for nombre, sql in SQL_ACTUALIZACIONES.items():
                filas = actualizaciones.get(nombre, ())
                for lote in _en_lotes(filas, tamano_lote):
                    if not lote:
                        continue
                    cursor.executemany(sql, lote)
                    sentencias += len(lote)
                    lotes += 1
                    modificadas += max(int(getattr(cursor, "rowcount", 0)), 0)
        conexion_prestashop.commit()
    except Exception:
        conexion_prestashop.rollback()
        raise
    return ResultadoAplicacionPlanGlobal(
        metricas_plan=metricas_plan,
        filas_modificadas=modificadas,
        sentencias_sql=sentencias,
        lotes_update=lotes,
    )
