from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from bd.bd import ejecutar_consulta
import pandas as pd
from io import BytesIO
import uvicorn
import logging
from decimal import Decimal
from typing import Optional
import math

# Configuración de logs en archivo
logging.basicConfig(
    filename="server.log",
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

app = FastAPI()

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/get_data")
async def get_data(
    tipo: str,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    ventas: str = "global",
    familia: Optional[str] = None,
    subfamilia: Optional[str] = None,
    proveedor: Optional[str] = None
):
    """ Devuelve datos en formato JSON desde la base de datos """
    try:
        logging.info(f"📡 Petición recibida: tipo={tipo}, fecha_desde={fecha_desde}, fecha_hasta={fecha_hasta}, familia={familia}, subfamilia={subfamilia}, proveedor={proveedor}")

        if tipo == "ventas":
            if not fecha_desde or not fecha_hasta:
                logging.error("Error: Faltan fechas en la consulta de ventas.")
                raise HTTPException(status_code=400, detail="Las fechas son obligatorias para este reporte.")
            
            datos = obtener_ventas(fecha_desde, fecha_hasta, ventas, familia, subfamilia, proveedor)

        elif tipo in ["compras", "vencimientos"]:
            if not fecha_desde or not fecha_hasta:
                logging.error("Error: Faltan fechas en la consulta de compras o vencimientos.")
                raise HTTPException(status_code=400, detail="Las fechas son obligatorias para este reporte.")
            datos = obtener_datos(tipo, fecha_desde, fecha_hasta)

        elif tipo == "stock":
            datos = obtener_stock_actual(familia, subfamilia, proveedor)

        else:
            logging.error(f"Error: Tipo de reporte no válido ({tipo}).")
            raise HTTPException(status_code=400, detail="Tipo de reporte no válido.")

        return JSONResponse(content=datos)
    
    except Exception as e:
        logging.exception("Error en get_data")  # Captura más detalles en los logs
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_filtros_stock")
async def get_filtros_stock(familia: Optional[str] = None, subfamilia: Optional[str] = None, proveedor: Optional[str] = None):
    """ Devuelve Familias, Subfamilias y Proveedores con descripciones """
    
    # Consulta para obtener Familias con Descripción
    query_familias = "SELECT DISTINCT Familia, Descripción FROM Familias"
    familias_result = ejecutar_consulta(query_familias)
    
    # Consulta para obtener SubFamilias (no tiene descripción en la BD)
    query_subfamilias = "SELECT DISTINCT SubFamilia FROM Artículos"
    subfamilias_result = ejecutar_consulta(query_subfamilias)

    # Consulta para obtener Proveedores con Nombre
    query_proveedores = "SELECT DISTINCT Proveedor, Nombre FROM Proveedores"
    proveedores_result = ejecutar_consulta(query_proveedores)

    # Procesar Familias con Descripción
    familias = sorted(set(row[0] for row in familias_result if row[0]))
    familia_descripciones = {row[0]: row[1] for row in familias_result if row[0] and row[1]}

    # Procesar SubFamilias (no hay descripción en la BD)
    subfamilias = sorted(set(row[0] for row in subfamilias_result if row[0]))

    # Procesar Proveedores con Nombre
    proveedores = sorted(set(row[0] for row in proveedores_result if row[0]))
    proveedor_nombres = {row[0]: row[1] for row in proveedores_result if row[0] and row[1]}

    return {
        "familias": familias,
        "familia_descripciones": familia_descripciones,
        "subfamilias": subfamilias,
        "proveedores": proveedores,
        "proveedor_nombres": proveedor_nombres
    }

@app.get("/descargar")
async def descargar_excel(
    tipo: str,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    ventas: str = "global",
    familia: Optional[str] = None,
    subfamilia: Optional[str] = None,
    proveedor: Optional[str] = None
):
    """ Devuelve el archivo Excel para su descarga """
    try:
        # Si es stock, ahora se pasan los filtros correctamente
        if tipo == "stock":
            datos = obtener_stock_actual(familia, subfamilia, proveedor)
        else:
            if not fecha_desde or not fecha_hasta:
                raise HTTPException(status_code=400, detail="Las fechas son obligatorias para este reporte.")
            datos = obtener_ventas(fecha_desde, fecha_hasta, ventas, familia, subfamilia, proveedor) if tipo == "ventas" else obtener_datos(tipo, fecha_desde, fecha_hasta)

        # Convertir datos a DataFrame
        df = pd.DataFrame(datos)

        # Generar archivo Excel
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)

        # Nombre del archivo según el tipo de reporte
        filename = f"{tipo}.xlsx"

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logging.exception("Error en descargar_excel")
        raise HTTPException(status_code=500, detail=str(e))

# Nueva función obtener_datos para manejar otros reportes
def obtener_datos(tipo, fecha_desde, fecha_hasta):
    """ Obtiene datos según el tipo de reporte (excepto ventas, que tiene su propia función). """
    logging.info(f"📥 Obtener datos para: {tipo}, desde {fecha_desde} hasta {fecha_hasta}")

    if tipo == "compras":
        return obtener_compras(fecha_desde, fecha_hasta)
    elif tipo == "vencimientos":
        return obtener_vencimientos(fecha_desde, fecha_hasta)
    elif tipo == "stock":
        return obtener_stock_actual()
    else:
        logging.error(f"Tipo de reporte inválido: {tipo}")
        raise HTTPException(status_code=400, detail="Tipo de reporte no válido.")

# Función para formatear números correctamente
def formatear_numero(valor):
    """ Formatea los números con separador de miles '.' y decimales ',' """
    if isinstance(valor, (int, float)):
        if math.isnan(valor) or math.isinf(valor):
            return "0,00"
        return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return valor

# Función para obtener ventas (global o individual)
def obtener_ventas(fecha_desde, fecha_hasta, ventas="global", familia=None, subfamilia=None, proveedor=None):
    try:
        query = """
        SELECT 
            fvl.[Artículo] AS refProducto, 
            a.[Descripción] AS nombreProducto, 
            fvl.Cantidad AS cantidad_vendida, 
            fvl.FechaLin AS fecha_venta,
            fvl.TotalE AS total_linea,  
            fvc.ImporteTotalE AS total_factura,  
            CASE 
                WHEN SUM(fvl.TotalE) OVER (PARTITION BY fvl.[Serie], fvl.[Codigo]) = 0 
                THEN 0  
                ELSE (fvl.TotalE / NULLIF(SUM(fvl.TotalE) OVER (PARTITION BY fvl.[Serie], fvl.[Codigo]), 0)) * fvc.ImporteTotalE
            END AS total_ajustado,  
            (fvl.Cantidad * a.PrecioUltCompraEu) AS costo_venta,
            fvl.Dcto AS descuento,
            fvl.Iva AS iva,
            fvl.Recargo AS recargo,
            fvl.PrecioE AS precioE,
            a.Familia AS familia,
            a.SubFamilia AS subfamilia,
            a.Proveedor AS proveedor
        FROM FacturasVentaLin fvl
        INNER JOIN Artículos a ON fvl.[Artículo] = a.[Artículo]
        INNER JOIN FacturasVentaCab fvc ON fvl.[Serie] = fvc.[Serie] AND fvl.[Codigo] = fvc.[Codigo]
        WHERE fvl.FechaLin BETWEEN CONVERT(DATE, ?) AND CONVERT(DATE, ?)
        """

        parametros = [fecha_desde, fecha_hasta]

        # Agregar filtros opcionales
        if familia and familia.strip():
            query += " AND a.Familia = ?"
            parametros.append(familia.strip())

        if subfamilia and subfamilia.strip():
            query += " AND a.SubFamilia = ?"
            parametros.append(subfamilia.strip())

        if proveedor and proveedor.strip():
            query += " AND a.Proveedor = ?"
            parametros.append(proveedor.strip())

        logging.info(f"Ejecutando consulta SQL desde {fecha_desde} hasta {fecha_hasta} con filtros: {parametros}")
        resultados = ejecutar_consulta(query, tuple(parametros))

        if not resultados:
            logging.warning("No hay datos para mostrar.")
            return []

        ventas_lista = []
        total_factura_acumulado = 0
        total_beneficio_sin_iva = 0
        total_beneficio_con_iva = 0

        for row in resultados:
            try:
                total_linea = round(float(row[4] or 0), 2)
                total_factura = round(float(row[5] or 0), 2)
                total_ajustado = round(float(row[6] or 0), 2)
                costo_venta = round(float(row[7] or 0), 2)
            except (ValueError, TypeError):
                logging.warning(f"❌ Error convirtiendo valores numéricos: {row}")
                continue  # Saltar fila si hay un error en los datos

            # Evitar división por cero
            iva = float(row[9] or 0)  
            beneficio_sin_iva = 0.00
            if total_ajustado > 0 and (1 + iva / 100) != 0:
                beneficio_sin_iva = round(total_ajustado / (1 + iva / 100) - costo_venta, 2)

            beneficio_con_iva = total_ajustado - costo_venta

            # Evitar error al calcular porcentaje
            beneficio_sin_iva_pct = 0.00
            if total_ajustado > 0:
                beneficio_sin_iva_pct = round((beneficio_sin_iva / total_ajustado) * 100, 2)

            fila = {
                "refProducto": row[0] or "",
                "nombreProducto": row[1] or "Sin nombre",
                "cantidad_vendida": int(row[2]) if row[2] else 0,
                "fecha_venta": row[3].strftime("%d-%m-%Y") if row[3] else "N/A",
                "total_linea": formatear_numero(total_linea),
                "total_factura": formatear_numero(total_factura),
                "total_ajustado": formatear_numero(total_ajustado),
                "costo_venta": formatear_numero(costo_venta),
                "beneficio_sin_iva": formatear_numero(beneficio_sin_iva),
                "beneficio_sin_iva_%": formatear_numero(beneficio_sin_iva_pct),
                "beneficio_con_iva": formatear_numero(beneficio_con_iva),
                "familia": row[12] or "",
                "subfamilia": row[13] or "",
                "proveedor": row[14] or ""
            }

            ventas_lista.append(fila)

            # Acumular totales
            total_factura_acumulado += total_ajustado
            total_beneficio_sin_iva += beneficio_sin_iva
            total_beneficio_con_iva += beneficio_con_iva

        # Calcular porcentaje de beneficio total
        total_beneficio_sin_iva_pct = round((total_beneficio_sin_iva / total_factura_acumulado) * 100, 2) if total_factura_acumulado > 0 else 0.00

        # Agregar stock actual
        stock_data = obtener_stock_actual() or []
        stock_dict = {s.get("refProducto", ""): s.get("stock_actual", 0) for s in stock_data}

        for fila in ventas_lista:
            fila["stock_actual"] = stock_dict.get(fila["refProducto"], 0)

        # Agregar fila de totales
        total_fila = {
            "refProducto": "TOTAL",
            "nombreProducto": "",
            "cantidad_vendida": sum(int(item["cantidad_vendida"]) for item in ventas_lista),
            "fecha_venta": "",
            "total_linea": "",
            "total_factura": "",
            "total_ajustado": formatear_numero(total_factura_acumulado),
            "costo_venta": formatear_numero(sum(float(item["costo_venta"].replace(".", "").replace(",", ".")) for item in ventas_lista)),
            "beneficio_sin_iva": formatear_numero(total_beneficio_sin_iva),
            "beneficio_sin_iva_%": formatear_numero(total_beneficio_sin_iva_pct),
            "beneficio_con_iva": formatear_numero(total_beneficio_con_iva),
            "familia": "",
            "subfamilia": "",
            "proveedor": "",
            "stock_actual": ""
        }
        ventas_lista.append(total_fila)

        return ventas_lista

    except Exception as e:
        logging.exception("❌ Error en obtener_ventas")
        raise HTTPException(status_code=500, detail=str(e))

# Función para agrupar ventas globales
def agrupar_ventas(ventas_lista, total_beneficio_sin_iva_pct):
    import pandas as pd

    df = pd.DataFrame(ventas_lista)

    # Verificar que el DataFrame no esté vacío antes de agrupar
    if df.empty:
        return []

    # Convertir columnas a float antes de agrupar
    columnas_a_convertir = ["total_ajustado", "costo_venta", "beneficio_sin_iva", "beneficio_con_iva"]
    for col in columnas_a_convertir:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)

    # 🔹 Agrupar por refProducto, nombreProducto, Familia, SubFamilia y Proveedor
    df_grouped = df.groupby(["refProducto", "nombreProducto", "familia", "subfamilia", "proveedor"]).agg({
        "cantidad_vendida": "sum",
        "fecha_venta": "max",
        "total_ajustado": "sum",
        "costo_venta": "sum",
        "beneficio_sin_iva": "sum",
        "beneficio_con_iva": "sum",
    }).reset_index()

    # Calcular el porcentaje de beneficio sin IVA
    df_grouped["beneficio_sin_iva_%"] = df_grouped.apply(
        lambda row: round((row["beneficio_sin_iva"] / row["total_ajustado"]) * 100, 2) if row["total_ajustado"] > 0 else 0.00,
        axis=1
    )

    # Convertir fechas al formato "DD-MM-YYYY"
    df_grouped["fecha_venta"] = pd.to_datetime(df_grouped["fecha_venta"], errors="coerce").dt.strftime("%d-%m-%Y")

    # Agregar stock actual
    stock_data = obtener_stock_actual()
    stock_dict = {s["refProducto"]: s["stock_actual"] for s in stock_data}
    df_grouped["stock_actual"] = df_grouped["refProducto"].map(stock_dict).fillna(0).astype(int)

    # Formatear números con miles separados por puntos y decimales con comas
    for col in ["total_ajustado", "costo_venta", "beneficio_sin_iva", "beneficio_con_iva", "beneficio_sin_iva_%"]:
        df_grouped[col] = df_grouped[col].apply(lambda x: f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."))

    # 🔹 Agregar fila de totales
    total_fila = {
        "refProducto": "TOTAL",
        "nombreProducto": "",
        "familia": "",
        "subfamilia": "",
        "proveedor": "",
        "cantidad_vendida": int(df_grouped["cantidad_vendida"].sum()),
        "fecha_venta": "",
        "total_ajustado": f"{df_grouped['total_ajustado'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float).sum():,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
        "costo_venta": f"{df_grouped['costo_venta'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float).sum():,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
        "beneficio_sin_iva": f"{df_grouped['beneficio_sin_iva'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float).sum():,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
        "beneficio_con_iva": f"{df_grouped['beneficio_con_iva'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float).sum():,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
        "beneficio_sin_iva_%": f"{total_beneficio_sin_iva_pct:,.2f}".replace(".", ","),
        "stock_actual": ""
    }

    resultado = df_grouped.to_dict(orient="records")
    resultado.append(total_fila)

    return resultado

# Función para obtener compras con formato corregido
def obtener_compras(fecha_desde, fecha_hasta):
    try:
        query = """
        SELECT 
            fcl.[Almacén] AS almacen,
            fcl.[Artículo] AS refProducto, 
            fcl.[Serie] AS serie,
            fcl.[Codigo] AS codigo,
            fcl.[Descripción] AS descripcion,
            fcl.[Cantidad] AS cantidad_comprada,
            fcl.[TotalE] AS total_linea,  
            fcc.ImportePagadoE AS total_factura,  
            CASE 
                WHEN SUM(fcl.TotalE) OVER (PARTITION BY fcl.[Serie], fcl.[Codigo]) = 0 
                THEN 0  
                ELSE (fcl.TotalE / NULLIF(SUM(fcl.TotalE) OVER (PARTITION BY fcl.[Serie], fcl.[Codigo]), 0)) * fcc.ImportePagadoE
            END AS total_ajustado,  
            fcl.[Precio] AS precio,
            fcl.[Dcto] AS descuento,
            fcl.[Iva] AS iva,
            fcl.[Recargo] AS recargo,
            fcl.[PrecioE] AS precioE,
            fcl.[FechaLin] AS fecha_compra
        FROM FacturasCompraLin fcl
        JOIN FacturasCompraCab fcc ON fcl.[Serie] = fcc.[Serie] AND fcl.[Codigo] = fcc.[Codigo]
        WHERE fcl.FechaLin BETWEEN CONVERT(DATE, ?) AND CONVERT(DATE, ?)
        AND fcc.Pagado = 'S'

        UNION

        SELECT 
            fcc.[Almacén] AS almacen,
            'Gasto' AS refProducto,
            fcc.[Serie] AS serie,
            fcc.[Codigo] AS codigo,
            'Gasto' AS descripcion,
            '1' AS cantidad_comprada,
            fcc.[ImporteTotalE] AS total_linea,  
            fcc.ImportePagadoE AS total_factura,  
            fcc.ImportePagadoE AS total_ajustado,  
            fcc.[ImporteTotalE] AS precio,
            '0' AS descuento,
            fcc.Iva1 AS iva,
            '0' AS recargo,
            '0' AS precioE,
            fcc.[Fecha] AS fecha_compra
        FROM FacturasCompraCab fcc
        WHERE fcc.Fecha BETWEEN CONVERT(DATE, ?) AND CONVERT(DATE, ?)
        AND fcc.Serie = 'H'
        AND fcc.Pagado = 'S'
        """

        logging.info(f"Ejecutando consulta SQL COMPRAS desde {fecha_desde} hasta {fecha_hasta}")
        resultados = ejecutar_consulta(query, (fecha_desde, fecha_hasta, fecha_desde, fecha_hasta))

        if not resultados:
            logging.warning("No hay compras registradas en este período.")
            return []

        logging.info(f"Compras obtenidas: {len(resultados)} filas")

        compras_lista = []
        total_factura_acumulado = 0

        for row in resultados:
            total_linea = round(float(row[6]), 2) if row[6] is not None else 0.00
            total_factura = round(float(row[7]), 2) if row[7] is not None else 0.00
            total_ajustado = round(float(row[8]), 2) if row[8] is not None else 0.00
            precio = round(float(row[9]), 2) if row[9] is not None else 0.00
            descuento = round(float(row[10]), 2) if row[10] is not None else 0.00
            iva = round(float(row[11]), 2) if row[11] is not None else 0.00
            recargo = round(float(row[12]), 2) if row[12] is not None else 0.00
            precioE = round(float(row[13]), 2) if row[13] is not None else 0.00

            fila = {
                "almacen": row[0] if row[0] is not None else 0,
                "refProducto": row[1] if row[1] is not None else "",
                "serie": row[2] if row[2] is not None else "",
                "codigo": row[3] if row[3] is not None else "",
                "descripcion": row[4] if row[4] is not None else "Sin descripción",
                "cantidad_comprada": int(row[5]) if row[5] is not None else 0,
                "total_linea": "{:,.2f}".format(total_linea).replace(",", "X").replace(".", ",").replace("X", "."),
                "total_factura": "{:,.2f}".format(total_factura).replace(",", "X").replace(".", ",").replace("X", "."),
                "total_ajustado": "{:,.2f}".format(total_ajustado).replace(",", "X").replace(".", ",").replace("X", "."),
                "precio": "{:,.2f}".format(precio).replace(",", "X").replace(".", ",").replace("X", "."),
                "descuento": "{:,.2f}".format(descuento).replace(",", "X").replace(".", ",").replace("X", "."),
                "iva": "{:,.2f}".format(iva).replace(",", "X").replace(".", ",").replace("X", "."),
                "recargo": "{:,.2f}".format(recargo).replace(",", "X").replace(".", ",").replace("X", "."),
                "precioE": "{:,.2f}".format(precioE).replace(",", "X").replace(".", ",").replace("X", "."),
                "fecha_compra": row[14].strftime("%d-%m-%Y") if row[14] else "N/A"
            }

            compras_lista.append(fila)

            # Acumular total ajustado
            total_factura_acumulado += total_ajustado

        # Agregar fila de totales
        fila_total = {
            "almacen": "TOTAL",
            "refProducto": "",
            "serie": "",
            "codigo": "",
            "descripcion": "",
            "cantidad_comprada": sum(int(item["cantidad_comprada"]) for item in compras_lista),
            "total_linea": "",
            "total_factura": "",
            "total_ajustado": "{:,.2f}".format(total_factura_acumulado).replace(",", "X").replace(".", ",").replace("X", "."),
            "precio": "",
            "descuento": "",
            "iva": "",
            "recargo": "",
            "precioE": "",
            "fecha_compra": ""
        }

        compras_lista.append(fila_total)
        return compras_lista

    except Exception as e:
        logging.exception("Error en obtener_compras")
        raise HTTPException(status_code=500, detail=str(e))

# Función para obtener vencimientos con formato corregido
def obtener_vencimientos(fecha_desde, fecha_hasta):
    try:
        query = """
        SELECT 
            CONCAT(ec.SerieDocumento, '-', ec.CodigoDocumento) AS refFactura,
            fcc.Factura AS numFacturaProveedor,
            ec.Fecha AS fechaFactura,
            ec.FechaVencimiento AS fechaVencimiento,
            fpv.FormaPago AS refFormaPago,
            fpv.[Días] AS diasGiroPago,
            fpv.Vencimiento AS numeroVencimientos,
            ec.ImporteTotalE AS totalFactura,
            ec.ImportePagadoE AS totalPagado,
            p.Proveedor AS refProveedor,
            p.Nombre AS nombreProveedor,
            b.Banco AS refBanco,
            b.Nombre AS nombreBanco
        FROM 
            EfectosCab ec 
            INNER JOIN FormasPagoVto fpv ON ec.FormaPago = fpv.FormaPago
            INNER JOIN Bancos b ON ec.Banco = b.Banco
            INNER JOIN Proveedores p ON ec.CliPro = p.Proveedor
            INNER JOIN FacturasCompraCab fcc ON (fcc.Serie = ec.SerieDocumento AND fcc.Codigo = ec.Codigo)
        WHERE 
            ec.TipoDocumento = 'FC'
            AND ec.FechaVencimiento BETWEEN CONVERT(DATE, ?) AND CONVERT(DATE, ?)
        """

        logging.info(f"Ejecutando consulta SQL VENCIMIENTOS desde {fecha_desde} hasta {fecha_hasta}")
        resultados = ejecutar_consulta(query, (fecha_desde, fecha_hasta))

        if not resultados:
            logging.warning("No hay vencimientos registrados en este período.")
            return []

        logging.info(f"Vencimientos obtenidos: {len(resultados)} filas")

        vencimientos_lista = []
        total_factura = 0
        total_pagado = 0

        for row in resultados:
            try:
                total_factura_val = float(row[7]) if row[7] is not None else 0.0
                total_pagado_val = float(row[8]) if row[8] is not None else 0.0

                # Calcular si está pagado (Si la diferencia es 0 se considera pagado)
                esta_pagado = "Sí" if abs(total_factura_val - total_pagado_val) < 0.01 else "No"

                fila = {
                    "refFactura": row[0] or "",
                    "numFacturaProveedor": row[1] or "",
                    "fechaFactura": row[2].strftime("%d-%m-%Y") if row[2] else "N/A",
                    "fechaVencimiento": row[3].strftime("%d-%m-%Y") if row[3] else "N/A",
                    "refFormaPago": row[4] or "",
                    "diasGiroPago": int(row[5]) if row[5] is not None else 0,
                    "numeroVencimientos": int(row[6]) if row[6] is not None else 0,
                    "totalFactura": "{:,.2f}".format(total_factura_val).replace(",", "X").replace(".", ",").replace("X", "."),
                    "totalPagado": "{:,.2f}".format(total_pagado_val).replace(",", "X").replace(".", ",").replace("X", "."),
                    "estaPagado": esta_pagado,
                    "refProveedor": row[9] or "",
                    "nombreProveedor": row[10] or "",
                    "refBanco": row[11] or "",
                    "nombreBanco": row[12] or ""
                }

                vencimientos_lista.append(fila)

                # Acumular totales
                total_factura += total_factura_val
                total_pagado += total_pagado_val

            except Exception as e:
                logging.error(f"Error al procesar fila: {repr(row)} - {str(e)}")

        # Agregar fila de totales
        fila_total = {
            "refFactura": "TOTAL",
            "numFacturaProveedor": "",
            "fechaFactura": "",
            "fechaVencimiento": "",
            "refFormaPago": "",
            "diasGiroPago": "",
            "numeroVencimientos": "",
            "totalFactura": "{:,.2f}".format(total_factura).replace(",", "X").replace(".", ",").replace("X", "."),
            "totalPagado": "{:,.2f}".format(total_pagado).replace(",", "X").replace(".", ",").replace("X", "."),
            "estaPagado": "",
            "refProveedor": "",
            "nombreProveedor": "",
            "refBanco": "",
            "nombreBanco": ""
        }

        vencimientos_lista.append(fila_total)
        return vencimientos_lista

    except Exception as e:
        logging.exception("Error en obtener_vencimientos")
        raise HTTPException(status_code=500, detail=str(e))

# Función para obtener stock actual con filtros
def obtener_stock_actual(familia: Optional[str] = None, subfamilia: Optional[str] = None, proveedor: Optional[str] = None):
    """
    Obtiene el stock actual de los productos en el Almacén 1 con opción de filtrar por Familia, SubFamilia y Proveedor.
    """
    query = """
    SELECT 
        s.[Artículo] AS refProducto, 
        a.[Descripción] AS nombreProducto, 
        s.StockUd1 AS stock_actual,
        a.PrecioUltCompraEu AS precio_compra,
        a.PVPGralSinIVAEu AS pvp_sin_iva,
        a.Familia AS familia,
        a.SubFamilia AS subfamilia,
        a.Proveedor AS proveedor
    FROM Stocks s
    INNER JOIN Artículos a ON s.[Artículo] = a.[Artículo]
    """

    filtros = []
    parametros = []

    if familia:
        filtros.append("a.Familia = ?")
        parametros.append(familia)

    if subfamilia:
        filtros.append("a.SubFamilia = ?")
        parametros.append(subfamilia)

    if proveedor:
        filtros.append("a.Proveedor = ?")
        parametros.append(proveedor)

    # Si hay filtros, los agregamos a la consulta SQL
    if filtros:
        query += " AND " + " AND ".join(filtros)

    logging.info(f"Ejecutando consulta STOCK con filtros: {parametros}")

    resultados = ejecutar_consulta(query, tuple(parametros))

    if not resultados:
        return []

    stock_lista = [
        {
            "refProducto": row[0],
            "nombreProducto": row[1],
            "stock_actual": int(row[2]) if row[2] is not None else 0,
            "precio_compra": f"{round(float(row[3]), 2):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if row[3] is not None else "0,00",
            "pvp_sin_iva": f"{round(float(row[4]), 2):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if row[4] is not None else "0,00",
            "familia": row[5] if row[5] else "",
            "subfamilia": row[6] if row[6] else "",
            "proveedor": row[7] if row[7] else ""
        }
        for row in resultados if (row[2] is not None and row[2] > 0)
    ]

    # Calcular los totales
    total_stock = sum(item["stock_actual"] for item in stock_lista)
    total_precio_compra = sum(float(item["precio_compra"].replace(".", "").replace(",", ".")) for item in stock_lista)
    total_pvp_sin_iva = sum(float(item["pvp_sin_iva"].replace(".", "").replace(",", ".")) for item in stock_lista)

    # Agregar la fila con los totales en el formato correcto
    stock_lista.append({
        "refProducto": "TOTAL",
        "nombreProducto": "",
        "stock_actual": total_stock,
        "precio_compra": f"{total_precio_compra:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
        "pvp_sin_iva": f"{total_pvp_sin_iva:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
        "familia": "",
        "subfamilia": "",
        "proveedor": ""
    })

    return stock_lista

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5002, log_level="debug")