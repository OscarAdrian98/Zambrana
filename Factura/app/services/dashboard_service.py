from datetime import date
from calendar import monthrange
from app.database.db import get_connection


def obtener_resumen_dashboard(mes=None, año=None):

    conn = get_connection()
    cursor = conn.cursor()

    hoy = date.today()

    if not mes:
        mes = hoy.month

    if not año:
        año = hoy.year

    # Primer y último día del mes
    ultimo_dia = monthrange(año, mes)[1]

    inicio_mes = f"{año}-{mes:02d}-01"
    fin_mes = f"{año}-{mes:02d}-{ultimo_dia}"

    # =====================================================
    # VENTAS
    # =====================================================

    cursor.execute(
        """
        SELECT IFNULL(SUM(total),0)
        FROM documentos
        WHERE tipo='FACTURA'
        AND fecha BETWEEN ? AND ?
        """,
        (inicio_mes, fin_mes),
    )
    facturado = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT IFNULL(SUM(total),0)
        FROM documentos
        WHERE tipo='FACTURA'
        AND estado='PAGADA'
        AND fecha_pago BETWEEN ? AND ?
        """,
        (inicio_mes, fin_mes),
    )
    cobrado = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT IFNULL(SUM(total),0)
        FROM documentos
        WHERE tipo='FACTURA'
        AND estado='PENDIENTE'
        """
    )
    pendiente_cobro = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT IFNULL(SUM(total),0)
        FROM documentos
        WHERE tipo='FACTURA'
        AND estado='VENCIDA'
        """
    )
    vencidas_venta = cursor.fetchone()[0] or 0

    # =====================================================
    # COMPRAS
    # =====================================================

    cursor.execute(
        """
        SELECT IFNULL(SUM(total),0)
        FROM documentos_compras
        WHERE fecha BETWEEN ? AND ?
        """,
        (inicio_mes, fin_mes),
    )
    compras_mes = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT IFNULL(SUM(total),0)
        FROM documentos_compras
        WHERE estado_pago='PAGADA'
        AND fecha_pago BETWEEN ? AND ?
        """,
        (inicio_mes, fin_mes),
    )
    pagado_proveedores = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT IFNULL(SUM(total),0)
        FROM documentos_compras
        WHERE estado_pago='PENDIENTE'
        """
    )
    pendiente_pago = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT IFNULL(SUM(total),0)
        FROM documentos_compras
        WHERE estado_pago='PENDIENTE'
        AND fecha_vencimiento IS NOT NULL
        AND fecha_vencimiento < ?
        """,
        (date.today().isoformat(),),
    )
    vencidas_compra = cursor.fetchone()[0] or 0

    conn.close()

    resultado_mes = facturado - compras_mes
    flujo_caja = cobrado - pagado_proveedores

    return {
        "facturado": float(facturado),
        "cobrado": float(cobrado),
        "pendiente_cobro": float(pendiente_cobro),
        "vencidas_venta": float(vencidas_venta),
        "compras_mes": float(compras_mes),
        "pagado_proveedores": float(pagado_proveedores),
        "pendiente_pago": float(pendiente_pago),
        "vencidas_compra": float(vencidas_compra),
        "resultado_mes": float(resultado_mes),
        "flujo_caja": float(flujo_caja),
    }
