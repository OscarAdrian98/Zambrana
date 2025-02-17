<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reportes de Inventario</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
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
<div class="mt-2 container">
    <h1 class="text-center">Reportes de Inventario</h1>

    <!-- Pestañas -->
    <ul class="nav nav-tabs" id="reportTabs">
        <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#ventas">Ventas</a></li>
        <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#compras">Compras</a></li>
        <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#vencimientos">Vencimientos</a></li>
        <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#stock">Stock Actual</a></li>
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
                    <select id="familiaStock" class="form-control" onchange="cargarSubfamilias(); actualizarDescripcion('familiaStock', 'descFamilia')">
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
    </div>
</div>

<script>
function cargarDatos(tipo) {
    let url = `http://192.168.1.201:5002/get_data?tipo=${tipo}`;

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
    let url = `http://192.168.1.201:5002/descargar?tipo=${tipo}`;

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

// 🔹 Cargar opciones de Familias, SubFamilias y Proveedores dinámicamente
let descripcionesFamilias = {};
let descripcionesProveedores = {};

function cargarFiltrosStock() {
    $.getJSON("http://192.168.1.201:5002/get_filtros_stock", function(data) {
        let familiaSelect = $("#familiaStock");
        let proveedorSelect = $("#proveedorStock");

        familiaSelect.html('<option value="" data-bs-toggle="tooltip" title="Todas las familias">Todas</option>');
        proveedorSelect.html('<option value="" data-bs-toggle="tooltip" title="Todos los proveedores">Todos</option>');

        descripcionesFamilias = {};
        descripcionesProveedores = {};

        data.familias.forEach(familia => {
            let descripcion = data.familia_descripciones[familia] || "Sin descripción";
            descripcionesFamilias[familia] = descripcion;
            familiaSelect.append(`<option value="${familia}">${familia}</option>`);
        });

        data.proveedores.forEach(proveedor => {
            let descripcion = data.proveedor_nombres[proveedor] || "Sin nombre";
            descripcionesProveedores[proveedor] = descripcion;
            proveedorSelect.append(`<option value="${proveedor}">${proveedor}</option>`);
        });

        activarTooltips();
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

// 🔹 Cargar subfamilias dinámicamente cuando se elija una familia
let isLoadingSubfamilias = false;

function cargarSubfamilias() {
    if (isLoadingSubfamilias) return;
    isLoadingSubfamilias = true;

    let familia = $("#familiaStock").val();
    let subfamiliaSelect = $("#subfamiliaStock");

    // 🎯 Limpiar subfamilias antes de agregar opciones nuevas
    subfamiliaSelect.html('<option value="">Todas</option>');

    if (!familia) {
        isLoadingSubfamilias = false;
        return;
    }

    $.getJSON(`http://192.168.1.201:5002/get_filtros_stock?familia=${encodeURIComponent(familia)}`, function(data) {
        let subfamiliasUnicas = [...new Set(data.subfamilias)];

        // 📌 Insertar Subfamilias dinámicamente
        let subfamiliasOptions = subfamiliasUnicas.map(subfamilia => `<option value="${subfamilia}">${subfamilia}</option>`).join("");
        subfamiliaSelect.append(subfamiliasOptions);

        console.log("✅ Subfamilias cargadas:", subfamiliasUnicas);
        activarTooltips(); // 🔹 Reinicializar tooltips en las opciones cargadas
        isLoadingSubfamilias = false;
    }).fail(function() {
        console.error("❌ Error al cargar subfamilias.");
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
    cargarFiltrosStock(); // ✅ Cargar familias y proveedores sin afectar subfamilias

    // ✅ Asegurar que el evento "change" solo se registre una vez
    $("#familiaStock").off("change").on("change", function() {
        console.log("🔄 Cambio detectado en familiaStock, ejecutando cargarSubfamilias...");
        cargarSubfamilias();
    });
});

function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

</script>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
