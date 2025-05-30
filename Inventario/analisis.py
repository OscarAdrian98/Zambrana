from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
import requests
import atexit
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum as _sum, to_date, regexp_replace, upper

# Establecer entorno PySpark
os.environ["PYSPARK_PYTHON"] = r"C:\Users\Zambrana\AppData\Local\Programs\Python\Python311\python.exe"
os.environ["PYSPARK_DRIVER_PYTHON"] = r"C:\Users\Zambrana\AppData\Local\Programs\Python\Python311\python.exe"

# Configurar logs
logging.basicConfig(
    filename="analisis.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Iniciar SparkSession
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

# Cerrar sesión de Spark al salir
def cerrar_spark():
    if spark and spark._jsc:
        logging.info("🛑 Cerrando sesión Spark")
        spark.stop()
atexit.register(cerrar_spark)

@app.get("/analisis_ventas")
async def analisis_ventas(fecha_desde: str = Query(...), fecha_hasta: str = Query(...)):
    try:
        logging.info("📡 Solicitando datos de ventas para análisis")

        response = requests.get(f"http://192.168.1.201:5002/get_data?tipo=ventas&fecha_desde={fecha_desde}&fecha_hasta={fecha_hasta}&ventas=individual")
        response.raise_for_status()
        ventas_data = response.json()

        if not ventas_data:
            return {
                "fechas": [], "ventas": [], "total_ventas": 0, "ticket_promedio": 0,
                "top_productos": [], "beneficio_sin_iva_total": 0, "beneficio_con_iva_total": 0
            }

        df_ventas = spark.createDataFrame(ventas_data)

        # Eliminar TOTAL y limpiar numéricos
        df_ventas = df_ventas.filter(col("refProducto") != "TOTAL") \
            .withColumn("total_ajustado", regexp_replace("total_ajustado", "\\.", "")) \
            .withColumn("total_ajustado", regexp_replace("total_ajustado", ",", ".")) \
            .withColumn("total_ajustado", col("total_ajustado").cast("double")) \
            .withColumn("beneficio_sin_iva", regexp_replace("beneficio_sin_iva", "\\.", "")) \
            .withColumn("beneficio_sin_iva", regexp_replace("beneficio_sin_iva", ",", ".")) \
            .withColumn("beneficio_sin_iva", col("beneficio_sin_iva").cast("double")) \
            .withColumn("beneficio_con_iva", regexp_replace("beneficio_con_iva", "\\.", "")) \
            .withColumn("beneficio_con_iva", regexp_replace("beneficio_con_iva", ",", ".")) \
            .withColumn("beneficio_con_iva", col("beneficio_con_iva").cast("double")) \
            .withColumn("cantidad_vendida", col("cantidad_vendida").cast("int"))

        referencias_excluir = ["PW", "MOTHVA", "PC3", "RE", "SC", "PAYPAL"]
        df_grafica = df_ventas \
            .filter(~upper(col("refProducto")).isin([r.upper() for r in referencias_excluir])) \
            .withColumn("fecha_venta", to_date("fecha_venta", "dd-MM-yyyy"))

        df_agrupada = df_grafica.groupBy("fecha_venta").agg(
            _sum("cantidad_vendida").alias("ventas_totales"),
            _sum("total_ajustado").alias("total_ventas")
        ).orderBy("fecha_venta")

        agg_collect = df_agrupada.collect()
        total_ventas = sum(row["total_ventas"] for row in agg_collect)
        total_cantidad = sum(row["ventas_totales"] for row in agg_collect)
        ticket_promedio = round(total_ventas / total_cantidad, 2) if total_cantidad > 0 else 0

        # Top productos
        ref_excluir = ["PW", "MOTHVA", "PC3", "RE", "SC", "PAYPAL", "PC10"]
        nom_excluir = ["PORTES", "MANO OBRA", "GASTOS DE REEMBOLSO", "RECARGO", "Recargo Pago Por Paypal"]

        df_top = df_ventas \
            .withColumn("nombreProducto_clean", upper(col("nombreProducto"))) \
            .withColumn("refProducto_clean", upper(col("refProducto"))) \
            .filter(~col("nombreProducto_clean").isin([n.upper() for n in nom_excluir])) \
            .filter(~col("refProducto_clean").isin([r.upper() for r in ref_excluir]))

        df_top_grouped = df_top.groupBy("refProducto", "nombreProducto").agg(
            _sum("cantidad_vendida").alias("cantidad_total"),
            _sum("beneficio_sin_iva").alias("beneficio_sin_iva"),
            _sum("beneficio_con_iva").alias("beneficio_con_iva")
        ).orderBy(col("cantidad_total").desc()).limit(10)

        top_productos = [row.asDict() for row in df_top_grouped.collect()]

        # Obtener stock
        try:
            stock_response = requests.get("http://192.168.1.201:5002/get_data?tipo=stock")
            stock_response.raise_for_status()
            stock_data = stock_response.json()
            df_stock = spark.createDataFrame(stock_data).select("refProducto", "stock_actual")
        except Exception as e:
            logging.warning(f"❌ Stock no disponible: {e}")
            df_stock = spark.createDataFrame([], schema="refProducto STRING, stock_actual INT")

        df_stock = df_stock.dropna().dropDuplicates(["refProducto"])

        # Unir top productos con stock
        if not df_stock.rdd.isEmpty():
            df_top_final = spark.createDataFrame(top_productos).join(df_stock, on="refProducto", how="left").fillna(0)
            top_productos = [row.asDict() for row in df_top_final.collect()]
        else:
            for producto in top_productos:
                producto["stock_actual"] = 0

        beneficio_sin_iva_total = df_ventas.agg(_sum("beneficio_sin_iva")).first()[0] or 0
        beneficio_con_iva_total = df_ventas.agg(_sum("beneficio_con_iva")).first()[0] or 0

        resultado = {
            "fechas": [row["fecha_venta"].strftime("%d/%m/%Y") for row in agg_collect],
            "ventas": [row["ventas_totales"] for row in agg_collect],
            "total_ventas": round(total_ventas, 2),
            "ticket_promedio": ticket_promedio,
            "top_productos": top_productos,
            "beneficio_sin_iva_total": round(beneficio_sin_iva_total, 2),
            "beneficio_con_iva_total": round(beneficio_con_iva_total, 2)
        }

        logging.info("✅ Análisis completado con PySpark")
        return resultado

    except Exception as e:
        logging.exception("❌ Error en análisis de ventas")
        raise HTTPException(status_code=500, detail=str(e))