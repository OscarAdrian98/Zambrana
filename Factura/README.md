# Factura

Aplicación de escritorio de facturación y gestión comercial, presentada como proyecto en evolución.

## Objetivo

Aplicación de escritorio de facturación y gestión comercial, presentada como proyecto en evolución.

## Funcionalidades principales

- Clientes, proveedores, productos, albaranes y facturas.
- Compras y panel financiero.
- PDF y preparación de remesas XML.
- Copias de seguridad y validación de licencia por instalación.

## Arquitectura

CustomTkinter presenta la interfaz. Los servicios encapsulan SQLite y generación de documentos. Las validaciones puras se prueban sin interfaz ni datos reales.

## Tecnologías

Python 3.11, CustomTkinter/Tkinter, SQLite, pandas, openpyxl, tkcalendar, ReportLab y pytest.

## Estructura

app/ui, app/services, app/database, app/utils, tests y main.py.

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

Exportar las variables al proceso; .env.example no se carga automáticamente. FACTURA_DATA_ROOT permite un directorio nuevo. FACTURA_LICENSE_SECRET proporciona la credencial externa. No se distribuyen licencias ni generadores privados.

## Ejecución

python main.py abre la interfaz y crea almacenamiento vacío. Sin licencia presenta activación. No se ejecutó la aplicación gráfica en esta reconstrucción ni se eludió la licencia.

## Tests

Desde la raíz: python -B tools/run_tests.py factura. Validaciones de campos, fechas, límites, importes y firma por entorno; sin emitir documentos ni abrir bases reales.

## Seguridad

Solo se distribuyen ejemplos ficticios, sin credenciales ni datos de negocio. Las pruebas se ejecutan con red bloqueada. Ver [política común](../SECURITY.md).

## Limitaciones / entorno empresarial

**VeriFactu no está implementado:** su módulo está vacío. No se declara conformidad normativa. IBAN tiene validación básica, no matemática completa. Documentos y remesas necesitan validación independiente. El dashboard fue adaptado de Qt al toolkit de la aplicación; su revisión visual está pendiente.
