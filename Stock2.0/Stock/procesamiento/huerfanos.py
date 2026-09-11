"""Clasificación conservadora de productos potencialmente huérfanos."""

from __future__ import annotations

import re

import pandas as pd

from config.lote_validacion import PROVEEDORES_OPERATIVOS_VALIDACION
from procesamiento.reglas import normalizar_ean, normalizar_identificador


DECISION_SEGURO = "SEGURO PARA DESACTIVAR"
DECISION_DUDOSO = "DUDOSO / REVISIÓN MANUAL"
DECISION_NO_DESACTIVAR = "NO DESACTIVAR"


def identificador_flexible(valor) -> str | None:
    """Normalización diagnóstica; nunca se usa para declarar disponibilidad."""

    texto = normalizar_identificador(valor)
    if texto is None:
        return None
    compacto = re.sub(r"[^0-9a-z]", "", texto.casefold())
    return compacto or None


def ean_valido(valor) -> bool:
    """Valida longitud y dígito de control de un GTIN/EAN/UPC."""

    ean = normalizar_ean(valor)
    if ean is None or len(ean) not in {8, 12, 13, 14}:
        return False
    suma = sum(
        int(digito) * (3 if posicion % 2 else 1)
        for posicion, digito in enumerate(reversed(ean[:-1]), start=1)
    )
    control = (10 - suma % 10) % 10
    return control == int(ean[-1])


def referencia_valida(valor) -> bool:
    """Exige una referencia imprimible con contenido alfanumérico."""

    referencia = normalizar_identificador(valor)
    return bool(
        referencia
        and len(referencia) <= 128
        and referencia.isprintable()
        and any(caracter.isalnum() for caracter in referencia)
    )


def _entero(fila, columna) -> int:
    valor = fila.get(columna, 0)
    try:
        return int(float(valor)) if not pd.isna(valor) else 0
    except (TypeError, ValueError):
        return 0


def _booleano(fila, columna) -> bool:
    return _entero(fila, columna) > 0


def _clasificar_fila(fila: pd.Series) -> tuple[str, str, str]:
    tiene_referencia_valida = referencia_valida(fila.get("reference"))
    tiene_ean_valido = ean_valido(fila.get("ean13"))
    proveedores_marca = set(fila.get("proveedores_marca_ids") or ())
    proveedores_fuera = proveedores_marca - set(PROVEEDORES_OPERATIVOS_VALIDACION)
    proveedores_supplier_fuera = set(
        fila.get("proveedores_supplier_fuera_lote_ids") or ()
    )
    proveedores_historicos_fuera = set(
        fila.get("proveedores_historicos_fuera_lote_ids") or ()
    )

    if not _booleano(fila, "active"):
        return (
            DECISION_NO_DESACTIVAR,
            "producto_ya_inactivo",
            "el producto ya está inactivo y no necesita ninguna acción",
        )
    if (
        _entero(fila, "stock_ps") > 0
        or _booleano(fila, "combinacion_con_stock_ps")
        or _entero(fila, "stock_total_combinaciones") > 0
    ):
        return (
            DECISION_NO_DESACTIVAR,
            "stock_prestashop",
            "existe stock en el padre o en alguna combinación",
        )
    if _booleano(fila, "variantes_presentes"):
        return (
            DECISION_NO_DESACTIVAR,
            "variante_presente",
            "existe una variante presente por referencia o EAN",
        )
    if _booleano(fila, "productos_actuales"):
        return (
            DECISION_NO_DESACTIVAR,
            "presente_en_productos",
            "continúa en productos y requiere investigación de compatibilidad",
        )
    if _booleano(fila, "referencias_supplier_presentes"):
        return (
            DECISION_NO_DESACTIVAR,
            "referencia_supplier_presente",
            "una referencia de ps_product_supplier sigue presente en proveedor",
        )
    if (
        proveedores_fuera
        or proveedores_supplier_fuera
        or proveedores_historicos_fuera
    ):
        ids = sorted(
            proveedores_fuera
            | proveedores_supplier_fuera
            | proveedores_historicos_fuera
        )
        return (
            DECISION_NO_DESACTIVAR,
            "proveedor_fuera_lote",
            "puede depender de proveedor no procesado: " + ",".join(map(str, ids)),
        )
    if _booleano(fila, "asociaciones_supplier_no_mapeadas"):
        return (
            DECISION_NO_DESACTIVAR,
            "otra_fuente_no_mapeada",
            "mantiene una asociación PrestaShop con una fuente no mapeada",
        )
    if _entero(fila, "asociaciones_supplier") > 1:
        return (
            DECISION_DUDOSO,
            "multiples_asociaciones_supplier",
            "mantiene varias asociaciones históricas en ps_product_supplier",
        )
    if not proveedores_marca:
        return (
            DECISION_DUDOSO,
            "fabricante_sin_ambito",
            "el fabricante no tiene proveedores configurados",
        )
    if not tiene_referencia_valida or not tiene_ean_valido:
        return (
            DECISION_DUDOSO,
            "identificador_insuficiente",
            "se exige referencia no vacía y EAN numérico válido para automatizar",
        )
    if _booleano(fila, "conflicto_identidad_ps"):
        return (
            DECISION_DUDOSO,
            "conflicto_identidad",
            "la referencia o el EAN identifica varios destinos PrestaShop",
        )
    if _booleano(fila, "coincidencia_flexible_proveedor"):
        return (
            DECISION_DUDOSO,
            "posible_cambio_identificador",
            "existe una coincidencia solo tras una normalización no exacta",
        )

    if _booleano(fila, "variantes_historicas"):
        return (
            DECISION_SEGURO,
            "historico_ausente_confirmado",
            "todas las variantes históricas están ausentes y no hay otra fuente actual",
        )
    return (
        DECISION_SEGURO,
        "sin_historial_marca_totalmente_sincronizada",
        "sin historial identificable, con marca cubierta solo por proveedores procesados",
    )


def clasificar_evidencias_huerfanos(evidencias: pd.DataFrame) -> pd.DataFrame:
    """Clasifica evidencias ya recopiladas sin acceder a bases de datos."""

    resultado = evidencias.copy()
    clasificaciones = resultado.apply(_clasificar_fila, axis=1)
    resultado["decision"] = clasificaciones.map(lambda valor: valor[0])
    resultado["categoria"] = clasificaciones.map(lambda valor: valor[1])
    resultado["motivo_clasificacion"] = clasificaciones.map(lambda valor: valor[2])
    resultado["accion_propuesta"] = resultado["decision"].map(
        {
            DECISION_SEGURO: "SET active = 0 (NO EJECUTADO)",
            DECISION_DUDOSO: "revisión manual",
            DECISION_NO_DESACTIVAR: "ninguna",
        }
    )
    return resultado
