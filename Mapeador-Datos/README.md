# Mapeador de Datos

## Descripción General

Este proyecto es un procesador de archivos Excel, diseñado para automatizar la conversión y el mapeo de datos según diferentes plantillas especificadas. Su función principal es procesar archivos Excel, CSV y otros formatos compatibles, aplicando transformaciones de datos específicas para adaptarlos a los requerimientos de diferentes sistemas o bases de datos.

## Características Principales

- **Interfaz Web**: Cuenta con una interfaz web para la carga y procesamiento de archivos.
- **Múltiples Plantillas**: Soporta varias plantillas de mapeo, como Polisport, Fox, Acerbis, FXR, y Prox.
- **Exportación Flexible**: Permite la exportación de datos procesados en formatos como Excel y ZIP, dependiendo del resultado del procesamiento.

## Tecnologías Utilizadas

- **HTML/CSS**: Para la estructura y diseño de la interfaz de usuario.
- **JavaScript y jQuery**: Para la interactividad del lado del cliente y la gestión de eventos.
- **Bootstrap**: Para el diseño responsivo y estilizado de la interfaz.
- **Python con Flask**: Servidor backend que maneja la lógica de procesamiento de archivos y las interacciones con la base de datos.
- **Pandas y Openpyxl**: Bibliotecas de Python utilizadas para el manejo y procesamiento de datos de Excel.
- **MySQL y SQL Server**: Bases de datos para almacenar información relacionada con los productos y el mapeo de datos.

## Estructura del Proyecto

El proyecto consta de varios componentes clave:
- **`index.php`**: Archivo principal de la interfaz de usuario que permite la carga y procesamiento de archivos.
- **`servidor.py`**: Script de Flask que expone la API para procesar archivos y realizar consultas a la base de datos.
- **`procesar_fichero.py`**: Módulo de Python que maneja el mapeo de archivos Excel a las plantillas especificadas.
- **`bd.py`**: Módulo de Python para la gestión de conexiones a las bases de datos MySQL y SQL Server.

## Instalación

1. Clona este repositorio en tu servidor local o remoto.
2. Asegúrate de tener Python instalado, y luego instala las dependencias con:
pip install -r requirements.txt

3. Configura las conexiones a las bases de datos editando los archivos de configuración correspondientes.
4. Inicia el servidor Flask con:
python servidor.py
5. Accede a la interfaz web a través de tu navegador en `http://localhost` o la dirección configurada en tu servidor.

## Uso

Para usar el procesador de archivos Excel:
1. Navega a la interfaz web.
2. Selecciona el archivo que deseas procesar.
3. Elige la plantilla de mapeo adecuada según tus necesidades.
4. Haz clic en "Procesar Archivo" y espera a que el sistema procese y descargue el resultado.

## Contribuciones

Las contribuciones a este proyecto son bienvenidas. Si deseas mejorar el procesador de archivos Excel o agregar nuevas características, por favor considera hacer fork del repositorio y enviar un pull request.

## Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo [LICENSE.md](LICENSE.md) para más detalles.

## Contacto

Para cualquier consulta técnica o colaboración, no dudes en contactarme:
- GitHub: [@OscarAdrian98](https://github.com/OscarAdrian98)
- LinkedIn: [Oscar Adrian](https://www.linkedin.com/in/oscar-adrian)
