import uvicorn
import logging
import os
import multiprocessing

# Crear la carpeta logs si no existe
log_dir = "D:\\www\\oscar\\Inventario\\logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Configuración básica de logs
logging.basicConfig(
    filename=os.path.join(log_dir, "start_uvicorn.log"),  # Ruta del log para el servidor
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Función para iniciar el servidor de `main.py`
def run_main():
    try:
        logging.info("Iniciando el servidor de Main en el puerto 5002...")
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=5002,
            workers=1,
            reload=False
        )
    except Exception as e:
        logging.error(f"Error al iniciar Main: {e}")

# Función para iniciar el servidor de `analisis.py`
def run_analisis():
    try:
        logging.info("Iniciando el servidor de Análisis en el puerto 5003...")
        uvicorn.run(
            "analisis:app",
            host="0.0.0.0",
            port=5003,
            workers=1,
            reload=False
        )
    except Exception as e:
        logging.error(f"Error al iniciar Análisis: {e}")

if __name__ == "__main__":
    # Crear procesos para ejecutar ambos servidores en paralelo
    process_main = multiprocessing.Process(target=run_main)
    process_analisis = multiprocessing.Process(target=run_analisis)

    # Iniciar procesos
    process_main.start()
    process_analisis.start()

    # Esperar a que ambos servidores finalicen (bloquea el script)
    process_main.join()
    process_analisis.join()
