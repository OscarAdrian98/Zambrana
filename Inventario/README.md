# Inventario

Panel PHP con API de consulta SQL Server y análisis de ventas mediante Spark.

## Objetivo

Panel PHP con API de consulta SQL Server y análisis de ventas mediante Spark.

## Funcionalidades principales

- Consultas de ventas, compras, vencimientos y stock.
- Exportación de resultados.
- Análisis separado con PySpark.
- Acceso PHP mediante un hash de contraseña externo.

## Arquitectura

PHP presenta el panel; main.py sirve FastAPI. analisis.py usa Spark y consulta la API principal. bd adapta SQL Server.

## Tecnologías

PHP 8.3, Python 3.11, FastAPI, pyodbc, pandas, PySpark 3.5 y Java compatible con Spark.

## Estructura

index.php, main.py, analisis.py, bd y start_uvicorn.py.

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

Exportar .env.example a Python/PHP. Generar INVENTARIO_PASSWORD_HASH con password_hash de PHP y mantenerlo fuera del repositorio. Configurar URLs y orígenes CORS. Spark utiliza el intérprete actual.

## Ejecución

API: python start_uvicorn.py. Análisis opcional: python -m uvicorn analisis:app --host 127.0.0.1 --port 5003. PHP local: php -S localhost:8080. Requiere infraestructura de integración y Java para análisis; CI no ejecuta estos comandos.

## Tests

Sintaxis Python y PHP. No existe suite funcional ni se han consultado bases.

## Seguridad

Solo se distribuyen ejemplos ficticios, sin credenciales ni datos de negocio. Las pruebas se ejecutan con red bloqueada. Ver [política común](../SECURITY.md).

## Limitaciones / entorno empresarial

El acceso PHP no autentica los endpoints Python. Los backends deben permanecer restringidos o detrás de un proxy autenticado. Importar analisis.py inicia Spark; el chequeo estático no lo importa. SQL Server y su esquema son externos.
