import logging
import os
import time

# Configuración de logging general
logging.basicConfig(filename='Registro-Stock-Hoy.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8')

# Configuración del logger específico para funciones seleccionadas
logger_funciones_especificas = logging.getLogger('FuncionesEspecificas')
handler_especifico = logging.FileHandler('Resumen-Stock.log', encoding='utf-8')  # Añadir encoding aquí
formatter_especifico = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler_especifico.setFormatter(formatter_especifico)
logger_funciones_especificas.addHandler(handler_especifico)
logger_funciones_especificas.setLevel(logging.INFO)

# Función para borrar registro
def borrar_archivo_log():
    intentos = 0
    while intentos < 5:  # Intentar hasta 5 veces
        try:
            logging.shutdown()
            os.remove('Registro-Stock-Hoy.log')
            os.remove('Resumen-Stock.log')
            print("Archivo de registro borrado exitosamente.")
            break
        except OSError as e:
            print(f"No se pudo borrar el archivo de registro, reintento {intentos + 1}: {e}")
            time.sleep(1)  # Esperar 1 segundo antes de reintentar
            intentos += 1