"""
services/cliente_service.py - Logica de negocio para crear/activar clientes Ambar.
"""
import logging
from datetime import date

import pyodbc

from app.schemas.cliente import (
    ActivarClienteResponseDTO,
    CrearClienteRequestDTO,
    CrearClienteResponseDTO,
)
from app.repositories import clientes_repository as rc
from app.services import normalizacion_service as ns
from app.services.cliente_fiscal_service import (
    CountryResolutionError,
    build_ambar_customer_fiscal_profile,
)

logger = logging.getLogger(__name__)


def crear_cliente(
    conn: pyodbc.Connection,
    req: CrearClienteRequestDTO,
) -> CrearClienteResponseDTO:
    """
    Crea un nuevo cliente en Ambar con logica de negocio legacy,
    manteniendo SQL parametrizado via repositorio.
    """
    try:
        fiscal_profile = build_ambar_customer_fiscal_profile(
            req.cod_pais,
            req.pais,
            req.tiene_iva,
        )
        id_cliente = rc.obtener_proximo_id_cliente(conn)
        cc_cliente = f"43{id_cliente:07d}"

        if fiscal_profile.pais_codigo == "PT":
            dni = req.dni
            if not dni.upper().startswith("PT"):
                dni = f"PT{dni}"
            if not req.tiene_iva:
                serie = "X"
            else:
                serie = "W"
        else:
            dni = req.dni
            serie = "W" if req.tiene_iva else "Z"

        logger.info(
            "Alta cliente perfil fiscal pedido_ps=%s iso=%s pais=%s tipo_documento=%s tiene_iva=%s iva_regimen=%s iva_clase=%s serie=%s",
            req.id_pedido,
            fiscal_profile.pais_codigo,
            fiscal_profile.pais,
            fiscal_profile.tipo_documento,
            req.tiene_iva,
            fiscal_profile.iva_regimen,
            fiscal_profile.iva_clase,
            serie,
        )

        telefonos = ns.combinar_telefonos_ambar(req.movil, req.telefono)

        datos = {
            "fecha_alta": date.today().strftime("%d-%m-%Y"),
            "tipo_documento": fiscal_profile.tipo_documento,
            "nif": dni[:20],
            "nombre": req.nombre[:80],
            "postal": req.postal[:10],
            "ciudad": req.ciudad[:30],
            "provincia": req.provincia[:30],
            "cod_pais": fiscal_profile.pais_codigo,
            "pais": fiscal_profile.pais[:30],
            "direccion": req.direccion[:60],
            "telefonos": telefonos[:40],
            "email": req.email[:60],
            "serie": serie,
            "cuenta_contable": cc_cliente,
            "regimen_iva": fiscal_profile.iva_regimen,
            "clase_iva": fiscal_profile.iva_clase,
        }

        id_creado = rc.crear_cliente_ambar(conn, datos)

        logger.info(
            "Alta cliente insertado id_cliente=%d cuenta_contable=%s serie=%s tipo_documento=%s iva_regimen=%s iva_clase=%s",
            id_creado,
            cc_cliente,
            serie,
            fiscal_profile.tipo_documento,
            fiscal_profile.iva_regimen,
            fiscal_profile.iva_clase,
        )
        return CrearClienteResponseDTO(
            ok=True,
            id_cliente=id_creado,
            cuenta_contable=cc_cliente,
            mensaje=f"Cliente registrado correctamente con ID: {id_creado}",
        )

    except CountryResolutionError as exc:
        logger.warning(
            "Alta cliente bloqueada pedido_ps=%s iso=%s motivo=%s",
            req.id_pedido,
            (req.cod_pais or "").strip().upper() or "-",
            exc,
        )
        return CrearClienteResponseDTO(
            ok=False,
            mensaje=f"No se puede crear el cliente: {exc}.",
        )
    except Exception as exc:
        logger.error("Error creando cliente Ambar: %s", exc)
        return CrearClienteResponseDTO(
            ok=False,
            mensaje=f"Error al crear cliente: {str(exc)}",
        )


def activar_cliente(
    conn: pyodbc.Connection,
    id_cliente: int,
) -> ActivarClienteResponseDTO:
    """Reactiva un cliente dado de baja."""
    try:
        rc.activar_cliente_ambar(conn, id_cliente)
        return ActivarClienteResponseDTO(
            ok=True,
            id_cliente=id_cliente,
            mensaje=f"Cliente {id_cliente} activado correctamente.",
        )
    except Exception as exc:
        logger.error("Error activando cliente %d: %s", id_cliente, exc)
        return ActivarClienteResponseDTO(
            ok=False,
            id_cliente=id_cliente,
            mensaje=f"Error al activar cliente: {str(exc)}",
        )
