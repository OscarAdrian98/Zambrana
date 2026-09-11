"""Único launcher autorizado para la futura ejecución de producción."""

from __future__ import annotations

import argparse
import os

from config.bd import (
    BASE_PRESTASHOP_OPERATIVA,
    BASE_PROVEEDORES_OPERATIVA,
    ENTORNO_OPERATIVO,
)
from config.lote_validacion import PROVEEDORES_OPERATIVOS_VALIDACION
from config.operativa import validar_secretos_operativos
from config.resultado import construir_resumen_terminal
from main import main


EXIT_SUCCESS = 0
EXIT_ERROR = 1
PROVEEDORES_OPERATIVOS = PROVEEDORES_OPERATIVOS_VALIDACION


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ejecución operativa controlada de Stock 2.0",
    )
    modos = parser.add_mutually_exclusive_group(required=True)
    modos.add_argument(
        "--report-only",
        action="store_true",
        help=(
            "persiste proveedores y genera candidatos sin escribir cambios "
            "funcionales en PrestaShop"
        ),
    )
    modos.add_argument(
        "--apply",
        action="store_true",
        help="aplica la sincronización autorizada en PrestaShop",
    )
    return parser


def _validar_autorizaciones(*, aplicar: bool) -> None:
    if os.environ.get("STOCK_ENV") != ENTORNO_OPERATIVO:
        raise SystemExit("STOCK_ENV debe ser operational")
    if aplicar and os.environ.get("STOCK_OPERATIONAL_WRITES_AUTHORIZED") != "SI":
        raise SystemExit(
            "--apply requiere STOCK_OPERATIONAL_WRITES_AUTHORIZED=SI"
        )


def ejecutar(argv=None) -> int:
    args = _parser().parse_args(argv)
    _validar_autorizaciones(aplicar=args.apply)
    if not PROVEEDORES_OPERATIVOS:
        raise SystemExit("Configure STOCK_PROVIDER_IDS before running an integration.")
    validar_secretos_operativos()
    resultado = main(
        PROVEEDORES_OPERATIVOS,
        ejecutar_huerfanos=False,
        ejecutar_obsoletos=False,
        ejecutar_visibilidad=True,
        enviar_notificacion=True,
        prefijo_asunto="[STOCK 2 OPERATIVO] ",
        base_prestashop_esperada=BASE_PRESTASHOP_OPERATIVA,
        base_proveedores_esperada=BASE_PROVEEDORES_OPERATIVA,
        solo_previsualizar_prestashop=args.report_only,
        detener_en_primer_fallo=True,
        refrescar_prestashop_entre_proveedores=True,
    )
    exit_code = (
        EXIT_SUCCESS if resultado.estado.value == "SUCCESS" else EXIT_ERROR
    )
    print(
        construir_resumen_terminal(
            resultado,
            total_proveedores=len(PROVEEDORES_OPERATIVOS),
            exit_code=exit_code,
            cambios_aplicados=args.apply,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(ejecutar())
