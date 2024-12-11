📊 Proyecto: Procesador de Archivos Excel y Mapeador de Datos
Descripción
Este proyecto facilita el procesamiento de archivos Excel y CSV mediante una interfaz web interactiva y una API Flask. Permite mapear datos de los archivos a diferentes plantillas específicas y consultar información adicional en bases de datos como Ambar y Prestashop. El resultado final es un archivo enriquecido que puede ser descargado directamente desde la interfaz.

📌 Funcionalidades Principales
Subida y Procesamiento de Archivos:

Los usuarios pueden subir archivos Excel (.xlsx, .xls) o CSV.
Seleccionar una plantilla específica para mapear los datos (POLISPORT, FOX, ACERBIS, FXR, PROX).
Mapeo Automático:

Mapea las columnas del archivo subido a las columnas definidas en la plantilla seleccionada.
Genera un archivo de salida con los datos mapeados.
Enriquecimiento de Datos:

Consulta bases de datos Ambar y Prestashop para obtener información adicional (precios, stock, EAN, categorías, etc.).
Si hay referencias no encontradas en las bases de datos, genera un archivo separado con esas referencias.
Descarga de Resultados:

Si todo está correcto, se descarga un único archivo Excel.
Si hay referencias no encontradas, se descarga un archivo ZIP con dos Excel:
Referencias encontradas.
Referencias no encontradas.
Interfaz de Usuario Intuitiva:

Utiliza Bootstrap para el diseño responsive.
Indicadores visuales para el estado de procesamiento (loading, mensajes de error y éxito).
🗂️ Estructura del Proyecto
bash
Copiar código
📁 Proyecto-automatizar/
│
├── 📄 index.php               # Frontend para subir archivos y seleccionar plantillas
│
├── 📁 servidor/
│   └── 📄 servidor.py         # API Flask para procesar archivos y consultar bases de datos
│
└── 📁 procesar/
    └── 📄 procesar_fichero.py # Lógica de mapeo y consulta a bases de datos
🚀 Instalación y Ejecución
1. Clonar el Repositorio
bash
Copiar código
git clone https://github.com/OscarAdrian98/tu-repositorio.git
cd tu-repositorio
2. Instalar Dependencias
Asegúrate de tener Python 3 instalado y ejecuta:

bash
Copiar código
pip install -r requirements.txt
3. Configurar el Servidor Flask
En el archivo servidor.py, asegúrate de configurar correctamente las conexiones a las bases de datos Ambar y Prestashop.

4. Ejecutar el Servidor Flask
bash
Copiar código
cd servidor
python servidor.py
El servidor se ejecutará en http://localhost:5000.

5. Abrir la Interfaz Web
Abre index.php en tu navegador o accede a través de un servidor local como XAMPP o WAMP.

⚙️ Endpoints de la API
GET /plantillas
Obtiene la lista de plantillas disponibles para el mapeo.

Ejemplo de Respuesta:

json
Copiar código
{
    "success": true,
    "plantillas": ["POLISPORT", "FOX", "ACERBIS", "FXR", "PROX"]
}
POST /procesar
Procesa el archivo subido según la plantilla seleccionada.

Parámetros:
file: Archivo Excel o CSV.
plantilla: Nombre de la plantilla (POLISPORT, FOX, etc.).
Respuesta:

Archivo Excel procesado o un archivo ZIP si hay múltiples resultados.
🛠️ Tecnologías Utilizadas
Frontend
HTML5 / CSS3
Bootstrap 5
JavaScript (jQuery)
Backend
Python (Flask)
Pandas: Procesamiento y análisis de datos.
Openpyxl: Manipulación de archivos Excel.
Flask-CORS: Manejo de CORS para solicitudes entre dominios.
Logging: Registro de eventos y errores.
Bases de Datos
SQL Server (Ambar)
MySQL (Prestashop)
📈 Beneficios del Proyecto
Automatización de Procesos: Reduce el tiempo y los errores en el procesamiento de archivos Excel.
Enriquecimiento de Datos: Combina información de múltiples fuentes para obtener datos más completos.
Interfaz Intuitiva: Facilita el uso de la herramienta sin necesidad de conocimientos técnicos avanzados.
📋 Requisitos del Sistema
Python 3.x
Servidor Web (Apache, Nginx, etc.)
Bases de Datos (SQL Server y MySQL)
🔗 Enlaces Relacionados
Tienda Zambrana: https://mxzambrana.com/
Repositorio Principal: GitHub - OscarAdrian98
🤝 Contacto
Para cualquier consulta o mejora relacionada con este proyecto, puedes contactarme en:

GitHub: @OscarAdrian98
