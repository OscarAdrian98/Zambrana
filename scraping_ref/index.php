<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Buscador Ref Competencia</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f8f9fa;
        }
        .container {
            max-width: 1000px;
            margin: auto;
        }
        .form-label {
            font-size: 16px;
        }
        .form-control {
            height: 42px;
            font-size: 16px;
        }
        .btn {
            height: 42px;
            font-size: 16px;
        }
        table {
            margin-top: 20px;
            width: 100%;
            border-collapse: collapse;
        }
        thead th {
            background-color: #007bff;
            color: white;
            text-align: center;
            font-size: 16px;
        }
        tbody tr:nth-child(odd) {
            background-color: #f2f2f2;
        }
        tbody tr:nth-child(even) {
            background-color: #ffffff;
        }
        tbody td {
            text-align: center;
            vertical-align: middle;
            font-size: 15px;
            padding: 10px;
        }
        .text-nowrap {
            white-space: nowrap;
        }
        h3 {
            margin-top: 30px;
            text-align: center;
            color: #343a40;
        }
        .btn-download {
            margin-top: 20px;
        }
        #resumen {
            margin-top: 20px;
            font-size: 16px;
            color: #343a40;
        }
        .mxzambrana {
            font-weight: bold;
        }
        .icon-medal {
            display: inline-block;
            width: 16px;
            height: 16px;
            vertical-align: middle;
        }
    </style>
</head>
<body>
<div class="container mt-5">
    <h1 class="text-center">Buscador Ref Competencia</h1>
    <form id="searchForm" class="mt-4">
        <div class="mb-3">
            <label for="reference" class="form-label">Referencia</label>
            <input type="text" class="form-control" id="reference" placeholder="Ejemplo: 32046-M-007" required>
        </div>
        <button type="submit" class="btn btn-primary w-100">Buscar</button>
    </form>
    <div id="resultados" class="mt-4">
        <h3>Resultados</h3>
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>Nombre</th>
                    <th>Referencia Competencia</th>
                    <th>PVP</th>
                    <th>Precio Final</th>
                    <th>Descuento</th>
                    <th>Competencia</th>
                </tr>
            </thead>
            <tbody id="resultadosBody"></tbody>
        </table>
        <div id="resumen"></div>
    </div>
</div>

<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<script>
    $(document).ready(function () {
        function calcularSimilitud(ref1, ref2) {
            const cleanRef1 = ref1.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
            const cleanRef2 = ref2.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();

            let matches = 0;
            for (let char of cleanRef1) {
                if (cleanRef2.includes(char)) {
                    matches++;
                }
            }

            return matches / Math.max(cleanRef1.length, cleanRef2.length);
        }

        $('#searchForm').on('submit', function (e) {
            e.preventDefault();
            const reference = $('#reference').val();

            $('#resultadosBody').empty();
            $('#resumen').empty();
            $('#resultados .alert').remove();
            $('#resultados .text-center.mt-3').remove();
            $('#resultadosBody').append('<tr id="loadingRow"><td colspan="6" class="text-center text-muted">Buscando...</td></tr>');

            const resultados = [];
            const eventSource = new EventSource(`http://:5001/buscar?reference=${encodeURIComponent(reference)}`); // Poner ip de la máquina donde se ejecute el script de Python

            eventSource.onmessage = function (event) {
                const data = JSON.parse(event.data);

                if (data.completed) {
                    eventSource.close();
                    $('#loadingRow').remove();
                    $('#resultados').append('<div class="alert alert-success text-center mt-3">Búsqueda completada.</div>');

                    if (resultados.length > 0) {
                        const mxzambrana = resultados.find(p => p.competencia === 'MX Zambrana');
                        const cheapest = resultados.reduce((prev, current) => {
                            const prevPrice = parseFloat(prev.final_price.replace(',', '.').replace('€', '')) || Infinity;
                            const currentPrice = parseFloat(current.final_price.replace(',', '.').replace('€', '')) || Infinity;
                            return currentPrice < prevPrice ? current : prev;
                        });

                        if (cheapest) {
                            $('#resultadosBody tr').each(function () {
                                const competencia = $(this).find('td:last').text().trim();
                                const price = parseFloat($(this).find('td:nth-child(4)').text().replace(',', '.').replace('€', '')) || Infinity;

                                if (price === parseFloat(cheapest.final_price.replace(',', '.').replace('€', ''))) {
                                    $(this).find('td:nth-child(4)').append(`
                                        <img src="https://www.svgrepo.com/show/422144/medal-award-winner.svg" class="icon-medal" alt="Cheapest">
                                    `);
                                }
                            });

                            const mxzambranaPrice = parseFloat(mxzambrana?.final_price.replace(',', '.').replace('€', '')) || Infinity;
                            const cheapestPrice = parseFloat(cheapest.final_price.replace(',', '.').replace('€', '')) || Infinity;
                            const diff = Math.max(0, mxzambranaPrice - cheapestPrice);

                            $('#resumen').html(`
                                <p>Lo tiene más barato: <strong>${cheapest.competencia || '-'}</strong> por <strong>${cheapest.final_price || '-'}</strong>.</p>
                                <p>La diferencia con MX Zambrana es de <strong>${diff.toFixed(2)}€</strong>.</p>
                            `);
                        }
                    }

                    if (resultados.length > 0) {
                        $('#resultados').append(`
                            <div class="text-center mt-3">
                                <button class="btn btn-success" id="downloadExcel">Descargar Excel</button>
                            </div>
                        `);

                        $('#downloadExcel').on('click', function () {
                            descargarExcel(resultados, reference);
                        });
                    }
                } else if (data.success) {
                    $('#loadingRow').remove();

                    const product = data.result;
                    const similarity = calcularSimilitud(reference, product.ref_competencia || '');

                    if (similarity >= 0.7) {
                        resultados.push(product);
                        const competenciaClass = product.competencia === 'MX Zambrana' ? 'mxzambrana' : '';
                        const row = `
                            <tr class="${competenciaClass}">
                                <td>${product.name || '-'}</td>
                                <td>${product.ref_competencia || '-'}</td>
                                <td class="text-nowrap">${product.pvp || '-'}</td>
                                <td class="text-nowrap">${product.final_price || '-'}</td>
                                <td>${product.discount || '-'}</td>
                                <td>${product.competencia || '-'}</td>
                            </tr>`;
                        $('#resultadosBody').append(row);
                    }
                } else if (data.error) {
                    console.error('Error:', data.error);
                }
            };

            eventSource.onerror = function () {
                $('#loadingRow').remove();
                eventSource.close();
                $('#resultados').append('<div class="alert alert-danger text-center mt-3">Ocurrió un error en la búsqueda.</div>');
                console.log('Conexión cerrada por error.');
            };
        });

        function descargarExcel(resultados, reference) {
            $.ajax({
                url: 'http://:5001/descargar', // Poner ip de la máquina donde se ejecute el script de Python
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ file_type: 'excel', results: resultados, reference: reference }),
                xhrFields: {
                    responseType: 'blob'
                },
                success: function (response, status, xhr) {
                    const contentType = xhr.getResponseHeader('Content-Type');
                    const blob = new Blob([response], { type: contentType });
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'resultados.xlsx';
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                },
                error: function () {
                    alert('Error al descargar el archivo.');
                }
            });
        }
    });
</script>
</body>
</html>