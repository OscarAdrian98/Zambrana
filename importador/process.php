<?php
// Mostrar errores para depuración (puedes comentarlo en producción)
error_reporting(E_ALL);
ini_set('display_errors', 1);

require 'bd/connection.php'; // Conexión a la base de datos principal

// Crear una conexión adicional para la base de datos "plantilla_pro" usando las mismas credenciales pero diferente nombre de base de datos
$dbname_pro = 'plantilla_pro'; // Cambia solo el nombre de la base de datos

try {
    $connPlantillaPro = new PDO("mysql:host=$host;port=$port;dbname=$dbname_pro", $username, $password);
    $connPlantillaPro->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch(PDOException $e) {
    echo "Error de conexión a plantilla_pro: " . $e->getMessage();
    exit;
}

session_start();
header('Content-Type: application/json');

// Verificar si se usa mapeo predefinido
$usePredefinedMapping = isset($_POST['usePredefinedMapping']);

// Guardar los mapeos en la sesión
if ($usePredefinedMapping) {
    // Mapeo predefinido
    $_SESSION['ambarMapping'] = [
        'seasonColumn' => 'av', // Temporada Ambar
        'productColumn' => 'aw', // Producto Ambar
        'gamaColumn' => 'ax', // Gama Ambar
        'marcaColumn' => 'au' // Marca Ambar
    ];

    $_SESSION['prestashopMapping'] = [
        'seasonColumn' => 'w', // Temporada Prestashop
        'productColumn' => 'l', // Product Prestashop
        'gamaColumn' => 'j', // Gama Prestashop
        'marcaColumn' => 'd', // Marca Prestashop
        'categoryColumn' => 'h', // Categoria Prestashop
        'sizeColumn' => 'x', // Talla Prestashop
        'genderColumn' => 'y', // Genero Prestashop
        'ageColumn' => 'z' // Edad Prestashop
    ];
} else {
    // Guardar mapeos de Ambar
    $_SESSION['ambarMapping'] = [
        'seasonColumn' => isset($_POST['ambarSeasonColumn']) ? $_POST['ambarSeasonColumn'] : '',
        'productColumn' => isset($_POST['ambarProductColumn']) ? $_POST['ambarProductColumn'] : '',
        'gamaColumn' => isset($_POST['ambarGamaColumn']) ? $_POST['ambarGamaColumn'] : '',
        'marcaColumn' => isset($_POST['ambarMarcaColumn']) ? $_POST['ambarMarcaColumn'] : ''
    ];

    // Guardar mapeos de Prestashop
    $_SESSION['prestashopMapping'] = [
        'seasonColumn' => isset($_POST['prestashopSeasonColumn']) ? $_POST['prestashopSeasonColumn'] : '',
        'productColumn' => isset($_POST['prestashopProductColumn']) ? $_POST['prestashopProductColumn'] : '',
        'gamaColumn' => isset($_POST['prestashopGamaColumn']) ? $_POST['prestashopGamaColumn'] : '',
        'marcaColumn' => isset($_POST['prestashopMarcaColumn']) ? $_POST['prestashopMarcaColumn'] : '',
        'categoryColumn' => isset($_POST['prestashopCategoryColumn']) ? $_POST['prestashopCategoryColumn'] : '',
        'sizeColumn' => isset($_POST['prestashopSizeColumn']) ? $_POST['prestashopSizeColumn'] : '',
        'genderColumn' => isset($_POST['prestashopGenderColumn']) ? $_POST['prestashopGenderColumn'] : '',
        'ageColumn' => isset($_POST['prestashopAgeColumn']) ? $_POST['prestashopAgeColumn'] : ''
    ];
}

// Insertar datos en la base de datos
if (isset($_POST['type'], $_POST['value'], $_POST['system'])) {
    $type = $_POST['type'];
    $value = $_POST['value'];
    $system = $_POST['system'];

    // Determinar la tabla según el tipo de dato y sistema
    if ($type === 'categoria' && $system === 'prestashop') {
        $table = 'ps_categorias';
        $sql = "INSERT INTO $table (categoria) VALUES (?)";
    } elseif ($type === 'tallas' && $system === 'prestashop') {
        $table = 'ps_tallas';
        $sql = "INSERT INTO $table (talla) VALUES (?)";
    } else {
        $table = $system === 'prestashop' ? 'ps_caracteristicas' : 'am_libres';
        $sql = "INSERT INTO $table (tipo, valor) VALUES (?, ?)";
    }

    $stmt = $conn->prepare($sql);

    if (($type === 'categoria' || $type === 'tallas') && $system === 'prestashop') {
        $success = $stmt->execute([$value]);
    } else {
        $success = $stmt->execute([strtolower($type), $value]);
    }

    echo json_encode(['success' => $success, 'message' => $success ? "El dato '$value' ha sido añadido correctamente." : "Error: " . implode(', ', $stmt->errorInfo())]);
    exit;
}

// Procesamiento del archivo CSV o Excel
if (isset($_FILES['fileToUpload']) && $_FILES['fileToUpload']['error'] == UPLOAD_ERR_OK) {
    $targetDir = "files/";
    $fileName = basename($_FILES["fileToUpload"]["name"]);
    $filePath = $targetDir . $fileName;

    if (move_uploaded_file($_FILES["fileToUpload"]["tmp_name"], $filePath)) {
        $_SESSION['filePath'] = $filePath;
    } else {
        echo json_encode(['success' => false, 'message' => 'Error al mover el archivo subido.']);
        exit;
    }
} elseif (isset($_SESSION['filePath']) && file_exists($_SESSION['filePath'])) {
    $filePath = $_SESSION['filePath'];
} else {
    echo json_encode(['success' => false, 'message' => 'No se encontró ningún archivo para procesar.']);
    exit;
}

// Procesar archivo y obtener datos de "PRODUCT CATEGORIA"
if (($handle = fopen($filePath, "r")) !== FALSE) {
    $headers = fgetcsv($handle, 0, ";");

    // Encontrar índice de "PRODUCT CATEGORIA"
    $productCategoryIndex = array_search("PRODUCT CATEGORIA", $headers);
    if ($productCategoryIndex === false) {
        echo json_encode(['success' => false, 'message' => 'No se encontró la columna "PRODUCT CATEGORIA".']);
        exit;
    }

    // Recoger valores de "PRODUCT CATEGORIA"
    $productCategories = [];
    while (($row = fgetcsv($handle, 0, ";")) !== FALSE) {
        if (isset($row[$productCategoryIndex])) {
            $productCategories[] = mb_strtoupper(trim($row[$productCategoryIndex]));
        }
    }

    // Extraer "categorias_producto" y "caracteristicas_producto" de "plantilla_pro"
    $categoryData = [];
    foreach ($productCategories as $productKey) {
        $stmt = $connPlantillaPro->prepare("SELECT categorias_producto FROM productos WHERE clave_producto = ?");
        $stmt->execute([$productKey]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($row) {
            $categoryData[$productKey] = [
                'categorias' => $row['categorias_producto'],
                //'caracteristicas' => $row['caracteristicas_producto']
            ];
        }
    }

    // Guardar datos en la sesión para usar en generate_excel.php
    $_SESSION['categoryData'] = $categoryData;

    // Función para convertir letras de columna de Excel a índices de columna
    function columnLetterToIndex($columnLetter) {
        $columnLetter = strtoupper($columnLetter);
        $length = strlen($columnLetter);
        $index = 0;
        for ($i = 0; $i < $length; $i++) {
            $index *= 26;
            $index += ord($columnLetter[$i]) - ord('A') + 1;
        }
        return $index - 1;
    }

    // Normalizar cadenas para evitar problemas con codificaciones diferentes
    function normalizeString($string) {
        return trim(normalizer_normalize($string, Normalizer::FORM_C));
    }

    function fetchData($handle, $columnLetter) {
        if (!$columnLetter) return [];
        $columnIndex = columnLetterToIndex($columnLetter);
        $data = [];
        rewind($handle);
        fgetcsv($handle, 0, ";");

        while (($row = fgetcsv($handle, 0, ";")) !== FALSE) {
            if (isset($row[$columnIndex])) {
                $data[] = normalizeString(trim($row[$columnIndex]));
            }
        }
        return $data;
    }

    function fetchDataFromDatabase($type, $table, $dbConnection) {
        if ($type === 'categoria' && $table === 'ps_categorias') {
            $sql = "SELECT DISTINCT categoria FROM ps_categorias";
        } elseif ($type === 'tallas' && $table === 'ps_tallas') {
            $sql = "SELECT DISTINCT talla FROM ps_tallas";
        } else {
            $sql = "SELECT DISTINCT valor FROM $table WHERE tipo = ?";
        }

        $stmt = $dbConnection->prepare($sql);
        $stmt->execute([strtolower($type)]);

        $dataFromDb = [];
        while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
            $dataFromDb[] = normalizeString(trim($row['valor'] ?? $row['categoria'] ?? $row['talla']));
        }
        return $dataFromDb;
    }

    function compareData($extractedData, $dbData) {
        $differences = [];
        foreach ($extractedData as $data) {
            // Verifica si el valor no está vacío y no está en los datos de la base de datos
            if (!empty($data) && !in_array($data, $dbData, true)) {
                $differences[] = $data;
            }
        }
        return $differences;
    }

    // Recoger y procesar los datos de las columnas especificadas
    $ambarMapping = $_SESSION['ambarMapping'];
    $prestashopMapping = $_SESSION['prestashopMapping'];
    $ambarSeasonData = fetchData($handle, $ambarMapping['seasonColumn']);
    $prestashopSeasonData = fetchData($handle, $prestashopMapping['seasonColumn']);
    $ambarProductData = fetchData($handle, $ambarMapping['productColumn']);
    $prestashopProductData = fetchData($handle, $prestashopMapping['productColumn']);
    $ambarGamaData = fetchData($handle, $ambarMapping['gamaColumn']);
    $prestashopGamaData = fetchData($handle, $prestashopMapping['gamaColumn']);
    $ambarMarcaData = fetchData($handle, $ambarMapping['marcaColumn']);
    $prestashopMarcaData = fetchData($handle, $prestashopMapping['marcaColumn']);
    $prestashopCategoryData = fetchData($handle, $prestashopMapping['categoryColumn']);
    $prestashopSizeData = fetchData($handle, $prestashopMapping['sizeColumn']);
    $prestashopGenderData = fetchData($handle, $prestashopMapping['genderColumn']);
    $prestashopAgeData = fetchData($handle, $prestashopMapping['ageColumn']);

    // Obtener los datos desde la base de datos
    $dbAmbarSeasonData = fetchDataFromDatabase('temporada', 'am_libres', $conn);
    $dbPrestashopSeasonData = fetchDataFromDatabase('temporada', 'ps_caracteristicas', $conn);
    $dbAmbarProductData = fetchDataFromDatabase('producto', 'am_libres', $conn);
    $dbPrestashopProductData = fetchDataFromDatabase('producto', 'ps_caracteristicas', $conn);
    $dbAmbarGamaData = fetchDataFromDatabase('gama', 'am_libres', $conn);
    $dbPrestashopGamaData = fetchDataFromDatabase('gama', 'ps_caracteristicas', $conn);
    $dbAmbarMarcaData = fetchDataFromDatabase('marca', 'am_libres', $conn);
    $dbPrestashopMarcaData = fetchDataFromDatabase('marca', 'ps_caracteristicas', $conn);
    $dbPrestashopCategoryData = fetchDataFromDatabase('categoria', 'ps_categorias', $conn);
    $dbPrestashopSizeData = fetchDataFromDatabase('tallas', 'ps_tallas', $conn);
    $dbPrestashopGenderData = fetchDataFromDatabase('genero', 'ps_caracteristicas', $conn);
    $dbPrestashopAgeData = fetchDataFromDatabase('edad', 'ps_caracteristicas', $conn);

    // Comparar los datos extraídos del CSV con los datos de la base de datos
    $ambarSeasonDifferences = compareData($ambarSeasonData, $dbAmbarSeasonData);
    $prestashopSeasonDifferences = compareData($prestashopSeasonData, $dbPrestashopSeasonData);
    $ambarProductDifferences = compareData($ambarProductData, $dbAmbarProductData);
    $prestashopProductDifferences = compareData($prestashopProductData, $dbPrestashopProductData);
    $ambarGamaDifferences = compareData($ambarGamaData, $dbAmbarGamaData);
    $prestashopGamaDifferences = compareData($prestashopGamaData, $dbPrestashopGamaData);
    $ambarMarcaDifferences = compareData($ambarMarcaData, $dbAmbarMarcaData);
    $prestashopMarcaDifferences = compareData($prestashopMarcaData, $dbPrestashopMarcaData);
    $prestashopCategoryDifferences = compareData($prestashopCategoryData, $dbPrestashopCategoryData);
    $prestashopSizeDifferences = compareData($prestashopSizeData, $dbPrestashopSizeData);
    $prestashopGenderDifferences = compareData($prestashopGenderData, $dbPrestashopGenderData);
    $prestashopAgeDifferences = compareData($prestashopAgeData, $dbPrestashopAgeData);

    // Guardar las diferencias en la sesión para su uso en generate_excel.php
    $_SESSION['ambarDifferences'] = [
        'seasonDifferences' => $ambarSeasonDifferences,
        'productDifferences' => $ambarProductDifferences,
        'gamaDifferences' => $ambarGamaDifferences,
        'marcaDifferences' => $ambarMarcaDifferences
    ];

    $_SESSION['prestashopDifferences'] = [
        'seasonDifferences' => $prestashopSeasonDifferences,
        'productDifferences' => $prestashopProductDifferences,
        'gamaDifferences' => $prestashopGamaDifferences,
        'marcaDifferences' => $prestashopMarcaDifferences,
        'categoryDifferences' => $prestashopCategoryDifferences,
        'sizeDifferences' => $prestashopSizeDifferences,
        'genderDifferences' => $prestashopGenderDifferences,
        'ageDifferences' => $prestashopAgeDifferences
    ];

    // Responder con los datos procesados para Ambar y Prestashop
    echo json_encode([
        'success' => true,
        'ambarDifferences' => $_SESSION['ambarDifferences'],
        'prestashopDifferences' => $_SESSION['prestashopDifferences'],
        'categoryData' => $_SESSION['categoryData'], // Añadido para incluir los datos de la base de datos plantilla_pro
        'showGenerateButton' => true
    ]);
    exit;
} else {
    echo json_encode(['success' => false, 'message' => "No se pudo abrir el archivo CSV."]);
    exit;
}
?>
