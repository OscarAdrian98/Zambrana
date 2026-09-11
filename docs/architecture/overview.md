# Arquitectura del portfolio

Los proyectos son aplicaciones independientes, no servicios que deban iniciarse juntos.

~~~mermaid
flowchart LR
  U[Interfaz web] --> GP[Gestión de Pedidos · FastAPI]
  GP --> S[Servicios y repositorios]
  S -. integración configurada .-> SQL[(SQL Server)]
  S -. integración configurada .-> MY[(MySQL)]
  F[Fichaje · Flask] --> FD[Servicios de dominio]
  FD --> FS[SQLAlchemy]
  FS -. producción configurada .-> MY
  T[Pruebas sintéticas] --> MEM[(SQLite en memoria)]
  ST[Stock Sync] --> R[Reglas y planificación]
  R --> TR[Trazabilidad y resultados]
  R -. integración autorizada .-> PS[PrestaShop]
  FC[Factura · CustomTkinter] --> FCDB[(SQLite local)]
  FC --> DOC[Generación de documentos]
~~~

Las líneas de integración no se recorren durante las pruebas del portfolio.

## Separación de responsabilidades

- Gestión de Pedidos: rutas HTTP, esquemas, servicios y repositorios.
- Fichaje: rutas y persistencia con servicios dedicados a fichajes, horarios, ausencias y permisos.
- Stock: lectura/normalización, reglas, planificación, aplicación y registro de resultados.
- Factura: interfaz, servicios, persistencia y generación de documentos.
- MXZ Ruedas: módulo/controlador PHP, plantilla Smarty y composición local Canvas.

## Límites

Los esquemas empresariales no forman un contrato público completo. Los repositorios conservan nombres de tablas y campos necesarios para entender el código, pero no contienen registros comerciales, credenciales ni servidores.

El portfolio no incorpora un despliegue conjunto ni una plataforma multiusuario común.
