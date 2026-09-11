"""
routes/pedidos.py - Endpoints principales de la primera fase funcional.
"""
import asyncio
import logging
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from config import get_settings
from app.db import mysql_prestashop, sqlserver_ambar
from app.services import (
    matching_ambar_service,
    cliente_preview_service,
    cliente_service,
    anticipo_service,
    anticipos_ambar_service,
    pedido_service,
    pedidos_ambar_service,
    prestashop_state_bridge_service,
    pro_service,
    comprobacion_stock_service,
    validacion_cliente_ambar_service,
)
from app.services import email_service
from app.db import mysql_b2b
from app.repositories import clientes_repository
from app.schemas.cliente import CrearClienteRequestDTO
from app.schemas.anticipo import CrearAnticipoRequestDTO, CrearPedidoAmbarRequestDTO
from app.schemas.pedido import FiltrosPedidosDTO
from app.schemas.email import EmailPedidoRequestDTO
from app.repositories.pedidos_repository import (
    obtener_max_id_pedido,
    obtener_cabecera_y_lineas_para_comprobacion_stock,
    obtener_lineas_pedido_para_email,
    obtener_resumen_pedido_para_email,
    obtener_modos_pago_ultimo_ano,
    obtener_pedidos_nuevos_desde,
    obtener_estados_pedido,
    obtener_pedidos,
)
from app.repositories import ambar_pedidos_repository
from app.repositories.internal_order_states_repository import (
    get_active_internal_order_state,
    list_internal_order_states,
    prestashop_order_exists,
    set_internal_order_state,
)

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")
settings = get_settings()


def _enriquecer_candidatos_con_validacion(
    pedido,
    candidatos,
):
    return [
        validacion_cliente_ambar_service.validar_cliente_ambar_contra_pedido(
            pedido,
            candidato,
            direccion_validada="Factura",
        )
        for candidato in candidatos
    ]


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Pantalla principal con filtros."""
    runtime_settings = request.app.state.settings
    modos_pago: list[str] = []
    estados_pedido: list[dict] = []
    estados_internos: list[dict] = []
    initial_last_id = 0
    warning_msg = None

    try:
        async with mysql_prestashop.get_connection() as conn:
            modos_pago = await obtener_modos_pago_ultimo_ano(conn)
            estados_pedido = await obtener_estados_pedido(conn)
            estados_internos = await list_internal_order_states(conn)
            initial_last_id = await obtener_max_id_pedido(conn)
    except Exception as exc:
        logger.error("No se pudieron cargar modos de pago: %s", exc, exc_info=True)
        warning_msg = "No hay conexion a PrestaShop. Puedes ajustar credenciales en .env y reintentar."

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "modos_pago": modos_pago,
            "estados_pedido": estados_pedido,
            "estados_internos": estados_internos,
            "initial_last_id": initial_last_id,
            "warning_msg": warning_msg,
            "env_context": runtime_settings.environment_context,
        },
    )


@router.get("/pedidos/nuevos")
async def obtener_pedidos_nuevos(request: Request):
    last_id_raw = str(request.query_params.get("last_id", "0")).strip()
    try:
        last_id = int(last_id_raw)
    except ValueError:
        last_id = 0
    last_id = max(0, last_id)

    try:
        async with mysql_prestashop.get_connection() as conn:
            result = await obtener_pedidos_nuevos_desde(conn, last_id)
        logger.info(
            "Polling pedidos nuevos last_id=%s encontrados=%s max_id=%s",
            last_id,
            result["count"],
            result["max_id"],
        )
        return JSONResponse(
            {
                "ok": True,
                "hay_nuevos": result["hay_nuevos"],
                "count": result["count"],
                "max_id": result["max_id"],
                "pedidos": result["pedidos"],
            }
        )
    except Exception as exc:
        logger.error("Error consultando /pedidos/nuevos last_id=%s: %s", last_id, exc, exc_info=True)
        return JSONResponse(
            {
                "ok": False,
                "hay_nuevos": False,
                "count": 0,
                "max_id": last_id,
                "pedidos": [],
                "error": "No se pudieron consultar pedidos nuevos.",
            },
            status_code=500,
        )


@router.post("/pedidos/buscar", response_class=HTMLResponse)
async def buscar_pedidos(request: Request):
    """Endpoint HTMX: listado de pedidos de PrestaShop con filtros."""
    runtime_settings = request.app.state.settings
    form_data = await request.form()

    if settings.app_debug:
        debug_form: dict[str, str | list[str]] = {}
        for key in form_data.keys():
            values = form_data.getlist(key)
            debug_form[key] = values if len(values) > 1 else (values[0] if values else "")
        logger.debug("FORM /pedidos/buscar: %s", debug_form)

    def _first(*names: str, default: str = "") -> str:
        for name in names:
            value = form_data.get(name)
            if value is not None:
                return str(value).strip()
        return default

    fecha_desde = _first("fecha_desde", "fechaDesde")
    fecha_hasta = _first("fecha_hasta", "fechaHasta")
    id_pedido_raw = _first("id_pedido", "txtId")
    ultimos_n_raw = _first("ultimos_n", "txtUltimos")
    campo_orden = _first("campo_orden", "selectOrden", default="o.id_order")
    direccion_orden = _first("direccion_orden", "txtOrden", default="DESC")
    usar_direccion = _first("usar_direccion", "radioUsarDir", default="Factura")
    hora_fin_dia = _first("hora_fin_dia", "txtHoraFin", default="23:00")

    ids_multi_raw = form_data.getlist("ids_multiples[]") or form_data.getlist("txtIdMulti[]")
    modos_pago_sel = form_data.getlist("modos_pago[]") or form_data.getlist("selectPago[]")
    estados_sel_raw = form_data.getlist("estados_pedido[]") or form_data.getlist("selectEstado[]")
    estados_internos_raw = form_data.getlist("estados_internos[]")

    ids_multiples: list[int] = []
    for value in ids_multi_raw:
        try:
            ids_multiples.append(int(value))
        except (TypeError, ValueError):
            continue

    estados_pedido: list[int] = []
    for value in estados_sel_raw:
        try:
            estado_id = int(value)
            if estado_id > 0:
                estados_pedido.append(estado_id)
        except (TypeError, ValueError):
            continue

    estados_internos: list[int] = []
    for value in estados_internos_raw:
        try:
            estado_interno_id = int(value)
            if estado_interno_id > 0:
                estados_internos.append(estado_interno_id)
        except (TypeError, ValueError):
            continue

    filtros = FiltrosPedidosDTO(
        fecha_desde=fecha_desde or None,
        fecha_hasta=fecha_hasta or None,
        id_pedido=int(id_pedido_raw) if id_pedido_raw.isdigit() else None,
        ids_multiples=ids_multiples,
        ultimos_n=int(ultimos_n_raw) if ultimos_n_raw.isdigit() else None,
        modos_pago=modos_pago_sel,
        estados_pedido=estados_pedido,
        estados_internos=estados_internos,
        campo_orden=campo_orden,
        direccion_orden=direccion_orden,
        usar_direccion=usar_direccion,
        hora_fin_dia=hora_fin_dia,
    )

    logger.info("Busqueda pedidos PrestaShop: %s", filtros.model_dump(exclude_none=True))

    t_total_start = time.monotonic()
    t_pedidos_ms = 0.0
    t_matching_ms = 0.0
    t_anticipos_ms = 0.0
    t_pedidos_ambar_ms = 0.0
    n_pedidos = 0

    try:
        async with mysql_prestashop.get_connection() as conn:
            t0 = time.monotonic()
            pedidos = await obtener_pedidos(conn, filtros, include_messages=False)
            t_pedidos_ms = (time.monotonic() - t0) * 1000
            estados_pedido_opciones = await obtener_estados_pedido(conn)
            estados_internos_opciones = await list_internal_order_states(conn)

        if pedidos and bool(getattr(request.app.state, "db_status", {}).get("b2b")):
            try:
                async with mysql_b2b.get_connection() as b2b_conn:
                    pro_emails, pro_nombres = await pro_service.cargar_indices_usuarios_pro(b2b_conn)
                pro_count = 0
                for pedido in pedidos:
                    es_pro, email_match, nombre_match = pro_service.diagnosticar_cliente_pro_por_email_o_nombre(
                        email=pedido.email_cliente,
                        nombre=pedido.nombre_cliente,
                        apellidos=pedido.apellidos_cliente,
                        pro_emails=pro_emails,
                        pro_nombres=pro_nombres,
                    )
                    pedido.es_pro = es_pro
                    if pedido.es_pro:
                        pro_count += 1
                    logger.info(
                        "PRO service: pedido id=%s cliente='%s %s' email='%s' email_match=%s nombre_match=%s es_pro=%s",
                        pedido.id_pedido,
                        pedido.nombre_cliente,
                        pedido.apellidos_cliente,
                        pedido.email_cliente,
                        email_match,
                        nombre_match,
                        pedido.es_pro,
                    )
                logger.info("PRO service: pedidos_total=%d marcados_pro=%d", len(pedidos), pro_count)
            except Exception as exc:
                if settings.app_debug:
                    logger.error("No se pudo cargar índice PRO de B2B: %s", exc, exc_info=True)
                else:
                    logger.warning("No se pudo cargar índice PRO de B2B: %s", exc)

        n_pedidos = len(pedidos)
        matches_por_pedido = {p.id_pedido: [] for p in pedidos}
        matching_error = None
        previews_por_pedido = {}
        puede_crear_por_pedido = {}
        bloqueo_por_pedido = {}
        anticipos_por_pedido = {}
        anticipos_error = None
        pedidos_ambar_por_pedido = {}
        pedidos_ambar_error = None
        try:
            t1 = time.monotonic()
            matches_por_pedido = await matching_ambar_service.buscar_matches_clientes(pedidos)
            pedidos_por_id = {p.id_pedido: p for p in pedidos}
            for id_pedido, candidatos in list(matches_por_pedido.items()):
                pedido = pedidos_por_id.get(id_pedido)
                if not pedido:
                    continue
                matches_por_pedido[id_pedido] = _enriquecer_candidatos_con_validacion(pedido, candidatos)
            t_matching_ms = (time.monotonic() - t1) * 1000
        except Exception as exc:
            t_matching_ms = (time.monotonic() - t1) * 1000
            if settings.app_debug:
                logger.error("Error en matching Ambar: %s", exc, exc_info=True)
            else:
                logger.warning("Error en matching Ambar: %s", exc)
            matching_error = (
                "No se pudieron cargar coincidencias de Ambar. "
                "Se muestra solo la informacion de PrestaShop."
            )

        for pedido in pedidos:
            candidatos = matches_por_pedido.get(pedido.id_pedido, [])
            preview = cliente_preview_service.construir_preview_cliente(
                pedido=pedido,
                usar_direccion=usar_direccion,
                candidatos_ambar=candidatos,
            )
            previews_por_pedido[pedido.id_pedido] = preview
            can_create, motivo = cliente_preview_service.puede_crear_cliente(preview)
            if matching_error:
                can_create = False
                motivo = "No se puede crear sin conexion estable con Ambar."
            puede_crear_por_pedido[pedido.id_pedido] = can_create
            bloqueo_por_pedido[pedido.id_pedido] = motivo

        async def _load_anticipos():
            t_start = time.monotonic()
            result = await anticipos_ambar_service.preparar_contexto_anticipos(
                pedidos=pedidos,
                matches_por_pedido=matches_por_pedido,
                hora_fin_dia=hora_fin_dia,
            )
            return result, (time.monotonic() - t_start) * 1000

        async def _load_pedidos_ambar():
            t_start = time.monotonic()
            result = await pedidos_ambar_service.preparar_contexto_pedidos(
                pedidos=pedidos,
                matches_por_pedido=matches_por_pedido,
            )
            return result, (time.monotonic() - t_start) * 1000

        ant_result, ped_result = await asyncio.gather(
            _load_anticipos(),
            _load_pedidos_ambar(),
            return_exceptions=True,
        )

        if isinstance(ant_result, Exception):
            if settings.app_debug:
                logger.error("Error cargando anticipos Ambar: %s", ant_result, exc_info=True)
            else:
                logger.warning("Error cargando anticipos Ambar: %s", ant_result)
            anticipos_error = "No se pudieron cargar anticipos de Ambar."
            t_anticipos_ms = 0.0
        else:
            anticipos_por_pedido, t_anticipos_ms = ant_result

        if isinstance(ped_result, Exception):
            if settings.app_debug:
                logger.error("Error cargando contexto de pedidos Ambar: %s", ped_result, exc_info=True)
            else:
                logger.warning("Error cargando contexto de pedidos Ambar: %s", ped_result)
            pedidos_ambar_error = "No se pudo cargar el estado de pedido Ambar."
            t_pedidos_ambar_ms = 0.0
        else:
            pedidos_ambar_por_pedido, t_pedidos_ambar_ms = ped_result

        t_total_ms = (time.monotonic() - t_total_start) * 1000
        logger.info(
            "Timing /pedidos/buscar t_total_ms=%.2f t_pedidos_ms=%.2f t_matching_ms=%.2f "
            "t_anticipos_ms=%.2f t_pedidos_ambar_ms=%.2f n_pedidos=%d",
            t_total_ms,
            t_pedidos_ms,
            t_matching_ms,
            t_anticipos_ms,
            t_pedidos_ambar_ms,
            n_pedidos,
        )

        return templates.TemplateResponse(
            "partials/tabla_pedidos.html",
            {
                "request": request,
                "pedidos": pedidos,
                "usar_dir": usar_direccion,
                "matches_por_pedido": matches_por_pedido,
                "matching_error": matching_error,
                "previews_por_pedido": previews_por_pedido,
                "puede_crear_por_pedido": puede_crear_por_pedido,
                "bloqueo_por_pedido": bloqueo_por_pedido,
                "anticipos_por_pedido": anticipos_por_pedido,
                "anticipos_error": anticipos_error,
                "pedidos_ambar_por_pedido": pedidos_ambar_por_pedido,
                "pedidos_ambar_error": pedidos_ambar_error,
                "env_context": runtime_settings.environment_context,
                "estados_pedido": estados_pedido_opciones,
                "estados_internos": estados_internos_opciones,
            },
        )
    except Exception as exc:
        t_total_ms = (time.monotonic() - t_total_start) * 1000
        logger.info(
            "Timing /pedidos/buscar (error) t_total_ms=%.2f t_pedidos_ms=%.2f t_matching_ms=%.2f "
            "t_anticipos_ms=%.2f t_pedidos_ambar_ms=%.2f n_pedidos=%d",
            t_total_ms,
            t_pedidos_ms,
            t_matching_ms,
            t_anticipos_ms,
            t_pedidos_ambar_ms,
            n_pedidos,
        )
        logger.error("Error en busqueda de pedidos: %s", exc, exc_info=True)
        return templates.TemplateResponse(
            "partials/tabla_pedidos.html",
            {
                "request": request,
                "pedidos": [],
                "usar_dir": usar_direccion,
                "matches_por_pedido": {},
                "matching_error": None,
                "previews_por_pedido": {},
                "puede_crear_por_pedido": {},
                "bloqueo_por_pedido": {},
                "anticipos_por_pedido": {},
                "anticipos_error": None,
                "pedidos_ambar_por_pedido": {},
                "pedidos_ambar_error": None,
                "env_context": runtime_settings.environment_context,
                "estados_pedido": [],
                "estados_internos": [],
                "error_msg": f"No se pudo consultar PrestaShop: {exc}",
            },
            status_code=200,
        )


@router.post("/pedidos/{id_pedido}/estado-interno", response_class=HTMLResponse)
async def cambiar_estado_interno_pedido(request: Request, id_pedido: int):
    """
    Cambia el estado interno auxiliar del pedido sin tocar ps_orders.current_state.
    """
    runtime_settings = request.app.state.settings
    if runtime_settings.app_read_only:
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Operacion bloqueada: modo solo lectura activo.",
                "detalle": "En solo lectura se permite consultar y filtrar, no cambiar Estados Internos.",
            },
            status_code=200,
        )

    form_data = await request.form()
    id_estado_raw = str(form_data.get("id_internal_state", "")).strip()
    if id_pedido <= 0 or not id_estado_raw.isdigit():
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Datos invalidos para cambiar Estado Interno.",
                "detalle": "Revise pedido y Estado Interno seleccionado.",
            },
            status_code=200,
        )

    id_internal_state = int(id_estado_raw)
    updated_by = str(form_data.get("updated_by", "")).strip() or None

    try:
        async with mysql_prestashop.get_connection() as conn:
            estado = await get_active_internal_order_state(conn, id_internal_state)
            if not estado:
                return templates.TemplateResponse(
                    "partials/toast.html",
                    {
                        "request": request,
                        "ok": False,
                        "mensaje": "Estado Interno invalido o inactivo.",
                        "detalle": "",
                    },
                    status_code=200,
                )
            if not await prestashop_order_exists(conn, id_pedido):
                return templates.TemplateResponse(
                    "partials/toast.html",
                    {
                        "request": request,
                        "ok": False,
                        "mensaje": f"No se encontro el pedido {id_pedido} en PrestaShop.",
                        "detalle": "",
                    },
                    status_code=200,
                )
            await set_internal_order_state(conn, id_pedido, id_internal_state, updated_by)

        logger.info(
            "Estado interno actualizado pedido_ps=%s estado=%s",
            id_pedido,
            estado["name"],
        )
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": True,
                "mensaje": f"Estado Interno actualizado: {estado['name']}",
                "detalle": f"Pedido PrestaShop #{id_pedido}. El Estado PrestaShop no se ha modificado.",
            },
            status_code=200,
        )
    except Exception as exc:
        logger.error("Error cambiando Estado Interno pedido=%s: %s", id_pedido, exc, exc_info=True)
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Error al cambiar Estado Interno.",
                "detalle": str(exc),
            },
            status_code=200,
        )


@router.get("/pedidos/{id_pedido}/validacion-cliente", response_class=HTMLResponse)
async def validacion_cliente_pedido(request: Request, id_pedido: int):
    try:
        filtros = FiltrosPedidosDTO(id_pedido=id_pedido, usar_direccion="Factura")
        async with mysql_prestashop.get_connection() as conn:
            pedidos = await obtener_pedidos(conn, filtros, include_messages=False)
        if not pedidos:
            return templates.TemplateResponse(
                "partials/validacion_cliente_pedido.html",
                {
                    "request": request,
                    "pedido": None,
                    "candidatos": [],
                    "error_msg": f"No se encontró el pedido {id_pedido}.",
                },
                status_code=200,
            )

        pedido = pedidos[0]
        candidatos = await matching_ambar_service.buscar_matches_clientes([pedido])
        candidatos_enriquecidos = _enriquecer_candidatos_con_validacion(
            pedido,
            candidatos.get(pedido.id_pedido, []),
        )
        return templates.TemplateResponse(
            "partials/validacion_cliente_pedido.html",
            {
                "request": request,
                "pedido": pedido,
                "candidatos": candidatos_enriquecidos,
                "error_msg": None,
            },
            status_code=200,
        )
    except Exception as exc:
        logger.error("Error cargando validación cliente pedido=%s: %s", id_pedido, exc, exc_info=True)
        return templates.TemplateResponse(
            "partials/validacion_cliente_pedido.html",
            {
                "request": request,
                "pedido": None,
                "candidatos": [],
                "error_msg": "No se pudo cargar la validación del cliente.",
            },
            status_code=200,
        )


@router.get("/pedidos/{id_pedido}/comprobacion-stock", response_class=HTMLResponse)
async def comprobacion_stock_pedido(request: Request, id_pedido: int):
    logger.info("Comprobación stock inicio id_pedido=%s", id_pedido)
    try:
        async with mysql_prestashop.get_connection() as conn:
            pedido_ps = await obtener_cabecera_y_lineas_para_comprobacion_stock(conn, id_pedido)
        if not pedido_ps:
            return templates.TemplateResponse(
                "partials/stock_pedido.html",
                {
                    "request": request,
                    "stock_check": None,
                    "error_msg": f"No se encontró el pedido {id_pedido}.",
                },
                status_code=200,
            )

        referencias = [
            str(linea.get("product_reference") or "").strip()
            for linea in pedido_ps.get("lineas", [])
            if str(linea.get("product_reference") or "").strip()
        ]
        with sqlserver_ambar.get_connection() as ambar_conn:
            stock_por_referencia = ambar_pedidos_repository.obtener_stock_articulos_batch(ambar_conn, referencias)

        stock_check = comprobacion_stock_service.construir_resultado_comprobacion_stock(
            pedido_ps=pedido_ps,
            stock_por_referencia=stock_por_referencia,
        )
        logger.info(
            "Comprobación stock resultado id_pedido=%s pagado=%s lineas=%s ok=%s",
            id_pedido,
            stock_check["pagado"],
            len(stock_check["lineas"]),
            stock_check["ok_global"],
        )
        return templates.TemplateResponse(
            "partials/stock_pedido.html",
            {
                "request": request,
                "stock_check": stock_check,
                "error_msg": None,
            },
            status_code=200,
        )
    except Exception as exc:
        logger.error("Error en comprobación stock id_pedido=%s: %s", id_pedido, exc, exc_info=True)
        return templates.TemplateResponse(
            "partials/stock_pedido.html",
            {
                "request": request,
                "stock_check": None,
                "error_msg": "No se pudo comprobar el stock del pedido.",
            },
            status_code=200,
        )


@router.post("/clientes/previsualizar", response_class=HTMLResponse)
async def previsualizar_cliente(request: Request):
    """
    Prepara y valida datos para futura creacion de cliente en Ambar.
    NO realiza escrituras.
    """
    form_data = await request.form()
    id_pedido_raw = str(form_data.get("id_pedido", "")).strip()
    usar_direccion = str(form_data.get("usar_direccion", "Factura")).strip() or "Factura"

    if not id_pedido_raw.isdigit():
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "ID de pedido invalido para previsualizacion.",
                "detalle": "",
            },
            status_code=200,
        )

    filtros = FiltrosPedidosDTO(id_pedido=int(id_pedido_raw), usar_direccion=usar_direccion)
    try:
        async with mysql_prestashop.get_connection() as conn:
            pedidos = await obtener_pedidos(conn, filtros)
        if not pedidos:
            return templates.TemplateResponse(
                "partials/toast.html",
                {
                    "request": request,
                    "ok": False,
                    "mensaje": f"No se encontro el pedido {id_pedido_raw}.",
                    "detalle": "",
                },
                status_code=200,
            )

        pedido = pedidos[0]
        matches_por_pedido = {}
        try:
            matches_por_pedido = await matching_ambar_service.buscar_matches_clientes([pedido])
        except Exception as exc:
            if settings.app_debug:
                logger.error("Error en matching Ambar para preview: %s", exc, exc_info=True)
            else:
                logger.warning("Error en matching Ambar para preview: %s", exc)

        candidatos = matches_por_pedido.get(pedido.id_pedido, [])
        preview = cliente_preview_service.construir_preview_cliente(
            pedido=pedido,
            usar_direccion=usar_direccion,
            candidatos_ambar=candidatos,
        )
        logger.info(
            "Preview cliente pedido=%s email=%s nif=%s coincidencia_suficiente=%s candidatos=%d",
            pedido.id_pedido,
            _mask_email(preview.email),
            _mask_nif(preview.dni),
            preview.coincidencia_suficiente,
            len(candidatos),
        )

        valid_errores = [v for v in preview.validaciones if v.severidad == "error"]
        puede_crear, motivo_bloqueo = cliente_preview_service.puede_crear_cliente(preview)
        estado_creacion = "PERMITIDA" if puede_crear else "BLOQUEADA"
        motivo_txt = ", ".join(preview.motivos_coincidencia) if preview.motivos_coincidencia else "-"
        lleva_iva_txt = "Sí" if preview.tiene_iva else "No"
        regimen_iva_txt = (
            "Sí"
            if preview.iva_regimen == "S"
            else "No"
            if preview.iva_regimen == "N"
            else "No disponible"
        )
        clase_iva_txt = (
            "Normal"
            if preview.iva_clase == "N"
            else "Intracomunitario"
            if preview.iva_clase == "I"
            else "No disponible"
        )
        detalle = (
            f"Nombre: {preview.nombre} | NIF: {preview.dni or '-'} | "
            f"País: {preview.pais or '-'} | Código ISO: {preview.cod_pais or '-'} | "
            f"Tipo documento: Otro | Lleva IVA: {lleva_iva_txt} | "
            f"Régimen IVA: {regimen_iva_txt} | Clase IVA: {clase_iva_txt} | "
            f"Errores: {len(valid_errores)} | "
            f"Coincidencia suficiente: {'SÍ' if preview.coincidencia_suficiente else 'NO'} | "
            f"Motivo: {motivo_txt} | Crear: {estado_creacion}"
        )
        if not puede_crear and motivo_bloqueo:
            detalle = f"{detalle} | {motivo_bloqueo}"
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": len(valid_errores) == 0 and puede_crear,
                "mensaje": "Previsualizacion de cliente preparada (sin escrituras).",
                "detalle": detalle,
            },
            status_code=200,
        )
    except Exception as exc:
        if settings.app_debug:
            logger.error("Error en previsualizacion de cliente: %s", exc, exc_info=True)
        else:
            logger.warning("Error en previsualizacion de cliente: %s", exc)
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "No se pudo previsualizar cliente.",
                "detalle": str(exc),
            },
            status_code=200,
        )


@router.post("/clientes/crear", response_class=HTMLResponse)
async def crear_cliente(request: Request):
    """
    Creacion real de cliente en Ambar con controles defensivos.
    """
    runtime_settings = request.app.state.settings
    if runtime_settings.app_read_only:
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Operacion bloqueada: modo solo lectura activo.",
                "detalle": "Desactive APP_READ_ONLY para permitir escrituras.",
            },
            status_code=200,
        )

    form_data = await request.form()
    id_pedido_raw = str(form_data.get("id_pedido", "")).strip()
    usar_direccion = str(form_data.get("usar_direccion", "Factura")).strip() or "Factura"
    force_override = str(form_data.get("force_override", "0")).strip().lower() in {"1", "true", "si", "s"}
    justificacion_override = str(form_data.get("justificacion_override", "")).strip()

    if not id_pedido_raw.isdigit():
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "ID de pedido invalido para crear cliente.",
                "detalle": "",
            },
            status_code=200,
        )

    filtros = FiltrosPedidosDTO(id_pedido=int(id_pedido_raw), usar_direccion=usar_direccion)
    try:
        async with mysql_prestashop.get_connection() as conn:
            pedidos = await obtener_pedidos(conn, filtros)
        if not pedidos:
            return templates.TemplateResponse(
                "partials/toast.html",
                {
                    "request": request,
                    "ok": False,
                    "mensaje": f"No se encontro el pedido {id_pedido_raw}.",
                    "detalle": "",
                },
                status_code=200,
            )
        pedido = pedidos[0]

        # Matching previo (control de coincidencia suficiente)
        try:
            matches = await matching_ambar_service.buscar_matches_clientes([pedido])
            candidatos = matches.get(pedido.id_pedido, [])
        except Exception as exc:
            if settings.app_debug:
                logger.error("Error en matching previo a crear cliente: %s", exc, exc_info=True)
            else:
                logger.warning("Error en matching previo a crear cliente: %s", exc)
            return templates.TemplateResponse(
                "partials/toast.html",
                {
                    "request": request,
                    "ok": False,
                    "mensaje": "No se puede crear cliente sin validar matching con Ambar.",
                    "detalle": "Revise conexion con Ambar e intente de nuevo.",
                },
                status_code=200,
            )

        preview = cliente_preview_service.construir_preview_cliente(
            pedido=pedido,
            usar_direccion=usar_direccion,
            candidatos_ambar=candidatos,
        )
        logger.info(
            "Alta cliente inicio pedido=%s email=%s nif=%s candidatos_ambar=%d coincidencia_suficiente=%s",
            pedido.id_pedido,
            _mask_email(preview.email),
            _mask_nif(preview.dni),
            len(candidatos),
            preview.coincidencia_suficiente,
        )
        if not preview.pais_resoluble:
            logger.warning(
                "Alta cliente bloqueada pedido_ps=%s iso=%s motivo=%s",
                pedido.id_pedido,
                preview.cod_pais or "-",
                preview.motivo_pais or "país no soportado o ISO ausente",
            )
            return templates.TemplateResponse(
                "partials/toast.html",
                {
                    "request": request,
                    "ok": False,
                    "mensaje": "Creacion bloqueada: no se pudo resolver el país del cliente.",
                    "detalle": preview.motivo_pais,
                },
                status_code=200,
            )
        puede_crear, motivo_bloqueo = cliente_preview_service.puede_crear_cliente(preview)
        if not puede_crear and not (force_override and justificacion_override):
            logger.info(
                "Alta cliente bloqueada pedido=%s email=%s nif=%s motivo=%s",
                pedido.id_pedido,
                _mask_email(preview.email),
                _mask_nif(preview.dni),
                motivo_bloqueo,
            )
            return templates.TemplateResponse(
                "partials/toast.html",
                {
                    "request": request,
                    "ok": False,
                    "mensaje": "Creacion bloqueada por validaciones de seguridad.",
                    "detalle": motivo_bloqueo,
                },
                status_code=200,
            )

        # Comprobacion defensiva final de duplicado justo antes del insert.
        loop = asyncio.get_event_loop()
        duplicados = await loop.run_in_executor(
            None,
            _buscar_duplicados_defensivos_sync,
            preview.email,
            preview.dni,
        )
        logger.info(
            "Alta cliente duplicado_defensivo pedido=%s email=%s nif=%s detectado=%s candidatos=%s",
            pedido.id_pedido,
            _mask_email(preview.email),
            _mask_nif(preview.dni),
            bool(duplicados),
            _cliente_ids_str(duplicados),
        )
        if duplicados and not (force_override and justificacion_override):
            top = ", ".join(str(c.numero_cliente) for c in duplicados[:5])
            return templates.TemplateResponse(
                "partials/toast.html",
                {
                    "request": request,
                    "ok": False,
                    "mensaje": "Creacion bloqueada: posible duplicado detectado.",
                    "detalle": f"Candidatos defensivos: {top}",
                },
                status_code=200,
            )

        req = cliente_preview_service.construir_solicitud_creacion(preview)
        logger.info(
            "Alta cliente insercion pedido=%s email=%s nif=%s cod_pais=%s tiene_iva=%s tipo_documento=%s iva_regimen=%s iva_clase=%s",
            pedido.id_pedido,
            _mask_email(req.email),
            _mask_nif(req.dni),
            req.cod_pais,
            req.tiene_iva,
            preview.tipo_documento,
            preview.iva_regimen,
            preview.iva_clase,
        )
        result = await loop.run_in_executor(
            None,
            _crear_cliente_sync,
            req,
        )

        logger.info(
            "Alta cliente resultado pedido=%s email=%s nif=%s ok=%s id_cliente=%s cuenta_contable=%s",
            pedido.id_pedido,
            _mask_email(req.email),
            _mask_nif(req.dni),
            result.ok,
            result.id_cliente,
            result.cuenta_contable,
        )
        detalle = ""
        if result.ok:
            detalle = f"ID: {result.id_cliente} | CC: {result.cuenta_contable}"
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": result.ok,
                "mensaje": result.mensaje,
                "detalle": detalle,
            },
            status_code=200,
        )
    except Exception as exc:
        if settings.app_debug:
            logger.error("Error creando cliente: %s", exc, exc_info=True)
        else:
            logger.error("Error creando cliente: %s", exc)
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Error al crear cliente en Ambar.",
                "detalle": str(exc),
            },
            status_code=200,
        )


@router.post("/clientes/{id_cliente}/activar", response_class=HTMLResponse)
async def activar_cliente(id_cliente: int, request: Request):
    """
    Reactiva un cliente de baja en Ambar (Baja=0, FechaModif=hoy, FechaBaja=NULL).
    """
    if settings.app_read_only:
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Operacion bloqueada: modo solo lectura activo.",
                "detalle": "Desactive APP_READ_ONLY para permitir reactivar clientes.",
            },
            status_code=200,
        )

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _activar_cliente_sync, id_cliente)
        logger.info(
            "Reactivar cliente resultado id_cliente=%s ok=%s",
            id_cliente,
            result.ok,
        )
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": result.ok,
                "mensaje": result.mensaje,
                "detalle": f"Cliente Ambar #{id_cliente}",
            },
            status_code=200,
        )
    except Exception as exc:
        if settings.app_debug:
            logger.error("Error reactivando cliente %s: %s", id_cliente, exc, exc_info=True)
        else:
            logger.error("Error reactivando cliente %s: %s", id_cliente, exc)
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Error al reactivar cliente en Ambar.",
                "detalle": str(exc),
            },
            status_code=200,
        )


@router.post("/anticipos/crear", response_class=HTMLResponse)
async def crear_anticipo(request: Request):
    """
    Registro real de anticipo en Ambar con controles defensivos.
    """
    form_data = await request.form()
    id_pedido_raw = str(form_data.get("id_pedido", "")).strip()
    cliente_manual_raw = str(form_data.get("cliente_ambar_manual", "")).strip()
    usar_direccion = str(form_data.get("usar_direccion", "Factura")).strip() or "Factura"
    hora_fin_dia = str(form_data.get("hora_fin_dia", "23:00")).strip() or "23:00"
    cliente_manual_id = int(cliente_manual_raw) if cliente_manual_raw.isdigit() else None

    if not id_pedido_raw.isdigit():
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "ID de pedido invalido para registrar anticipo.",
                "detalle": "",
            },
            status_code=200,
        )

    filtros = FiltrosPedidosDTO(id_pedido=int(id_pedido_raw), usar_direccion=usar_direccion, hora_fin_dia=hora_fin_dia)
    try:
        async with mysql_prestashop.get_connection() as conn:
            pedidos = await obtener_pedidos(conn, filtros)
        if not pedidos:
            return templates.TemplateResponse(
                "partials/toast.html",
                {
                    "request": request,
                    "ok": False,
                    "mensaje": f"No se encontro el pedido {id_pedido_raw}.",
                    "detalle": "",
                },
                status_code=200,
            )
        pedido = pedidos[0]

        matches = await matching_ambar_service.buscar_matches_clientes([pedido])
        seleccion_manual = {pedido.id_pedido: cliente_manual_id} if cliente_manual_id else None
        contexto = await anticipos_ambar_service.preparar_contexto_anticipos(
            pedidos=[pedido],
            matches_por_pedido=matches,
            hora_fin_dia=hora_fin_dia,
            seleccion_manual_por_pedido=seleccion_manual,
        )
        ant_ctx = contexto.get(pedido.id_pedido, {})
        if not ant_ctx:
            return templates.TemplateResponse(
                "partials/toast.html",
                {
                    "request": request,
                    "ok": False,
                    "mensaje": "No se pudo evaluar el anticipo para el pedido.",
                    "detalle": "",
                },
                status_code=200,
            )

        if not ant_ctx.get("puede_registrar", False):
            return templates.TemplateResponse(
                "partials/toast.html",
                {
                    "request": request,
                    "ok": False,
                    "mensaje": "Registro de anticipo bloqueado.",
                    "detalle": ant_ctx.get("motivo_bloqueo", "No procede registrar anticipo."),
                },
                status_code=200,
            )

        cliente_id = ant_ctx.get("cliente_id")
        if not cliente_id:
            return templates.TemplateResponse(
                "partials/toast.html",
                {
                    "request": request,
                    "ok": False,
                    "mensaje": "No hay cliente Ambar valido para registrar anticipo.",
                    "detalle": "",
                },
                status_code=200,
            )

        fecha_iso = pedido.fecha_pedido.isoformat() if pedido.fecha_pedido else datetime.now().isoformat()
        req = CrearAnticipoRequestDTO(
            id_pedido_ps=pedido.id_pedido,
            id_cliente_ambar=int(cliente_id),
            fecha_pedido=fecha_iso,
            total_pedido=float(pedido.total_con_iva),
            forma_pago_ambar=str(ant_ctx.get("forma_pago_ambar", "PE")),
            cod_banco=str(ant_ctx.get("cod_banco", "1")),
            cc_cliente=str(ant_ctx.get("cc_cliente", "")),
            hora_fin_dia=hora_fin_dia,
        )

        logger.info(
            "Alta anticipo inicio pedido=%s cliente=%s importe=%.2f forma=%s banco=%s",
            pedido.id_pedido,
            req.id_cliente_ambar,
            req.total_pedido,
            req.forma_pago_ambar,
            req.cod_banco,
        )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _crear_anticipo_sync, req)

        logger.info(
            "Alta anticipo resultado pedido=%s cliente=%s ok=%s id_anticipo=%s",
            pedido.id_pedido,
            req.id_cliente_ambar,
            result.ok,
            result.id_anticipo,
        )
        detalle = f"Anticipo #{result.id_anticipo}" if result.ok and result.id_anticipo else ""
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": result.ok,
                "mensaje": result.mensaje,
                "detalle": detalle,
            },
            status_code=200,
        )
    except Exception as exc:
        if settings.app_debug:
            logger.error("Error registrando anticipo: %s", exc, exc_info=True)
        else:
            logger.error("Error registrando anticipo: %s", exc)
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Error al registrar anticipo.",
                "detalle": str(exc),
            },
            status_code=200,
        )


@router.post("/ambar/pedidos/crear", response_class=HTMLResponse)
async def crear_pedido_ambar(request: Request):
    """
    Creacion real de pedido Ambar con validaciones defensivas.
    """
    if settings.app_read_only:
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Operacion bloqueada: modo solo lectura activo.",
                "detalle": "Desactive APP_READ_ONLY para permitir escrituras.",
            },
            status_code=200,
        )

    form_data = await request.form()
    id_pedido_raw = str(form_data.get("id_pedido", form_data.get("id_pedido_ps", ""))).strip()
    cliente_manual_raw = str(form_data.get("cliente_ambar_manual", "")).strip()
    usar_direccion = str(form_data.get("usar_direccion", "Factura")).strip() or "Factura"
    cliente_manual_id = int(cliente_manual_raw) if cliente_manual_raw.isdigit() else None
    logger.debug(
        "Alta pedido input form id_pedido=%s usar_direccion=%s ref_form=%s",
        id_pedido_raw or "-",
        usar_direccion,
        str(form_data.get("referencia", "")).strip() or "-",
    )

    if not id_pedido_raw.isdigit():
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "ID de pedido invalido para crear pedido Ambar.",
                "detalle": "",
            },
            status_code=200,
        )

    filtros = FiltrosPedidosDTO(id_pedido=int(id_pedido_raw), usar_direccion=usar_direccion)
    try:
        async with mysql_prestashop.get_connection() as conn:
            pedidos = await obtener_pedidos(conn, filtros)
            if not pedidos:
                return templates.TemplateResponse(
                    "partials/toast.html",
                    {
                        "request": request,
                        "ok": False,
                        "mensaje": f"No se encontro el pedido {id_pedido_raw}.",
                        "detalle": "",
                    },
                    status_code=200,
                )
            pedido = pedidos[0]

            matches = await matching_ambar_service.buscar_matches_clientes([pedido])
            seleccion_manual = {pedido.id_pedido: cliente_manual_id} if cliente_manual_id else None
            ctx_map = await pedidos_ambar_service.preparar_contexto_pedidos(
                [pedido],
                matches,
                seleccion_manual_por_pedido=seleccion_manual,
            )
            pctx = ctx_map.get(pedido.id_pedido, {})
            if not pctx:
                return templates.TemplateResponse(
                    "partials/toast.html",
                    {
                        "request": request,
                        "ok": False,
                        "mensaje": "No se pudo evaluar el pedido Ambar.",
                        "detalle": "",
                    },
                    status_code=200,
                )

            if not pctx.get("puede_crear", False):
                return templates.TemplateResponse(
                    "partials/toast.html",
                    {
                        "request": request,
                        "ok": False,
                        "mensaje": "Creacion de pedido bloqueada.",
                        "detalle": pctx.get("motivo_bloqueo", "No procede crear pedido Ambar."),
                    },
                    status_code=200,
                )

            cliente_id = pctx.get("cliente_id")
            if not cliente_id:
                return templates.TemplateResponse(
                    "partials/toast.html",
                    {
                        "request": request,
                        "ok": False,
                        "mensaje": "No hay cliente Ambar valido para crear pedido.",
                        "detalle": "",
                    },
                    status_code=200,
                )

            datos_ps = await pedido_service.leer_pedido_prestashop_para_ambar(conn, pedido.id_pedido)

        req = CrearPedidoAmbarRequestDTO(
            id_cliente_ambar=int(cliente_id),
            id_pedido_ps=pedido.id_pedido,
        )

        logger.info(
            "Alta pedido inicio pedido_ps=%s cliente_ambar=%s referencia_ps=%s total=%.2f",
            pedido.id_pedido,
            req.id_cliente_ambar,
            pedido.referencia,
            float(pedido.total_con_iva),
        )
        logger.debug(
            "Alta pedido debug pre-create pedido_ps=%s ref_ps=%s ped_can=%s exacto=%s probable=%s",
            pedido.id_pedido,
            pedido.referencia or "-",
            pctx.get("puede_crear", False),
            (pctx.get("pedido_existente_exacto") or {}).get("referencia", "-"),
            (pctx.get("pedido_probable") or {}).get("referencia", "-"),
        )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _crear_pedido_ambar_sync,
            req,
            datos_ps,
        )

        logger.info(
            "Alta pedido resultado pedido_ps=%s cliente_ambar=%s ok=%s ref=%s",
            pedido.id_pedido,
            req.id_cliente_ambar,
            result.ok,
            result.referencia,
        )
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": result.ok,
                "mensaje": result.mensaje,
                "detalle": result.referencia or "",
            },
            status_code=200,
        )
    except Exception as exc:
        if settings.app_debug:
            logger.error("Error creando pedido Ambar: %s", exc, exc_info=True)
        else:
            logger.error("Error creando pedido Ambar: %s", exc)
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Error al crear pedido Ambar.",
                "detalle": str(exc),
            },
            status_code=200,
        )


@router.post("/prestashop/estado/cambiar", response_class=HTMLResponse)
async def cambiar_estado_prestashop(request: Request):
    """
    Cambia estado de pedido en PrestaShop via bridge HTTP seguro.
    """
    logger.info("Entrada endpoint /prestashop/estado/cambiar")
    if settings.app_read_only:
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Operacion bloqueada: modo solo lectura activo.",
                "detalle": "En solo lectura se permite consultar y filtrar, no cambiar estados.",
            },
            status_code=200,
        )

    form_data = await request.form()
    logger.info("Cambio estado PrestaShop form_keys=%s", list(form_data.keys()))
    id_pedido_raw = str(form_data.get("id_pedido", "")).strip()
    id_estado_raw = str(form_data.get("id_order_state", "")).strip()

    if not id_pedido_raw.isdigit() or not id_estado_raw.isdigit():
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "ok": False,
                "mensaje": "Datos invalidos para cambiar estado.",
                "detalle": "Revise pedido y estado seleccionado.",
            },
            status_code=200,
        )

    id_pedido = int(id_pedido_raw)
    id_estado = int(id_estado_raw)
    enviar_email = str(form_data.get("send_email", "0")).strip().lower() in {"1", "true", "si", "s"}

    logger.info(
        "Cambio estado PrestaShop inicio pedido=%s estado=%s send_email=%s bridge_url=%s token_set=%s",
        id_pedido,
        id_estado,
        enviar_email,
        settings.ps_state_bridge_url or "-",
        bool((settings.ps_state_bridge_token or "").strip()),
    )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        prestashop_state_bridge_service.cambiar_estado_pedido,
        settings.ps_state_bridge_url,
        settings.ps_state_bridge_token,
        id_pedido,
        id_estado,
        enviar_email,
        settings.ps_state_bridge_timeout_sec,
    )

    logger.info(
        "Cambio estado PrestaShop resultado pedido=%s estado=%s ok=%s detalle=%s estado_aplicado=%s",
        id_pedido,
        id_estado,
        result.ok,
        result.detalle or "-",
        result.estado_aplicado,
    )

    return templates.TemplateResponse(
        "partials/toast.html",
        {
            "request": request,
            "ok": result.ok,
            "mensaje": result.mensaje,
            "detalle": result.detalle,
        },
        status_code=200,
    )


@router.post("/pedidos/{id_pedido}/email/enviar")
async def enviar_email_pedido(request: Request, id_pedido: int):
    runtime_settings = request.app.state.settings
    if runtime_settings.app_read_only:
        return JSONResponse(
            {"ok": False, "message": "Operacion bloqueada: modo solo lectura activo."},
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "message": "Payload JSON invalido."}, status_code=400)

    payload = payload or {}
    payload["id_pedido"] = id_pedido
    try:
        req = EmailPedidoRequestDTO(**payload)
    except ValidationError as exc:
        first_error = (exc.errors() or [{}])[0].get("msg", "Datos de email invalidos.")
        return JSONResponse({"ok": False, "message": first_error}, status_code=400)

    try:
        async with mysql_prestashop.get_connection() as conn:
            pedido = await obtener_resumen_pedido_para_email(conn, id_pedido)
            lineas = await obtener_lineas_pedido_para_email(conn, id_pedido)
    except Exception as exc:
        logger.error("Email pedido error consulta id_pedido=%s: %s", id_pedido, exc, exc_info=True)
        return JSONResponse({"ok": False, "message": "No se pudo validar el pedido."}, status_code=500)

    if not pedido:
        return JSONResponse({"ok": False, "message": f"No se encontro el pedido {id_pedido}."}, status_code=404)

    email_real = str(pedido.get("email") or "").strip()
    if not email_real:
        return JSONResponse(
            {"ok": False, "message": "El pedido no tiene email de cliente para enviar correo."},
            status_code=400,
        )

    if email_real.lower() != req.to_email.lower():
        logger.warning(
            "Email pedido bloqueado id_pedido=%s to_payload=%s to_real=%s",
            id_pedido,
            req.to_email,
            email_real,
        )
        return JSONResponse(
            {"ok": False, "message": "El email destino no coincide con el email del cliente del pedido."},
            status_code=400,
        )

    loop = asyncio.get_event_loop()
    productos_email = []
    for linea in lineas[:3]:
        image_url = construir_url_imagen_prestashop(
            runtime_settings.ps_public_url,
            linea.get("id_image"),
            image_type="home_default",
        )
        logger.info(
            "Email pedido producto imagen id_pedido=%s ref=%s id_image=%s image_url=%s",
            id_pedido,
            str(linea.get("reference") or "").strip() or "-",
            linea.get("id_image"),
            image_url or "-",
        )
        productos_email.append(
            {
                "name": str(linea.get("name") or "").strip(),
                "reference": str(linea.get("reference") or "").strip(),
                "quantity": int(linea.get("quantity") or 0),
                "unit_price": _format_money(linea.get("unit_price")),
                "total_price": _format_money(linea.get("total_price")),
                "image_url": image_url,
            }
        )
    products_extra_count = max(0, len(lineas) - len(productos_email))

    try:
        await loop.run_in_executor(
            None,
            lambda: email_service.enviar_email_cliente_pedido(
                settings=runtime_settings,
                destinatario=req.to_email,
                asunto=req.subject,
                cuerpo=req.body,
                id_pedido=req.id_pedido,
                referencia=str(pedido.get("reference") or "").strip(),
                fecha_pedido=pedido.get("date_add"),
                total_pedido=pedido.get("total_paid_tax_incl"),
                nombre_cliente=f"{str(pedido.get('firstname') or '').strip()} {str(pedido.get('lastname') or '').strip()}".strip(),
                products=productos_email,
                products_extra_count=products_extra_count,
            ),
        )
        return JSONResponse({"ok": True, "message": "Correo enviado correctamente."})
    except ValueError as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)
    except Exception:
        return JSONResponse({"ok": False, "message": "No se pudo enviar el correo."}, status_code=500)


def _buscar_duplicados_defensivos_sync(email: str, nif: str):
    with sqlserver_ambar.get_connection() as conn:
        return clientes_repository.buscar_duplicados_defensivos(conn, email=email, nif=nif)


def _crear_cliente_sync(req: CrearClienteRequestDTO):
    with sqlserver_ambar.get_connection() as conn:
        return cliente_service.crear_cliente(conn, req)


def _crear_anticipo_sync(req: CrearAnticipoRequestDTO):
    with sqlserver_ambar.get_connection() as conn:
        return anticipo_service.crear_anticipo(conn, req)


def _activar_cliente_sync(id_cliente: int):
    with sqlserver_ambar.get_connection() as conn:
        return cliente_service.activar_cliente(conn, id_cliente)


def _crear_pedido_ambar_sync(req: CrearPedidoAmbarRequestDTO, datos_ps: dict):
    with sqlserver_ambar.get_connection() as conn:
        return pedido_service.crear_pedido_ambar_desde_datos(
            ambar_conn=conn,
            req=req,
            datos_ps=datos_ps,
            strict_production=settings.is_any_production,
        )


def _mask_email(email: str) -> str:
    raw = (email or "").strip()
    if not raw or "@" not in raw:
        return "-"
    local, domain = raw.split("@", 1)
    if len(local) <= 2:
        local_mask = local[0] + "*"
    else:
        local_mask = local[:2] + "*" * max(1, len(local) - 2)
    return f"{local_mask}@{domain}"


def _mask_nif(nif: str) -> str:
    raw = (nif or "").strip().upper()
    if not raw:
        return "-"
    if len(raw) <= 3:
        return raw[0] + "*" * (len(raw) - 1)
    return raw[:2] + "*" * (len(raw) - 3) + raw[-1]


def _cliente_ids_str(clientes) -> str:
    if not clientes:
        return "-"
    return ",".join(str(c.numero_cliente) for c in clientes[:10])


def _format_money(value) -> str:
    try:
        return f"{float(value):.2f} €"
    except Exception:
        return ""


def construir_url_imagen_prestashop(base_url: str, id_image: int | str | None, image_type: str = "home_default") -> str:
    if not id_image:
        return ""
    url_base = (base_url or "").strip().rstrip("/")
    image_id = str(id_image).strip()
    image_type_safe = str(image_type or "home_default").strip() or "home_default"
    if not url_base or not image_id:
        return ""
    if not image_id.isdigit():
        return ""
    path = "/".join(image_id)
    return f"{url_base}/img/p/{path}/{image_id}-{image_type_safe}.jpg"


