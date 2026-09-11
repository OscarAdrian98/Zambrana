"""
services/anticipo_service.py — Lógica de negocio para anticipos.
Equivalente a payment.php con validaciones de idempotencia añadidas.
"""
import logging
from datetime import datetime, timedelta
import pyodbc

from app.schemas.anticipo import CrearAnticipoRequestDTO, CrearAnticipoResponseDTO
from app.repositories import anticipos_repository as ra

logger = logging.getLogger(__name__)


def crear_anticipo(
    conn: pyodbc.Connection,
    req: CrearAnticipoRequestDTO,
) -> CrearAnticipoResponseDTO:
    try:
        dt_pedido = datetime.fromisoformat(req.fecha_pedido)
        fecha_real = calcular_fecha_anticipo(dt_pedido, req.hora_fin_dia)
        fecha_anticipo = fecha_real.strftime("%d-%m-%Y")

        ya_existe = ra.anticipo_ya_existe(
            conn, [req.id_cliente_ambar], req.total_pedido, dt_pedido.date()
        )
        if ya_existe:
            logger.warning("Anticipo ya existe para cliente %d", req.id_cliente_ambar)
            return CrearAnticipoResponseDTO(
                ok=False,
                mensaje="Ya existe un anticipo con el mismo importe y fecha para este cliente."
            )

        id_anticipo = ra.obtener_proximo_id_anticipo(conn)
        ra.insertar_anticipo(
            conn=conn,
            id_anticipo=id_anticipo,
            id_cliente=req.id_cliente_ambar,
            fecha_insertar=fecha_anticipo,
            importe=req.total_pedido,
            forma_pago=req.forma_pago_ambar,
            cod_banco=req.cod_banco,
            cc_cliente=req.cc_cliente,
        )
        return CrearAnticipoResponseDTO(
            ok=True,
            id_anticipo=id_anticipo,
            fecha_insertada=fecha_anticipo,
            mensaje=(
                f"Anticipo {id_anticipo} registrado. "
                f"Fecha: {fecha_anticipo} | {req.total_pedido:.2f}€ | {req.forma_pago_ambar}"
            )
        )
    except Exception as e:
        logger.error("Error creando anticipo: %s", e)
        return CrearAnticipoResponseDTO(ok=False, mensaje=f"Error: {str(e)}")


def calcular_fecha_anticipo(dt_pedido: datetime, hora_fin_dia: str) -> datetime.date:
    """
    Calcula la fecha de anticipo segun la hora de corte (legacy payment.php).
    """
    hora_pedido = dt_pedido.strftime("%H:%M:%S")
    hora_fin = f"{hora_fin_dia}:00"
    if hora_pedido >= hora_fin:
        return dt_pedido.date() + timedelta(days=1)
    return dt_pedido.date()
