"""Retención conservadora de evidencias generadas por Stock3."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from pathlib import Path

from config.informe_cambios import carpeta_logs


PATRONES_RETENCION = {
    ".": (
        "stock2-general.log.*",
        "stock2-resumen.log.*",
        "stock2-errores.log.*",
    ),
    "planes": ("*_plan.json", "*_resultado.json"),
    "informes": ("*_cambios.txt",),
}


def _ruta_resuelta(ruta: Path) -> Path:
    return ruta.resolve(strict=False)


def limpiar_archivos_antiguos(
    *,
    dias: int = 7,
    ahora: datetime | None = None,
    protegidos=(),
    raiz_logs: Path | None = None,
) -> dict[str, int]:
    """Borra solo ficheros Stock3 vencidos y nunca los de esta ejecución."""

    if dias < 1:
        raise ValueError("La retención debe ser de al menos un día")
    instante = ahora or datetime.now().astimezone()
    limite = instante.timestamp() - timedelta(days=dias).total_seconds()
    raiz = _ruta_resuelta(Path(raiz_logs) if raiz_logs else carpeta_logs())
    protegidos_resueltos = {
        _ruta_resuelta(Path(ruta)) for ruta in protegidos if ruta is not None
    }
    eliminados = 0
    conservados = 0
    errores = 0
    vistos = set()
    for subcarpeta, patrones in PATRONES_RETENCION.items():
        carpeta = raiz if subcarpeta == "." else raiz / subcarpeta
        if not carpeta.is_dir():
            continue
        for patron in patrones:
            for ruta in carpeta.glob(patron):
                ruta_resuelta = _ruta_resuelta(ruta)
                if ruta_resuelta in vistos or not ruta.is_file():
                    continue
                vistos.add(ruta_resuelta)
                if ruta_resuelta in protegidos_resueltos:
                    conservados += 1
                    continue
                try:
                    if ruta.stat().st_mtime >= limite:
                        conservados += 1
                        continue
                    ruta.unlink()
                    eliminados += 1
                except OSError:
                    errores += 1
                    logging.exception(
                        "No se pudo aplicar retención a %s", ruta
                    )
    return {
        "eliminados": eliminados,
        "conservados": conservados,
        "errores": errores,
    }
