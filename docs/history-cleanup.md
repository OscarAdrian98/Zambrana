# Retirada del historial sensible y publicación

## Estado de esta reconstrucción

La rama portfolio-rebuild-2026 parte de main y conserva los ancestros originales para permitir revisar el diff. **No debe publicarse como sustitución normal de main:** un merge o un push de esa rama conservaría la historia comprometida.

La referencia local de partida es:

~~~text
2ccb32f79b729f1c68b69387c12ec74ec754752f
~~~

No se ha consultado ni modificado el remoto durante la reconstrucción. La copia de trabajo fue clonada de una fuente local; su origin apunta a esa fuente local. Los comandos de publicación de esta guía usan la URL de GitHub explícitamente para evitar escribir en una copia operativa.

## Recomendación: publicar un snapshot sin ancestros

Para un portfolio, la opción más verificable es un commit raíz cuyo árbol sea exactamente el árbol saneado, sin padres. Esto elimina del historial publicado todos los archivos, configuraciones, compilados y versiones antiguas, sin depender de enumerar cada secreto.

Después de los commits y verificaciones locales se prepara la referencia **portfolio-clean-main** con git commit-tree, sin cambiar la rama de trabajo. No se hace push. Se deben comprobar:

~~~sh
git rev-list --count portfolio-clean-main
git rev-list --parents -n 1 portfolio-clean-main
git diff --exit-code portfolio-rebuild-2026 portfolio-clean-main
~~~

El primer comando debe indicar 1; el segundo debe contener solo el SHA del commit; el tercero debe terminar sin diferencias.

Esto **no borra el historial sensible de la copia de reconstrucción**, porque main, origin y la rama de trabajo siguen apuntando a sus ancestros. No compartir esa carpeta ni crear archivos bundle o mirror a partir de ella.

## Antes de cualquier publicación

1. Rotar o revocar los secretos expuestos y confirmar los consumidores actualizados.
2. Revisar el informe final, el árbol y los resultados de pruebas.
3. Confirmar los derechos sobre el código y los recursos gráficos indicados en NOTICE.
4. Confirmar que se quiere sustituir la historia anterior por el snapshot.
5. Revisar protecciones de ramas y las referencias que conservarían ancestros sensibles.
6. Mantener el repositorio privado durante el proceso.

## Publicación pendiente: comandos PowerShell

**No se han ejecutado. Requieren aprobación explícita posterior.**

Dentro de la copia de reconstrucción, usar la URL de GitHub; no el origin local:

~~~powershell
$remote = 'https://github.com/OscarAdrian98/Zambrana.git'
$approvedMain = '2ccb32f79b729f1c68b69387c12ec74ec754752f'
$line = git ls-remote $remote refs/heads/main
if ($LASTEXITCODE -ne 0 -or -not $line) {
    throw 'No se pudo verificar main en GitHub.'
}
$observedMain = ($line -split '\s+')[0]
if ($observedMain -ne $approvedMain) {
    throw 'main ha cambiado: revisar el nuevo estado antes de autorizar el reemplazo.'
}
git diff --exit-code portfolio-rebuild-2026 portfolio-clean-main
if ($LASTEXITCODE -ne 0) { throw 'El snapshot no coincide con el árbol revisado.' }
git push --force-with-lease="refs/heads/main:$approvedMain" $remote portfolio-clean-main:refs/heads/main
~~~

El lease vincula la sustitución al SHA revisado. No usar --force, --mirror ni actualizar automáticamente el SHA aprobado para hacer desaparecer un rechazo.

Después, comprobar con git ls-remote que main apunta al SHA de portfolio-clean-main y realizar una clonación nueva de GitHub para verificar árbol, historial y CI.

## Otras referencias y copias retenidas por GitHub

Sustituir main no basta si quedan ramas o tags con historia sensible. La fuente local mostraba también master y limpieza/estructura-repo. La lista **debe volver a consultarse y aprobarse**, porque puede haber cambiado.

~~~powershell
git ls-remote --heads --tags $remote
~~~

Por cada rama antigua confirmada para retirada, la operación aprobada debe usar su nombre y SHA revisados:

~~~powershell
# Plantilla; sustituir únicamente tras revisión y aprobación:
git push --force-with-lease="refs/heads/RAMA_ANTIGUA:SHA_REVISADO" $remote :refs/heads/RAMA_ANTIGUA
~~~

Los tags se revisan y retiran individualmente del mismo modo, utilizando refs/tags y el SHA de la referencia, no el de un objeto desreferenciado.

No crear una rama/tag “backup” en GitHub que siga reteniendo la historia comprometida. Las referencias de pull requests, cachés, forks y clones ajenos no quedan saneados con estos comandos. Solicitar a GitHub la retirada de vistas/referencias sensibles que sigan accesibles y coordinar clones nuevos con colaboradores.

No hacer público el repositorio hasta cerrar esta revisión. La rotación de secretos sigue siendo necesaria aunque el historial ya no sea visible.

## Alternativa si conservar la cronología fuera obligatorio

Usar un clon mirror **aislado y privado**, inventariar todas las refs y aplicar git-filter-repo sobre todos los caminos sensibles y sus variantes históricas: compilados, configuraciones, env reales, bases, archivos empresariales y binarios. Las credenciales que aparezcan en archivos que se conserven requieren reemplazos exactos provenientes de un archivo privado, nunca de este repositorio.

Después se deben volver a escanear todos los blobs alcanzables y revisar cada ref resultante antes de publicar. No se incluye una orden parcial de filtrado presentada como suficiente: los secretos no se limitaban a un único archivo ni a los últimos commits.

Esta alternativa no se ha ejecutado. El snapshot sin ancestros evita trasladar esos objetos al nuevo main y es la opción recomendada para este portfolio.
