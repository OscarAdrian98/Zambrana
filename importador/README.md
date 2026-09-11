# Importador de Catálogo

Utilidad PHP para cargar archivos de catálogo y producir salidas de integración.

## Objetivo

Utilidad PHP para cargar archivos de catálogo y producir salidas de integración.

## Funcionalidades principales

- Carga con extensión permitida y límite de tamaño.
- Procesamiento y consultas MySQL.
- Exportación CSV.
- Muestra sintética mínima en examples/products.csv.

## Arquitectura

La carga guarda una ruta de trabajo en sesión y redirige al procesamiento. bd configura los adaptadores; PHP genera los resultados.

## Tecnologías

PHP 8.3, PDO MySQL, sqlsrv para el adaptador SQL Server, JavaScript y CSS.

## Estructura

upload.php, process.php, generate_excel.php, bd y examples.

## Instalación

Instalar PHP 8.3 con PDO MySQL. El adaptador SQL Server necesita sqlsrv y su controlador ODBC. No usa Python ni un requirements raíz.

## Configuración

Exportar .env.example al proceso PHP. Cargas y resultados deben quedar en directorios privados. No usar catálogos reales para la revisión.

## Ejecución

php -S localhost:8080 permite revisar el formulario local. Procesar/exportar exige una base configurada. No se proporciona un esquema empresarial completo.

## Tests

Lint PHP. No se ejecutaron importaciones ni escrituras de catálogo. La muestra ilustra formato, no garantiza compatibilidad con cualquier plantilla.

## Seguridad

Solo se distribuyen ejemplos ficticios, sin credenciales ni datos de negocio. Las pruebas se ejecutan con red bloqueada. Ver [política común](../SECURITY.md).

## Limitaciones / entorno empresarial

El formulario anuncia Excel y CSV; la compatibilidad efectiva debe comprobarse con el procesamiento existente. No incorpora autenticación completa: no exponer públicamente. El adaptador SQL Server requiere controlador externo.
