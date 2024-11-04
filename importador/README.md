# 📊 Sistema de Importación MXZ - Gestor de Datos para PrestaShop y Ambar

## 🎯 Descripción
El Sistema de Importación MXZ es una herramienta especializada desarrollada para MxZambrana que optimiza y automatiza el proceso de importación de productos entre diferentes sistemas. Su principal objetivo es mantener la consistencia de datos y reducir errores en la transferencia de información entre archivos Excel, el sistema Ambar y PrestaShop.

## 🌟 Características Principales

### 🗃️ Base de Datos Maestra Personalizada
Base de datos diseñada específicamente para validar y almacenar:
- Temporadas
- Categorías de productos
- Tallas
- Marcas
- Gamas
- Productos
- Otros atributos específicos

### 📥 Procesamiento de Archivos
- **Importación Flexible**: 
 - Soporte para archivos CSV y Excel
 - Mapeo personalizable de columnas
 - Opción de usar mapeos predefinidos

- **Validación de Datos**:
 - Comprobación automática contra la base de datos maestra
 - Detección de nuevos valores no registrados
 - Prevención de duplicados

### 📤 Generación de Archivos
El sistema genera automáticamente tres archivos diferentes:
1. **Plantilla Ambar**:
  - Formato específico para el sistema Ambar
  - Incluye campos necesarios para la importación
  - Estructurada según los requerimientos del sistema

2. **PS_Product (PrestaShop)**:
  - Archivo para productos base
  - Incluye todas las características del producto
  - Adaptado al formato de importación de PrestaShop

3. **PS_Combi (PrestaShop)**:
  - Archivo para combinaciones de productos
  - Gestión de variantes de productos
  - Formato compatible con PrestaShop

### 💻 Interfaz de Usuario
- **Panel de Control Intuitivo**:
 - Interfaz clara y fácil de usar
 - Visualización de diferencias encontradas
 - Gestión de nuevos valores

- **Gestión de Datos**:
 - Añadir nuevos valores a la base de datos
 - Visualización de valores no coincidentes
 - Control de duplicados

## 🛠️ Tecnologías Utilizadas

### Backend
- PHP
- MySQL
- Sistema de procesamiento de archivos CSV/Excel

### Frontend
- HTML5
- CSS3 con Bootstrap
- JavaScript
- jQuery
- AJAX para operaciones asíncronas

### Herramientas Adicionales
- Bootstrap para diseño responsive
- Sistema de validación de datos
- Gestión de sesiones para procesamiento de datos

## 📈 Beneficios

### Eficiencia Operativa
- Reducción significativa del tiempo de importación
- Minimización de errores humanos
- Proceso de validación automatizado

### Consistencia de Datos
- Mantiene uniformidad en nombres y atributos
- Previene duplicados
- Asegura la integridad de los datos

### Flexibilidad
- Mapeo personalizable de columnas
- Adaptable a diferentes formatos de entrada
- Fácil mantenimiento y actualización

## 💡 Características Avanzadas
- **Validación Inteligente**: Sistema de comprobación contra base de datos maestra
- **Gestión de Errores**: Identificación y manejo de inconsistencias
- **Proceso Automatizado**: Reducción de intervención manual
- **Mapeo Flexible**: Adaptable a diferentes estructuras de datos

## 🚀 Uso del Sistema

1. **Subida de Archivo**:
  - Seleccionar archivo Excel/CSV
  - Elegir tipo de mapeo (predefinido o personalizado)

2. **Configuración de Mapeo**:
  - Asignar columnas a campos correspondientes
  - Verificar correspondencia de datos

3. **Procesamiento**:
  - Validación automática de datos
  - Identificación de nuevos valores

4. **Generación de Archivos**:
  - Creación de archivos para cada sistema
  - Descarga de resultados

## 👨‍💻 Autor
- GitHub: [@OscarAdrian98](https://github.com/OscarAdrian98)
- LinkedIn: [Oscar Adrian](https://www.linkedin.com/in/oscar-adrian)

## 📄 Licencia
Este proyecto es propiedad de MxZambrana y su uso está restringido.
