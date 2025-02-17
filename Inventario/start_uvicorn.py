import uvicorn
import logging
import os

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

if __name__ == "__main__":
    try:
        logging.info("Iniciando el servidor FastAPI con Uvicorn...")
        uvicorn.run(
            "main:app",  # Archivo `main.py` con la aplicación `app`
            host="0.0.0.0",
            port=5002,  # Usa el puerto correcto
            workers=1,  # Número de workers para multitarea
            reload=False  # Dejar en False para producción
        )
    except Exception as e:
        logging.error(f"Error al iniciar Uvicorn: {e}")
        raise
