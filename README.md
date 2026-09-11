# Zambrana · Portfolio de desarrollo

Aplicaciones de gestión, automatización e integración de datos desarrolladas con Python, PHP y JavaScript. Este repositorio reúne código seleccionado y saneado: las configuraciones publicables son ejemplos y las pruebas utilizan datos sintéticos.

## Proyectos destacados

| Proyecto | Problema y arquitectura | Aspectos técnicos |
|---|---|---|
| [Gestión de Pedidos](Gestion-Pedidos/) | FastAPI y Jinja2 para coordinar pedidos entre comercio electrónico y ERP; rutas, servicios y repositorios separados. | MySQL/SQL Server, validación de clientes, matching, anticipos y pruebas de lógica de dominio. |
| [Fichaje](fichaje/) | Flask y SQLAlchemy para control horario, ausencias y administración. | Servicios de dominio, CSRF, validaciones de conflictos, migraciones incrementales y suite SQLite extensa. |
| [Stock Sync](Stock2.0/) | Motor actual de sincronización de disponibilidad y variantes con PrestaShop. | pandas, reglas vectorizadas, trazabilidad, planificación por lotes, guardas y pruebas sin conexiones externas. |
| [Factura](Factura/) | Aplicación de escritorio con CustomTkinter y SQLite para documentos comerciales. | Servicios, PDF, remesas, validaciones y pruebas puras. Proyecto en evolución: VeriFactu no implementado. |
| [MXZ Ruedas](mxz_ruedas/) | Configurador visual integrado como módulo PrestaShop. | PHP/Smarty, Canvas y composición asíncrona de imágenes. No incluye envío de presupuestos. |

## Perfil técnico

El trabajo se centra en aplicaciones de gestión, integración entre sistemas y automatización de procesos. Incluye separación de responsabilidades, validación de entradas, normalización de datos, adaptadores de persistencia y tratamiento de errores.

**Tecnologías presentes:** Python, Flask, FastAPI, SQLAlchemy, Pydantic, PHP, PrestaShop, JavaScript, Jinja2/Smarty, Canvas, MySQL, SQL Server, SQLite y pandas. Las interfaces gráficas usan CustomTkinter; las herramientas de análisis incluyen Spark y Selenium.

## Otros proyectos

- [Inventario](Inventario/): panel PHP, API SQL Server y análisis Spark.
- [Mapeador de Datos](Mapeador-Datos/): transformación de hojas mediante PHP y una API Flask.
- [Importador](importador/): procesamiento y exportación de catálogo con una muestra sintética.
- [Buscador de Referencias](scraping_ref/): prototipo Selenium/FastAPI; integraciones externas desactivadas por defecto.

## Cómo revisar el repositorio

Cada proyecto tiene instalación, configuración, ejecución, pruebas y limitaciones en su README. Las aplicaciones utilizan **entornos independientes**: no hay un requirements global que mezcle dependencias.

La lógica automatizada se comprueba desde la raíz con el entorno del proyecto activado:

~~~sh
python -B tools/check_repository.py
python -B tools/run_tests.py fichaje
# Alternativas con su entorno correspondiente: pedidos, stock, factura
~~~

[Arquitectura general](docs/architecture/overview.md) · [Validación realizada](docs/validation.md) · [Decisiones de selección](docs/portfolio-decisions.md)

## Integraciones y seguridad

Las integraciones empresariales requieren esquemas e infraestructura privados que no se distribuyen. No se incluyen datos de clientes, pedidos, facturas, catálogos, credenciales ni resultados operativos. Las muestras son mínimas y ficticias.

Las pruebas bloquean conexiones de red y usan SQLite en memoria, datos sintéticos o funciones puras. Las tareas operativas no se ejecutan en CI. Las aplicaciones secundarias necesitan control de acceso de despliegue; no se presentan como servicios públicos preparados para producción.

[Política de seguridad](SECURITY.md) · [Contexto de derechos y recursos](NOTICE)

Este árbol saneado no implica que los ancestros Git sean seguros. El procedimiento de publicación y retirada del historial anterior se mantiene separado en [la guía de historial](docs/history-cleanup.md).
