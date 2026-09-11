"""
services/matching_service.py — Servicio de enriquecimiento de pedidos.

Orquesta: pedidos PS + matching Ambar + PRO + normalización de datos.
MEJORA: el PHP mezclaba presentación, consultas y lógica en matches.php.
Aquí cada responsabilidad está separada.
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from aiomysql import Connection as MySQLConn
import pyodbc

from app.schemas.pedido import PedidoPSDTO, FiltrosPedidosDTO
from app.schemas.cliente import ClienteAmbarDTO
from app.repositories import pedidos_repository as rp
from app.repositories import clientes_repository as rc
from app.repositories import anticipos_repository as ra
from app.repositories import ambar_pedidos_repository as rpv
from app.services import pro_service, normalizacion_service as ns
from app.utils.mapeo_pago import mapear_pago
from app.utils.paises import iva_para_pais, es_portugal

logger = logging.getLogger(__name__)

# Ejecutor para llamadas síncronas a SQL Server
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ambar")


class PedidoEnriquecidoDTO:
    """
    Agrega un PedidoPSDTO con todos los datos calculados necesarios
    para renderizar la fila completa en la tabla.
    """
    def __init__(
        self,
        pedido: PedidoPSDTO,
        usar_dir: str,
    ):
        self.pedido = pedido
        self.usar_dir = usar_dir

        # Dirección activa según opción usuario
        self.dir_activa = (
            pedido.direccion_factura
            if usar_dir == "Factura"
            else pedido.direccion_envio
        )

        # Datos normalizados para crear cliente si es nuevo
        self.nombre_ambar = ns.normalizar_nombre_ambar(
            self.dir_activa.apellidos, self.dir_activa.nombre
        )
        self.direccion_ambar = ns.normalizar_direccion_ambar(
            self.dir_activa.linea1, self.dir_activa.linea2
        )
        self.ciudad_ambar = ns.normalizar_ciudad_ambar(self.dir_activa.ciudad)
        self.provincia_ambar = ns.normalizar_provincia_ambar(self.dir_activa.provincia)
        pais_n, cod_pais_n = ns.normalizar_pais_ambar(
            self.dir_activa.pais, self.dir_activa.cod_pais
        )
        self.pais_ambar = pais_n
        self.cod_pais_ambar = cod_pais_n
        self.postal_ambar = (self.dir_activa.postal or "").strip()
        self.telefono_ambar = ns.normalizar_telefono_ambar(self.dir_activa.telefono)
        self.movil_ambar = ns.normalizar_telefono_ambar(self.dir_activa.movil)
        self.email_ambar = pedido.email_cliente.strip()
        self.dni_ambar = ns.formatear_dni_ambar(
            self.dir_activa.dni, self.dir_activa.pais
        )

        # IVA
        self.porcentaje_iva = iva_para_pais(self.dir_activa.id_pais)
        self.tiene_iva = pedido.tiene_iva
        self.es_portugal = es_portugal(self.dir_activa.pais)

        # Pago
        self.info_pago = mapear_pago(pedido.modo_pago)

        # Campos que rellena el matching
        self.clientes_ambar: list[ClienteAmbarDTO] = []
        self.anticipos: list = []
        self.pedido_ambar_existente: str | None = None
        self.es_cliente_nuevo: bool = True
        self.coincide_anticipo: bool = False
        self.coincide_pedido: bool = False

    @property
    def cliente_ambar_principal(self) -> ClienteAmbarDTO | None:
        return self.clientes_ambar[0] if self.clientes_ambar else None

    @property
    def numeros_clientes_ambar(self) -> list[int]:
        return [c.numero_cliente for c in self.clientes_ambar]


async def enriquecer_pedidos(
    ps_conn: MySQLConn,
    ambar_conn: pyodbc.Connection,
    b2b_conn: MySQLConn,
    filtros: FiltrosPedidosDTO,
) -> list[PedidoEnriquecidoDTO]:
    """
    Función principal: obtiene pedidos PS y los enriquece con datos Ambar+PRO.
    """
    # 1. Pedidos PrestaShop (async)
    pedidos = await rp.obtener_pedidos(ps_conn, filtros)
    if not pedidos:
        return []

    # 2. Set PRO (async, en paralelo con matching)
    pro_task = asyncio.create_task(
        pro_service.cargar_set_usuarios_pro(b2b_conn)
    )

    # 3. Matching Ambar (síncrono en executor)
    loop = asyncio.get_event_loop()
    pedidos_datos = [
        {
            "id_pedido": p.id_pedido,
            "email": p.email_cliente,
            "dni_num_envio": p.direccion_envio.dni_numerico,
            "dni_num_factura": p.direccion_factura.dni_numerico,
        }
        for p in pedidos
    ]
    matches_task = loop.run_in_executor(
        _executor,
        rc.buscar_clientes_batch,
        ambar_conn,
        pedidos_datos,
    )

    # Esperar ambas tareas
    pro_set, matches_por_pedido = await asyncio.gather(pro_task, matches_task)

    # 4. Construir DTOs enriquecidos
    usar_dir = filtros.usar_direccion
    resultados: list[PedidoEnriquecidoDTO] = []

    for pedido in pedidos:
        enriq = PedidoEnriquecidoDTO(pedido, usar_dir)

        # PRO
        pedido.es_pro = pro_service.es_cliente_pro(
            pedido.nombre_cliente, pedido.apellidos_cliente, pro_set
        )

        # Clientes Ambar candidatos
        enriq.clientes_ambar = matches_por_pedido.get(pedido.id_pedido, [])
        enriq.es_cliente_nuevo = len(enriq.clientes_ambar) == 0

        # Si hay clientes candidatos → buscar anticipos y pedido existente (síncronos)
        if not enriq.es_cliente_nuevo:
            numeros = enriq.numeros_clientes_ambar

            anticipos = await loop.run_in_executor(
                _executor,
                ra.obtener_anticipos_clientes,
                ambar_conn, numeros, 3,
            )
            enriq.anticipos = anticipos

            # Comprobar si anticipo ya existe
            from datetime import date
            fecha_p = pedido.fecha_pedido.date() if pedido.fecha_pedido else date.today()
            enriq.coincide_anticipo = await loop.run_in_executor(
                _executor,
                ra.anticipo_ya_existe,
                ambar_conn, numeros,
                pedido.total_con_iva, fecha_p,
            )

            # Comprobar si pedido ya existe
            ref_existe = await loop.run_in_executor(
                _executor,
                rpv.pedido_ya_existe,
                ambar_conn, numeros,
                pedido.fecha_pedido.strftime("%Y-%m-%d") if pedido.fecha_pedido else "",
                pedido.total_con_iva,
            )
            enriq.pedido_ambar_existente = ref_existe
            enriq.coincide_pedido = ref_existe is not None

        resultados.append(enriq)

    logger.info(
        "Matching completado: %d pedidos, %d nuevos clientes",
        len(resultados),
        sum(1 for r in resultados if r.es_cliente_nuevo),
    )
    return resultados
