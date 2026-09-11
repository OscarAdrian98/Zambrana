import uvicorn
import logging

# Configuración básica de logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

if __name__ == "__main__":
    try:
        logging.info("Iniciando el servidor FastAPI con Uvicorn...")
        uvicorn.run(
            "server:app",  # Archivo `server.py` con la aplicación `app`
            host="127.0.0.1",
            port=5001,
            workers=1,  # Número de workers para multitarea
            reload=False  # Dejar en False para producción
        )
    except Exception as e:
        logging.error(f"Error al iniciar Uvicorn: {e}")
        raise
