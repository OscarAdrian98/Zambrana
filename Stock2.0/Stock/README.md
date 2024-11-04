# Zambrana

Este proyecto es una solución automatizada en Python para la sincronización y gestión de stock entre proveedores y una tienda online en PrestaShop. La herramienta realiza un proceso completo de descarga, análisis,
comparación y actualización de datos de stock y disponibilidad, lo cual permite mantener actualizada la información en la tienda de manera eficiente.

## Descripción

El programa sigue un flujo de trabajo automatizado para la actualización del stock y la disponibilidad de productos en PrestaShop, con los siguientes pasos principales:

1. **Descarga de Excel desde FTP de Proveedores**:
   - Accede al servidor FTP de los proveedores para descargar los archivos Excel con información de productos y stock actual.

2. **Lectura y Procesamiento de Datos**:
   - Los archivos Excel descargados se leen y se convierten en **dataframes** (tablas de datos) que son luego procesados y cargados en una base de datos personalizada para almacenar temporalmente la información de stock y fecha de disponibilidad de los productos.

3. **Conexión a Dos Bases de Datos**:
   - El sistema conecta con dos bases de datos distintas:
     - **Base de Datos de Stock**: Una base de datos creada específicamente para el proyecto, donde se almacenan todos los datos de referencias, tiempo de disponibilidad y stock de los proveedores.
     - **Base de Datos de PrestaShop**: La base de datos del sistema de la tienda de Zambrana en PrestaShop, donde se actualiza la información del stock y la disponibilidad de productos en la tienda online.

4. **Comparación y Actualización en PrestaShop**:
   - El programa compara las referencias de productos entre ambas bases de datos y, al encontrar coincidencias, aplica actualizaciones en PrestaShop, tales como:
     - **Etiquetado de Productos**: Añade etiquetas para indicar si el producto tiene stock o no.
     - **Fecha de Disponibilidad**: Actualiza la fecha de disponibilidad si está proporcionada.
     - **Permisos de Pedido**: Activa o desactiva la opción de realizar pedidos según la disponibilidad.
     - **Activación de Productos**: Activa o desactiva productos en función del stock.
     - **Gestión de Atributos de Talla**: Desactiva atributos de talla cuando no hay disponibilidad en dicha talla.

5. **Generación de Informe de Resumen**:
   - El programa crea un informe que resume todas las acciones realizadas durante el proceso.
   - Envía el informe por correo electrónico para llevar un registro de los cambios, permitiendo un control detallado de las actualizaciones realizadas en la base de datos de PrestaShop.

## Tecnologías Utilizadas

- **Python**: Lenguaje principal del proyecto.
- **Pandas**: Para la manipulación y análisis de datos a través de dataframes.
- **PyMySQL**: Librería para conectarse y operar con las bases de datos MySQL.
- **smtplib**: Librería para el envío de correos electrónicos con informes de resumen.
- **logging**: Librería para la gestión y creación de registros detallados de cada proceso.
- **Bases de Datos**: SQL para la base de datos de stock y la integración con PrestaShop.
- **FTP**: Protocolo utilizado para la descarga de archivos Excel desde los proveedores.

## Requisitos

- Python 3.x
- Librerías: `pandas`, `sqlalchemy`, `ftplib`, `smtplib`
- Acceso a las bases de datos de stock y PrestaShop
- Acceso FTP a los archivos de proveedores

## Uso

1. Configura el acceso a las bases de datos y el servidor FTP en el archivo de configuración.
2. Ejecuta el script principal para iniciar el proceso de descarga, análisis y actualización.
3. Revisa el informe que recibirás por correo para verificar los cambios aplicados.

## Autor

Este proyecto fue desarrollado por OscarAdrian98 para la gestión automática y optimizada de stock en la tienda de Zambrana en PrestaShop.

