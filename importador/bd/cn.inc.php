<?php
$serverName = getenv('SQLSERVER_HOST') ?: 'localhost';
$connectionInfo = [
    'Database' => getenv('SQLSERVER_DATABASE') ?: 'erp_example',
    'CharacterSet' => 'UTF-8',
    'UID' => getenv('SQLSERVER_USER') ?: '',
    'PWD' => getenv('SQLSERVER_PASSWORD') ?: '',
];
if ($connectionInfo['UID'] === '' || $connectionInfo['PWD'] === '' || $connectionInfo['PWD'] === 'change_me') {
    http_response_code(503);
    exit('Configure la conexión de integración.');
}
$conn = sqlsrv_connect($serverName, $connectionInfo);
if (!$conn) {
    http_response_code(503);
    exit('Conexión no disponible.');
}
