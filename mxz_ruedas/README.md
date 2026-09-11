# MXZ Ruedas

Módulo visual de PrestaShop que compone una configuración de ruedas sobre Canvas.

## Objetivo

Explorar combinaciones de modelo, aro, buje, radios y tuercas.

## Funcionalidades principales

- Selección de modelo y colores.
- Composición de imágenes por capas.
- Actualización de la vista y gestión de errores de carga.

## Arquitectura

El módulo registra CSS y JavaScript mediante el hook header. El controlador frontal asigna la ruta de recursos a Smarty. Canvas dibuja las capas; la selección permanece en el DOM.

## Tecnologías

PHP, PrestaShop, Smarty, JavaScript, Canvas 2D y CSS.

## Estructura

mxz_ruedas.php, controllers/front/display.php, views e img.

## Instalación

Copiar esta carpeta como modules/mxz_ruedas en una instalación de pruebas e instalar desde el gestor de módulos.
El código declara compatibilidad desde PrestaShop 1.7; no se ha ejecutado una matriz de versiones.

## Configuración

No necesita credenciales. Las imágenes se resuelven desde la ruta del módulo.
Revisar los derechos de los recursos gráficos antes de redistribuirlos.

## Ejecución

Abrir el controlador frontal display mediante el sistema de enlaces de módulos de PrestaShop.
Las selecciones posteriores descartan las cargas de imagen antiguas.

## Tests

Lint PHP y sintaxis JavaScript. La integración visual necesita revisión en PrestaShop.
No se han creado capturas ni conectado a una tienda.

## Seguridad

No contiene credenciales ni operaciones de pedido. La composición es local.
El script se incluye una sola vez mediante el hook.

## Limitaciones / entorno empresarial

**Solicitud de presupuesto:** no existe formulario de envío ni endpoint de presupuesto en el código conservado.
No se atribuyen integraciones inexistentes de correo o checkout.
La presentación debe revisarse con el tema de destino.
