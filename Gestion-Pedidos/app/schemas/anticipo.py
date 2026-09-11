"""
schemas/anticipo.py — DTOs para anticipos y pedidos de venta Ambar.
"""
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional


class AnticipoCabDTO(BaseModel):
    codigo: int
    cliente: int
    fecha: str
    importe_disponible: float
    importe_entregado: float
    forma_pago: str
    banco: str
    fecha_utilizacion: Optional[str] = None


class CrearAnticipoRequestDTO(BaseModel):
    id_pedido_ps: int
    id_cliente_ambar: int
    fecha_pedido: str       # ISO datetime string del pedido PS
    total_pedido: float
    forma_pago_ambar: str   # TC, PY, BZ, etc.
    cod_banco: str           # 8, 2, 30, etc.
    cc_cliente: str          # Cuenta contable del cliente
    hora_fin_dia: str = "23:00"


class CrearAnticipoResponseDTO(BaseModel):
    ok: bool
    id_anticipo: Optional[int] = None
    fecha_insertada: Optional[str] = None
    mensaje: str


class CrearPedidoAmbarRequestDTO(BaseModel):
    id_cliente_ambar: int
    id_pedido_ps: int


class CrearPedidoAmbarResponseDTO(BaseModel):
    ok: bool
    serie: Optional[str] = None
    codigo: Optional[int] = None
    referencia: Optional[str] = None
    mensaje: str
