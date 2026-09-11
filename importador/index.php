<?php
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['fileToUpload'])) {
    $targetDir = "files/";
    $fileName = "data.csv"; // Un nombre fijo para sobrescribir el archivo existente
    $targetFile = $targetDir . $fileName;

    if (move_uploaded_file($_FILES["fileToUpload"]["tmp_name"], $targetFile)) {
        // Redirigir al archivo de procesamiento
        header('Location: process.php');
        exit;
    } else {
        echo "Hubo un error subiendo el archivo.";
    }
} else {
    // Mostrar el formulario HTML si no se está procesando una subida de archivo
    include('upload_form.html');
}
?>
