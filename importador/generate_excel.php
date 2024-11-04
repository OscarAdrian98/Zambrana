<?php
session_start();
require 'bd/connection.php'; // Conexión a la base de datos

// Comprobar si la variable de sesión con la ruta del archivo está definida y el archivo existe
if (!isset($_SESSION['filePath']) || !file_exists($_SESSION['filePath'])) {
    die("Error: No se ha encontrado el archivo subido.");
}

$csvFilePath = $_SESSION['filePath']; // Ruta del archivo subido por el usuario

// Obtener los mapeos desde la sesión para Ambar
$seasonColumnMappedAmbar = isset($_SESSION['ambarMapping']['seasonColumn']) && !empty($_SESSION['ambarMapping']['seasonColumn']) ? strtoupper($_SESSION['ambarMapping']['seasonColumn']) : null;
$productColumnMappedAmbar = isset($_SESSION['ambarMapping']['productColumn']) && !empty($_SESSION['ambarMapping']['productColumn']) ? strtoupper($_SESSION['ambarMapping']['productColumn']) : null;
$gamaColumnMappedAmbar = isset($_SESSION['ambarMapping']['gamaColumn']) && !empty($_SESSION['ambarMapping']['gamaColumn']) ? strtoupper($_SESSION['ambarMapping']['gamaColumn']) : null;
$marcaColumnMappedAmbar = isset($_SESSION['ambarMapping']['marcaColumn']) && !empty($_SESSION['ambarMapping']['marcaColumn']) ? strtoupper($_SESSION['ambarMapping']['marcaColumn']) : null;

// Obtener los mapeos desde la sesión para Prestashop
$seasonColumnMappedPrestashop = isset($_SESSION['prestashopMapping']['seasonColumn']) && !empty($_SESSION['prestashopMapping']['seasonColumn']) ? strtoupper($_SESSION['prestashopMapping']['seasonColumn']) : null;
$productColumnMappedPrestashop = isset($_SESSION['prestashopMapping']['productColumn']) && !empty($_SESSION['prestashopMapping']['productColumn']) ? strtoupper($_SESSION['prestashopMapping']['productColumn']) : null;
$gamaColumnMappedPrestashop = isset($_SESSION['prestashopMapping']['gamaColumn']) && !empty($_SESSION['prestashopMapping']['gamaColumn']) ? strtoupper($_SESSION['prestashopMapping']['gamaColumn']) : null;
$marcaColumnMappedPrestashop = isset($_SESSION['prestashopMapping']['marcaColumn']) && !empty($_SESSION['prestashopMapping']['marcaColumn']) ? strtoupper($_SESSION['prestashopMapping']['marcaColumn']) : null;
$categoryColumnMappedPrestashop = isset($_SESSION['prestashopMapping']['categoryColumn']) && !empty($_SESSION['prestashopMapping']['categoryColumn']) ? strtoupper($_SESSION['prestashopMapping']['categoryColumn']) : null;
$sizeColumnMappedPrestashop = isset($_SESSION['prestashopMapping']['sizeColumn']) && !empty($_SESSION['prestashopMapping']['sizeColumn']) ? strtoupper($_SESSION['prestashopMapping']['sizeColumn']) : null;

// Obtener las diferencias desde la sesión para Ambar y Prestashop
$ambarDifferences = isset($_SESSION['ambarDifferences']) ? $_SESSION['ambarDifferences'] : [];
$prestashopDifferences = isset($_SESSION['prestashopDifferences']) ? $_SESSION['prestashopDifferences'] : [];
$categoryData = isset($_SESSION['categoryData']) ? $_SESSION['categoryData'] : []; // Datos de "CATEGORIAS" y "CARACTERISTICAS" de la base de datos plantilla_pro

// Función para verificar si un valor está en las diferencias sin modificar su capitalización
function checkDifferences($value, $differences) {
    return in_array($value, $differences, true) ? '' : $value;
}

// Leer el archivo CSV subido por el usuario y obtener datos mapeados, forzando a UTF-8
function readUploadedCSV($filePath) {
    $csvData = [];
    if (($handle = fopen($filePath, "r")) !== FALSE) {
        $headers = fgetcsv($handle, 1000, ";");

        // Convertir encabezados y filas a UTF-8 desde ISO-8859-1
        $headers = array_map(function($header) {
            return mb_convert_encoding($header, 'UTF-8', 'ISO-8859-1');
        }, $headers);

        while (($row = fgetcsv($handle, 1000, ";")) !== FALSE) {
            $row = array_map(function($value) {
                return mb_convert_encoding($value, 'UTF-8', 'ISO-8859-1');
            }, $row);
            $csvData[] = array_combine($headers, $row);
        }
        fclose($handle);
    }
    return $csvData;
}

// Leer el archivo CSV subido
$csvData = readUploadedCSV($csvFilePath);

$filteredAmbarData = [];
$filteredPrestashopData = [];
$filteredPsCombiData = []; // Aquí almacenaremos los datos filtrados para ps_combi

// Filtrar los datos del CSV según las coincidencias en las diferencias y en la base de datos
foreach ($csvData as $row) {
    // Filtrar para Ambar
    $filteredRowAmbar = [];
    $filteredRowAmbar['REF'] = $row['REF'] ?? '';
    $filteredRowAmbar['NOMBRE'] = $row['NOMBRE'] ?? '';
    $filteredRowAmbar['PROVEEDOR'] = $row['PROVEEDOR'] ?? '';
    $filteredRowAmbar['FAMILIA'] = $row['FAMILIA'] ?? '';
    $filteredRowAmbar['SUBFAMILIA'] = $row['SUBFAMILIA'] ?? '';
    $filteredRowAmbar['P.COMPRA'] = $row['P.COMPRA'] ?? '';
    $filteredRowAmbar['PVP (+IVA)'] = $row['PVP (+IVA)'] ?? '';
    $filteredRowAmbar['EAN'] = $row['EAN'] ?? '';
    $filteredRowAmbar['ALT 1'] = $row['ALT 1'] ?? '';
    $filteredRowAmbar['ALT 2'] = $row['ALT 2'] ?? '';
    $filteredRowAmbar['ALT 3'] = $row['ALT 3'] ?? '';
    $filteredRowAmbar['UNIDAD'] = $row['UNIDAD'] ?? '';
    $filteredRowAmbar['LOTE'] = $row['LOTE'] ?? '';
    $filteredRowAmbar['PESO'] = $row['PESO'] ?? '';
    $filteredRowAmbar['CODNC'] = $row['CODNC'] ?? '';

    // Para Mapeo MARCA AMBAR
    if ($marcaColumnMappedAmbar && isset($row[$marcaColumnMappedAmbar])) {
        $filteredRowAmbar['LIBRE1=MARCA'] = checkDifferences($row[$marcaColumnMappedAmbar], $ambarDifferences['marcaDifferences']);
    } else {
        $filteredRowAmbar['LIBRE1=MARCA'] = checkDifferences($row['LIBRE1=MARCA'] ?? '', $ambarDifferences['marcaDifferences']);
    }

    // Mapeo TEMPORADA AMBAR
    if ($seasonColumnMappedAmbar && isset($row[$seasonColumnMappedAmbar])) {
        $filteredRowAmbar['LIBRE2=TEMPORADA'] = checkDifferences($row[$seasonColumnMappedAmbar], $ambarDifferences['seasonDifferences']);
    } else {
        $filteredRowAmbar['LIBRE2=TEMPORADA'] = checkDifferences($row['LIBRE2=TEMPORADA'] ?? '', $ambarDifferences['seasonDifferences']);
    }

    // Mapeo PRODUCTO AMBAR
    if ($productColumnMappedAmbar && isset($row[$productColumnMappedAmbar])) {
        $filteredRowAmbar['LIBRE3=PRODUCTO'] = checkDifferences($row[$productColumnMappedAmbar], $ambarDifferences['productDifferences']);
    } else {
        $filteredRowAmbar['LIBRE3=PRODUCTO'] = checkDifferences($row['LIBRE3=PRODUCTO'] ?? '', $ambarDifferences['productDifferences']);
    }

    // Mapeo GAMA AMBAR
    if ($gamaColumnMappedAmbar && isset($row[$gamaColumnMappedAmbar])) {
        $filteredRowAmbar['LIBRE4=GAMA/MODELO'] = checkDifferences($row[$gamaColumnMappedAmbar], $ambarDifferences['gamaDifferences']);
    } else {
        $filteredRowAmbar['LIBRE4=GAMA/MODELO'] = checkDifferences($row['LIBRE4=GAMA/MODELO'] ?? '', $ambarDifferences['gamaDifferences']);
    }

    // Añadir la fila filtrada a los datos de Ambar
    $filteredAmbarData[] = $filteredRowAmbar;

    // Filtrar para Prestashop (ps_product)
    $filteredRowPrestashop = [];
    $filteredRowPrestashop['REF MADRE'] = $row['REF MADRE'] ?? '';
    $filteredRowPrestashop['REF FXR'] = $row['REF MADRE'] ?? ''; 
    $filteredRowPrestashop['REF OK'] = $row['REF MADRE'] ?? ''; // Valor pendiente de mapear
    $filteredRowPrestashop['EAN PRODUCT'] = $row['EAN PRODUCT'] ?? '';
    $filteredRowPrestashop['NOMBRE (SIN TALLA)'] = $row['NOMBRE (SIN TALLA)'] ?? '';

    // Mapeo MARCA PRESTASHOP
    if ($marcaColumnMappedPrestashop && isset($row[$marcaColumnMappedPrestashop])) {
        $filteredRowPrestashop['MARCA'] = checkDifferences($row[$marcaColumnMappedPrestashop], $prestashopDifferences['marcaDifferences']);
    } else {
        $filteredRowPrestashop['MARCA'] = checkDifferences($row['MARCA'] ?? '', $prestashopDifferences['marcaDifferences']);
    }

    // Mapeo PVP (+IVA)
    $filteredRowPrestashop['PVP +IVA'] = $row['PVP +IVA'] ?? '';

    // Mapeo ID IVA
    $filteredRowPrestashop['ID IVA'] = $row['ID IVA'] ?? ''; 

    // Mapeo CATEGORIAS
    $productCategoryKey = strtoupper(trim($row['PRODUCT CATEGORIA'] ?? ''));
    $filteredRowPrestashop['CATEGORIAS'] = $categoryData[$productCategoryKey]['categorias'] ?? '';

    // Construir CARACTERISTICAS manualmente con TEMPORADA, EDAD, GENERO, GAMA, y FILTROS
    $caracteristicas = [];

    // Agregar EDAD
    if (!empty($row['EDAD']) && !in_array(strtoupper($row['EDAD']), array_map('strtoupper', $prestashopDifferences['ageDifferences'] ?? []))) {
        $caracteristicas[] = 'Edad:' . $row['EDAD'];
    }

    // Agregar GENERO
    if (!empty($row['GENERO']) && !in_array(strtoupper($row['GENERO']), array_map('strtoupper', $prestashopDifferences['genderDifferences'] ?? []))) {
        $caracteristicas[] = mb_convert_encoding('Edad:' . $row['EDAD'], 'UTF-8', 'auto');
    }

    // Agregar TEMPORADA
    if (!empty($row['TEMPORADA']) && !in_array(strtoupper($row['TEMPORADA']), array_map('strtoupper', $prestashopDifferences['seasonDifferences'] ?? []))) {
        $caracteristicas[] = 'Temporada:' . $row['TEMPORADA'];
    }

    // Agregar GAMA
    if (!empty($row['GAMA']) && !in_array(strtoupper($row['GAMA']), array_map('strtoupper', $prestashopDifferences['gamaDifferences'] ?? []))) {
        $caracteristicas[] = 'Gama:' . $row['GAMA'];
    }

    // Agregar siempre "Productos:" seguido del valor de la columna "PRODUCT"
    if (!empty($row['PRODUCT']) && !in_array(strtoupper($row['PRODUCT']), array_map('strtoupper', $prestashopDifferences['productDifferences'] ?? []))) {
        $caracteristicas[] = 'Productos:' . $row['PRODUCT'];
    }

    // Agregar "Filtros:" seguido del valor en la columna "FILTROS" si está presente
    if (!empty($row['FILTROS'])) {
        $caracteristicas[] = 'Filtros:' . $row['FILTROS'];
    }

    // Unir todos los elementos con coma y asignar a CARACTERISTICAS
    $filteredRowPrestashop['CARACTERISTICAS'] = mb_convert_encoding(implode(',', $caracteristicas), 'UTF-8', 'auto');

    // Mapeo META-DESCRIPCION
    $filteredRowPrestashop['META-DESCRIPCION'] = $row['META-DESCRIPCION'] ?? '';

    // Mapeo URL IMGs
    $filteredRowPrestashop['URL IMGs'] = $row['URL IMGs'] ?? '';

    // Mapeo DESCRIPCION LARGA
    $filteredRowPrestashop['DESCRIPCION LARGA'] = $row['DESCRIPCION LARGA'] ?? '';

    // Mapeo dimensiones
    $filteredRowPrestashop['ANCHURA'] = $row['ANCHURA'] ?? ''; 
    $filteredRowPrestashop['ALTURA'] = $row['ALTURA'] ?? ''; 
    $filteredRowPrestashop['PROFUNDIDAD'] = $row['PROFUNDIDAD'] ?? ''; 
    $filteredRowPrestashop['PESO'] = $row['PESO'] ?? '';

    // Mapeo ID DISPONIBILIDAD
    $filteredRowPrestashop['ID DISPONIBILIDAD'] = $row['ID DISPONIBILIDAD'] ?? ''; 

    // Mapeo estado ACTIVO
    $filteredRowPrestashop['ACTIVO'] = $row['ACTIVO'] ?? ''; 

    // Mapeo DISP. PEDIDOS
    $filteredRowPrestashop['DISP. PEDIDOS'] = $row['DISP. PEDIDOS'] ?? '';

    $filteredPrestashopData[] = $filteredRowPrestashop;

    // Filtrar para ps_combi
    $filteredRowPsCombi = [];
    $filteredRowPsCombi['#'] = ''; // Se completará con un índice
    $filteredRowPsCombi['REF MADRE'] = $row['REF MADRE'] ?? '';
    $filteredRowPsCombi['REF COMBI'] = $row['REF COMBI'] ?? '';
    $filteredRowPsCombi['EAN COMBI'] = $row['EAN COMBI'] ?? '';
    $filteredRowPsCombi['NOMBRE COMBI:TIPO'] = $row['NOMBRE COMBI:TIPO'] ?? '';

    // Mapeo de TALLAS para ps_combi
    if ($sizeColumnMappedPrestashop && isset($row[$sizeColumnMappedPrestashop])) {
        $filteredRowPsCombi['TALLAS'] = checkDifferences($row[$sizeColumnMappedPrestashop], $prestashopDifferences['sizeDifferences']);
    } else {
        $filteredRowPsCombi['TALLAS'] = checkDifferences($row['TALLAS'] ?? '', $prestashopDifferences['sizeDifferences']);
    }

    $filteredPsCombiData[] = $filteredRowPsCombi;
}

// Función para generar el CSV de Ambar filtrado
function generateAmbarCSV($filteredData) {
    $headers = [
        'REF', 'NOMBRE', 'PROVEEDOR', 'FAMILIA', 'SUBFAMILIA', 'P.COMPRA', 'PVP S/IVA', 'EAN', 
        'ALT 1', 'ALT 2', 'ALT 3', 'UNIDAD', 'LOTE', 'PESO', 'CODNC', 
        'LIBRE1=MARCA', 'LIBRE2=TEMPORADA', 'LIBRE3=PRODUCTO', 'LIBRE4=GAMA/MODELO'
    ];

    header('Content-Type: text/csv; charset=UTF-8');
    header('Content-Disposition: attachment;filename=ambar.csv');
    $output = fopen('php://output', 'w');
    fprintf($output, "\xEF\xBB\xBF"); // Añadir BOM para UTF-8

    fputcsv($output, $headers, ';');
    foreach ($filteredData as $row) {
        $row = array_map(function($value) {
            return mb_convert_encoding($value, 'UTF-8', 'auto'); // Convertir cada valor a UTF-8
        }, $row);
        fputcsv($output, $row, ';');
    }
    fclose($output);
}

// Función para generar el CSV para Prestashop (ps_product)
function generatePrestashopCSV($filteredData) {
    $headers = [
        'REF MADRE', 'REF FXR', 'REF OK', 'EAN PRODUCT', 'NOMBRE (SIN TALLA)', 'MARCA', 'PVP (+IVA)', 
        'ID IVA', 'CATEGORIAS', 'CARACTERISTICAS', 'META-DESCRIPCION', 'URL IMGs', 'DESCRIPCION LARGA', 
        'ANCHURA', 'ALTURA', 'PROFUNDIDAD', 'PESO', 'ID DISPONIBILIDAD', 'ACTIVO', 'DISP. PEDIDOS'
    ];

    // Enviar cabeceras con codificación UTF-8
    header('Content-Type: text/csv; charset=UTF-8');
    header('Content-Disposition: attachment;filename=ps_product.csv');
    
    // UTF-8 BOM para asegurar la correcta visualización de caracteres especiales en Excel
    $output = fopen('php://output', 'w');
    fprintf($output, "\xEF\xBB\xBF"); // Añade el BOM al inicio del archivo

    // Escribir los encabezados
    fputcsv($output, $headers, ';');

    // Escribir los datos
    foreach ($filteredData as $row) {
        // Convertir cada valor de la fila a UTF-8
        $row = array_map(function($value) {
            return mb_convert_encoding($value, 'UTF-8', 'auto');
        }, $row);

        fputcsv($output, $row, ';');
    }

    fclose($output);
}

// Función para generar el CSV para Prestashop (ps_combi)
function generatePsCombiCSV($filteredData) {
    $headers = [
        '#', 'REF MADRE', 'REF COMBI', 'EAN COMBI', 'NOMBRE COMBI:TIPO', 'TALLAS'
    ];

    header('Content-Type: text/csv');
    header('Content-Disposition: attachment;filename=ps_combi.csv');
    $output = fopen('php://output', 'w');
    fputcsv($output, $headers, ';');

    // Agregar un índice numérico en la primera columna
    $index = 1;
    foreach ($filteredData as &$row) {
        $row['#'] = $index;
        fputcsv($output, $row, ';');
        $index++;
    }

    fclose($output);
}

// Generar solo uno de los archivos según el tipo de descarga
if (isset($_GET['file']) && $_GET['file'] === 'ambar') {
    generateAmbarCSV($filteredAmbarData);
} elseif (isset($_GET['file']) && $_GET['file'] === 'prestashop') {
    generatePrestashopCSV($filteredPrestashopData);
} elseif (isset($_GET['file']) && $_GET['file'] === 'ps_combi') {
    generatePsCombiCSV($filteredPsCombiData);
} else {
    echo "Error: Tipo de archivo no especificado.";
}
?>
