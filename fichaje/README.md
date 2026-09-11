# Fichaje

Control horario con servicios de dominio y una suite extensa de pruebas sobre datos sintéticos.

## Objetivo

Control horario con servicios de dominio y una suite extensa de pruebas sobre datos sintéticos.

## Funcionalidades principales

- Inicio de sesión, roles y protección CSRF.
- Fichajes, horarios, sábados y ausencias.
- Edición administrativa y validación de conflictos.
- Exportación Excel/PDF.
- Tareas de avisos y autofichaje con guardas explícitas.

## Arquitectura

Flask y SQLAlchemy presentan rutas y modelos; app/services contiene las reglas. Los tests utilizan SQLite en memoria y nunca cargan la configuración de producción.

## Tecnologías

Python 3.11, Flask, Flask-Login, Flask-SQLAlchemy, Alembic, pandas, openpyxl, ReportLab y pytest.

## Estructura

app, config, migrations, tests, deploy/windows y scripts independientes.

## Instalación

Crear y activar un entorno Python 3.11 independiente. Instalar con python -m pip install -r requirements-runtime.lock. Para la suite usar requirements-dev.lock. Se conservan y comprueban los cierres de la fuente moderna.

## Configuración

.env.example enumera variables; no se carga automáticamente. Exportarlas al proceso. Desarrollo exige base local y cuenta fichaje_dev. Producción requiere DB_* y SECRET_KEY. Integraciones y autofichaje están desactivados por defecto.

## Ejecución

python run_dev.py exige MySQL local y FICHAJE_DEV_*. python run_server.py utiliza el perfil explícito FICHAJE_ENV. Para revisar sin infraestructura, ejecutar la suite SQLite; no hay servidor demo precargado.

## Tests

Desde la raíz: python -B tools/run_tests.py fichaje. Autenticación, CSRF, fichajes, ausencias, horarios, exportación y guardas. No se distribuyen procedimientos ligados a bases empresariales ni tareas específicas de una instalación.

## Seguridad

Solo se distribuyen ejemplos ficticios, sin credenciales ni datos de negocio. Las pruebas se ejecutan con red bloqueada. Ver [política común](../SECURITY.md).

## Limitaciones / entorno empresarial

Las migraciones conservadas son incrementales: presuponen un esquema previo, no una migración inicial universal. Los tests crean su esquema sintético con SQLAlchemy. Web Push necesita un productor externo de suscripciones. La rotación de secretos puede invalidar sesiones o suscripciones.
