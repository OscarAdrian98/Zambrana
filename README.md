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
