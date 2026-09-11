# Buscador de Referencias

Prototipo de búsqueda en sitios externos con resultados progresivos y exportación.

## Objetivo

Prototipo de búsqueda en sitios externos con resultados progresivos y exportación.

## Funcionalidades principales

- Adaptadores Selenium/BeautifulSoup.
- Consultas concurrentes y resultados SSE.
- Exportación Excel/PDF.

## Arquitectura

FastAPI expone búsqueda y exportación. scraping.py agrupa adaptadores. Utiliza el navegador instalado, sin distribuir Chrome ni drivers.

## Tecnologías

Python 3.11, FastAPI, Selenium, BeautifulSoup, openpyxl, fpdf2 y PHP.

## Estructura

server.py, scraping.py, index.php y start_uvicorn.py.

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

Las consultas externas están desactivadas por defecto. SCRAPING_ENABLE_EXTERNAL=1 solo para un uso permitido. Selenium Manager puede descargar un controlador durante la primera ejecución autorizada.

## Ejecución

python -m uvicorn server:app --host 127.0.0.1 --port 8000. Servir PHP por separado y configurar el endpoint. No se han visitado sitios ni ejecutado el navegador en esta reconstrucción.

## Tests

Sintaxis Python/PHP. No se validaron los selectores contra sitios externos.

## Seguridad

Solo se distribuyen ejemplos ficticios, sin credenciales ni datos de negocio. Las pruebas se ejecutan con red bloqueada. Ver [política común](../SECURITY.md).

## Limitaciones / entorno empresarial

Los adaptadores dependen del HTML y las condiciones de uso de terceros. Respetar permisos, límites y privacidad. El adaptador interno fue neutralizado y requiere sustitución/configuración; no se afirma operatividad de todos los destinos.
