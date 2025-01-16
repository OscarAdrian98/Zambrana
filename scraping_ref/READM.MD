# Buscador Ref Competencia

## Descripción

El **Buscador Ref Competencia** es una herramienta web diseñada para comparar precios y referencias de productos entre diferentes plataformas de venta en tiempo real. Su objetivo principal es ayudar a **MxZambrana** a identificar oportunidades competitivas en el mercado al ofrecer una búsqueda rápida y precisa de información sobre precios y descuentos.

## Características Principales

- **Búsqueda de Referencias**: Permite buscar una referencia específica y obtener información relacionada en tiempo real.
- **Comparación de Precios**: Muestra precios, descuentos y proveedores disponibles para la referencia ingresada.
- **Proveedor Destacado**: Resalta el proveedor con el precio más competitivo.
- **Generación de Informes**: Ofrece la posibilidad de descargar los resultados en formato Excel para un análisis posterior.

## Tecnologías Utilizadas

### Frontend
- **HTML** y **CSS (Bootstrap)**: Para el diseño de una interfaz limpia y responsiva.
- **JavaScript (jQuery)**: Para la interacción del usuario y la comunicación con el backend.

### Backend
- **Python (FastAPI)**: Para la gestión de la lógica del servidor y la generación de eventos en tiempo real mediante EventSource.
- **Selenium**: Para realizar scraping en diferentes sitios web de competidores y obtener información actualizada.

### Otras Tecnologías
- **Openpyxl**: Para la generación de archivos Excel.
- **Logging**: Para el seguimiento y depuración del sistema.

## Funcionamiento

1. **Ingreso de Referencia**: El usuario introduce una referencia en el campo de búsqueda y envía el formulario.
2. **Scraping de Competidores**: El backend utiliza Selenium para buscar información relevante en plataformas como Greenland, Motocard, y otras.
3. **Visualización de Resultados**: Se muestran los resultados en una tabla interactiva, destacando el mejor precio y proporcionando un resumen de las diferencias.
4. **Descarga de Informes**: El usuario puede descargar un archivo Excel con los resultados para su posterior revisión.

## Beneficios

- **Toma de Decisiones Informada**: Proporciona datos precisos para tomar decisiones estratégicas de precios.
- **Ahorro de Tiempo**: Automatiza la tarea de buscar y comparar información en múltiples sitios web.
- **Flexibilidad**: Permite obtener resultados personalizados y descargarlos para su análisis.

## Requisitos de Instalación

1. Clona el repositorio en tu equipo:
   ```bash
   git clone <URL_DEL_REPOSITORIO>
   ```
2. Instala las dependencias necesarias:
   ```bash
   pip install -r requirements.txt
   ```
3. Asegúrate de tener configurado el **chromedriver** en tu sistema y que coincida con la versión de tu navegador Chrome.
4. Ejecuta el servidor:
   ```bash
   python start_uvicorn.py
   ```

## Uso

1. Accede a la interfaz web del buscador a través de tu navegador ingresando la dirección del servidor (por ejemplo, `http://localhost:5001`).
2. Introduce una referencia en el campo de búsqueda y presiona el botón de "Buscar".
3. Revisa los resultados en la tabla interactiva.
4. Descarga el informe en Excel si lo necesitas.

## Estructura del Proyecto

```
.
├── index.php               # Interfaz web
├── start_uvicorn.py        # Script para iniciar el servidor FastAPI
├── server.py               # Backend principal con los endpoints
├── scraping.py             # Funciones de scraping con Selenium
├── templates/              # Plantillas HTML para la interfaz (si aplica)
├── static/                 # Archivos CSS y JavaScript
├── logs/                   # Archivos de logs
└── requirements.txt        # Lista de dependencias del proyecto
```

## Contribuciones

Las contribuciones son bienvenidas. Si tienes sugerencias o mejoras, no dudes en abrir un **issue** o enviar un **pull request**.

## Contacto

Para más información o consultas, contáctame en:
- GitHub: [@OscarAdrian98](https://github.com/OscarAdrian98)
- LinkedIn: [Oscar Adrian](https://www.linkedin.com/in/oscar-adrian)