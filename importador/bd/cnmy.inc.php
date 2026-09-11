<?
// Configuracion local de MySQL.
$cnMySQL = new mysqli("", "", "");
if (!$cnMySQL) { die($cnMySQL->error);}
mysqli_select_db($cnMySQL, "base de datos") or die($cnMySQL->error);
