"""
schemas/pedido.py — DTOs para pedidos PrestaShop y datos de direcciones.
"""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, field_validator
from typing import Optional


class DireccionDTO(BaseModel):
    nombre: str
    apellidos: str
    empresa: str = ""
    linea1: str
    linea2: str = ""
    dni: str = ""
    dni_numerico: str = ""  # Solo dígitos, para cruce Ambar
    ciudad: str
    postal: str
    provincia: str
    pais: str
    cod_pais: str = ""
    id_pais: int = 0
    telefono: str = ""
    movil: str = ""
    otros: str = ""


class MensajePedidoDTO(BaseModel):
    mensaje: str
    fecha: Optional[datetime] = None
    id_cliente: int


class FiltrosPedidosDTO(BaseModel):
    fecha_desde: Optional[str] = None
    fecha_hasta: Optional[str] = None
    id_pedido: Optional[int] = None
    ids_multiples: list[int] = []
    ultimos_n: Optional[int] = None
    modos_pago: list[str] = []
    estados_pedido: list[int] = []
    estados_internos: list[int] = []
    campo_orden: str = "o.id_order"
    direccion_orden: str = "DESC"
    usar_direccion: str = "Factura"   # "Factura" | "Envio"
    hora_fin_dia: str = "23:00"

    @field_validator("direccion_orden")
    @classmethod
    def validar_orden(cls, v: str) -> str:
        if v.upper() not in ("ASC", "DESC"):
            return "DESC"
        return v.upper()

    @field_validator("ultimos_n")
    @classmethod
    def validar_ultimos(cls, v):
        if v is not None and (v <= 0 or v > 200):
            return None
        return v

    @field_validator("campo_orden")
    @classmethod
    def validar_campo_orden(cls, v: str) -> str:
        permitidos = {"o.id_order", "o.invoice_date", "o.date_add", "o.payment"}
        return v if v in permitidos else "o.id_order"

    @field_validator("estados_pedido")
    @classmethod
    def validar_estados_pedido(cls, values: list[int]) -> list[int]:
        return [v for v in values if isinstance(v, int) and v > 0]

    @field_validator("estados_internos")
    @classmethod
    def validar_estados_internos(cls, values: list[int]) -> list[int]:
        return [v for v in values if isinstance(v, int) and v > 0]


class PedidoPSDTO(BaseModel):
    id_pedido: int
    referencia: str
    fecha_pedido: Optional[datetime] = None
    fecha_factura: Optional[datetime] = None
    modo_pago: str
    total_pagado: float
    total_sin_iva: float
    total_con_iva: float
    tiene_iva: bool
    estado_nombre: str
    estado_id: Optional[int] = None
    color_estado: str
    internal_state_id: int = 1
    internal_state_code: str = "nuevo_pedido"
    internal_state_name: str = "Nuevo Pedido"
    internal_state_color: str = "#2563eb"
    id_cliente: int
    nombre_cliente: str
    apellidos_cliente: str
    email_cliente: str
    id_direccion_envio: int
    id_direccion_factura: int
    direccion_envio: DireccionDTO
    direccion_factura: DireccionDTO
    mensajes: list[MensajePedidoDTO] = []

    # Campos calculados (se rellenan en el servicio de matching)
    es_pro: bool = False
    info_pago_ambar: Optional[dict] = None


class ModosPagoListaDTO(BaseModel):
    modos: list[str]
