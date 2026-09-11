# Stock Sync · Stock Synchronization Platform

Generación actual del motor de sincronización de disponibilidad y variantes. Se conserva la carpeta histórica para facilitar la comparación.

## Objetivo

Generación actual del motor de sincronización de disponibilidad y variantes. Se conserva la carpeta histórica para facilitar la comparación.

## Funcionalidades principales

- Normalización de referencias, EAN y disponibilidad.
- Procesamiento por lotes y validación de fuentes.
- Variantes, marcas y huérfanos.
- Planificación de etiquetas.
- Trazabilidad, informes y resultados.
- Perfiles separados y autorizaciones de escritura.

## Arquitectura

Stock/main.py coordina procesamiento y planificación. main_operativo.py ofrece modos explícitos. config concentra conexiones, guardas, cifrado y resultados. Las reglas escalares y vectorizadas se prueban sin MySQL.

## Tecnologías

Python 3.11, pandas, PyMySQL, cryptography/Fernet, Paramiko, requests y pytest.

## Estructura

Stock/config, Stock/procesamiento, Stock/etiquetas y Stock/tests.

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

Usar .env.example como plantilla. STOCK_PROVIDER_IDS define el alcance: no se incluyen listas empresariales. Las cuentas y claves son externas. Los nombres de bases de ejemplo de config/bd.py y config/operativa.py deben mantenerse coherentes con el esquema de integración.

## Ejecución

Desde Stock: python main_operativo.py --report-only o --apply, solo en una integración autorizada. **--report-only puede persistir datos de proveedores y generar resultados; no es un dry-run sin efectos.** --apply exige además autorización de escritura.

## Tests

Desde la raíz: python -B tools/run_tests.py stock. Referencias con ceros iniciales, EAN, disponibilidad y equivalencia de reglas escalares/vectorizadas.

## Seguridad

Solo se distribuyen ejemplos ficticios, sin credenciales ni datos de negocio. Las pruebas se ejecutan con red bloqueada. Ver [política común](../SECURITY.md).

## Limitaciones / entorno empresarial

No se incluyen bases, catálogos, fuentes FTP ni resultados reales. El código valida un esquema externo; no se suministra una instalación empresarial completa. STOCK_OPEN_QUANTITY_PROVIDER_ID y STOCK_FTPS_PROVIDER_ID asignan capacidades especiales sin incluir identidades privadas. Rotar la clave maestra exige recifrar las contraseñas almacenadas.
