$(document).ready(function() {
    // Mostrar u ocultar los campos de mapeo manual según el checkbox
    $('#usePredefinedMapping').change(function() {
        if ($(this).is(':checked')) {
            // Ocultar los campos de mapeo manual si está seleccionado el mapeo predefinido
            $('.row.mb-4').not(':first').hide();
        } else {
            // Mostrar los campos de mapeo manual
            $('.row.mb-4').not(':first').show();
        }
    });

    // Evento de envío del formulario
    $('#uploadForm').submit(function(e) {
        e.preventDefault();
        var formData = new FormData();

        // Añadir el archivo seleccionado al FormData
        var fileInput = $('#fileToUpload')[0];
        if (fileInput.files.length > 0) {
            formData.append('fileToUpload', fileInput.files[0]);
        } else {
            alert('Por favor, selecciona un archivo para subir.');
            return;
        }

        // Comprobar si se ha seleccionado el mapeo predefinido
        if ($('#usePredefinedMapping').is(':checked')) {
            formData.append('usePredefinedMapping', 'true');
        } else {
            // Agregar las letras de las columnas del mapeo a formData solo si no están vacías
            function appendToFormData(key, value) {
                if (value && value.trim() !== '') {
                    formData.append(key, value.trim());
                }
            }

            // Ambar: recoger las columnas mapeadas de Ambar
            appendToFormData('ambarSeasonColumn', $('#ambarSeasonColumn').val());
            appendToFormData('ambarProductColumn', $('#ambarProductColumn').val());
            appendToFormData('ambarGamaColumn', $('#ambarGamaColumn').val());
            appendToFormData('ambarMarcaColumn', $('#ambarMarcaColumn').val());

            // Prestashop: recoger las columnas mapeadas de Prestashop
            appendToFormData('prestashopSeasonColumn', $('#prestashopSeasonColumn').val());
            appendToFormData('prestashopProductColumn', $('#prestashopProductColumn').val());
            appendToFormData('prestashopGamaColumn', $('#prestashopGamaColumn').val());
            appendToFormData('prestashopMarcaColumn', $('#prestashopMarcaColumn').val());
            appendToFormData('prestashopCategoryColumn', $('#prestashopCategoryColumn').val());
            appendToFormData('prestashopSizeColumn', $('#prestashopSizeColumn').val());
            appendToFormData('prestashopGenderColumn', $('#prestashopGenderColumn').val());
            appendToFormData('prestashopAgeColumn', $('#prestashopAgeColumn').val());
        }

        // Realizar petición AJAX para enviar el archivo y procesarlo
        $.ajax({
            url: 'process.php',
            type: 'POST',
            data: formData,
            contentType: false,
            processData: false,
            dataType: 'json',
            success: function(data) {
                if (!data.success) {
                    $('#results').html(`<p class="text-danger">${data.message}</p>`);
                } else {
                    $('#ambarResults').empty();
                    $('#prestashopResults').empty();
                    displayDifferences(data, 'ambar', $('#ambarResults'));
                    displayDifferences(data, 'prestashop', $('#prestashopResults'));

                    // Mostrar botones de generar Excel si el procesamiento fue exitoso
                    if (data.showGenerateButton) {
                        // Remover botones existentes si ya están presentes
                        $('#generateExcel').remove();
                        $('#generateProductExcel').remove();
                        $('#generatePsCombiExcel').remove();

                        // Botón para generar el archivo Excel de Ambar
                        $('#results').append('<button id="generateExcel" class="btn btn-success mt-4">Generar Excel para Ambar</button>');
                        $('#generateExcel').on('click', function() {
                            window.location.href = 'generate_excel.php?file=ambar'; // Redirigir al script que genera el Excel para Ambar
                        });

                        // Botón para generar el archivo Excel de Prestashop (ps_product)
                        $('#results').append('<button id="generateProductExcel" class="btn btn-primary mt-4">Generar Excel para Prestashop (ps_product)</button>');
                        $('#generateProductExcel').on('click', function() {
                            window.location.href = 'generate_excel.php?file=prestashop'; // Redirigir al script que genera el Excel para Prestashop
                        });

                        // Botón para generar el archivo Excel de Prestashop (ps_combi)
                        $('#results').append('<button id="generatePsCombiExcel" class="btn btn-warning mt-4">Generar Excel para Prestashop (ps_combi)</button>');
                        $('#generatePsCombiExcel').on('click', function() {
                            window.location.href = 'generate_excel.php?file=ps_combi'; // Redirigir al script que genera el Excel para ps_combi
                        });
                    }
                }
            },
            error: function(xhr, status, error) {
                // Mostrar mensaje de error más detallado
                $('#results').html("<p>Error al procesar el archivo. Por favor intenta de nuevo.</p>");
                console.error('Error en la petición AJAX:', status, error);
                console.error('Respuesta completa del servidor:', xhr.responseText); // Ver respuesta completa
                alert('Error del servidor: ' + xhr.responseText);
            }
        });
    });

    // Función para mostrar las diferencias entre los datos del CSV y la base de datos
    function displayDifferences(data, type, container) {
        if (!data[type + 'Differences']) {
            console.error(`No differences data available for ${type}`);
            return;
        }

        var output = `<h3>Diferencias en ${type.charAt(0).toUpperCase() + type.slice(1)}:</h3>`;
        const mapping = {
            seasonDifferences: 'TEMPORADA',
            productDifferences: 'PRODUCTO',
            gamaDifferences: 'GAMA',
            marcaDifferences: 'MARCA',
            categoryDifferences: 'CATEGORÍA',
            sizeDifferences: 'TALLAS',
            genderDifferences: 'GÉNERO',
            ageDifferences: 'EDAD'
        };

        const dbMapping = {
            seasonDifferences: 'temporada',
            productDifferences: 'producto',
            gamaDifferences: 'gama',
            marcaDifferences: 'marca',
            categoryDifferences: 'categoria',
            sizeDifferences: 'tallas',
            genderDifferences: 'genero',
            ageDifferences: 'edad'
        };

        let hasDifferences = false; // Variable para verificar si hay diferencias

        Object.keys(data[type + 'Differences']).forEach(key => {
            if (data[type + 'Differences'][key] && data[type + 'Differences'][key].length > 0) {
                hasDifferences = true;
                output += `<h4>${mapping[key] || key}:</h4>`;
                data[type + 'Differences'][key].forEach(function(diff) {
                    var dbFieldName = dbMapping[key];
                    output += `<p>${diff} <button class='btn btn-primary add-to-db' data-type='${dbFieldName}' data-value='${diff}' data-system='${type}'>Añadir a ${type.charAt(0).toUpperCase() + type.slice(1)}</button></p>`;
                });
            }
        });

        if (!hasDifferences) {
            output += '<p>No hay diferencias encontradas.</p>';
        }

        container.html(output);
    }

    // Evento para el botón "Añadir a" (inserción en la base de datos)
    $(document).on('click', '.add-to-db', function(event) {
        event.preventDefault();

        var button = $(this);
        var type = button.data('type');
        var value = button.data('value');
        var system = button.data('system');

        $.ajax({
            url: 'process.php',
            type: 'POST',
            data: {
                type: type,
                value: value,
                system: system
            },
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    alert('Dato añadido correctamente a la base de datos.');
                    // Opcional: remover el elemento de la lista o actualizar la interfaz
                    button.parent().remove();
                } else {
                    alert('Error al añadir el dato a la base de datos: ' + response.message);
                }
            },
            error: function(xhr) {
                alert('Error al añadir el dato a la base de datos: ' + xhr.responseText);
            }
        });
    });
});
