import pandas as pd
import logging
import re

from app.database.db import get_connection
from app.services.productos_service import crear_producto, ajustar_stock


# =========================================================
# LEER EXCEL
# =========================================================
def leer_excel(path_archivo):

    try:

        df = pd.read_excel(path_archivo)

        df = df.dropna(how="all")
        df = df.reset_index(drop=True)

        return df

    except Exception as e:
        logging.exception("Error leyendo Excel")
        raise Exception(f"No se pudo leer el Excel: {e}")


# =========================================================
# COLUMNAS
# =========================================================
def obtener_columnas(df):

    return list(df.columns)


# =========================================================
# LIMPIAR TEXTO
# =========================================================
def limpiar_texto(valor):

    if valor is None:
        return ""

    try:
        return str(valor).strip()
    except Exception:
        return ""


# =========================================================
# CONVERTIR NUMEROS (ULTRA FLEXIBLE)
# =========================================================
def convertir_numero(valor):

    if valor is None:
        return None

    try:

        if isinstance(valor, (int, float)):
            return float(valor)

        valor = str(valor).strip()

        if valor == "":
            return None

        valor = valor.replace("+", "")

        if "," in valor and "." in valor:
            valor = valor.replace(".", "").replace(",", ".")
        else:
            valor = valor.replace(",", ".")

        valor = re.sub(r"[^\d\.\-]", "", valor)

        return float(valor)

    except Exception:
        return None


# =========================================================
# MAPEAR EXCEL
# =========================================================
def mapear_excel(df, columnas):

    productos = []

    for i, row in df.iterrows():

        referencia = limpiar_texto(row.get(columnas.get("referencia")))
        nombre = limpiar_texto(row.get(columnas.get("nombre")))
        cantidad = convertir_numero(row.get(columnas.get("cantidad")))
        precio = convertir_numero(row.get(columnas.get("precio")))
        ean = limpiar_texto(row.get(columnas.get("ean")))

        # -------------------------------------------------
        # ignorar filas totalmente vacías
        # -------------------------------------------------
        if not referencia and not nombre:
            continue

        # -------------------------------------------------
        # limpiar cantidad
        # -------------------------------------------------
        if cantidad is None:
            cantidad = 0

        # ignorar productos sin cantidad
        if cantidad <= 0:
            continue

        # -------------------------------------------------
        # limpiar precio
        # -------------------------------------------------
        if precio is None:
            precio = 0

        productos.append(
            {
                "referencia": referencia,
                "nombre": nombre,
                "cantidad": cantidad,
                "precio": precio,
                "ean": ean,
                "fila_excel": i + 2,
            }
        )

    return productos


# =========================================================
# PREVIEW
# =========================================================
def generar_preview(productos, limite=20):

    return productos[:limite]


# =========================================================
# VALIDAR
# =========================================================
def validar_productos(productos):

    errores = []

    for p in productos:

        fila = p["fila_excel"]

        if not p["nombre"]:
            errores.append(f"Fila {fila}: nombre vacío")

        if p["cantidad"] < 0:
            errores.append(f"Fila {fila}: cantidad negativa")

        if p["precio"] < 0:
            errores.append(f"Fila {fila}: precio inválido")

    return errores


# =========================================================
# BUSCAR PRODUCTO EXISTENTE
# =========================================================
def buscar_producto(referencia, ean):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        if referencia:

            cursor.execute(
                """
                SELECT id
                FROM productos
                WHERE referencia = ? AND activo = 1
                """,
                (referencia,),
            )

            row = cursor.fetchone()

            if row:
                return row[0]

        if ean:

            cursor.execute(
                """
                SELECT id
                FROM productos
                WHERE ean = ? AND activo = 1
                """,
                (ean,),
            )

            row = cursor.fetchone()

            if row:
                return row[0]

        return None

    finally:
        conn.close()


# =========================================================
# CREAR PRODUCTO SI NO EXISTE
# =========================================================
def obtener_o_crear_producto(p):

    referencia = p["referencia"]
    nombre = p["nombre"]
    precio = p["precio"]
    ean = p["ean"]

    producto_id = buscar_producto(referencia, ean)

    if producto_id:
        return producto_id

    logging.info(f"Creando producto nuevo: {nombre}")

    producto_id = crear_producto(
        nombre=nombre,
        precio=precio,
        iva=21,
        referencia=referencia,
        stock_inicial=0,
        control_stock=1,
    )

    if ean:

        conn = get_connection()
        cursor = conn.cursor()

        try:

            cursor.execute(
                """
                UPDATE productos
                SET ean = ?
                WHERE id = ?
                """,
                (ean, producto_id),
            )

            conn.commit()

        finally:
            conn.close()

    return producto_id


# =========================================================
# IMPORTAR PRODUCTOS A FACTURA
# =========================================================
def importar_productos_factura(productos, factura_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        total = 0

        for p in productos:

            if p["cantidad"] <= 0:
                continue

            producto_id = obtener_o_crear_producto(p)

            cantidad = p["cantidad"]
            precio = p["precio"]

            total_linea = cantidad * precio

            cursor.execute(
                """
                INSERT INTO documento_compras_lineas
                (documento_compra_id, producto_id, descripcion, cantidad, precio, iva, total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    factura_id,
                    producto_id,
                    p["nombre"],
                    cantidad,
                    precio,
                    21,
                    total_linea,
                ),
            )

            ajustar_stock(
                producto_id,
                cantidad,
                tipo="ENTRADA",
                detalle="Importación Excel compra",
                cursor_externo=cursor,
            )

            total += total_linea

        cursor.execute(
            """
            SELECT SUM(total)
            FROM documento_compras_lineas
            WHERE documento_compra_id = ?
            """,
            (factura_id,),
        )

        total = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            UPDATE documentos_compras
            SET total = ?
            WHERE id = ?
            """,
            (total, factura_id),
        )

        conn.commit()

        return True

    except Exception:

        conn.rollback()
        logging.exception("Error importando Excel")

        raise

    finally:

        conn.close()
