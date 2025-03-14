# 📦 Proyecto: Reportes de Inventario

## 📌 Descripción
Este proyecto es un sistema de reportes de inventario que permite la consulta y descarga de informes de ventas, compras, vencimientos y stock actual. Utiliza **FastAPI** como backend para gestionar los datos y una interfaz en **PHP** con **Bootstrap** para visualizar la información. Además, se ha incorporado **PySpark** para el análisis avanzado de ventas y stock.

## 🚀 Funcionalidades Principales
- **Autenticación con clave de acceso** para garantizar seguridad.
- **Interfaz web con pestañas dinámicas** para consultar distintos reportes.
- **Generación y descarga de reportes en Excel**.
- **Filtros avanzados** para ajustar las consultas de ventas, compras y stock.
- **Sistema de API en FastAPI** para recuperar y procesar datos en tiempo real.
- **Conexión con bases de datos SQL Server y MySQL**.
- **Análisis avanzado de ventas con PySpark** para obtener insights y tendencias.
- **Manejo de sesiones y seguridad para evitar caché en el navegador**.
- **Diseño responsive y dinámico con Bootstrap y jQuery**.

## 🛠️ Tecnologías Utilizadas
- **Frontend:** PHP, HTML, CSS, Bootstrap, jQuery.
- **Backend:** FastAPI (Python), SQL Server, MySQL.
- **Bibliotecas:** Pandas, Openpyxl, Logging, Uvicorn, PySpark, Requests, NumPy.
- **Servicios:** API REST con CORS habilitado.

## 💾 Estructura del Proyecto
```
📂 Inventario
├── 📄 index.php               # Interfaz web principal con pestañas y filtros
├── 📄 main.py                 # Servidor FastAPI para reportes
├── 📄 analisis.py             # Servidor FastAPI para análisis avanzado con PySpark
├── 📂 bd                      # Conexión a la base de datos
├── 📄 xml.xml                 # Configuración del servicio para FastAPI
├── 📄 start_uvicorn.py        # Script para iniciar ambos servidores FastAPI
└── 📂 logs                    # Carpeta para logs del sistema
```

## 📌 Instalación y Configuración
### 1️⃣ **Requisitos**
- **Python 3.10 o superior**
- **Servidor web (Apache o Nginx con PHP)**
- **Base de datos SQL Server / MySQL**
- **Java instalado (para PySpark)**

### 2️⃣ **Instalar dependencias en el backend**
```bash
pip install fastapi uvicorn pandas openpyxl pymysql pyodbc pyspark requests numpy
```

### 3️⃣ **Configurar y ejecutar los servidores FastAPI**
```bash
python start_uvicorn.py
```

### 4️⃣ **Acceder a la Interfaz Web**
Abre en tu navegador:
```
http://localhost/index.php
```

## 🔗 Endpoints API (FastAPI)
### Servidor principal (`main.py`)
| Método | Endpoint | Descripción |
|--------|---------|-------------|
| `GET` | `/get_data?tipo=ventas` | Obtiene ventas filtradas por fecha |
| `GET` | `/get_data?tipo=compras` | Obtiene compras filtradas por fecha |
| `GET` | `/get_data?tipo=vencimientos` | Obtiene vencimientos filtrados por fecha |
| `GET` | `/get_data?tipo=stock` | Obtiene el stock actual filtrado por familia y proveedor |
| `GET` | `/descargar?tipo=ventas` | Descarga un Excel con los datos filtrados |

### Servidor de análisis (`analisis.py`)
| Método | Endpoint | Descripción |
|--------|---------|-------------|
| `GET` | `/analisis_ventas?fecha_desde=YYYY-MM-DD&fecha_hasta=YYYY-MM-DD` | Analiza ventas y devuelve insights (ticket promedio, top productos, total de ventas) |

## 🏆 Beneficios del Proyecto
✅ **Automatización** de reportes y descarga de datos.
✅ **Análisis avanzado** con PySpark para obtener insights valiosos.
✅ **Eficiencia** en la generación de reportes sin intervención manual.
✅ **Reducción de errores** en la gestión del inventario.
✅ **Escalabilidad** para incorporar nuevas funcionalidades en el futuro.

## 📩 Contacto
Para más información o mejoras, puedes contactarme en:
- **GitHub:** [@OscarAdrian98](https://github.com/OscarAdrian98)
- **LinkedIn:** [Oscar Adrian](https://www.linkedin.com/in/oscar-adrian/)