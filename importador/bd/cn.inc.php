<?php

$serverName = ""; # Base de datos
$connectionInfo = array( "Database"=>"database", "CharacterSet" => "UTF-8", "UID"=>"UID", "PWD"=>"PASSWORD");
$conn = sqlsrv_connect( $serverName, $connectionInfo);

if(!$conn) {
echo "No se pudo conectar.<br />";
die( print_r( sqlsrv_errors(), true));
}