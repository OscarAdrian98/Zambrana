"""
repositories/anticipos_repository.py — Consultas de anticipos en Ambar.

MEJORA: comprobación de anticipo existente antes de insertar (idempotencia).
El legacy no tenía ninguna comprobación de duplicado.
"""
import logging
import pyodbc
from datetime import datetime, date
from app.schemas.anticipo import AnticipoCabDTO

logger = logging.getLogger(__name__)


def obtener_anticipos_clientes(
    conn: pyodbc.Connection,
    numeros_cliente: list[int],
    top: int = 3,
) -> list[AnticipoCabDTO]:
    """
    Devuelve los últimos N anticipos para una lista de clientes Ambar.
    Equivalente al $sqlAnticiposCliente del PHP (TOP 3).
    """
    if not numeros_cliente:
        return []

    placeholders = ",".join(["?"] * len(numeros_cliente))
    sql = f"""
        SELECT TOP {top}
            CliPro, FechaEntrega, ImporteDisponible,
            ImporteEntregado, FormaPago, Banco, FechaUltUtilizacion
        FROM AnticiposCab
        WHERE CliPro IN ({placeholders})
        ORDER BY FechaEntrega DESC
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, numeros_cliente)
        rows = cursor.fetchall()
        anticipos = []
        for row in rows:
            cli, fecha_ent, disp, entregado, forma, banco, fecha_util = row
            fecha_str = fecha_ent.strftime("%Y-%m-%d") if fecha_ent else ""
            util_str = fecha_util.strftime("%Y-%m-%d") if fecha_util else None
            anticipos.append(AnticipoCabDTO(
                codigo=0,  # No se devuelve en esta query
                cliente=int(cli),
                fecha=fecha_str,
                importe_disponible=float(disp or 0),
                importe_entregado=float(entregado or 0),
                forma_pago=forma or "",
                banco=str(banco or ""),
                fecha_utilizacion=util_str,
            ))
        return anticipos
    except Exception as e:
        logger.error("Error obteniendo anticipos para clientes %s: %s", numeros_cliente, e)
        return []


def obtener_anticipos_clientes_batch(
    conn: pyodbc.Connection,
    numeros_cliente: list[int],
    top_por_cliente: int = 5,
) -> dict[int, list[AnticipoCabDTO]]:
    """
    Devuelve anticipos por cliente en lote (top N por cliente) para evitar N queries por fila.
    """
    if not numeros_cliente:
        return {}

    placeholders = ",".join(["?"] * len(numeros_cliente))
    sql = f"""
        WITH ant AS (
            SELECT
                CliPro,
                Codigo,
                FechaEntrega,
                ImporteDisponible,
                ImporteEntregado,
                FormaPago,
                Banco,
                FechaUltUtilizacion,
                ROW_NUMBER() OVER (
                    PARTITION BY CliPro
                    ORDER BY FechaEntrega DESC, Codigo DESC
                ) AS rn
            FROM AnticiposCab
            WHERE CliPro IN ({placeholders})
        )
        SELECT
            CliPro,
            Codigo,
            FechaEntrega,
            ImporteDisponible,
            ImporteEntregado,
            FormaPago,
            Banco,
            FechaUltUtilizacion
        FROM ant
        WHERE rn <= ?
        ORDER BY CliPro, FechaEntrega DESC, Codigo DESC
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, [*numeros_cliente, top_por_cliente])
        rows = cursor.fetchall()
        resultado: dict[int, list[AnticipoCabDTO]] = {}
        for row in rows:
            (
                cli,
                codigo,
                fecha_ent,
                disp,
                entregado,
                forma,
                banco,
                fecha_util,
            ) = row
            dto = AnticipoCabDTO(
                codigo=int(codigo or 0),
                cliente=int(cli),
                fecha=fecha_ent.strftime("%Y-%m-%d") if fecha_ent else "",
                importe_disponible=float(disp or 0),
                importe_entregado=float(entregado or 0),
                forma_pago=forma or "",
                banco=str(banco or ""),
                fecha_utilizacion=fecha_util.strftime("%Y-%m-%d") if fecha_util else None,
            )
            resultado.setdefault(int(cli), []).append(dto)
        return resultado
    except Exception as e:
        logger.error("Error batch anticipos para clientes %s: %s", numeros_cliente, e)
        return {}


def anticipo_ya_existe(
    conn: pyodbc.Connection,
    numeros_cliente: list[int],
    importe: float,
    fecha_pedido: date,
) -> bool:
    """
    Comprueba si ya existe un anticipo del mismo importe en la fecha del pedido.
    MEJORA vs legacy: el PHP no tenía esta comprobación (riesgo duplicados).
    """
    if not numeros_cliente:
        return False
    placeholders = ",".join(["?"] * len(numeros_cliente))
    fecha_base = fecha_pedido if isinstance(fecha_pedido, date) else datetime.now().date()
    fecha_iso = fecha_base.strftime("%Y-%m-%d")
    fecha_dmy = fecha_base.strftime("%d-%m-%Y")
    importe_min = float(importe) - 0.01
    importe_max = float(importe) + 0.01
    sql = f"""
        SELECT TOP 1 Codigo
        FROM AnticiposCab
        WHERE CliPro IN ({placeholders})
          AND (
                LEFT(LTRIM(RTRIM(CONVERT(VARCHAR(19), FechaEntrega))), 10) = ?
             OR LEFT(LTRIM(RTRIM(CONVERT(VARCHAR(19), FechaEntrega))), 10) = ?
          )
          AND ImporteEntregado >= ?
          AND ImporteEntregado <= ?
    """
    try:
        cursor = conn.cursor()
        params = [
            *[int(c) for c in numeros_cliente],
            fecha_iso,
            fecha_dmy,
            importe_min,
            importe_max,
        ]
        logger.info(
            (
                "Verificacion anticipo duplicado criterio clientes=%s "
                "fecha_iso=%s fecha_dmy=%s campo_fecha=FechaEntrega "
                "estrategia=compare_text_day importe=[%.2f..%.2f]"
            ),
            ",".join(str(int(c)) for c in numeros_cliente),
            fecha_iso,
            fecha_dmy,
            importe_min,
            importe_max,
        )
        cursor.execute(sql, params)
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error("Error verificando anticipo duplicado: %s", e)
        return False


def obtener_proximo_id_anticipo(conn: pyodbc.Connection) -> int:
    """Obtiene el próximo código de anticipo (< 900000)."""
    sql = "SELECT MAX(Codigo) FROM AnticiposCab WHERE Codigo < 900000"
    cursor = conn.cursor()
    cursor.execute(sql)
    row = cursor.fetchone()
    return int(row[0] or 0) + 1


def insertar_anticipo(
    conn: pyodbc.Connection,
    id_anticipo: int,
    id_cliente: int,
    fecha_insertar: str,
    importe: float,
    forma_pago: str,
    cod_banco: str,
    cc_cliente: str,
) -> int:
    """
    Inserta AnticiposCab + MovimBanco + actualiza contador.
    Equivalente al payment.php pero en transacción real.
    Devuelve el código de anticipo creado.
    """
    sql_anticipo = """
        INSERT INTO AnticiposCab
            (Codigo, FechaEntrega, Tipo, CliPro, Concepto,
             ImporteDisponible, ImporteEntregado, FormaPago, Banco)
        VALUES (?, ?, 'V', ?, '', ?, ?, ?, ?)
    """
    sql_movim = """
        INSERT INTO MovimBanco
            (Banco, Fecha, EntradaSalida, ImporteEu, Observaciones,
             Contrapartida, EnlazadoSN, TipoDocumento, Serie,
             NumDocumento, ClienteProveedor, Conciliado)
        VALUES (?, ?, 'E', ?, '', ?, 'N', 'AN', NULL, ?, ?, 'N')
    """
    sql_contador = """
        UPDATE Config SET Valor = ?
        WHERE Grupo = 'CONTADORES DE DOCUMENTOS' AND Variable = 'ANTICIPOS'
    """

    cursor = conn.cursor()
    cursor.execute(sql_anticipo, (
        id_anticipo, fecha_insertar, id_cliente,
        importe, importe, forma_pago, cod_banco
    ))
    cursor.execute(sql_movim, (
        cod_banco, fecha_insertar, importe,
        cc_cliente, id_anticipo, id_cliente
    ))
    cursor.execute(sql_contador, (str(id_anticipo),))
    conn.commit()

    logger.info(
        "✅ Anticipo %d creado para cliente %d — %.2f€ (%s)",
        id_anticipo, id_cliente, importe, forma_pago
    )
    return id_anticipo
