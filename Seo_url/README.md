```markdown
# 🛠️ Proyecto: Seo_url

## 📌 Descripción

**Seo_url** es una aplicación web desarrollada en **Python (Flask)** que permite scrapear páginas de productos (por ejemplo, de tiendas PrestaShop) para extraer información clave como nombre del producto, descripciones, meta etiquetas e imágenes.

Integra **IA (Groq)** para generar contenido SEO automáticamente, como descripciones largas, meta titles, meta descriptions y reseñas de clientes. Además, permite gestionar esta información y sincronizarla con la base de datos de **PrestaShop**, manteniendo actualizadas las fichas de producto y las reseñas en la tienda online.

## 🚀 Funcionalidades Principales

- **Scraping de datos** desde URLs de productos:
  - Nombre de producto
  - Descripción larga
  - Meta Title
  - Meta Description
  - Imagen principal
- **Generación de contenido SEO mediante IA:**
  - Descripción larga optimizada
  - Meta Title SEO
  - Meta Description SEO
  - Reseñas de clientes simuladas
- **Edición web** de la información scrapings o generada.
- **Sincronización con PrestaShop:**
  - Inserción o actualización de productos
  - Gestión de reseñas en PrestaShop
- **Panel web interactivo** con Bootstrap, DataTables y CKEditor para:
  - Editar productos
  - Gestionar reseñas
  - Filtrar productos sin campos SEO completados
- **Sistema de logs** para registrar errores y operaciones.

## 🛠️ Tecnologías Utilizadas

- **Backend:** Python, Flask, Groq API
- **Frontend:** HTML, Bootstrap 5, DataTables, CKEditor, JavaScript, jQuery
- **Scraping:** BeautifulSoup
- **Bases de Datos:**
  - Base de datos SEO (MySQL o MariaDB)
  - Base de datos PrestaShop (MySQL o MariaDB)
- **Servidor producción:** Waitress

## 💻 Estructura del Proyecto

```
📂 seo_url
├── app.py                   # Servidor Flask con rutas y lógica principal
├── ia.py                    # Funciones IA para generar textos y reseñas
├── scraping_url.py          # Scraping de datos de productos
├── start.py                 # Script para lanzar el servidor en producción (Waitress)
├── db/
│   ├── conexion.py          # Conexiones a las bases de datos (SEO y PrestaShop)
│   └── config.py            # Configuración y claves sensibles
├── templates/
│   ├── index.html           # Interfaz principal para scraping y edición
│   └── reseñas.html         # Gestión de reseñas
├── static/
│   ├── js/
│   │    ├── script.js       # Lógica JS para la vista principal
│   │    └── reseñas.js      # Lógica JS para gestionar reseñas
│   └── css/                 # Estilos CSS
└── flask_error.log          # Archivo de logs
```

## 📌 Instalación y Configuración

### 1️⃣ Requisitos

- **Python 3.10 o superior**
- **MySQL o MariaDB** para las bases de datos
- **Cuenta Groq y API Key**

### 2️⃣ Clonar el proyecto

```bash
git clone https://github.com/TU_USUARIO/seo_url.git
cd seo_url
```

### 3️⃣ Instalar dependencias

Crea un entorno virtual si lo deseas, y luego instala las librerías necesarias:

```bash
pip install -r requirements.txt
```

**Ejemplo de `requirements.txt`:**

```
Flask
waitress
requests
beautifulsoup4
groq
faker
pymysql
```

> **⚠️ Importante:** Dependiendo de tu motor de base de datos, incluye el driver adecuado (e.g. pymysql, mysqlclient, etc.)

### 4️⃣ Configuración de variables sensibles

Configura tus accesos a base de datos y API Key de Groq en el archivo `db/config.py` o mediante variables de entorno.

**Ejemplo (no subir nunca a GitHub):**

```python
# db/config.py

Clave = "TU_API_KEY_GROQ"

DB_SEO = {
    "host": "localhost",
    "user": "usuario",
    "password": "password",
    "database": "seo_scraping"
}

DB_PRESTASHOP = {
    "host": "localhost",
    "user": "usuario",
    "password": "password",
    "database": "prestashop_db"
}
```

### 5️⃣ Ejecutar en desarrollo

Para desarrollo local:

```bash
python app.py
```

### 6️⃣ Ejecutar en producción

Usa Waitress para producción:

```bash
python start.py
```

## 🔗 Endpoints Principales

| Método | Endpoint                                               | Descripción                                       |
|--------|--------------------------------------------------------|---------------------------------------------------|
| `GET`  | `/`                                                    | Formulario para scrapear producto                 |
| `POST` | `/`                                                    | Procesa scraping de la URL introducida            |
| `POST` | `/generar_descripcion_larga`                           | Genera descripción larga con IA                   |
| `POST` | `/generar_meta_title`                                  | Genera meta title con IA                          |
| `POST` | `/generar_meta_description`                            | Genera meta description con IA                    |
| `POST` | `/generar_reseñas`                                     | Genera reseñas con IA                             |
| `POST` | `/guardar_datos_seo`                                   | Guarda datos SEO en base SEO y PrestaShop         |
| `GET`  | `/productos`                                           | Obtiene todos los productos registrados           |
| `PUT`  | `/producto/<id_product>`                               | Actualiza producto existente                      |
| `GET`  | `/producto/<id_product>/reseñas`                       | Obtiene reseñas de un producto en base SEO        |
| `GET`  | `/prestashop/reviews/producto/<id_product>`            | Obtiene reseñas de PrestaShop para un producto    |
| `POST` | `/prestashop/reviews/guardar`                          | Guarda reseñas en PrestaShop                      |
| `GET`  | `/prestashop/reviews/productos`                        | Lista productos con reseñas en PrestaShop         |

## 🏆 Beneficios del Proyecto

✅ **Automatización** de generación de contenido SEO.  
✅ **Sincronización** automática con PrestaShop.  
✅ **Interfaz fácil de usar** para editar productos y reseñas.  
✅ **Reducción de errores** en datos SEO gracias a IA.  
✅ **Escalabilidad** para adaptarse a otras tiendas o marketplaces.

## 📩 Contacto

Para más información o mejoras, puedes contactarme en:

- **GitHub:** [@TU_USUARIO](https://github.com/TU_USUARIO)
- **LinkedIn:** [Tu Nombre](https://www.linkedin.com/in/TU_PERFIL)
```