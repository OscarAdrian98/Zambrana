<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Procesador de Archivos Excel</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f8f9fa;
            min-height: 100vh;
            display: flex;
            align-items: center;
        }
        .main-container {
			max-width: 1100px;
			margin: 0 auto;
			padding: 2rem;
		}
        .upload-card {
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            padding: 2rem;
        }
        .form-title {
            color: #2c3e50;
            margin-bottom: 1.5rem;
            text-align: center;
        }
        .upload-btn {
            background-color: #3498db;
            border: none;
            width: 100%;
            padding: 0.8rem;
            font-weight: 500;
            transition: all 0.3s ease;
        }
        .upload-btn:hover {
            background-color: #2980b9;
            transform: translateY(-2px);
        }
        .alert {
            margin-top: 1rem;
        }
        .loading {
            display: none;
            text-align: center;
            margin-top: 1rem;
        }
        .loading-spinner {
            width: 3rem;
            height: 3rem;
        }
        .download-btn {
            display: inline-block;
            padding: 0.375rem 0.75rem;
            background-color: #28a745;
            color: white;
            text-decoration: none;
            border-radius: 0.25rem;
            margin-top: 0.5rem;
        }
        .download-btn:hover {
            background-color: #218838;
            color: white;
        }
        .download-container {
            text-align: center;
            margin-top: 1rem;
        }
        .separate-downloads {
            display: none;
            margin-top: 1rem;
            padding: 1rem;
            border: 1px solid #dee2e6;
            border-radius: 0.25rem;
            background-color: #f8f9fa;
        }
        .download-link {
            color: #007bff;
            text-decoration: underline;
            cursor: pointer;
        }
        .download-link:hover {
            color: #0056b3;
        }
		#tablaVistaPrevia {
			overflow-x: auto;
			max-width: 100%;
		}
    </style>
</head>
<body>
	<div class="container-fluid px-4">
        <div class="upload-card">
            <h2 class="form-title">Mapeador de Datos</h2>
            <form id="uploadForm">
                <div class="mb-4">
                    <label for="file" class="form-label">Seleccionar archivo:</label>
                    <input type="file" class="form-control" id="file" name="file" accept=".xlsx,.xls,.csv" required>
                    <small class="text-muted">Formatos permitidos: Excel (.xlsx, .xls) y CSV</small>
                </div>

                <div class="mb-4">
                    <label for="plantilla" class="form-label">Seleccionar plantilla:</label>
                    <!-- Select cerrado correctamente -->
					<select class="form-select" id="plantilla" name="plantilla">
						<option value="">Elegir plantilla...</option>
						<option value="POLISPORT">Polisport</option>
						<option value="FOX">Fox</option>
						<option value="ACERBIS">Acerbis</option>
						<option value="FXR">FXR</option>
						<option value="PROX">Prox</option>
						<option value="UFO">Ufo</option>
						<option value="UFO PLASTICS">Ufo-Plastic</option>
					</select>

					<!-- Botón fuera del select -->
					<div class="mb-3 mt-2">
						<button type="button" class="btn btn-secondary w-100" id="vistaPreviaBtn">
							Vista previa y asignar columnas
						</button>
					</div>
                    </select>
                </div>

                <button type="submit" class="btn btn-primary upload-btn">
					Procesar Archivo
				</button>

				<div class="progress mt-3">
					<div id="progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%;">
						0%
					</div>
				</div>
            </form>

            <div id="loading" class="loading">
                <div class="spinner-border text-primary loading-spinner" role="status">
                    <span class="visually-hidden">Procesando...</span>
                </div>
                <p class="mt-2">Procesando archivo, por favor espere...</p>
            </div>

            <div id="resultado" class="mt-3"></div>
			<!-- Contenedor para vista previa y selects de mapeo -->
			<div id="contenedorVistaPrevia" class="mt-4" style="display:none;">
				<h5>Vista previa (primeras filas del archivo)</h5>
				<div id="tablaVistaPrevia" class="table-responsive"></div>

				<h6 class="mt-3">Asignar columnas</h6>
				<div id="mapeoColumnas" class="row row-cols-auto gy-2"></div>
			</div>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
        $(document).ready(function() {
			// Vista previa y mapeo manual
			$('#vistaPreviaBtn').on('click', function () {
				const fileInput = $('#file')[0];
				if (!fileInput.files[0]) {
					alert('Por favor selecciona un archivo primero.');
					return;
				}

				const formData = new FormData();
				formData.append('file', fileInput.files[0]);

				$('#contenedorVistaPrevia').hide();
				$('#tablaVistaPrevia').empty();
				$('#mapeoColumnas').empty();

				$.ajax({
					url: 'http://localhost:5000/vista-previa',
					type: 'POST',
					data: formData,
					processData: false,
					contentType: false,
					success: function (res) {
						if (!res.success) {
							alert(res.error || 'Error al generar vista previa');
							return;
						}

						const columnas = res.columnas;
						const datos = res.vista;

						let html = '<table class="table table-bordered table-sm"><thead><tr>';
						columnas.forEach(col => html += `<th>${col}</th>`);
						html += '</tr></thead><tbody>';
						datos.forEach(row => {
							html += '<tr>';
							columnas.forEach(col => {
								html += `<td>${row[col] || ''}</td>`;
							});
							html += '</tr>';
						});
						html += '</tbody></table>';
						$('#tablaVistaPrevia').html(html);

						const campos = ['REF MADRE', 'REF', 'EAN', 'NOMBRE', 'P.COMPRA', 'PVP S/IVA', 'PVP +IVA', 'COLOR', 'TALLA', 'TIPO PRODUCT'];
						campos.forEach(campo => {
							let select = `<div class="col-md-3">
								<label class="form-label">${campo}</label>
								<select class="form-select campo-mapeado" data-campo="${campo}">
									<option value="">Sin asignar</option>`;
							columnas.forEach(col => {
								select += `<option value="${col}">${col}</option>`;
							});
							select += '</select></div>';
							$('#mapeoColumnas').append(select);
						});

						$('#contenedorVistaPrevia').show();
					},
					error: function () {
						alert('No se pudo conectar con el servidor Flask (/vista-previa)');
					}
				});
			});
			$('#uploadForm').on('submit', function(e) {
				e.preventDefault();

				const formData = new FormData();
				const fileInput = $('#file')[0];
				const plantilla = $('#plantilla').val();

				if (!fileInput.files[0]) {
					$('#resultado').html(`
						<div class="alert alert-danger">
							Por favor, seleccione un archivo
						</div>
					`);
					return;
				}

				formData.append('file', fileInput.files[0]);
				formData.append('plantilla', plantilla);
				// Añadir el mapeo manual si existe
				const mapeo = {};
				$('.campo-mapeado').each(function () {
					const campo = $(this).data('campo');
					const columna = $(this).val();
					if (columna) mapeo[campo] = columna;
				});
				formData.append('mapeo', JSON.stringify(mapeo));

				// Mostrar loading y ocultar el resultado anterior
				$('#loading').show();
				$('#resultado').empty();

				// Iniciar la barra de progreso
				$("#progress-bar").css("width", "0%").text("0%");
				const progresoIntervalo = setInterval(function() {
					$.getJSON("http://localhost:5000/progreso", function(data) {
						const progreso = Math.round(data.progreso);
						$("#progress-bar").css("width", progreso + "%").text(progreso + "%");

						if (progreso >= 100) {
							clearInterval(progresoIntervalo); // Detener las actualizaciones
						}
					});
				}, 500); // Actualizar cada 500ms

				$.ajax({
					url: 'http://localhost:5000/procesar',
					type: 'POST',
					data: formData,
					processData: false,
					contentType: false,
					xhrFields: {
						responseType: 'blob'
					},
					success: function(response, status, xhr) {
						$('#loading').hide();
						clearInterval(progresoIntervalo); // Detener las actualizaciones

						// Verificar el tipo de respuesta
						const contentType = xhr.getResponseHeader('content-type');

						if (contentType && contentType.includes('application/json')) {
							const reader = new FileReader();
							reader.onload = function() {
								try {
									const error = JSON.parse(this.result);
									$('#resultado').html(`
										<div class="alert alert-danger">
											Error: ${error.error || 'Error desconocido'}
										</div>
									`);
								} catch (e) {
									$('#resultado').html(`
										<div class="alert alert-danger">
											Error al procesar la respuesta del servidor
										</div>
									`);
								}
							};
							reader.readAsText(response);
						} else if (contentType && contentType.includes('application/zip')) {
							// Archivo ZIP
							const blob = new Blob([response], { type: 'application/zip' });
							const url = window.URL.createObjectURL(blob);
							const filename = xhr.getResponseHeader('content-disposition')
								? xhr.getResponseHeader('content-disposition').split('filename=')[1].replace(/"/g, '')
								: 'resultados.zip';

							const a = document.createElement('a');
							a.href = url;
							a.download = filename;
							document.body.appendChild(a);
							a.click();
							window.URL.revokeObjectURL(url);
							document.body.removeChild(a);

							$('#resultado').html(`
								<div class="alert alert-success">
									<h5>Archivos procesados correctamente</h5>
									<p>Se ha descargado un archivo ZIP con los resultados.</p>
								</div>
							`);
						} else {
							// Archivo Excel
							const blob = new Blob([response], {
								type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
							});

							const filename = xhr.getResponseHeader('content-disposition')
								? xhr.getResponseHeader('content-disposition').split('filename=')[1].replace(/"/g, '')
								: `procesado_${fileInput.files[0].name}`;

							const url = window.URL.createObjectURL(blob);
							const a = document.createElement('a');
							a.href = url;
							a.download = filename;
							document.body.appendChild(a);
							a.click();
							window.URL.revokeObjectURL(url);
							document.body.removeChild(a);

							$('#resultado').html(`
								<div class="alert alert-success">
									<h5>Archivo procesado correctamente</h5>
									<p>El archivo procesado ha sido descargado exitosamente.</p>
								</div>
							`);
						}
					},
					error: function(xhr, status, error) {
						$('#loading').hide();
						clearInterval(progresoIntervalo); // Detener las actualizaciones
						let errorMessage = 'Error en el servidor';

						try {
							const response = JSON.parse(xhr.responseText);
							errorMessage = response.error || errorMessage;
						} catch (e) {
							errorMessage = `${errorMessage}: ${error}`;
						}

						$('#resultado').html(`
							<div class="alert alert-danger">
								${errorMessage}
							</div>
						`);
                    }
                });
            });
        });
    </script>
</body>
</html>