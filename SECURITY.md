# Seguridad

## Credenciales y datos

No introducir contraseñas, tokens, claves de firma, licencias, webhooks, conexiones con credenciales ni datos de negocio. Mantener los valores en el entorno del proceso o en almacenes privados. Solo se versionan plantillas explícitas como .env.example.

Una credencial publicada debe revocarse o rotarse en su servicio. Borrar el archivo, limpiar el último commit o hacer privado el repositorio no invalida el secreto.

## Reporte

Usar la opción privada de reporte de vulnerabilidades de GitHub si está habilitada. Si no lo está, contactar al propietario mediante los canales de su perfil y solicitar un canal privado. No adjuntar secretos, datos personales ni una prueba contra sistemas reales en un issue público.

Describir el componente, las condiciones de reproducción y el impacto utilizando datos sintéticos.

## Verificación

- tools/check_repository.py revisa el árbol por tipos de archivo, sintaxis Python, patrones de credenciales, entropía y datos internos.
- tools/run_tests.py bloquea sockets y resolución de red en las suites y sus subprocesos Python que conservan el entorno del runner.
- Las pruebas no deben ejecutar lanzadores operativos, navegadores ni adaptadores reales.
- El escáner es una defensa adicional: un resultado limpio no demuestra ausencia absoluta de secretos ni derechos de redistribución.

## Despliegue

Configurar autenticación, autorización, TLS, orígenes CORS, límites de carga y permisos de bases antes de cualquier exposición. Las aplicaciones que no incorporan autenticación completa deben permanecer detrás de un control de acceso externo.

Stock --report-only puede escribir en almacenamiento de proveedores. Fichaje tiene tareas con efectos de negocio. Factura puede producir documentos y remesas. Ninguno de esos flujos se utiliza como prueba contra sistemas reales en CI.

## Historial

Los ancestros anteriores a la reconstrucción contienen material sensible. No publicar la rama de trabajo ni sus tags por comodidad. Revisar docs/history-cleanup.md y publicar únicamente una historia saneada después de rotar credenciales.
