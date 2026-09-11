<?php
// 🔹 Configurar la sesión ANTES de iniciarla
ini_set("session.cookie_lifetime", 0);  // La sesión dura hasta que el navegador se cierra
ini_set("session.gc_maxlifetime", 0);   // Evita que la sesión tenga un tiempo de expiración fijo

session_start();
$accessHash = getenv('INVENTARIO_PASSWORD_HASH') ?: '';


// 🔹 Evitar caché del navegador
header("Cache-Control: no-cache, no-store, must-revalidate");
header("Pragma: no-cache");
header("Expires: 0");

// 🔹 Cerrar sesión si se solicita (botón de logout)
if (isset($_GET['logout'])) {
    session_destroy();
    header("Location: index.php");
    exit();
}

// 🔹 Verificar autenticación
if (!isset($_SESSION['acceso_autorizado']) || $_SESSION['acceso_autorizado'] !== true) {
    $error = "";

    // Si el usuario envía la clave
    if ($_SERVER["REQUEST_METHOD"] == "POST" && isset($_POST['clave'])) {
        if ($accessHash !== "" && password_verify((string) $_POST['clave'], $accessHash)) { // Clave de acceso
            session_regenerate_id(true);
            $_SESSION['acceso_autorizado'] = true;
            header("Location: index.php"); // Recargar la página autenticada
            exit();
        } else {
            $error = "⚠ Clave incorrecta, inténtelo de nuevo.";
        }
    }

    // 🔹 Mostrar formulario de acceso si no está autenticado
    echo '<!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Acceso Restringido</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
    <div class="container mt-5">
        <h2 class="text-center" style= "margin-bottom: 25px;">🔒 Acceso Restringido</h2>
        <form method="POST" class="w-50 mx-auto">
            <div class="mb-3">
                <label class="form-label">Clave de acceso:</label>
                <input type="password" name="clave" class="form-control" required>
            </div>';
    if ($error) {
        echo '<div class="alert alert-danger text-center">' . $error . '</div>';
    }
    echo '<button type="submit" class="btn btn-primary w-100">Ingresar</button>
        </form>
    </div>
    </body>
    </html>';
    exit();
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reportes de Inventario</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <style>
        /* Estilos generales */
        body { background-color: #f8f9fa; }
        .container { max-width: 90%; margin: auto; }
        .tab-content { margin-top: 20px; }
        .btn-download { margin-top: 20px; }
        th { text-align: center; }

        /* 🔹 Diseño mejorado para la tabla */
        .table {
            width: 100%;
            margin-top: 20px;
            background-color: white;
            border-collapse: collapse;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.1);
        }

        /* 🔹 Cabecera azul con texto blanco */
        .table thead {
            background-color: #007bff;
            color: white;
            font-weight: bold;
            text-align: center;
        }

        .table thead th {
            padding: 14px;
            border: 1px solid #dee2e6;
        }

        .table tbody td {
            padding: 12px;
            text-align: center;
            border: 1px solid #dee2e6;
        }

        /* 🔹 Filas alternas con fondo gris claro */
        .table tbody tr:nth-child(odd) {
            background-color: #f8f9fa;
        }

        /* 🔹 Efecto hover en filas */
        .table tbody tr:hover {
            background-color: #e3f2fd;
        }

        /* Ajuste para tablas responsivas */
        .table-container {
            max-width: 100%;
            overflow-x: auto;
            padding: 10px;
        }

        /* 🔹 Ajuste para las columnas de fechas en Ventas y Compras */
        .table th:nth-child(4),  /* FECHA VENTA en Ventas */
        .table td:nth-child(4),
        .table th:last-child,    /* FECHA COMPRA en Compras */
        .table td:last-child {
            min-width: 150px;  /* Mayor espacio solo para fechas */
            text-align: center;
            white-space: nowrap;
        }
    </style>
</head>
<body>
<div class="container mt-2">
    <button class="btn btn-danger logout-btn" onclick="window.location.href='index.php?logout=true'">Cerrar sesión</button>
    <h1 class="text-center">Reportes de Inventario</h1>

    <!-- Pestañas -->
    <ul class="nav nav-tabs" id="reportTabs">
        <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#ventas">Ventas</a></li>
        <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#compras">Compras</a></li>
        <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#vencimientos">Vencimientos</a></li>
        <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#stock">Stock Actual</a></li>
        <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#analisis">📊 Análisis y Predicción</a></li>
    </ul>

    <div class="tab-content">
        <!-- Ventas -->
        <div id="ventas" class="tab-pane fade show active">
            <h3 class="mt-4">Ventas</h3>

            <div class="row">
                <div class="col-md-3">
                    <label for="tipoVentas" class="form-label">Tipo de Reporte:</label>
                    <select id="tipoVentas" class="form-control">
                        <option value="global">Ventas Globales</option>
                        <option value="individual">Ventas Individuales</option>
                    </select>
                </div>
                <div class="col-md-3">
                    <label for="fechaDesdeVentas" class="form-label">Desde:</label>
                    <input type="date" id="fechaDesdeVentas" class="form-control">
                </div>
                <div class="col-md-3">
                    <label for="fechaHastaVentas" class="form-label">Hasta:</label>
                    <input type="date" id="fechaHastaVentas" class="form-control">
                </div>
                <div class="col-md-3 d-flex align-items-end">
                    <button class="btn btn-primary w-100" onclick="cargarDatos('ventas')">Generar Reporte</button>
                </div>
            </div>

            <!-- 🔹 NUEVOS FILTROS: Familia, SubFamilia y Proveedor -->
            <div class="row mt-2">
                <div class="col-md-3">
                    <label for="familiaVentas" class="form-label">Familia:</label>
                    <select id="familiaVentas" class="form-control" onchange="cargarSubfamilias('ventas'); actualizarDescripcion('familiaVentas', 'descFamiliaVentas')">
                        <option value="">Todas</option>
                    </select>
                    <input type="text" id="descFamiliaVentas" class="form-control mt-1" placeholder="Descripción" readonly>
                </div>
                <div class="col-md-3">
                    <label for="subfamiliaVentas" class="form-label">SubFamilia:</label>
                    <select id="subfamiliaVentas" class="form-control">
                        <option value="">Todas</option>
                    </select>
                </div>
                <div class="col-md-3">
                    <label for="proveedorVentas" class="form-label">Proveedor:</label>
                    <select id="proveedorVentas" class="form-control" onchange="actualizarDescripcion('proveedorVentas', 'descProveedorVentas')">
                        <option value="">Todos</option>
                    </select>
                    <input type="text" id="descProveedorVentas" class="form-control mt-1" placeholder="Descripción" readonly>
                </div>
            </div>

            <button class="btn btn-success mt-2" onclick="descargarReporte('ventas')">Descargar Excel</button>
            <div style="max-width: 100%; overflow-x: auto;">
                <div id="tablaVentas"></div>
            </div>
        </div>

        <!-- Compras -->
        <div id="compras" class="tab-pane fade">
            <h3 class="mt-4">Compras</h3>
            
            <div class="row">
                <div class="col-md-4">
                    <label for="fechaDesdeCompras" class="form-label">Desde:</label>
                    <input type="date" id="fechaDesdeCompras" class="form-control">
                </div>
                <div class="col-md-4">
                    <label for="fechaHastaCompras" class="form-label">Hasta:</label>
                    <input type="date" id="fechaHastaCompras" class="form-control">
                </div>
                <div class="col-md-4 d-flex align-items-end">
                    <button class="btn btn-primary w-100" onclick="cargarDatos('compras')">Generar Reporte</button>
                </div>
            </div>

            <button class="btn btn-success mt-2" onclick="descargarReporte('compras')">Descargar Excel</button>
            <div style="max-width: 100%; overflow-x: auto;">
                <div id="tablaCompras"></div>
            </div>
        </div>

        <!-- Vencimientos -->
        <div id="vencimientos" class="tab-pane fade">
            <h3 class="mt-4">Vencimientos</h3>
            
            <div class="row">
                <div class="col-md-4">
                    <label for="fechaDesdeVencimientos" class="form-label">Desde:</label>
                    <input type="date" id="fechaDesdeVencimientos" class="form-control">
                </div>
                <div class="col-md-4">
                    <label for="fechaHastaVencimientos" class="form-label">Hasta:</label>
                    <input type="date" id="fechaHastaVencimientos" class="form-control">
                </div>
                <div class="col-md-4 d-flex align-items-end">
                    <button class="btn btn-primary w-100" onclick="cargarDatos('vencimientos')">Generar Reporte</button>
                </div>
            </div>

            <button class="btn btn-success mt-2" onclick="descargarReporte('vencimientos')">Descargar Excel</button>
            <div style="max-width: 100%; overflow-x: auto;">
                <div id="tablaVencimientos"></div>
            </div>
        </div>

        <!-- Stock Actual -->
        <div id="stock" class="tab-pane fade">
            <h3 class="mt-4">Stock Actual</h3>

            <div class="row">
                <!-- Filtro Familia -->
                <div class="col-md-3">
                    <label for="familiaStock" class="form-label">Familia:</label>
                    <select id="familiaStock" class="form-control" onchange="cargarSubfamilias('stock'); actualizarDescripcion('familiaStock', 'descFamilia')">
                        <option value="">Todas</option>
                    </select>
                    <input type="text" id="descFamilia" class="form-control mt-1" placeholder="Descripción" readonly>
                </div>

                <!-- Filtro SubFamilia -->
                <div class="col-md-3">
                    <label for="subfamiliaStock" class="form-label">SubFamilia:</label>
                    <select id="subfamiliaStock" class="form-control">
                        <option value="">Todas</option>
                        <!-- Opciones de subfamilia se llenarán dinámicamente -->
                    </select>
                </div>

                <!-- Filtro Proveedor -->
                <div class="col-md-3">
                    <label for="proveedorStock" class="form-label">Proveedor:</label>
                    <select id="proveedorStock" class="form-control" onchange="actualizarDescripcion('proveedorStock', 'descProveedor')">
                        <option value="">Todos</option>
                    </select>
                    <input type="text" id="descProveedor" class="form-control mt-1" placeholder="Descripción" readonly>
                </div>

                <!-- Botón Generar Reporte -->
                <div class="col-md-3 d-flex align-items-end">
                    <button class="btn btn-primary btn-sm w-100" onclick="cargarDatos('stock')">Generar Reporte</button>
                </div>
            </div>

            <div class="row mt-2">
                <!-- Botón Descargar Excel -->
                <div class="col-md-3 d-flex">
                    <button class="btn btn-success btn-sm w-100" onclick="descargarReporte('stock')">Descargar Excel</button>
                </div>
            </div>

            <div style="max-width: 100%; overflow-x: auto; margin-top: 10px;">
                <div id="tablaStock"></div>
            </div>
        </div>
        <!-- Análisis -->
        <div id="analisis" class="tab-pane fade">
            <h3 class="mt-4">📊 Análisis de Ventas</h3>

            <!-- 🔹 Selección de fechas -->
            <div class="row mt-3">
                <div class="col-md-4">
                    <label for="fechaDesdeAnalisis" class="form-label">Desde:</label>
                    <input type="date" id="fechaDesdeAnalisis" class="form-control">
                </div>
                <div class="col-md-4">
                    <label for="fechaHastaAnalisis" class="form-label">Hasta:</label>
                    <input type="date" id="fechaHastaAnalisis" class="form-control">
                </div>
                <div class="col-md-4 d-flex align-items-end">
                    <button class="btn btn-primary w-100" onclick="cargarAnalisis()">Actualizar Análisis</button>
                </div>
            </div>

            <!-- 🔹 Nueva sección con métricas clave -->
            <div class="row mt-4">
                <!-- 🔹 Total Ventas y Beneficios -->
                <div class="col-md-5">
                    <div class="alert alert-info">
                        <strong>🔢 Total Ventas (€):</strong> <span id="totalVentas">-</span> <br>
                        <strong>💰 Beneficio sin IVA (€):</strong> <span id="beneficioSinIVA">-</span> <br>
                        <strong>💰 Beneficio con IVA (€):</strong> <span id="beneficioConIVA">-</span> <br>
                        <strong>📊 Ticket Promedio (€):</strong> <span id="ticketPromedio">-</span> <!-- Movido aquí -->
                    </div>
                </div>
                <!-- 🔹 Top Productos (ahora más ancho) -->
                <div class="col-md-7">
                    <div class="alert alert-warning">
                        <strong>🔥 Top 10 Productos:</strong> 
                        <div id="topProductos" style="max-height: 400px; overflow: auto;"></div>
                    </div>
                </div>
            </div>

            <canvas id="graficoVentas" class="mt-3"></canvas>
        </div>
</div>

<script>
function cargarDatos(tipo) {
    let url = `<?php echo htmlspecialchars(rtrim(getenv('INVENTARIO_API_URL') ?: 'http://127.0.0.1:5002', '/'), ENT_QUOTES, 'UTF-8'); ?>/get_data?tipo=${tipo}`;

    if (tipo === "ventas" || tipo === "compras" || tipo === "vencimientos") {
        let fechaDesde = document.getElementById(`fechaDesde${capitalize(tipo)}`).value;
        let fechaHasta = document.getElementById(`fechaHasta${capitalize(tipo)}`).value;

        if (!fechaDesde || !fechaHasta) {
            alert("Debes seleccionar un rango de fechas.");
            return;
        }

        url += `&fecha_desde=${fechaDesde}&fecha_hasta=${fechaHasta}`;

        if (tipo === "ventas") {
            let ventasTipo = document.getElementById("tipoVentas").value;
            url += `&ventas=${ventasTipo}`;

            // 🔹 Obtener los valores de los nuevos filtros de ventas
            let familia = document.getElementById("familiaVentas").value;
            let subfamilia = document.getElementById("subfamiliaVentas").value;
            let proveedor = document.getElementById("proveedorVentas").value;

            // 🔹 Agregar filtros a la URL solo si tienen valor
            if (familia && familia !== "Todas") url += `&familia=${encodeURIComponent(familia)}`;
            if (subfamilia && subfamilia !== "Todas") url += `&subfamilia=${encodeURIComponent(subfamilia)}`;
            if (proveedor && proveedor !== "Todos") url += `&proveedor=${encodeURIComponent(proveedor)}`;
        }
    } else if (tipo === "stock") {
        // 🔹 Obtener los valores de los filtros de stock
        let familia = document.getElementById("familiaStock").value;
        let subfamilia = document.getElementById("subfamiliaStock").value;
        let proveedor = document.getElementById("proveedorStock").value;

        // 🔹 Agregar filtros a la URL solo si tienen valor
        if (familia && familia !== "Todas") url += `&familia=${encodeURIComponent(familia)}`;
        if (subfamilia && subfamilia !== "Todas") url += `&subfamilia=${encodeURIComponent(subfamilia)}`;
        if (proveedor && proveedor !== "Todos") url += `&proveedor=${encodeURIComponent(proveedor)}`;
    }

    console.log("📡 URL de solicitud:", url);

    $.getJSON(url, function(data) {
        if (data.length === 0) {
            $(`#tabla${capitalize(tipo)}`).html("<p class='text-danger mt-3'>No hay datos disponibles.</p>");
            return;
        }

        let tableHtml = `<table class="table">
            <thead>
                <tr>`;
        for (let key in data[0]) {
            let headerText = key.replace(/_/g, " ");
            tableHtml += `<th>${headerText.toUpperCase()}</th>`;
        }
        tableHtml += `</tr></thead><tbody>`;

        data.forEach(row => {
            tableHtml += '<tr>';
            for (let key in row) {
                tableHtml += `<td>${row[key]}</td>`;
            }
            tableHtml += '</tr>';
        });

        tableHtml += `</tbody></table>`;

        $(`#tabla${capitalize(tipo)}`).html(tableHtml);
    }).fail(function() {
        $(`#tabla${capitalize(tipo)}`).html("<p class='text-danger mt-3'>Error al cargar los datos.</p>");
    });
}

// 🔹 Descargar el reporte en Excel con los filtros aplicados
function descargarReporte(tipo) {
    let url = `<?php echo htmlspecialchars(rtrim(getenv('INVENTARIO_API_URL') ?: 'http://127.0.0.1:5002', '/'), ENT_QUOTES, 'UTF-8'); ?>/descargar?tipo=${tipo}`;

    if (tipo === "ventas" || tipo === "compras" || tipo === "vencimientos") {
        let fechaDesde = document.getElementById(`fechaDesde${capitalize(tipo)}`).value;
        let fechaHasta = document.getElementById(`fechaHasta${capitalize(tipo)}`).value;

        if (!fechaDesde || !fechaHasta) {
            alert("Debes seleccionar un rango de fechas antes de descargar el reporte.");
            return;
        }

        url += `&fecha_desde=${fechaDesde}&fecha_hasta=${fechaHasta}`;

        if (tipo === "ventas") {
            let ventasTipo = document.getElementById("tipoVentas").value;
            url += `&ventas=${ventasTipo}`; // 🔹 Aseguramos que se envía el tipo de ventas

            // 🔹 Obtener los valores de los nuevos filtros de ventas
            let familia = document.getElementById("familiaVentas").value;
            let subfamilia = document.getElementById("subfamiliaVentas").value;
            let proveedor = document.getElementById("proveedorVentas").value;

            // 🔹 Agregar filtros a la URL solo si tienen valor
            if (familia && familia !== "Todas") url += `&familia=${encodeURIComponent(familia)}`;
            if (subfamilia && subfamilia !== "Todas") url += `&subfamilia=${encodeURIComponent(subfamilia)}`;
            if (proveedor && proveedor !== "Todos") url += `&proveedor=${encodeURIComponent(proveedor)}`;
        }
    } else if (tipo === "stock") {
        let familia = document.getElementById("familiaStock").value;
        let subfamilia = document.getElementById("subfamiliaStock").value;
        let proveedor = document.getElementById("proveedorStock").value;

        if (familia && familia !== "Todas") url += `&familia=${encodeURIComponent(familia)}`;
        if (subfamilia && subfamilia !== "Todas") url += `&subfamilia=${encodeURIComponent(subfamilia)}`;
        if (proveedor && proveedor !== "Todos") url += `&proveedor=${encodeURIComponent(proveedor)}`;
    }

    console.log("📡 URL de descarga:", url);
    window.location.href = url; // 🔹 Descarga del archivo
}

function cargarFiltrosStock() {
    $.getJSON("<?php echo htmlspecialchars(rtrim(getenv('INVENTARIO_API_URL') ?: 'http://127.0.0.1:5002', '/'), ENT_QUOTES, 'UTF-8'); ?>/get_filtros_stock", function(data) {
        let familiaStock = $("#familiaStock");
        let proveedorStock = $("#proveedorStock");
        let familiaVentas = $("#familiaVentas");
        let proveedorVentas = $("#proveedorVentas");

        // Limpiar y agregar opción por defecto
        familiaStock.html('<option value="">Todas</option>');
        proveedorStock.html('<option value="">Todos</option>');
        familiaVentas.html('<option value="">Todas</option>');
        proveedorVentas.html('<option value="">Todos</option>');

        descripcionesFamilias = {};
        descripcionesProveedores = {};

        if (data.familias && data.familias.length > 0) {
            data.familias.forEach(familia => {
                let descripcion = data.familia_descripciones[familia] || "Sin descripción";
                descripcionesFamilias[familia] = descripcion;
                familiaStock.append(`<option value="${familia}">${familia}</option>`);
                familiaVentas.append(`<option value="${familia}">${familia}</option>`);
            });
        } else {
            console.error("⚠ No se encontraron familias en la API.");
        }

        if (data.proveedores && data.proveedores.length > 0) {
            data.proveedores.forEach(proveedor => {
                let descripcion = data.proveedor_nombres[proveedor] || "Sin nombre";
                descripcionesProveedores[proveedor] = descripcion;
                proveedorStock.append(`<option value="${proveedor}">${proveedor}</option>`);
                proveedorVentas.append(`<option value="${proveedor}">${proveedor}</option>`);
            });
        } else {
            console.error("⚠ No se encontraron proveedores en la API.");
        }

        console.log("✅ Familias y proveedores cargados correctamente.");
        activarTooltips();
    }).fail(function() {
        console.error("❌ Error al cargar los filtros desde la API.");
    });
}

function actualizarDescripcion(selectId, inputId) {
    let valorSeleccionado = document.getElementById(selectId).value;
    let descripcion = "";

    if (selectId === "familiaStock") {
        descripcion = descripcionesFamilias[valorSeleccionado] || "Sin descripción";
    } else if (selectId === "proveedorStock") {
        descripcion = descripcionesProveedores[valorSeleccionado] || "Sin nombre";
    }

    document.getElementById(inputId).value = descripcion;
}

// 🔹 Cargar análisis de ventas con selección de fechas
let chartInstance = null; // Guardará el gráfico actual para evitar superposición

function cargarAnalisis() {
    let fechaDesde = document.getElementById("fechaDesdeAnalisis").value;
    let fechaHasta = document.getElementById("fechaHastaAnalisis").value;

    if (!fechaDesde || !fechaHasta) {
        alert("Por favor, selecciona un rango de fechas.");
        return;
    }

    let btn = document.querySelector("button[onclick='cargarAnalisis()']");
    btn.innerHTML = "Cargando...";
    btn.disabled = true;

    fetch(`<?php echo htmlspecialchars(rtrim(getenv('INVENTARIO_ANALISIS_URL') ?: 'http://127.0.0.1:5003', '/'), ENT_QUOTES, 'UTF-8'); ?>/analisis_ventas?fecha_desde=${fechaDesde}&fecha_hasta=${fechaHasta}`)
        .then(response => response.json())
        .then(data => {
            let ctx = document.getElementById("graficoVentas").getContext("2d");

            // Si ya hay un gráfico, destruirlo antes de crear uno nuevo
            if (chartInstance) {
                chartInstance.destroy();
            }

            chartInstance = new Chart(ctx, {
                type: "bar",
                data: {
                    labels: data.fechas,
                    datasets: [{
                        label: "Ventas",
                        data: data.ventas,
                        backgroundColor: "blue"
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        x: { 
                            ticks: { autoSkip: true, maxTicksLimit: 20 }, 
                            title: { display: true, text: "Fecha de Venta" }
                        },
                        y: { 
                            title: { display: true, text: "Cantidad Vendida" } 
                        }
                    }
                }
            });

            // Función para convertir un texto a formato "NOMPROPIO" (primera letra en mayúscula)
            function capitalizeWords(str) {
                return str.toLowerCase().replace(/\b\w/g, char => char.toUpperCase());
            }

            // 🔹 Función para formatear números con separador de miles y coma para decimales
            function formatNumber(num) {
                return new Intl.NumberFormat("es-ES", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                }).format(num);
            }

            // 🔹 Actualizar métricas en el frontend aplicando el formato correcto
            document.getElementById("totalVentas").innerText = formatNumber(data.total_ventas) + " €";
            document.getElementById("beneficioSinIVA").innerText = formatNumber(data.beneficio_sin_iva_total) + " €";
            document.getElementById("beneficioConIVA").innerText = formatNumber(data.beneficio_con_iva_total) + " €";
            document.getElementById("ticketPromedio").innerText = formatNumber(data.ticket_promedio) + " €";

            // 🔥 Ajustar la tabla de "Top Productos"
            let topProductosHtml = `
                <div style="max-height: 400px; overflow: auto; padding: 5px;">
                    <table class="table table-striped table-sm">
                        <thead class="table-light">
                            <tr>
                                <th>Referencia</th>
                                <th>Producto</th>
                                <th>Cantidad Vendida</th>
                                <th>Beneficio sin IVA (€)</th>
                                <th>Beneficio con IVA (€)</th>
                                <th>Stock Actual</th> <!-- ✅ Nueva columna añadida -->
                            </tr>
                        </thead>
                        <tbody>`;

            data.top_productos.forEach(producto => {
                topProductosHtml += `
                    <tr>
                        <td>${producto.refProducto}</td>
                        <td>${capitalizeWords(producto.nombreProducto)}</td>
                        <td>${formatNumber(producto.cantidad_total)}</td>
                        <td>${producto.beneficio_sin_iva ? formatNumber(producto.beneficio_sin_iva) + " €" : "0,00 €"}</td>
                        <td>${producto.beneficio_con_iva ? formatNumber(producto.beneficio_con_iva) + " €" : "0,00 €"}</td>
                        <td>${producto.stock_actual ?? "N/A"}</td> <!-- ✅ Mostrar stock actual -->
                    </tr>`;
            });

            topProductosHtml += `</tbody></table></div>`;
            document.getElementById("topProductos").innerHTML = topProductosHtml;

            // Restablecer el botón
            btn.innerHTML = "Actualizar Análisis";
            btn.disabled = false;
        })
        .catch(error => {
            console.error("Error cargando análisis:", error);
            btn.innerHTML = "Actualizar Análisis";
            btn.disabled = false;
        });
}

// 🔹 Cargar subfamilias dinámicamente cuando se elija una familia
let isLoadingSubfamilias = false;

function cargarSubfamilias(tipo) {
    if (isLoadingSubfamilias) return;
    isLoadingSubfamilias = true;

    let familiaSelect, subfamiliaSelect;

    // 🔹 Determinar si es para Stock o Ventas
    if (tipo === "stock") {
        familiaSelect = $("#familiaStock");
        subfamiliaSelect = $("#subfamiliaStock");
    } else if (tipo === "ventas") {
        familiaSelect = $("#familiaVentas");
        subfamiliaSelect = $("#subfamiliaVentas");
    } else {
        console.error("❌ Error: tipo desconocido en cargarSubfamilias");
        return;
    }

    let familia = familiaSelect.val();

    // 🎯 Limpiar subfamilias antes de agregar opciones nuevas
    subfamiliaSelect.html('<option value="">Todas</option>');

    if (!familia) {
        isLoadingSubfamilias = false;
        return;
    }

    $.getJSON(`<?php echo htmlspecialchars(rtrim(getenv('INVENTARIO_API_URL') ?: 'http://127.0.0.1:5002', '/'), ENT_QUOTES, 'UTF-8'); ?>/get_filtros_stock?familia=${encodeURIComponent(familia)}`, function(data) {
        let subfamiliasUnicas = [...new Set(data.subfamilias)];

        // 📌 Insertar Subfamilias dinámicamente
        let subfamiliasOptions = subfamiliasUnicas.map(subfamilia => `<option value="${subfamilia}">${subfamilia}</option>`).join("");
        subfamiliaSelect.append(subfamiliasOptions);

        console.log(`✅ Subfamilias cargadas para ${tipo}:`, subfamiliasUnicas);
        activarTooltips(); // 🔹 Reinicializar tooltips en las opciones cargadas
        isLoadingSubfamilias = false;
    }).fail(function() {
        console.error(`❌ Error al cargar subfamilias para ${tipo}.`);
        isLoadingSubfamilias = false;
    });
}

function activarTooltips() {
    // 🛠️ Destruir tooltips existentes antes de inicializar nuevos
    $('[data-bs-toggle="tooltip"]').each(function() {
        let tooltipInstance = bootstrap.Tooltip.getInstance(this);
        if (tooltipInstance) {
            tooltipInstance.dispose();
        }
    });

    // 🎯 Inicializar tooltips nuevamente
    $('[data-bs-toggle="tooltip"]').tooltip();
}

// 🔹 ELIMINAR EVENTOS PREVIOS ANTES DE AÑADIR EL `onchange`
$(document).ready(function() {
    cargarFiltrosStock(); // ✅ Cargar familias y proveedores

    $("#familiaStock").off("change").on("change", function() {
        console.log("🔄 Cambio detectado en familiaStock, ejecutando cargarSubfamilias...");
        cargarSubfamilias('stock');
    });

    $("#familiaVentas").off("change").on("change", function() {
        console.log("🔄 Cambio detectado en familiaVentas, ejecutando cargarSubfamilias...");
        cargarSubfamilias('ventas');
    });
});

function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

</script>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>