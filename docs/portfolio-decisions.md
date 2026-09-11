# Selección y saneamiento

## Criterio

Se seleccionaron archivos de código mediante listas permitidas. No se copiaron entornos, datos, informes operativos ni configuraciones reales. docs/source-manifest.json registra las rutas relativas seleccionadas de las fuentes; algunos archivos fueron sustituidos o retirados durante el saneamiento posterior.

## Proyectos actualizados

- Gestión de Pedidos: versión moderna con servicios adicionales, correo y estado interno.
- Fichaje: versión moderna con servicios, migraciones incrementales y pruebas SQLite.
- Stock Sync: lógica de la generación actual, conservando Stock2.0 como ruta histórica.
- Factura: únicamente código y configuración ejemplo; sin base, licencias, remesas ni documentos.

Inventario, Mapeador, Importador, Buscador de Referencias y MXZ Ruedas se mantienen como proyectos secundarios o componentes con limitaciones explícitas.

## Exclusiones

SEO no se incluye: la generación de reseñas ficticias estaba entrelazada con su publicación como opiniones. No se presenta ese comportamiento como una funcionalidad editorial.

No se incorporan bots de trading, descargadores operativos sueltos, colecciones de scripts, variantes antiguas del configurador ni ejercicios. Sus fuentes originales no se modificaron.

Se retiran de la distribución los runbooks de instalaciones privadas, tareas Windows específicas y runners de bases externas. Las pruebas de dominio que usan SQLite permanecen incluso cuando su nombre incluye “integration”: la ejecución efectiva se verifica mediante el runner sin red.

## Cambios localizados

- Configuración por entorno y plantillas ficticias.
- Firma de licencia de Factura sin semilla incrustada ni bypass.
- Dashboard de Factura adaptado al toolkit del resto de la interfaz.
- Credencial web de Inventario sustituida por un hash externo.
- Debug desactivado y CORS configurado explícitamente.
- Listas de proveedores de Stock retiradas de la distribución.
- Enlaces y marca de la instalación sustituidos por ejemplos.
- Corrección de la carga duplicada y de carreras de imágenes en Canvas.

## Qué no se afirma

No se declara que una integración real haya sido ejecutada, que VeriFactu esté implementado, que el configurador envíe presupuestos ni que las aplicaciones secundarias incluyan autenticación completa.
