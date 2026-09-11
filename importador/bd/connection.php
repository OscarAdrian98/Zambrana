<?php
$host = getenv('MYSQL_HOST') ?: 'localhost';
$port = getenv('MYSQL_PORT') ?: '3306';
$dbname = getenv('MYSQL_DATABASE') ?: 'prestashop_example';
$username = getenv('MYSQL_USER') ?: '';
$password = getenv('MYSQL_PASSWORD') ?: '';
if ($username === '' || $password === '' || $password === 'change_me') {
    http_response_code(503);
    exit('Configure la conexión de integración.');
}
try {
    $conn = new PDO("mysql:host=$host;port=$port;dbname=$dbname;charset=utf8mb4", $username, $password, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
} catch (PDOException $e) {
    error_log('Fallo de conexión MySQL.');
    http_response_code(503);
    exit('Conexión no disponible.');
}
