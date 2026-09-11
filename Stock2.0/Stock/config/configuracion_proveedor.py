"""Lectura de la configuración de proveedores."""

import logging

from config.crypto import decrypt_password


def obtener_configuraciones_proveedor(id_proveedor, conexion_proveedores):
    """Devuelve las configuraciones de un proveedor sin exponer secretos."""

    try:
        with conexion_proveedores.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ftp_server_configuracion,
                    ftp_port_configuracion,
                    ftp_user_configuracion,
                    ftp_pass_enc,
                    fichero_configuracion,
                    extension_configuracion,
                    col_referencia_configuracion,
                    col_stock_configuracion,
                    fila_comienzo_configuracion,
                    separador_csv_configuracion,
                    id_marca,
                    http_configuracion,
                    plazo_entrega_proveedor,
                    col_ean_configuracion,
                    col_fecha_configuracion,
                    cp.id_configuracion,
                    col_referencia_alternativa_configuracion
                FROM configuracion_proveedores cp
                INNER JOIN proveedores p
                    ON cp.id_proveedor = p.id_proveedor
                WHERE p.id_proveedor = %s
                """,
                (id_proveedor,),
            )
            filas = cursor.fetchall()
        resultados = []
        for fila_original in filas:
            fila = list(fila_original)
            if fila[3]:
                fila[3] = decrypt_password(fila[3])
            resultados.append(tuple(fila))
        return resultados
    except Exception:
        logging.exception(
            "Error al obtener configuraciones del proveedor %s",
            id_proveedor,
        )
        return None


def obtener_marcas_permitidas_configuracion(
    id_configuracion,
    conexion_proveedores,
):
    """Devuelve la lista multipmarca activa de una configuración.

    La ausencia de la tabla aditiva conserva el comportamiento monomarca y
    permite que el código antiguo siga funcionando durante la migración.
    """

    with conexion_proveedores.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'configuracion_marcas_permitidas'
            """
        )
        if int(cursor.fetchone()[0]) == 0:
            return []
        cursor.execute(
            """
            SELECT
                cmp.id_marca,
                m.nombre_marca,
                cmp.nombre_marca_prestashop,
                cmp.prioridad
            FROM configuracion_marcas_permitidas cmp
            INNER JOIN marcas m ON m.id_marca = cmp.id_marca
            WHERE cmp.id_configuracion = %s
              AND cmp.estado = 1
            ORDER BY cmp.prioridad, cmp.id_marca
            """,
            (id_configuracion,),
        )
        return [
            {
                "id_marca": int(fila[0]),
                "nombre_marca": fila[1],
                "nombre_marca_prestashop": fila[2],
                "prioridad": int(fila[3]),
            }
            for fila in cursor.fetchall()
        ]


def obtener_resolucion_marca_configuracion(
    id_configuracion,
    conexion_proveedores,
):
    """Devuelve columna de marca y marca genérica pendiente, si existen."""

    with conexion_proveedores.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=DATABASE() "
            "AND TABLE_NAME='configuracion_resolucion_marca'"
        )
        if int(cursor.fetchone()[0]) == 0:
            return None
        cursor.execute(
            "SELECT crm.col_marca_fuente,crm.id_marca_pendiente,"
            "m.nombre_marca FROM configuracion_resolucion_marca crm "
            "JOIN marcas m ON m.id_marca=crm.id_marca_pendiente "
            "WHERE crm.id_configuracion=%s AND crm.estado=1",
            (id_configuracion,),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return {
        "col_marca_fuente": (
            int(row[0]) if row[0] is not None else None
        ),
        "id_marca_pendiente": int(row[1]),
        "nombre_marca_pendiente": row[2],
    }


def comparar_bases_de_datos(*_args, **_kwargs):
    """Impide usar el cruce histórico que dependía del resumen por referencia."""

    raise RuntimeError(
        "comparar_bases_de_datos está retirado: use el cruce por variantes "
        "de procesamiento.tablas_auxiliares"
    )
