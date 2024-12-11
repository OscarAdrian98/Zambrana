
# Proyecto: Gestión y Optimización de la Tienda Zambrana

## Descripción General

Este proyecto forma parte de la gestión y optimización de los procesos de la tienda [Zambrana](https://mxzambrana.com/), un comercio especializado en motos de Cross y Enduro, así como en la venta de equipamiento, recambios y accesorios. Mis responsabilidades en este proyecto abarcan desde la administración de productos hasta el desarrollo de soluciones automatizadas para mejorar la eficiencia en la carga y actualización de inventario en el sistema de PrestaShop de la tienda.

## Responsabilidades Principales

Mi trabajo en Zambrana se centra en la automatización, mantenimiento de productos, y creación de soluciones interactivas y personalizadas para los clientes. Esto incluye:

- **Gestión de Productos en PrestaShop**:
  - Subida de productos y actualización masiva de precios, stock y características directamente en el sistema.
  - Activación y desactivación de productos y atributos según la disponibilidad del inventario.

- **Desarrollo de Programas en Python**:
  - Creación de scripts en Python para automatizar tareas como la sincronización de datos de proveedores, actualización de precios, control de stock y envío de informes automáticos.
  - Uso de bibliotecas como **pandas** para el procesamiento de datos, **pymysql** para la conexión a bases de datos, y **smtplib** para el envío de correos con informes de actualización.

- **Manejo de Bases de Datos (MySQL y SQL Server)**:
  - Implementación y mantenimiento de una base de datos exclusiva para almacenar la información de productos, incluyendo stock, disponibilidad y precios de los proveedores.
  - Comparación y sincronización de los datos entre la base de datos interna y la base de datos de PrestaShop para asegurar coherencia en la información del catálogo de productos.
  - Ejecución de consultas complejas para unir datos de distintas fuentes y actualizar información crítica en el sistema de la tienda.

- **Automatización de Importaciones con Ambar**:
  - Uso del sistema **Ambar** para importar archivos de Excel con información detallada de productos (precios, referencias, nombres, EAN, etc.).
  - Procesamiento de archivos Excel descargados desde los proveedores a través de FTP y carga de los datos a la base de datos para su posterior sincronización.

- **Extracción y Scraping de Datos**:
  - Aplicación de técnicas de scraping y uso de **Selenium** para extraer información actualizada de productos y precios desde sitios web de proveedores.
  - Automatización de tareas repetitivas y extracción de datos relevantes para apoyar en la toma de decisiones sobre el inventario.

- **Desarrollo de Módulo Interactivo en PHP**:
  - Creación de un módulo en PHP que permite a los clientes visualizar diferentes combinaciones de ruedas para sus modelos de motos.
  - Los usuarios pueden personalizar la selección de llantas, bujes, radios y tuercas en distintos colores, lo que les permite ver cómo se vería su moto con cada combinación.
  - Incluye la opción de solicitar un presupuesto para las configuraciones seleccionadas, lo cual facilita el proceso de compra y mejora la experiencia del cliente en el sitio.

## Herramientas y Tecnologías

- **Python**: Lenguaje principal utilizado para la creación de scripts de automatización y gestión de datos.
- **Pandas**: Para el procesamiento y análisis de datos a través de dataframes.
- **PyMySQL**: Para la conexión a las bases de datos MySQL y la actualización masiva de datos.
- **Selenium**: Herramienta de automatización para el scraping de información relevante de sitios web de proveedores.
- **SQL (MySQL y SQL Server)**: Gestión de bases de datos, consultas complejas y mantenimiento de datos de productos.
- **Ambar**: Plataforma para la importación y sincronización de archivos Excel con la información de los productos.
- **PHP**: Desarrollo de módulos personalizados, como la herramienta de visualización de ruedas, para mejorar la interacción del cliente en el sitio de Zambrana.

## Objetivo del Proyecto

El objetivo de este proyecto es optimizar la gestión de inventario y la actualización de productos en la tienda de manera eficiente, reduciendo los tiempos de carga y minimizando errores en la información mostrada al cliente. La implementación de estos procesos garantiza que el catálogo esté siempre alineado con la disponibilidad real de los productos, mejorando así la experiencia del cliente en el sitio.

# Portfolio de Proyectos MxZambrana

## 🏍️ Sobre MxZambrana
[MxZambrana](https://mxzambrana.com/) es una tienda especializada en motos de Cross y Enduro, así como en la venta de equipamiento, recambios y accesorios. Este repositorio contiene los diversos proyectos desarrollados para optimizar y automatizar los procesos de la tienda.

## 📁 Proyectos Principales

### 1. Sistema de Gestión de Stock
Sistema automatizado para la sincronización y gestión de stock entre proveedores y PrestaShop.

#### Características Principales:
- Descarga automática de archivos Excel desde FTP de proveedores
- Procesamiento y análisis de datos mediante pandas
- Sincronización bidireccional entre base de datos de stock y PrestaShop
- Sistema de etiquetado automático de productos
- Gestión automática de disponibilidad y fechas
- Generación y envío de informes por correo

#### Tecnologías:
- Python (pandas, PyMySQL, smtplib, logging)
- SQL (MySQL)
- FTP

### 2. Configurador de Ruedas (Módulo PrestaShop)
Módulo interactivo que permite a los clientes personalizar y visualizar diferentes combinaciones de ruedas para sus motos.

#### Características Principales:
- Interfaz visual interactiva
- Personalización de componentes (aros, bujes, radios, tuercas)
- Previsualización en tiempo real
- Diseño responsive
- Soporte para múltiples marcas de motos

#### Tecnologías:
- PHP (PrestaShop Module)
- JavaScript
- HTML5 Canvas
- CSS3
- Smarty Templates

### 3. Sistema de Importación de Productos
Sistema integral para el procesamiento y validación de datos de productos, diseñado para mantener la consistencia en la importación de datos entre diferentes plataformas (Ambar y PrestaShop).

#### Características Principales:
- Base de datos personalizada para almacenar y validar atributos de productos:
 - Temporadas
 - Categorías
 - Tallas
 - Marcas
 - Gamas
 - Productos
- Procesamiento inteligente de archivos Excel:
 - Mapeo flexible de columnas de entrada
 - Validación automática contra la base de datos maestra
 - Detección de nuevos valores no registrados
- Generación automática de tres archivos de salida:
 - Plantilla Ambar: Formato específico para importación en sistema Ambar
 - PS_Product: Archivo adaptado para productos base en PrestaShop
 - PS_Combi: Archivo para combinaciones de productos en PrestaShop
- Interfaz de usuario para gestión de datos:
 - Visualización de valores no coincidentes
 - Opción de añadir nuevos valores a la base de datos maestra
 - Prevención de duplicados en la importación
 - Mapeo personalizado o predefinido de columnas

#### Beneficios:
- Mantiene la consistencia de datos entre sistemas
- Reduce errores en la importación de productos
- Automatiza la transformación de datos entre diferentes formatos
- Facilita la detección y gestión de nuevos valores
- Ahorra tiempo en el proceso de importación

#### Tecnologías:
- PHP para el backend y procesamiento de datos
- MySQL para la base de datos maestra
- JavaScript (jQuery) para la interfaz interactiva
- Bootstrap para el diseño responsive
- AJAX para operaciones asíncronas

## 🛠️ Tecnologías Utilizadas

### Lenguajes de Programación
- Python
- PHP
- JavaScript
- SQL

### Frameworks y Bibliotecas
- PrestaShop
- Bootstrap
- jQuery
- Pandas
- PyMySQL

### Bases de Datos
- MySQL
- SQL Server

### Herramientas
- FTP
- Git
- Visual Studio Code
- Ambar (Sistema de importación)

## 📊 Resultados y Mejoras
- Automatización de procesos manuales de actualización de stock
- Reducción de errores en la gestión de inventario
- Mejora en la experiencia de usuario para la personalización de productos
- Optimización del proceso de importación de productos
- Sistema escalable y mantenible

## 🔗 Contacto

Para cualquier consulta relacionada con estos proyectos, puedes contactarme a través de:
- GitHub: [@OscarAdrian98](https://github.com/OscarAdrian98)
- LinkedIn: [Oscar Adrian](https://www.linkedin.com/in/oscar-adrian)

