"""
schemas/cliente.py — DTOs para clientes Ambar y operaciones sobre ellos.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class EstadoCliente(str, Enum):
    OK = "ok"
    BAJA = "baja"
    BLOQUEO = "bloqueo"
    AVISO = "aviso"
    AVISO_FUERTE = "aviso_fuerte"  # Cuando el aviso o nombre contiene '*'


class ClienteAmbarDTO(BaseModel):
    numero_cliente: int
    nombre: str
    nif: str
    direccion: str = ""
    ciudad: str = ""
    provincia: str = ""
    postal: str = ""
    telefono: str = ""
    email: str = ""
    cuenta_contable: str = ""
    libre1: str = ""
    pais: str = ""
    cod_pais: str = ""
    baja: bool = False
    bloqueo: bool = False
    aviso: str = ""
    match_reason: list[str] = Field(default_factory=list)
    estado: EstadoCliente = EstadoCliente.OK
    validacion_cliente_ok: bool = True
    discrepancias_criticas: list[str] = Field(default_factory=list)
    discrepancias_menores: list[str] = Field(default_factory=list)
    discrepancias_detalle: list[dict] = Field(default_factory=list)
    resumen_validacion: str = ""
    direccion_validada: str = "Factura"

    def calcular_estado(self) -> "ClienteAmbarDTO":
        if self.baja:
            self.estado = EstadoCliente.BAJA
        elif "*" in (self.aviso or "") or "*" in (self.nombre or ""):
            self.estado = EstadoCliente.AVISO_FUERTE
        elif self.bloqueo:
            self.estado = EstadoCliente.BLOQUEO
        elif self.aviso and self.aviso.strip():
            self.estado = EstadoCliente.AVISO
        else:
            self.estado = EstadoCliente.OK
        return self


class CrearClienteRequestDTO(BaseModel):
    id_pedido: int
    dni: str
    nombre: str
    direccion: str
    ciudad: str
    provincia: str
    pais: str
    cod_pais: str
    postal: str
    telefono: str
    movil: str
    email: str
    tiene_iva: bool


class CrearClienteResponseDTO(BaseModel):
    ok: bool
    id_cliente: Optional[int] = None
    cuenta_contable: Optional[str] = None
    mensaje: str


class ActivarClienteResponseDTO(BaseModel):
    ok: bool
    id_cliente: int
    mensaje: str


class ClientePreviewValidationDTO(BaseModel):
    campo: str
    mensaje: str
    severidad: str = "error"  # error | warning


class ClientePreviewDTO(BaseModel):
    id_pedido: int
    usar_direccion: str
    dni: str
    nombre: str
    direccion: str
    ciudad: str
    provincia: str
    pais: str
    cod_pais: str
    postal: str
    telefono: str
    movil: str
    email: str
    tiene_iva: bool
    tipo_documento: str = ""
    iva_regimen: str = ""
    iva_clase: str = ""
    pais_resoluble: bool = True
    motivo_pais: str = ""
    coincidencia_suficiente: bool = False
    motivos_coincidencia: list[str] = Field(default_factory=list)
    validaciones: list[ClientePreviewValidationDTO] = Field(default_factory=list)
