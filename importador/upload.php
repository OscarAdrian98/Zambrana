<?php
session_start();

$targetDir = "files/";  // Asegúrate de que esta carpeta exista y tenga permisos de escritura
$uploadStatus = 1;
$errorMessage = "";

if ($_SERVER["REQUEST_METHOD"] == "POST") {
    if (isset($_FILES["fileToUpload"]["name"]) && $_FILES["fileToUpload"]["name"] != '') {
        $fileName = basename($_FILES["fileToUpload"]["name"]);
        $targetFilePath = $targetDir . $fileName;
        $fileType = strtolower(pathinfo($targetFilePath, PATHINFO_EXTENSION));

        // Tipos de archivo permitidos
        $allowTypes = array('xlsx', 'xls', 'csv');
        if (in_array($fileType, $allowTypes)) {
            // Subir el archivo a la carpeta especificada
            if (move_uploaded_file($_FILES["fileToUpload"]["tmp_name"], $targetFilePath)) {
                // Guardar la ruta del archivo y las columnas seleccionadas en la sesión
                $_SESSION['filePath'] = realpath($targetFilePath); // Guardar la ruta absoluta del archivo
                $_SESSION['seasonColumn'] = htmlspecialchars($_POST['seasonColumn']);
                $_SESSION['productColumn'] = htmlspecialchars($_POST['productColumn']);

                // Redirigir a process.php para procesar el archivo
                header("Location: process.php");
                exit;
            } else {
                $uploadStatus = 0;
                $errorMessage = "Error al subir el archivo. Por favor, intenta de nuevo.";
            }
        } else {
            $uploadStatus = 0;
            $errorMessage = "Formato de archivo no permitido. Solo se aceptan archivos Excel (XLS, XLSX) y CSV.";
        }
    } else {
        $uploadStatus = 0;
        $errorMessage = "Por favor, selecciona un archivo para subir.";
    }
} else {
    $errorMessage = "No se recibió ningún formulario.";
}

if ($uploadStatus == 0) {
    echo "<p style='color:red;'>$errorMessage</p>";
}
?>
