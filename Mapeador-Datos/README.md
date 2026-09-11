# Mapeador de Datos

Transformación de hojas de cálculo a plantillas de integración mediante PHP y una API Python.

## Objetivo

Transformación de hojas de cálculo a plantillas de integración mediante PHP y una API Python.

## Funcionalidades principales

- Vista previa de hojas.
- Selección de plantillas y transformación.
- Cruce de referencias con bases externas.
- Generación de resultados y seguimiento de progreso.

## Arquitectura

frontend-servidor/index.php consume Flask en servidor/servidor.py. procesar/procesar_fichero.py concentra las transformaciones; bd separa MySQL y SQL Server.

## Tecnologías

PHP 8.3, Python 3.11, Flask, pandas, openpyxl, pyodbc, mysql-connector-python y deep-translator.

## Estructura

frontend-servidor, servidor, procesar y bd.

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

Exportar .env.example. La traducción externa está desactivada salvo MAPPER_ALLOW_TRANSLATION=1. Configurar el endpoint del frontend y CORS para la instalación. No se incluyen hojas comerciales.

## Ejecución

python servidor/servidor.py. Servir PHP por separado. El servidor se enlaza a localhost y tiene debug desactivado.

## Tests

Verificación estática Python/PHP. No se afirma cobertura funcional de cruces ni de traducción externa.

## Seguridad

Solo se distribuyen ejemplos ficticios, sin credenciales ni datos de negocio. Las pruebas se ejecutan con red bloqueada. Ver [política común](../SECURITY.md).

## Limitaciones / entorno empresarial

El progreso global pertenece al proceso, no a una cola multiusuario. Las plantillas dependen de esquemas externos. Requiere control de acceso; no se presenta como servicio público listo para desplegar.
