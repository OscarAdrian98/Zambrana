<?
if (isset($cnMySQL))
    $cnMySQL->close();

if (isset($conn))
    sqlsrv_close($conn);