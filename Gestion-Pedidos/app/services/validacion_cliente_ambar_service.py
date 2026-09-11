"""
services/validacion_cliente_ambar_service.py - Validacion visual de datos entre pedido PS y cliente Ambar.
"""
from __future__ import annotations

import logging
import re

from app.schemas.cliente import ClienteAmbarDTO
from app.schemas.pedido import PedidoPSDTO
from app.services.normalizacion_service import normalizar_para_comparar

logger = logging.getLogger(__name__)

_RE_SPACES = re.compile(r"\s+")


def _norm_text(value: str | None) -> str:
    return normalizar_para_comparar(value or "")


def _norm_nif(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").strip().upper())


def _norm_phone(value: str | None) -> str:
    return re.sub(r"[^0-9]", "", value or "")


def _nombre_pedido(pedido: PedidoPSDTO) -> str:
    return _RE_SPACES.sub(" ", f"{pedido.nombre_cliente} {pedido.apellidos_cliente}").strip()


def _nombres_muy_distintos(nombre_ps: str, nombre_ambar: str) -> bool:
    a = _norm_text(nombre_ps)
    b = _norm_text(nombre_ambar)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return False
    toks_a = set(a.split())
    toks_b = set(b.split())
    if not toks_a or not toks_b:
        return a != b
    inter = len(toks_a & toks_b)
    min_len = min(len(toks_a), len(toks_b))
    return inter < max(1, min_len // 2)


def _agregar_detalle(
    detalles: list[dict],
    *,
    campo: str,
    prestashop: str,
    ambar: str,
    distinto: bool,
    critica: bool,
) -> None:
    detalles.append(
        {
            "campo": campo,
            "prestashop": prestashop or "-",
            "ambar": ambar or "-",
            "estado": "Distinto" if distinto else "OK",
            "critica": critica and distinto,
        }
    )


def validar_cliente_ambar_contra_pedido(
    pedido: PedidoPSDTO,
    cliente: ClienteAmbarDTO,
    *,
    direccion_validada: str = "Factura",
) -> ClienteAmbarDTO:
    dir_ps = pedido.direccion_factura
    nombre_ps = _nombre_pedido(pedido)
    nombre_ambar = cliente.nombre or ""

    detalle: list[dict] = []
    criticas: list[str] = []
    menores: list[str] = []

    nif_ps = dir_ps.dni or ""
    nif_ambar = cliente.nif or ""
    nif_distinto = bool(_norm_nif(nif_ps) and _norm_nif(nif_ambar) and _norm_nif(nif_ps) != _norm_nif(nif_ambar))
    if nif_distinto:
        criticas.append("NIF")
    _agregar_detalle(detalle, campo="NIF", prestashop=nif_ps, ambar=nif_ambar, distinto=nif_distinto, critica=True)

    nombre_distinto = _nombres_muy_distintos(nombre_ps, nombre_ambar)
    if nombre_distinto:
        criticas.append("Nombre")
    _agregar_detalle(detalle, campo="Nombre", prestashop=nombre_ps, ambar=nombre_ambar, distinto=nombre_distinto, critica=True)

    direccion_ps = _RE_SPACES.sub(" ", f"{dir_ps.linea1} {dir_ps.linea2}".strip()).strip()
    direccion_ambar = cliente.direccion or ""
    direccion_distinta = bool(_norm_text(direccion_ps) and _norm_text(direccion_ambar) and _norm_text(direccion_ps) != _norm_text(direccion_ambar))
    if direccion_distinta:
        criticas.append("Dirección")
    _agregar_detalle(detalle, campo="Dirección", prestashop=direccion_ps, ambar=direccion_ambar, distinto=direccion_distinta, critica=True)

    cp_ps = dir_ps.postal or ""
    cp_ambar = cliente.postal or ""
    cp_distinto = bool(cp_ps and cp_ambar and _norm_text(cp_ps) != _norm_text(cp_ambar))
    if cp_distinto:
        criticas.append("CP")
    _agregar_detalle(detalle, campo="CP", prestashop=cp_ps, ambar=cp_ambar, distinto=cp_distinto, critica=True)

    ciudad_ps = dir_ps.ciudad or ""
    ciudad_ambar = cliente.ciudad or ""
    ciudad_distinta = bool(_norm_text(ciudad_ps) and _norm_text(ciudad_ambar) and _norm_text(ciudad_ps) != _norm_text(ciudad_ambar))
    if ciudad_distinta:
        menores.append("Población")
    _agregar_detalle(detalle, campo="Población", prestashop=ciudad_ps, ambar=ciudad_ambar, distinto=ciudad_distinta, critica=False)

    prov_ps = dir_ps.provincia or ""
    prov_ambar = cliente.provincia or ""
    prov_distinta = bool(_norm_text(prov_ps) and _norm_text(prov_ambar) and _norm_text(prov_ps) != _norm_text(prov_ambar))
    if prov_distinta:
        menores.append("Provincia")
    _agregar_detalle(detalle, campo="Provincia", prestashop=prov_ps, ambar=prov_ambar, distinto=prov_distinta, critica=False)

    pais_ps = dir_ps.pais or ""
    pais_ambar = cliente.pais or ""
    pais_distinto = bool(_norm_text(pais_ps) and _norm_text(pais_ambar) and _norm_text(pais_ps) != _norm_text(pais_ambar))
    if pais_distinto:
        menores.append("País")
    _agregar_detalle(detalle, campo="País", prestashop=pais_ps, ambar=pais_ambar, distinto=pais_distinto, critica=False)

    tel_ps = dir_ps.telefono or dir_ps.movil or ""
    tel_ambar = cliente.telefono or ""
    tel_distinto = bool(_norm_phone(tel_ps) and _norm_phone(tel_ambar) and _norm_phone(tel_ps) != _norm_phone(tel_ambar))
    if tel_distinto:
        menores.append("Teléfono")
    _agregar_detalle(detalle, campo="Teléfono", prestashop=tel_ps, ambar=tel_ambar, distinto=tel_distinto, critica=False)

    email_ps = pedido.email_cliente or ""
    email_ambar = cliente.email or ""
    email_distinto = bool(_norm_text(email_ps) and _norm_text(email_ambar) and _norm_text(email_ps) != _norm_text(email_ambar))
    if email_distinto:
        menores.append("Email")
    _agregar_detalle(detalle, campo="Email", prestashop=email_ps, ambar=email_ambar, distinto=email_distinto, critica=False)

    validacion_ok = not criticas and not menores
    if criticas:
        logger.warning(
            "cliente Ambar con datos distintos pedido_ps=%s cliente_ambar=%s campos=%s",
            pedido.id_pedido,
            cliente.numero_cliente,
            ",".join(criticas),
        )
    else:
        logger.info(
            "validación cliente Ambar OK pedido_ps=%s cliente_ambar=%s",
            pedido.id_pedido,
            cliente.numero_cliente,
        )

    if criticas:
        resumen = "Cliente coincide por matching, pero hay diferencias importantes."
    elif menores:
        resumen = "Hay pequeñas diferencias en los datos del cliente."
    else:
        resumen = "Datos cliente OK."

    return cliente.model_copy(
        update={
            "validacion_cliente_ok": validacion_ok,
            "discrepancias_criticas": criticas,
            "discrepancias_menores": menores,
            "discrepancias_detalle": [d for d in detalle if d["estado"] == "Distinto"],
            "resumen_validacion": resumen,
            "direccion_validada": direccion_validada,
        }
    )
