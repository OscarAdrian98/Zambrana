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
            datos = obtener_ventas(fecha_desde, fecha_hasta, ventas)

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
            datos = obtener_ventas(fecha_desde, fecha_hasta, ventas) if tipo == "ventas" else obtener_datos(tipo, fecha_desde, fecha_hasta)

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

# Función para obtener ventas (global o individual)
def obtener_ventas(fecha_desde, fecha_hasta, ventas="global"):
    try:
        query = """
        SELECT 
            fvl.[Artículo] AS refProducto, 
            a.[Descripción] AS nombreProducto, 
            fvl.Cantidad AS cantidad_vendida, 
            fvl.FechaLin AS fecha_venta,
            fvl.TotalE AS ingreso_venta,
            fvl.TotalE / (1 + fvl.Iva / 100) AS ingreso_sin_iva,
            (fvl.Cantidad * a.PrecioUltCompraEu) AS costo_venta,
            (fvl.TotalE / (1 + fvl.Iva / 100)) - (fvl.Cantidad * a.PrecioUltCompraEu) AS beneficio_sin_iva,
            fvl.TotalE - (fvl.Cantidad * a.PrecioUltCompraEu) AS beneficio_con_iva,
            fvl.Dcto AS descuento,
            fvl.Iva AS iva,
            fvl.Recargo AS recargo,
            fvl.PrecioE AS precioE
        FROM FacturasVentaLin fvl
        INNER JOIN Artículos a ON fvl.[Artículo] = a.[Artículo]
        WHERE fvl.FechaLin BETWEEN CONVERT(DATE, ?) AND CONVERT(DATE, ?)
        AND fvl.[Almacén] = 1
        """

        logging.info(f"Ejecutando consulta SQL desde {fecha_desde} hasta {fecha_hasta}")
        resultados = ejecutar_consulta(query, (fecha_desde, fecha_hasta))

        if not resultados:
            logging.warning("No hay datos para mostrar.")
            return []

        ventas_lista = []
        total_ingreso_venta = 0
        total_beneficio_sin_iva = 0
        total_beneficio_con_iva = 0

        for row in resultados:
            ingreso_venta = round(float(row[4]), 2) if row[4] is not None else 0.00
            beneficio_sin_iva = round(float(row[7]), 2) if row[7] is not None else 0.00
            beneficio_con_iva = round(float(row[8]), 2) if row[8] is not None else 0.00
            beneficio_sin_iva_pct = round((beneficio_sin_iva / ingreso_venta) * 100, 2) if ingreso_venta > 0 else 0.00

            fila = {
                "refProducto": row[0] if row[0] else "",
                "nombreProducto": row[1] if row[1] else "Sin nombre",
                "cantidad_vendida": int(row[2]) if row[2] else 0,
                "fecha_venta": row[3].strftime("%d-%m-%Y") if row[3] else "N/A",
                "ingreso_venta": f"{ingreso_venta:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
                "costo_venta": f"{round(float(row[6]), 2):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if row[6] else "0,00",
                "beneficio_sin_iva": f"{beneficio_sin_iva:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
                "beneficio_sin_iva_%": f"{beneficio_sin_iva_pct:,.2f}".replace(".", ","),
                "beneficio_con_iva": f"{beneficio_con_iva:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
                "descuento": f"{round(float(row[9]), 2):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if row[9] else "0,00",
                "iva": f"{round(float(row[10]), 2):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if row[10] else "0,00",
                "recargo": f"{round(float(row[11]), 2):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if row[11] else "0,00",
                "precioE": f"{round(float(row[12]), 2):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if row[12] else "0,00",
            }

            ventas_lista.append(fila)

            # Acumular totales
            total_ingreso_venta += ingreso_venta
            total_beneficio_sin_iva += beneficio_sin_iva
            total_beneficio_con_iva += beneficio_con_iva

        # Calcular el porcentaje total correctamente
        total_beneficio_sin_iva_pct = round((total_beneficio_sin_iva / total_ingreso_venta) * 100, 2) if total_ingreso_venta > 0 else 0.00

        # Agregar stock actual
        stock_data = obtener_stock_actual()
        stock_dict = {s["refProducto"]: s["stock_actual"] for s in stock_data}
        for fila in ventas_lista:
            fila["stock_actual"] = stock_dict.get(fila["refProducto"], 0)

        if ventas == "global":
            return agrupar_ventas(ventas_lista, total_beneficio_sin_iva_pct)
        else:
            total_fila = {
                "refProducto": "TOTAL",
                "nombreProducto": "",
                "cantidad_vendida": sum(int(item["cantidad_vendida"]) for item in ventas_lista),
                "fecha_venta": "",
                "ingreso_venta": f"{total_ingreso_venta:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
                "costo_venta": f"{sum(float(item['costo_venta'].replace('.', '').replace(',', '.')) for item in ventas_lista):,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
                "beneficio_sin_iva": f"{total_beneficio_sin_iva:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
                "beneficio_sin_iva_%": f"{total_beneficio_sin_iva_pct:,.2f}".replace(".", ","),
                "beneficio_con_iva": f"{total_beneficio_con_iva:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
                "descuento": "",
                "iva": "",
                "recargo": "",
                "precioE": "",
                "stock_actual": "",
            }
            ventas_lista.append(total_fila)
            return ventas_lista

    except Exception as e:
        logging.exception("Error en obtener_ventas")
        raise HTTPException(status_code=500, detail=str(e))

# Función para agrupar ventas globales
def agrupar_ventas(ventas_lista, total_beneficio_sin_iva_pct):
    import pandas as pd

    df = pd.DataFrame(ventas_lista)

    # Verificar que el DataFrame no esté vacío antes de agrupar
    if df.empty:
        return []

    # Convertir columnas a float antes de agrupar
    columnas_a_convertir = ["ingreso_venta", "costo_venta", "beneficio_sin_iva", "beneficio_con_iva"]
    for col in columnas_a_convertir:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)

    # Agrupar por refProducto y nombreProducto
    df_grouped = df.groupby(["refProducto", "nombreProducto"]).agg({
        "cantidad_vendida": "sum",
        "fecha_venta": "max",
        "ingreso_venta": "sum",
        "costo_venta": "sum",
        "beneficio_sin_iva": "sum",
        "beneficio_con_iva": "sum",
    }).reset_index()

    # Calcular el porcentaje de beneficio sin IVA
    df_grouped["beneficio_sin_iva_%"] = df_grouped.apply(
        lambda row: round((row["beneficio_sin_iva"] / row["ingreso_venta"]) * 100, 2) if row["ingreso_venta"] > 0 else 0.00,
        axis=1
    )

    # Convertir fechas al formato "DD-MM-YYYY"
    df_grouped["fecha_venta"] = pd.to_datetime(df_grouped["fecha_venta"], errors="coerce").dt.strftime("%d-%m-%Y")

    # Agregar stock actual
    stock_data = obtener_stock_actual()
    stock_dict = {s["refProducto"]: s["stock_actual"] for s in stock_data}
    df_grouped["stock_actual"] = df_grouped["refProducto"].map(stock_dict).fillna(0).astype(int)

    # Formatear números con miles separados por puntos y decimales con comas
    for col in ["ingreso_venta", "costo_venta", "beneficio_sin_iva", "beneficio_con_iva", "beneficio_sin_iva_%"]:
        df_grouped[col] = df_grouped[col].apply(lambda x: f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."))

    # Agregar fila de totales
    total_fila = {
        "refProducto": "TOTAL",
        "nombreProducto": "",
        "cantidad_vendida": int(df_grouped["cantidad_vendida"].sum()),
        "fecha_venta": "",
        "ingreso_venta": f"{df_grouped['ingreso_venta'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float).sum():,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
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
            fcl.[Precio] AS precio,
            fcl.[Dcto] AS descuento,
            fcl.[Iva] AS iva,
            fcl.[Recargo] AS recargo,
            fcl.[Total] AS total,
            fcl.[PrecioE] AS precioE,
            fcl.[TotalE] AS totalE,
            fcl.[FechaLin] AS fecha_compra
        FROM FacturasCompraLin fcl
        WHERE fcl.FechaLin BETWEEN CONVERT(DATE, ?) AND CONVERT(DATE, ?)
        AND fcl.[Almacén] = 1
        """

        logging.info(f"Ejecutando consulta SQL COMPRAS desde {fecha_desde} hasta {fecha_hasta}")
        resultados = ejecutar_consulta(query, (fecha_desde, fecha_hasta))

        if not resultados:
            logging.warning(" No hay compras registradas en este período.")
            return []

        logging.info(f"Compras obtenidas: {len(resultados)} filas")

        compras_lista = []
        total_cantidad_comprada = 0
        total_precio = 0
        total_descuento = 0
        total_iva = 0
        total_recargo = 0
        total_total = 0
        total_precioE = 0
        total_totalE = 0

        for row in resultados:
            try:
                logging.info(f"Procesando fila: {repr(row)}")

                # Convertir valores Decimal a float y manejar NoneType
                precio = float(row[6]) if isinstance(row[6], Decimal) else 0.0
                descuento = float(row[7]) if isinstance(row[7], Decimal) else 0.0
                iva = float(row[8]) if isinstance(row[8], Decimal) else 0.0
                recargo = float(row[9]) if isinstance(row[9], Decimal) else 0.0
                total = float(row[10]) if isinstance(row[10], Decimal) else 0.0
                precioE = float(row[11]) if isinstance(row[11], Decimal) else 0.0
                totalE = float(row[12]) if isinstance(row[12], Decimal) else 0.0

                fila = {
                    "almacen": row[0] if row[0] is not None else 0,
                    "refProducto": row[1] if row[1] is not None else "",
                    "serie": row[2] if row[2] is not None else "",
                    "codigo": row[3] if row[3] is not None else "",
                    "descripcion": row[4] if row[4] is not None else "Sin descripción",
                    "cantidad_comprada": int(row[5]) if row[5] is not None else 0,
                    "precio": "{:,.2f}".format(precio).replace(",", "X").replace(".", ",").replace("X", "."),
                    "descuento": "{:,.2f}".format(descuento).replace(",", "X").replace(".", ",").replace("X", "."),
                    "iva": "{:,.2f}".format(iva).replace(",", "X").replace(".", ",").replace("X", "."),
                    "recargo": "{:,.2f}".format(recargo).replace(",", "X").replace(".", ",").replace("X", "."),
                    "total": "{:,.2f}".format(total).replace(",", "X").replace(".", ",").replace("X", "."),
                    "precioE": "{:,.2f}".format(precioE).replace(",", "X").replace(".", ",").replace("X", "."),
                    "totalE": "{:,.2f}".format(totalE).replace(",", "X").replace(".", ",").replace("X", "."),
                    "fecha_compra": row[13].strftime("%d-%m-%Y") if row[13] else "N/A"
                }
                
                compras_lista.append(fila)

                # Acumular totales
                total_cantidad_comprada += fila["cantidad_comprada"]
                total_precio += precio
                total_descuento += descuento
                total_iva += iva
                total_recargo += recargo
                total_total += total
                total_precioE += precioE
                total_totalE += totalE

            except Exception as e:
                logging.error(f"Error al procesar fila de compras: {repr(row)} - {str(e)}")

        # Agregar fila de totales con formato correcto
        fila_total = {
            "almacen": "TOTAL",
            "refProducto": "",
            "serie": "",
            "codigo": "",
            "descripcion": "",
            "cantidad_comprada": total_cantidad_comprada,
            "precio": "{:,.2f}".format(total_precio).replace(",", "X").replace(".", ",").replace("X", "."),
            "descuento": "{:,.2f}".format(total_descuento).replace(",", "X").replace(".", ",").replace("X", "."),
            "iva": "{:,.2f}".format(total_iva).replace(",", "X").replace(".", ",").replace("X", "."),
            "recargo": "{:,.2f}".format(total_recargo).replace(",", "X").replace(".", ",").replace("X", "."),
            "total": "{:,.2f}".format(total_total).replace(",", "X").replace(".", ",").replace("X", "."),
            "precioE": "{:,.2f}".format(total_precioE).replace(",", "X").replace(".", ",").replace("X", "."),
            "totalE": "{:,.2f}".format(total_totalE).replace(",", "X").replace(".", ",").replace("X", "."),
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
    WHERE s.[Almacén] = 1
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
