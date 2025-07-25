from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import sys
import logging
from werkzeug.utils import secure_filename
from io import BytesIO
import zipfile
import pandas as pd
import json

# Configurar paths de manera correcta
current_dir = os.path.dirname(os.path.abspath(__file__))  # servidor/
project_dir = os.path.dirname(current_dir)  # Proyecto-automatizar/
sys.path.append(project_dir)  # Añadir el directorio principal al path

# Importar el módulo - ahora usando la ruta relativa correcta
try:
    from procesar.procesar_fichero import mapear_excel_a_plantilla, plantillas
    logging.info("Módulo procesar_fichero importado correctamente")
except ImportError as e:
    logging.error(f"Error importando procesar_fichero: {str(e)}")
    logging.error(f"Directorio actual: {current_dir}")
    logging.error(f"Python path: {sys.path}")
    raise

# Configuración de la app
app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST"],
        "allow_headers": ["Content-Type"]
    }
})

# Configuración de logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
file_handler = logging.FileHandler('servidor.log', encoding='utf-8')
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(file_handler)
logger = logging.getLogger(__name__)

# Variable global para el progreso
progreso_global = {"progreso": 0}

def actualizar_progreso(progreso):
    """Actualiza el progreso global."""
    progreso_global["progreso"] = progreso
    logger.debug(f"Progreso actualizado a: {progreso}%")

# Configuración para subida de archivos
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/plantillas', methods=['GET'])
def get_plantillas():
    """Endpoint para obtener la lista de plantillas disponibles"""
    try:
        return jsonify({
            'success': True,
            'plantillas': list(plantillas.keys())
        })
    except Exception as e:
        logger.error(f"Error al obtener plantillas: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Error al obtener la lista de plantillas'
        })

@app.route('/progreso', methods=['GET'])
def obtener_progreso():
    """Endpoint para consultar el progreso actual del procesamiento"""
    return jsonify(progreso_global)

@app.route('/procesar', methods=['POST'])
def procesar():
    """Endpoint principal para procesar archivos"""
    try:
        # Inicializar progreso
        actualizar_progreso(0)
        logger.info("Iniciando procesamiento de archivo")

        # Verificar si se recibió un archivo
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No se encontró archivo en la solicitud'
            }), 400
            
        file = request.files['file']
        nombre_plantilla = request.form.get('plantilla')
        mapeo_manual = request.form.get('mapeo')

        # Convertir el mapeo si se ha enviado
        mapeo_dict = {}
        if mapeo_manual:
            try:
                mapeo_dict = json.loads(mapeo_manual)
                logger.info(f"Mapeo personalizado recibido: {mapeo_dict}")
            except Exception as e:
                logger.warning(f"Error al interpretar el mapeo personalizado: {str(e)}")
        
        # Validaciones básicas
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No se seleccionó ningún archivo'
            }), 400
            
        if not nombre_plantilla and not mapeo_dict:
            return jsonify({
                'success': False,
                'error': 'Debe seleccionar una plantilla o hacer mapeo manual'
            }), 400
            
        if nombre_plantilla and nombre_plantilla not in plantillas:
            return jsonify({
                'success': False,
                'error': f'Plantilla no válida: {nombre_plantilla}. Plantillas disponibles: {list(plantillas.keys())}'
            }), 400
            
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': 'Tipo de archivo no permitido'
            }), 400
            
        try:
            # Crear BytesIO para el archivo de entrada
            actualizar_progreso(10)
            logger.info("Iniciando lectura del archivo")
            input_stream = BytesIO()
            file.save(input_stream)
            input_stream.seek(0)
            
            # Procesar el archivo
            actualizar_progreso(30)
            logger.info("Iniciando mapeo de datos")
            resultado = mapear_excel_a_plantilla(input_stream, nombre_plantilla, mapeo_dict)
            
            if not resultado['success']:
                return jsonify({
                    'success': False,
                    'error': resultado.get('error', 'Error durante el procesamiento')
                }), 500
                
            # Preparar nombre base para los archivos
            actualizar_progreso(60)
            logger.info("Preparando archivos de salida")
            base_filename = secure_filename(file.filename)
            name_without_ext = os.path.splitext(base_filename)[0]
            
            # Si hay referencias no encontradas, crear un ZIP con ambos archivos
            if resultado.get('not_found_data'):
                actualizar_progreso(80)
                logger.info("Generando archivo ZIP con resultados")
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    # Añadir archivo de referencias encontradas
                    zip_file.writestr(
                        f"{name_without_ext}_encontradas.xlsx",
                        resultado['file_data'].getvalue()
                    )
                    # Añadir archivo de referencias no encontradas
                    zip_file.writestr(
                        f"{name_without_ext}_no_encontradas.xlsx",
                        resultado['not_found_data'].getvalue()
                    )
                
                zip_buffer.seek(0)
                actualizar_progreso(100)
                logger.info("Proceso completado - enviando archivo ZIP")
                return send_file(
                    zip_buffer,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=f"{name_without_ext}_resultados.zip",
                    max_age=0
                )
            else:
                # Si solo hay referencias encontradas, enviar un único archivo
                actualizar_progreso(90)
                logger.info("Generando archivo único de resultados")
                output_stream = resultado['file_data']
                output_stream.seek(0)
                actualizar_progreso(100)
                logger.info("Proceso completado - enviando archivo único")
                return send_file(
                    output_stream,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True,
                    download_name=f"procesado_{base_filename}",
                    max_age=0
                )
                
        except Exception as e:
            actualizar_progreso(0)  # Resetear progreso en caso de error
            logger.error(f"Error procesando el archivo: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'error': f'Error durante el procesamiento: {str(e)}'
            }), 500
            
    except Exception as e:
        actualizar_progreso(0)  # Resetear progreso en caso de error
        logger.error(f"Error general en el endpoint: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error en el servidor: {str(e)}'
        }), 500

# Manejador de errores para excepciones no capturadas
@app.errorhandler(Exception)
def handle_exception(e):
    actualizar_progreso(0)  # Resetear progreso en caso de error no manejado
    logger.error(f"Error no manejado: {str(e)}", exc_info=True)
    return jsonify({
        'success': False,
        'error': 'Error interno del servidor'
    }), 500

# Configuración adicional de CORS para manejo de errores
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST')
    return response

# Endpoint para vista previa de archivos
@app.route('/vista-previa', methods=['POST'])
def vista_previa():
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'error': 'No se ha subido ningún archivo'}), 400

    df = pd.read_excel(file, dtype=str)
    columnas = df.columns.tolist()
    vista = df.head(5).fillna('').to_dict(orient='records')
    return jsonify({'success': True, 'columnas': columnas, 'vista': vista})


if __name__ == '__main__':
    logger.info("Iniciando servidor Flask...")
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        logger.error(f"Error al iniciar el servidor: {str(e)}", exc_info=True)