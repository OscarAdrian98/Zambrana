"""Persistencia inmutable y legible del plan global de PrestaShop."""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

from config.logging import RAIZ


def nuevo_execution_id() -> str:
    return uuid4().hex


def _ahora() -> datetime:
    return datetime.now().astimezone()


def carpeta_planes() -> Path:
    carpeta_logs = Path(os.environ.get("STOCK_LOG_DIR", "logs"))
    if not carpeta_logs.is_absolute():
        carpeta_logs = RAIZ / carpeta_logs
    return carpeta_logs / "planes"


def _json_default(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if hasattr(valor, "item"):
        return valor.item()
    raise TypeError(f"Tipo no serializable: {type(valor).__name__}")


def _escribir_json_atomico(ruta: Path, contenido: dict) -> Path:
    """Publica un JSON completo mediante temporal y rename en igual carpeta."""

    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        raise FileExistsError(f"La evidencia ya existe: {ruta}")
    temporal = ruta.with_name(f".{ruta.name}.{uuid4().hex}.tmp")
    try:
        with temporal.open("x", encoding="utf-8", newline="\n") as fichero:
            json.dump(
                contenido,
                fichero,
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
            fichero.write("\n")
            fichero.flush()
            os.fsync(fichero.fileno())
        # El nombre contiene un UUID por ejecucion. La comprobacion previa
        # evita reescrituras y replace impide exponer un fichero parcial.
        if ruta.exists():
            raise FileExistsError(f"La evidencia ya existe: {ruta}")
        os.replace(temporal, ruta)
    finally:
        if temporal.exists():
            temporal.unlink()
    return ruta


def persistir_plan_detallado(
    plan,
    *,
    execution_id: str,
    modo: str,
    fecha_hora: datetime | None = None,
    destino: Path | None = None,
) -> tuple[Path, dict]:
    """Guarda la evidencia previa al SQL y devuelve su contenido exacto."""

    if modo not in {"report-only", "apply"}:
        raise ValueError(f"Modo de trazabilidad no valido: {modo}")
    instante = fecha_hora or _ahora()
    acciones = [
        {
            "execution_id": execution_id,
            "fecha_hora": instante.isoformat(),
            "modo": modo,
            **dict(accion),
        }
        for accion in getattr(plan, "acciones_detalladas", ())
    ]
    metricas = dict(getattr(plan, "metricas", {}))
    contenido = {
        "esquema": "stock3-plan-detallado-v1",
        "execution_id": execution_id,
        "fecha_hora": instante.isoformat(),
        "modo": modo,
        "estado": "PROPUESTO" if modo == "report-only" else "PREVIO_AL_SQL",
        "metricas": metricas,
        "total_acciones": len(acciones),
        "acciones": acciones,
    }
    marca = instante.strftime("%Y%m%d_%H%M%S_%f")
    ruta = destino or (
        carpeta_planes() / f"{marca}_{execution_id}_{modo}_plan.json"
    )
    return _escribir_json_atomico(Path(ruta), contenido), contenido


def persistir_resultado_ejecucion(
    *,
    execution_id: str,
    modo: str,
    ruta_plan: Path,
    success: bool,
    filas_modificadas: int = 0,
    rowcount: int = 0,
    commits: int = 0,
    error_tipo: str | None = None,
    fecha_hora: datetime | None = None,
) -> Path:
    """Crea un resultado separado sin modificar el plan previo."""

    instante = fecha_hora or _ahora()
    nombre_plan = Path(ruta_plan).name
    sufijo = "_plan.json"
    base = nombre_plan[:-len(sufijo)] if nombre_plan.endswith(sufijo) else nombre_plan
    ruta = Path(ruta_plan).with_name(f"{base}_resultado.json")
    contenido = {
        "esquema": "stock3-resultado-ejecucion-v1",
        "execution_id": execution_id,
        "modo": modo,
        "plan": str(ruta_plan),
        "success": bool(success),
        "estado": (
            "PROPUESTO"
            if modo == "report-only" and success
            else ("APLICADO" if success else "FALLIDO")
        ),
        "filas_modificadas": int(filas_modificadas),
        "rowcount": int(rowcount),
        "commits": int(commits),
        "hora_final": instante.isoformat(),
        # Nunca se serializa el mensaje de una excepcion: puede contener
        # parametros de conexion. El tipo basta para la auditoria tecnica.
        "error_tipo": error_tipo,
    }
    return _escribir_json_atomico(ruta, contenido)


def registrar_acciones_humanas(plan, *, modo: str) -> None:
    """Registra solo cambios comerciales, packs y conflictos."""

    prefijo = "ACCION PROPUESTA" if modo == "report-only" else "ACCION APLICADA"
    nombres = {
        "ACTIVAR_PRODUCTO": "ACTIVADO",
        "DESACTIVAR_PRODUCTO": "DESACTIVADO",
        "ACTIVAR_PEDIDO": "AVAILABLE_FOR_ORDER 0→1",
        "DESACTIVAR_PEDIDO": "AVAILABLE_FOR_ORDER 1→0",
        "REACTIVAR_COMBINACION_99_A_1": "COMBINACION 99→1",
        "DESACTIVAR_COMBINACION_1_A_99": "COMBINACION 1→99",
        "EXCLUIDO_PACK": "PACK EXCLUIDO",
        "CONFLICTO_DESCARTADO": "CONFLICTO DESCARTADO",
    }
    for accion in getattr(plan, "acciones_detalladas", ()):
        tipo = accion.get("tipo_accion")
        if tipo not in nombres:
            continue
        # active/available_for_order se refleja en dos tablas; el log humano
        # muestra una sola linea comercial y el JSON conserva ambas.
        if tipo in {
            "ACTIVAR_PRODUCTO", "DESACTIVAR_PRODUCTO",
            "ACTIVAR_PEDIDO", "DESACTIVAR_PEDIDO",
        } and accion.get("tabla") != "ps_product":
            continue
        proveedores = ",".join(map(str, accion.get("proveedores", ()))) or "ninguno"
        atributos = ""
        if accion.get("id_product_attribute"):
            atributos = (
                " | id_product_attribute="
                f"{accion['id_product_attribute']}"
            )
        logging.info(
            "%s | %s | id_product=%s%s | ref=%s | proveedores=%s | "
            "match=%s | valor_match=%s | motivo=%s",
            prefijo,
            nombres[tipo],
            accion.get("id_product"),
            atributos,
            accion.get("referencia", ""),
            proveedores,
            accion.get("match_method", ""),
            accion.get("match_value", ""),
            accion.get("motivo", ""),
        )
