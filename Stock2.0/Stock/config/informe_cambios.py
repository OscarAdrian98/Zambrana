"""Informe humano de cambios funcionales de una ejecución de Stock3."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from uuid import uuid4

from config.logging import RAIZ


SECCIONES = (
    ("ACTIVADOS", "ACTIVAR_PRODUCTO"),
    ("DESACTIVADOS", "DESACTIVAR_PRODUCTO"),
    ("PEDIDO HABILITADO", "ACTIVAR_PEDIDO"),
    ("PEDIDO DESHABILITADO", "DESACTIVAR_PEDIDO"),
    ("COMBINACIONES 99 → 1", "REACTIVAR_COMBINACION_99_A_1"),
    ("COMBINACIONES 1 → 99", "DESACTIVAR_COMBINACION_1_A_99"),
    ("PACKS EXCLUIDOS", "EXCLUIDO_PACK"),
    ("CONFLICTOS DESCARTADOS", "CONFLICTO_DESCARTADO"),
)

ETIQUETAS_RESUMEN = (
    ("Activados", "ACTIVADOS"),
    ("Desactivados", "DESACTIVADOS"),
    ("Pedido habilitado", "PEDIDO HABILITADO"),
    ("Pedido deshabilitado", "PEDIDO DESHABILITADO"),
    ("99 → 1", "COMBINACIONES 99 → 1"),
    ("1 → 99", "COMBINACIONES 1 → 99"),
    ("Packs excluidos", "PACKS EXCLUIDOS"),
    ("Conflictos", "CONFLICTOS DESCARTADOS"),
)

TIPOS_SIN_DUPLICADO_TIENDA = {
    "ACTIVAR_PRODUCTO",
    "DESACTIVAR_PRODUCTO",
    "ACTIVAR_PEDIDO",
    "DESACTIVAR_PEDIDO",
}


def carpeta_logs() -> Path:
    carpeta = Path(os.environ.get("STOCK_LOG_DIR", "logs"))
    if not carpeta.is_absolute():
        carpeta = RAIZ / carpeta
    return carpeta


def carpeta_informes() -> Path:
    return carpeta_logs() / "informes"


def _acciones_del_plan(plan) -> tuple[dict, ...]:
    if plan is None:
        return ()
    if isinstance(plan, dict):
        return tuple(plan.get("acciones", ()) or ())
    return tuple(getattr(plan, "acciones_detalladas", ()) or ())


def _acciones_humanas(plan) -> tuple[dict, ...]:
    acciones = []
    for accion in _acciones_del_plan(plan):
        tipo = accion.get("tipo_accion")
        if (
            tipo in TIPOS_SIN_DUPLICADO_TIENDA
            and accion.get("tabla") != "ps_product"
        ):
            continue
        acciones.append(dict(accion))
    return tuple(acciones)


def _valor(valor) -> str:
    if valor is None:
        return "ninguno"
    if isinstance(valor, dict):
        return ", ".join(
            f"{clave}={_valor(elemento)}"
            for clave, elemento in valor.items()
        )
    if isinstance(valor, (list, tuple, set)):
        return ",".join(map(str, valor)) or "ninguno"
    return str(valor)


def _tienda(accion: dict) -> str:
    tipo = accion.get("tipo_accion")
    if tipo == "REACTIVAR_COMBINACION_99_A_1":
        return "id_shop=99 → 1"
    if tipo == "DESACTIVAR_COMBINACION_1_A_99":
        return "id_shop=1 → 99"
    if accion.get("tabla") in {
        "ps_product_shop",
        "ps_product_attribute_shop",
        "ps_stock_available",
    }:
        return "id_shop=1"
    return "id_shop=global"


def _linea_accion(accion: dict) -> str:
    partes = [f"id_product={accion.get('id_product', '')}"]
    id_atributo = accion.get("id_product_attribute")
    if id_atributo:
        partes.append(f"id_product_attribute={id_atributo}")
    proveedores = tuple(accion.get("proveedores", ()) or ())
    etiqueta_proveedor = "proveedor" if len(proveedores) == 1 else "proveedores"
    partes.extend(
        [
            f"referencia={accion.get('referencia', '')}",
            _tienda(accion),
            "cambio="
            f"{_valor(accion.get('valor_anterior'))} → "
            f"{_valor(accion.get('valor_deseado'))}",
            f"{etiqueta_proveedor}={_valor(proveedores)}",
            f"motivo={accion.get('motivo', '')}",
        ]
    )
    if accion.get("match_method"):
        partes.extend(
            [
                f"match={accion['match_method']}",
                f"valor_match={_valor(accion.get('match_value'))}",
            ]
        )
    return " | ".join(partes)


def _motivo_resumido(errores) -> str:
    for error in errores or ():
        texto = " ".join(str(error).split())
        if texto:
            return texto[:500]
    return "Fallo anterior a la generación del plan"


def _informe_failed_sin_plan(
    *,
    instante: datetime,
    modo: str,
    proveedores_fallidos,
    errores,
) -> str:
    proveedores = ", ".join(map(str, proveedores_fallidos or ()))
    etiqueta = (
        "Proveedor fallido"
        if len(tuple(proveedores_fallidos or ())) <= 1
        else "Proveedores fallidos"
    )
    return "\n".join(
        [
            "INFORME DE CAMBIOS STOCK3.0",
            f"Fecha: {instante.strftime('%d/%m/%Y %H:%M')}",
            f"Modo: {modo}",
            "Resultado: FAILED",
            "",
            "NO SE GENERÓ PLAN DE CAMBIOS",
            "",
            f"{etiqueta}: {proveedores or 'no identificado'}",
            f"Motivo: {_motivo_resumido(errores)}",
            "",
            "Cambios aplicados en PrestaShop: 0",
            "",
            "La ejecución se detuvo antes de la resolución global,",
            "por lo que no existen referencias activadas, desactivadas",
            "ni modificadas por esta ejecución.",
            "",
        ]
    )


def construir_informe_cambios(
    plan,
    *,
    execution_id: str,
    modo: str,
    resultado: str,
    cambios_aplicados: bool | None = None,
    proveedores_fallidos=(),
    errores=(),
    fecha_hora: datetime | None = None,
) -> str:
    """Construye exclusivamente trazabilidad funcional, sin datos técnicos."""

    instante = fecha_hora or datetime.now().astimezone()
    if resultado == "FAILED" and plan is None:
        return _informe_failed_sin_plan(
            instante=instante,
            modo=modo,
            proveedores_fallidos=tuple(proveedores_fallidos or ()),
            errores=errores,
        )
    acciones = _acciones_humanas(plan)
    if cambios_aplicados is None:
        cambios_aplicados = modo == "apply" and resultado == "SUCCESS"
    estado_cambios = (
        "PROPUESTOS, NO APLICADOS"
        if modo == "report-only"
        else ("APLICADOS" if cambios_aplicados else "NO APLICADOS")
    )
    lineas = [
        "INFORME DE CAMBIOS STOCK3.0",
        f"Fecha: {instante.strftime('%d/%m/%Y %H:%M')}",
        f"Modo: {modo}",
        f"Resultado: {resultado}",
        f"Estado de los cambios: {estado_cambios}",
        "",
    ]
    totales = {}
    for titulo, tipo in SECCIONES:
        seleccion = [
            accion for accion in acciones
            if accion.get("tipo_accion") == tipo
        ]
        totales[titulo] = len(seleccion)
        lineas.extend([titulo, "-" * len(titulo)])
        if seleccion:
            lineas.extend(_linea_accion(accion) for accion in seleccion)
        else:
            lineas.append("Sin cambios")
        lineas.append("")

    ids_packs = set(
        getattr(plan, "ids_packs_excluidos", ()) or ()
        if not isinstance(plan, dict)
        else (
            accion.get("id_product")
            for accion in acciones
            if accion.get("tipo_accion") == "EXCLUIDO_PACK"
        )
    )
    packs_modificados = sum(
        bool(accion.get("aplicable", True))
        and accion.get("tipo_accion") != "EXCLUIDO_PACK"
        and accion.get("id_product") in ids_packs
        for accion in acciones
    )
    lineas.extend(
        [
            "RESUMEN",
            "-------",
            *(
                f"{etiqueta}: {totales[seccion]}"
                for etiqueta, seccion in ETIQUETAS_RESUMEN
            ),
            f"Añadidas al informe: {sum(totales.values())}",
            f"Packs modificados: {packs_modificados}",
            "",
        ]
    )
    return "\n".join(lineas)


def persistir_informe_cambios(
    plan,
    *,
    execution_id: str,
    modo: str,
    resultado: str,
    cambios_aplicados: bool | None = None,
    proveedores_fallidos=(),
    errores=(),
    fecha_hora: datetime | None = None,
    destino: Path | None = None,
) -> Path:
    """Publica el informe completo en UTF-8 mediante un rename atómico."""

    instante = fecha_hora or datetime.now().astimezone()
    contenido = construir_informe_cambios(
        plan,
        execution_id=execution_id,
        modo=modo,
        resultado=resultado,
        cambios_aplicados=cambios_aplicados,
        proveedores_fallidos=proveedores_fallidos,
        errores=errores,
        fecha_hora=instante,
    )
    marca = instante.strftime("%Y%m%d_%H%M%S_%f")
    ruta = Path(destino) if destino else (
        carpeta_informes() / f"{marca}_{execution_id}_cambios.txt"
    )
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        raise FileExistsError(f"El informe ya existe: {ruta}")
    temporal = ruta.with_name(f".{ruta.name}.{uuid4().hex}.tmp")
    try:
        with temporal.open("x", encoding="utf-8", newline="\n") as fichero:
            fichero.write(contenido)
            fichero.flush()
            os.fsync(fichero.fileno())
        if ruta.exists():
            raise FileExistsError(f"El informe ya existe: {ruta}")
        os.replace(temporal, ruta)
    finally:
        if temporal.exists():
            temporal.unlink()
    return ruta
