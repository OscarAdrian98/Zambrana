# Gestión de Pedidos

Aplicación web para consultar pedidos de comercio electrónico, contrastarlos con un ERP y coordinar tareas de gestión.

## Objetivo

Aplicación web para consultar pedidos de comercio electrónico, contrastarlos con un ERP y coordinar tareas de gestión.

## Funcionalidades principales

- Consulta y filtrado de pedidos.
- Validación de clientes y resolución de países.
- Comparación de referencias y comprobación de stock.
- Anticipos, integración de estados y composición de correos.

## Arquitectura

FastAPI organiza rutas, esquemas Pydantic, servicios y repositorios. Jinja2 sirve las pantallas; JavaScript actualiza la interfaz. Los adaptadores de datos separan MySQL y SQL Server.

## Tecnologías

Python 3.11, FastAPI, Pydantic Settings, Jinja2, JavaScript, aiomysql y pyodbc.

## Estructura

app/routes, app/services, app/repositories, app/schemas, app/db, templates, static y tests.

## Instalación

Crear y activar un entorno independiente con Python 3.11:

~~~sh
python -m venv .venv
# Windows PowerShell: .venv/Scripts/Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
~~~

Para las pruebas, instalar también requirements-dev.txt cuando exista. No compartir entornos entre aplicaciones.

## Configuración

Copiar .env.example a .env y completar solo un entorno autorizado. APP_ENV_FILE selecciona otro archivo; las variables del proceso tienen prioridad. APP_READ_ONLY=true es el valor predeterminado.

## Ejecución

python run_server.py inicia Uvicorn y trata de conectar con las bases configuradas. No es una demo autónoma. No ejecutarlo con credenciales reales durante una revisión del código.

## Tests

Desde la raíz, con el entorno de este proyecto activado: python -B tools/run_tests.py pedidos. Normalización, resolución de países, perfiles fiscales y configuración segura.

## Seguridad

Solo se distribuyen ejemplos ficticios, sin credenciales ni datos de negocio. Las pruebas se ejecutan con red bloqueada. Ver [política común](../SECURITY.md).

## Limitaciones / entorno empresarial

Los esquemas de ERP/B2B y los datos de integración son externos. Las reglas fiscales reflejan el código y requieren validación por instalación. Cambiar estados, anticipos o enviar correos tiene efectos externos. No hay autenticación de usuarios completa: desplegar detrás de control de acceso.
