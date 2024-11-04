<?
//$cnMySQL = new mysqli("127.0.0.1", "root", "rootzambra");
$cnMySQL = new mysqli("", "", "");
if (!$cnMySQL) { die($cnMySQL->error);}
mysqli_select_db($cnMySQL, "base de datos") or die($cnMySQL->error);