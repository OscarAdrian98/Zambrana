"""
services/cliente_preview_service.py - Preparacion de datos para futura creacion de cliente.
Solo lectura: normaliza, valida y evalua si ya existe coincidencia suficiente en Ambar.
"""
from __future__ import annotations

from app.schemas.cliente import (
    ClienteAmbarDTO,
    CrearClienteRequestDTO,
    ClientePreviewDTO,
    ClientePreviewValidationDTO,
)
from app.schemas.pedido import PedidoPSDTO
from app.services import normalizacion_service as ns
from app.services.cliente_fiscal_service import (
    CountryResolutionError,
    build_ambar_customer_fiscal_profile,
)


def construir_preview_cliente(
    pedido: PedidoPSDTO,
    usar_direccion: str,
    candidatos_ambar: list[ClienteAmbarDTO],
) -> ClientePreviewDTO:
    dir_activa = pedido.direccion_factura if usar_direccion == "Factura" else pedido.direccion_envio
    pais_resoluble = True
    motivo_pais = ""
    try:
        fiscal_profile = build_ambar_customer_fiscal_profile(
            dir_activa.cod_pais,
            dir_activa.pais,
            pedido.tiene_iva,
        )
        pais = fiscal_profile.pais
        cod_pais = fiscal_profile.pais_codigo
        tipo_documento = fiscal_profile.tipo_documento
        iva_regimen = fiscal_profile.iva_regimen
        iva_clase = fiscal_profile.iva_clase
    except CountryResolutionError as exc:
        pais_resoluble = False
        motivo_pais = str(exc)
        pais = (dir_activa.pais or "").strip().upper()
        cod_pais = (dir_activa.cod_pais or "").strip().upper()
        tipo_documento = "O"
        iva_regimen = ""
        iva_clase = ""

    preview = ClientePreviewDTO(
        id_pedido=pedido.id_pedido,
        usar_direccion=usar_direccion,
        dni=ns.formatear_dni_ambar(dir_activa.dni, dir_activa.pais),
        nombre=ns.normalizar_nombre_ambar(dir_activa.apellidos, dir_activa.nombre),
        direccion=ns.normalizar_direccion_ambar(dir_activa.linea1, dir_activa.linea2),
        ciudad=ns.normalizar_ciudad_ambar(dir_activa.ciudad),
        provincia=ns.normalizar_provincia_ambar(dir_activa.provincia),
        pais=pais,
        cod_pais=cod_pais,
        postal=(dir_activa.postal or "").strip()[:10],
        telefono=ns.normalizar_telefono_ambar(dir_activa.telefono),
        movil=ns.normalizar_telefono_ambar(dir_activa.movil),
        email=(pedido.email_cliente or "").strip(),
        tiene_iva=pedido.tiene_iva,
        tipo_documento=tipo_documento,
        iva_regimen=iva_regimen,
        iva_clase=iva_clase,
        pais_resoluble=pais_resoluble,
        motivo_pais=motivo_pais,
    )

    preview.validaciones = _validar_preview(preview)
    (
        preview.coincidencia_suficiente,
        preview.motivos_coincidencia,
    ) = _evaluar_coincidencia_suficiente(candidatos_ambar)
    return preview


def construir_solicitud_creacion(preview: ClientePreviewDTO) -> CrearClienteRequestDTO:
    """Convierte el mismo preview validado en la solicitud del INSERT real."""
    return CrearClienteRequestDTO(
        id_pedido=preview.id_pedido,
        dni=preview.dni,
        nombre=preview.nombre,
        direccion=preview.direccion,
        ciudad=preview.ciudad,
        provincia=preview.provincia,
        pais=preview.pais,
        cod_pais=preview.cod_pais,
        postal=preview.postal,
        telefono=preview.telefono,
        movil=preview.movil,
        email=preview.email,
        tiene_iva=preview.tiene_iva,
    )


def puede_crear_cliente(preview: ClientePreviewDTO) -> tuple[bool, str]:
    if not preview.pais_resoluble:
        return False, f"Creación bloqueada: {preview.motivo_pais}."
    errores = [v for v in preview.validaciones if v.severidad == "error"]
    if errores:
        return False, f"Datos incompletos para crear cliente ({len(errores)} errores de validacion)."
    if preview.coincidencia_suficiente:
        motivo_txt = _motivo_humano(preview.motivos_coincidencia)
        return False, (
            "Creacion bloqueada: cliente ya existente en Ambar "
            f"({motivo_txt})."
        )
    return True, ""


def _validar_preview(preview: ClientePreviewDTO) -> list[ClientePreviewValidationDTO]:
    validaciones: list[ClientePreviewValidationDTO] = []

    if not preview.pais_resoluble:
        validaciones.append(
            ClientePreviewValidationDTO(
                campo="cod_pais",
                mensaje=f"País no resoluble: {preview.motivo_pais}",
            )
        )

    if not preview.nombre:
        validaciones.append(ClientePreviewValidationDTO(campo="nombre", mensaje="Nombre vacio"))
    if not preview.direccion:
        validaciones.append(ClientePreviewValidationDTO(campo="direccion", mensaje="Direccion vacia"))
    if not preview.ciudad:
        validaciones.append(ClientePreviewValidationDTO(campo="ciudad", mensaje="Ciudad vacia"))
    if not preview.postal:
        validaciones.append(ClientePreviewValidationDTO(campo="postal", mensaje="Codigo postal vacio"))
    if not preview.dni and not preview.email:
        validaciones.append(
            ClientePreviewValidationDTO(
                campo="identificacion",
                mensaje="Debe existir al menos DNI o email",
            )
        )
    if preview.pais_resoluble and not preview.cod_pais:
        validaciones.append(ClientePreviewValidationDTO(campo="cod_pais", mensaje="Codigo de pais vacio"))
    if not preview.telefono and not preview.movil:
        validaciones.append(
            ClientePreviewValidationDTO(
                campo="telefono",
                mensaje="No hay telefono ni movil",
                severidad="warning",
            )
        )
    return validaciones


def _evaluar_coincidencia_suficiente(
    candidatos_ambar: list[ClienteAmbarDTO],
) -> tuple[bool, list[str]]:
    # Legacy: un cliente existente no debe "desaparecer" por estar bloqueado/aviso.
    # Para evitar altas duplicadas, la coincidencia suficiente considera cualquier candidato no dado de baja.
    activos = [c for c in candidatos_ambar if not c.baja]
    if not activos:
        return False, []

    razones_total: set[str] = set()
    for candidato in activos:
        razones = set(candidato.match_reason or [])
        if "email" in razones:
            razones_total.add("email")
        if "dni_factura" in razones or "dni_envio" in razones:
            razones_total.add("nif")

    if "email" in razones_total and "nif" in razones_total:
        return True, ["coincide por ambos"]
    if "email" in razones_total:
        return True, ["coincide por email"]
    if "nif" in razones_total:
        return True, ["coincide por nif"]
    return False, []


def _motivo_humano(motivos: list[str]) -> str:
    if not motivos:
        return "coincidencia suficiente"
    m = set(motivos)
    if "coincide por ambos" in m:
        return "coincide por email y NIF exactos"
    if "coincide por nif" in m:
        return "coincide por NIF exacto"
    if "coincide por email" in m:
        return "coincide por email exacto"
    return ", ".join(motivos)
