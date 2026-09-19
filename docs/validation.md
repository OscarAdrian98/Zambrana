# Validación de la reconstrucción

## Entorno y alcance

Comprobaciones locales con Python 3.11, PHP 8.3 y Node.js. Cada aplicación con pruebas tiene un entorno virtual independiente. Se instalaron sus dependencias sin iniciar servidores, navegadores ni aplicaciones gráficas.

## Resultados

| Comprobación | Resultado |
|---|---|
| Fichaje | 858 pruebas aprobadas |
| Gestión de Pedidos | 8 pruebas aprobadas |
| Stock Sync | 23 pruebas aprobadas |
| Factura | 9 pruebas aprobadas |
| Total | **898 pruebas aprobadas** |
| Sintaxis PHP | 14 archivos, sin errores |
| Sintaxis JavaScript | 5 archivos, sin errores |
| JavaScript embebido | 17 scripts, sin errores |
| Dependencias de las cuatro suites | pip check sin incompatibilidades |

Fichaje muestra 20 avisos de deprecación relacionados con pandas, PyPDF2 y APIs de SQLAlchemy; no son fallos de prueba.

## Seguridad del árbol

Se revisan todos los archivos publicables con tools/check_repository.py: artefactos prohibidos, Python, JSON, patrones de credenciales, cadenas de entropía elevada, emails ajenos a ejemplos, rutas personales y direcciones internas. El resultado final debe ser cero hallazgos.

Además del escáner publicable, se realizó una comparación privada contra 13 valores sensibles conocidos, sin imprimirlos ni guardarlos en el repositorio. No se encontraron coincidencias. Esta comparación no es una afirmación de exhaustividad sobre secretos desconocidos.

Las imágenes seleccionadas del configurador son recursos funcionales, no ejecutables ni datos de pedidos. Su publicación como parte de este repositorio está confirmada.

## Reproducción

Activar el entorno de cada aplicación e instalar su requirements-dev.lock. Desde la raíz ejecutar:

~~~sh
python -B tools/run_tests.py fichaje
python -B tools/run_tests.py pedidos
python -B tools/run_tests.py stock
python -B tools/run_tests.py factura
~~~

Los comandos se ejecutan por separado con sus respectivos entornos.

~~~sh
python -B tools/check_repository.py
python -B tools/check_syntax.py
~~~

El segundo requiere php y node en PATH; permite --php y --node para rutas explícitas.

## CI

El workflow comprueba árbol y sintaxis en Ubuntu; las cuatro suites se ejecutan en Windows con Python 3.11 y cierres independientes. No utiliza secretos del proyecto ni inicia integraciones.

Se han ejecutado localmente sus comandos equivalentes. La [ejecución 2 de `Portfolio checks`](https://github.com/OscarAdrian98/Zambrana/actions/runs/34685671922) finalizó correctamente en GitHub Actions el 12 de septiembre de 2026 sobre `main`, para el commit `961dc36a2862e117900b6fe221a0ecf46075e379`.

## Límites de la validación

No hay validación contra MySQL, SQL Server, PrestaShop, SMTP, FTP, proveedores o producción. No se han ejecutado migraciones reales, GUI de Factura, Spark ni Selenium. No se han emitido facturas, remesas ni correos.

La instalación completa de los proyectos secundarios y la presentación visual de sus interfaces no se han probado. La documentación describe esas limitaciones; un lint correcto no demuestra funcionamiento de una integración.
