from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pyspark.sql import SparkSession
import pandas as pd
import numpy as np
import uvicorn
import logging
import requests
import atexit

# Configuración de logs
logging.basicConfig(
    filename="analisis.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

# Inicializar FastAPI
app = FastAPI()

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Iniciar PySpark con manejo de errores
try:
    spark = SparkSession.builder \
        .appName("AnalisisVentas") \
        .config("spark.driver.memory", "2g") \
        .config("spark.executor.memory", "2g") \
        .getOrCreate()
    logging.info("🚀 PySpark inicializado correctamente")
except Exception as e:
    logging.error(f"❌ Error al iniciar PySpark: {e}")
    raise RuntimeError("Error al iniciar Spark")

# Cerrar sesión de Spark al finalizar
def cerrar_spark():
    if spark and spark._jsc:
        logging.info("🛑 Cerrando sesión Spark")
        spark.stop()
atexit.register(cerrar_spark)

@app.get("/analisis_ventas")
async def analisis_ventas(fecha_desde: str = Query(...), fecha_hasta: str = Query(...)):
    """ Analiza las ventas y devuelve datos agregados para gráficos, incluyendo el stock actual """
    try:
        logging.info("📡 Solicitando datos de ventas para análisis")

        # ✅ 1. Obtener datos de ventas
        try:
            response = requests.get(f"http://192.168.1.201:5002/get_data?tipo=ventas&fecha_desde={fecha_desde}&fecha_hasta={fecha_hasta}&ventas=global")
            response.raise_for_status()
            ventas_data = response.json()
        except (requests.RequestException, ValueError) as e:
            logging.error(f"❌ Error al obtener ventas: {e}")
            raise HTTPException(status_code=500, detail="Error al obtener datos de ventas")

        if not ventas_data:
            logging.warning("⚠️ No hay datos de ventas disponibles para analizar.")
            return {
                "fechas": [], "ventas": [], "total_ventas": 0, "ticket_promedio": 0,
                "top_productos": [], "beneficio_sin_iva_total": 0, "beneficio_con_iva_total": 0
            }

        df_ventas = pd.DataFrame(ventas_data)

        required_columns = ["refProducto", "total_ajustado", "beneficio_sin_iva", "beneficio_con_iva", "cantidad_vendida"]
        for col in required_columns:
            if col not in df_ventas.columns:
                logging.error(f"❌ Falta la columna {col} en ventas_data")
                raise HTTPException(status_code=500, detail=f"Columna {col} no encontrada en los datos de ventas.")

        # ✅ 2. Extraer la fila "TOTAL"
        total_ventas = 0
        beneficio_sin_iva_total = 0
        beneficio_con_iva_total = 0

        if "TOTAL" in df_ventas["refProducto"].values:
            total_fila = df_ventas[df_ventas["refProducto"] == "TOTAL"].iloc[0]
            total_ventas = float(str(total_fila["total_ajustado"]).replace(".", "").replace(",", "."))
            beneficio_sin_iva_total = float(str(total_fila["beneficio_sin_iva"]).replace(".", "").replace(",", "."))
            beneficio_con_iva_total = float(str(total_fila["beneficio_con_iva"]).replace(".", "").replace(",", "."))

        # ✅ 3. Filtrar ventas excluyendo la fila "TOTAL"
        df_ventas = df_ventas[df_ventas["refProducto"] != "TOTAL"]

        # ✅ 4. Convertir valores numéricos
        def limpiar_numeros(valor):
            return valor.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)

        df_ventas["total_ajustado"] = limpiar_numeros(df_ventas["total_ajustado"])
        df_ventas["beneficio_sin_iva"] = limpiar_numeros(df_ventas["beneficio_sin_iva"])
        df_ventas["beneficio_con_iva"] = limpiar_numeros(df_ventas["beneficio_con_iva"])
        df_ventas["cantidad_vendida"] = df_ventas["cantidad_vendida"].astype(int)

        # ✅ 5. Agrupar ventas por fecha
        ventas_agrupadas = df_ventas.groupby("fecha_venta").agg(
            ventas_totales=("cantidad_vendida", "sum"),
            total_ventas=("total_ajustado", "sum")
        ).reset_index()

        # ✅ 6. Calcular ticket promedio
        total_cantidad_vendida = ventas_agrupadas["ventas_totales"].sum() if not ventas_agrupadas.empty else 0
        ticket_promedio = round(total_ventas / total_cantidad_vendida, 2) if total_cantidad_vendida > 0 else 0

        # ✅ 7. Obtener top productos
        referencias_excluir = ["PW", "MOTHVA", "PC3", "RE", "SC", "PAYPAL"]
        nombres_excluir = ["PORTES", "MANO OBRA", "GASTOS DE REEMBOLSO", "RECARGO", "Recargo Pago Por Paypal"]

        df_ventas["nombreProducto_clean"] = df_ventas["nombreProducto"].str.upper().str.strip()
        df_ventas["refProducto_clean"] = df_ventas["refProducto"].str.upper().str.strip()

        df_top_productos = df_ventas[
            ~df_ventas["nombreProducto_clean"].isin(nombres_excluir) & 
            ~df_ventas["refProducto_clean"].isin(referencias_excluir)
        ]

        top_productos = df_top_productos.nlargest(10, "cantidad_vendida")[[
            "refProducto", "nombreProducto", "cantidad_vendida", "beneficio_sin_iva", "beneficio_con_iva"
        ]].rename(columns={"cantidad_vendida": "cantidad_total"})

        # ✅ 8. Obtener stock actual desde la API
        try:
            stock_response = requests.get("http://192.168.1.201:5002/get_data?tipo=stock")
            stock_response.raise_for_status()
            stock_data = stock_response.json()
            df_stock = pd.DataFrame(stock_data)
        except (requests.RequestException, ValueError) as e:
            logging.error(f"❌ Error al obtener stock: {e}")
            df_stock = pd.DataFrame(columns=["refProducto", "stock_actual"])

        # ✅ 9. Unir el stock con el top productos
        df_stock = df_stock[["refProducto", "stock_actual"]].drop_duplicates()
        df_stock["stock_actual"] = df_stock["stock_actual"].fillna(0).astype(int)

        if not df_stock.empty:
            top_productos = top_productos.merge(df_stock, on="refProducto", how="left").fillna(0)
        else:
            top_productos["stock_actual"] = 0  # Si no hay stock, agregar columna con 0

        # ✅ 10. Convertir a JSON
        resultado = {
            "fechas": ventas_agrupadas["fecha_venta"].tolist() if not ventas_agrupadas.empty else [],
            "ventas": ventas_agrupadas["ventas_totales"].tolist() if not ventas_agrupadas.empty else [],
            "total_ventas": round(total_ventas, 2),
            "ticket_promedio": ticket_promedio,
            "top_productos": top_productos.to_dict(orient="records"),
            "beneficio_sin_iva_total": round(beneficio_sin_iva_total, 2),
            "beneficio_con_iva_total": round(beneficio_con_iva_total, 2)
        }

        logging.info("✅ Análisis completado con éxito")
        return resultado

    except Exception as e:
        logging.exception("❌ Error en análisis de ventas")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("analisis:app", host="0.0.0.0", port=5003, log_level="debug")