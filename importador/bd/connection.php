<?php
// Configuración de los parámetros de la base de datos
$host = '1';  // Aquí va el host de la base de datos
$port = '';  // Aquí va el puerto de la base de datos, por ejemplo, 3306 para MySQL
$dbname = '';  // Aquí va el nombre de la base de datos
$username = '';  // Aquí va el usuario de la base de datos
$password = '';  // Aquí va la contraseña del usuario de la base de datos

// Crear la cadena de conexión
$dsn = "mysql:host=$host;port=$port;dbname=$dbname";

try {
    // Crear el objeto PDO para la conexión
    $conn = new PDO($dsn, $username, $password);
    $conn->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    // Comenta o elimina la siguiente línea para evitar el problema con session_start()
    // echo "Conexión exitosa a la base de datos";
} catch (PDOException $e) {
    // En lugar de hacer echo, considera registrar este error en un log:
    error_log("Error de conexión: " . $e->getMessage());
    // O puedes manejar el error de una forma que no interfiera, por ejemplo:
    die("No se puede conectar a la base de datos, inténtelo más tarde.");
}

// Puedes utilizar $conn para realizar tus operaciones en la base de datos
?>
