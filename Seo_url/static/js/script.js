document.addEventListener("DOMContentLoaded", () => {
    let editorDescripcionLarga = null;

    function showLoading() {
        new bootstrap.Modal(document.getElementById("modalLoading")).show();
    }

    function hideLoading() {
        const modalEl = document.getElementById("modalLoading");
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
    }

    function fetchWithMinDelay(url, options, callback) {
        showLoading();
        const start = Date.now();
        fetch(url, options)
            .then(response => response.json())
            .then(data => {
                const elapsed = Date.now() - start;
                const waitTime = Math.max(0, 2000 - elapsed);
                setTimeout(() => callback(null, data), waitTime);
            })
            .catch(err => {
                hideLoading();
                callback(err, null);
            });
    }

    const $tabla = $('#tabla-productos');

    if ($tabla.length) {
        if ($.fn.DataTable.isDataTable($tabla)) {
            $tabla.DataTable().destroy();
        }

        const tablaDt = $tabla.DataTable({
            responsive: true,
            pageLength: 10,
            language: {
                url: "//cdn.datatables.net/plug-ins/1.13.6/i18n/es-ES.json"
            },
            createdRow: function(row, data, dataIndex) {
                const dataProducto = $(row).attr("data-producto");
                if (dataProducto) {
                    const producto = JSON.parse(dataProducto);
                    if (producto.ya_existe_en_seo) {
                        $(row).addClass("producto-existe-seo");
                    }
                }
            }
        });

        fetch("/productos")
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    data.productos.forEach(producto => {
                        insertarFilaEnTabla(producto);
                    });
                    $tabla.DataTable().draw();
                } else {
                    alert("Error cargando productos de la base de datos.");
                }
            })
            .catch(err => {
                console.error(err);
                alert("Error obteniendo datos de la base de datos.");
            });

        $tabla.on('draw.dt', function() {
            $('#tabla-productos tbody tr').each(function() {
                const dataProducto = $(this).attr("data-producto");
                if (dataProducto) {
                    const producto = JSON.parse(dataProducto);
                    if (producto.ya_existe_en_seo) {
                        $(this).addClass("producto-existe-seo");
                    } else {
                        $(this).removeClass("producto-existe-seo");
                    }
                }
            });
        });

        $tabla.on('click', '.btn-editar', function () {
            const fila = $(this).closest('tr')[0];
            const producto = JSON.parse(fila.dataset.producto);

            const idElem = document.getElementById("modal-id-product");
            idElem.textContent = producto.id_product || "";
            idElem.setAttribute("data-id", producto.id_product || "");

            const nombreElem = document.getElementById("modal-nombre-producto");
            nombreElem.textContent = producto.nombre_producto || "";
            nombreElem.setAttribute("data-nombre", producto.nombre_producto || "");

            document.getElementById("modal-imagen").src = producto.img_url || "";

            document.getElementById("modal-meta-title").value = producto.meta_title || "";
            document.getElementById("modal-meta-description").value = producto.meta_description || "";
            document.getElementById("modal-reseñas").innerHTML = "";

            document.getElementById("modal-existe-seo").innerHTML = producto.ya_existe_en_seo
                ? '<i class="bi bi-check-circle-fill text-success fs-3"></i>'
                : '<i class="bi bi-x-circle-fill text-danger fs-3"></i>';

            if (editorDescripcionLarga) {
                editorDescripcionLarga.destroy()
                    .then(() => {
                        createCKEditor(producto.descripcion_larga || "");
                    })
                    .catch(error => {
                        console.error(error);
                        createCKEditor(producto.descripcion_larga || "");
                    });
            } else {
                createCKEditor(producto.descripcion_larga || "");
            }

            fetch(`/producto/${producto.id_product}/reseñas`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        mostrarReseñasModal(data.reseñas);
                    } else {
                        console.error("Error obteniendo reseñas:", data.error);
                        document.getElementById("modal-reseñas").innerHTML = "<p>Error obteniendo reseñas.</p>";
                    }
                })
                .catch(err => {
                    console.error("Error AJAX reseñas:", err);
                    document.getElementById("modal-reseñas").innerHTML = "<p>Error obteniendo reseñas.</p>";
                });

            new bootstrap.Modal(document.getElementById("modalEditar")).show();
        });
    }

    function createCKEditor(initialData = "") {
        ClassicEditor
            .create(document.querySelector("#modal-descripcion-larga"))
            .then(editor => {
                editorDescripcionLarga = editor;
                editor.setData(initialData);
            })
            .catch(error => {
                console.error("Error inicializando CKEditor:", error);
            });
    }

    const btnGenerarDescripcionLargaDesdeActual = document.getElementById("btn-generar-descripcion-larga-desde-actual");
    if (btnGenerarDescripcionLargaDesdeActual) {
        btnGenerarDescripcionLargaDesdeActual.addEventListener("click", () => {
            const nombre_producto = document.getElementById("modal-nombre-producto").getAttribute("data-nombre");
            const descripcion_larga_actual = editorDescripcionLarga.getData();

            fetchWithMinDelay(
                "/generar_descripcion_larga_desde_existente",
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ nombre_producto, descripcion_larga_actual })
                },
                (err, data) => {
                    hideLoading();
                    if (err) return alert("Error generando la descripción larga desde la descripción actual.");
                    if (data.success) {
                        let textoHTML = (data.descripcion_larga || "")
                            .split('\n\n')
                            .map(p => `<p>${p.trim()}</p>`)
                            .join('\n');
                        editorDescripcionLarga.setData(textoHTML);
                        alert("✅ Nueva descripción larga generada.");
                    } else {
                        alert("Error al generar la descripción larga desde la descripción actual.");
                    }
                }
            );
        });
    }

    const btnGenerarDescripcionLarga = document.getElementById("btn-generar-descripcion-larga");
    if (btnGenerarDescripcionLarga) {
        btnGenerarDescripcionLarga.addEventListener("click", () => {
            const nombre_producto = document.getElementById("modal-nombre-producto").getAttribute("data-nombre");

            fetchWithMinDelay(
                "/generar_descripcion_larga",
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ nombre_producto })
                },
                (err, data) => {
                    hideLoading();
                    if (err) return alert("Error generando la descripción larga.");
                    if (data.success) {
                        let textoHTML = (data.descripcion_larga || "")
                            .split('\n\n')
                            .map(p => `<p>${p.trim()}</p>`)
                            .join('\n');
                        editorDescripcionLarga.setData(textoHTML);
                        alert("✅ Nueva descripción larga generada.");
                    } else {
                        alert("Error al generar la descripción larga.");
                    }
                }
            );
        });
    }

    const btnGenerarMetaTitle = document.getElementById("btn-generar-meta-title");
    if (btnGenerarMetaTitle) {
        btnGenerarMetaTitle.addEventListener("click", () => {
            const nombre_producto = document.getElementById("modal-nombre-producto").getAttribute("data-nombre");
            const descripcion_larga = editorDescripcionLarga.getData();

            fetchWithMinDelay(
                "/generar_meta_title",
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ nombre_producto, descripcion_larga })
                },
                (err, data) => {
                    hideLoading();
                    if (err) return alert("Error generando Meta Title.");
                    if (data.success) {
                        document.getElementById("modal-meta-title").value = data.meta_title || "";
                        alert("✅ Meta Title generado.");
                    } else {
                        alert("Error al generar el Meta Title.");
                    }
                }
            );
        });
    }

    const btnGenerarMetaDescription = document.getElementById("btn-generar-meta-description");
    if (btnGenerarMetaDescription) {
        btnGenerarMetaDescription.addEventListener("click", () => {
            const nombre_producto = document.getElementById("modal-nombre-producto").getAttribute("data-nombre");
            const descripcion_larga = editorDescripcionLarga.getData();

            fetchWithMinDelay(
                "/generar_meta_description",
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ nombre_producto, descripcion_larga })
                },
                (err, data) => {
                    hideLoading();
                    if (err) return alert("Error generando Meta Description.");
                    if (data.success) {
                        document.getElementById("modal-meta-description").value = data.meta_description || "";
                        alert("✅ Meta Description generada.");
                    } else {
                        alert("Error al generar la Meta Description.");
                    }
                }
            );
        });
    }

    const btnGenerarReseñas = document.getElementById("btn-generar-reseñas");
    if (btnGenerarReseñas) {
        btnGenerarReseñas.addEventListener("click", () => {
            const id_product = document.getElementById("modal-id-product").getAttribute("data-id");
            const nombre_producto = document.getElementById("modal-nombre-producto").getAttribute("data-nombre");
            const descripcion_larga = editorDescripcionLarga.getData();

            fetchWithMinDelay(
                "/generar_reseñas",
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ id_product, nombre_producto, descripcion_larga })
                },
                (err, data) => {
                    hideLoading();
                    if (err) return alert("Error generando reseña.");
                    if (data.success && data.reseñas?.length) {
                        document.getElementById("modal-reseñas").innerHTML = "<h5>Reseñas generadas:</h5>";
                        añadirReseñaAlModal(data.reseñas[0]);
                        alert("✅ Reseña generada.");
                    } else {
                        alert("Error al generar reseña.");
                    }
                }
            );
        });
    }

    const btnGenerarOtraReseña = document.getElementById("btn-generar-otra-reseña");
    if (btnGenerarOtraReseña) {
        btnGenerarOtraReseña.addEventListener("click", () => {
            const id_product = document.getElementById("modal-id-product").getAttribute("data-id");
            const nombre_producto = document.getElementById("modal-nombre-producto").getAttribute("data-nombre");
            const descripcion_larga = editorDescripcionLarga.getData();

            fetchWithMinDelay(
                "/generar_reseñas",
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ id_product, nombre_producto, descripcion_larga })
                },
                (err, data) => {
                    hideLoading();
                    if (err) return alert("Error generando otra reseña.");
                    if (data.success && data.reseñas?.length) {
                        añadirReseñaAlModal(data.reseñas[0]);
                        alert("✅ Otra reseña generada.");
                    } else {
                        alert("Error al generar otra reseña.");
                    }
                }
            );
        });
    }

    // ✅ Botón Guardar (solo SEO)
    const btnGuardar = document.getElementById("btn-guardar");
    if (btnGuardar) {
        btnGuardar.addEventListener("click", () => {
            guardarCambios(false);
        });
    }

    // ✅ Botón Guardar y Sincronizar
    const btnGuardarSync = document.getElementById("btn-guardar-sincronizar");
    if (btnGuardarSync) {
        btnGuardarSync.addEventListener("click", () => {
            guardarCambios(true);
        });
    }

    function guardarCambios(sincronizar) {
        const id_product = document.getElementById("modal-id-product").getAttribute("data-id");
        const nombre_producto = document.getElementById("modal-nombre-producto").getAttribute("data-nombre");
        const img_url = document.getElementById("modal-imagen").src || "";
        const descripcion_larga = editorDescripcionLarga.getData();
        const meta_title = document.getElementById("modal-meta-title").value;
        const meta_description = document.getElementById("modal-meta-description").value;

        const reseñas = [];
        const divReseñas = document.getElementById("modal-reseñas");
        if (divReseñas) {
            const reseñaBlocks = divReseñas.querySelectorAll(".mb-3.border");
            reseñaBlocks.forEach((block, i) => {
                const titulo = block.querySelector(`#reseña-titulo-${i}`)?.value || "";
                const autor = block.querySelector(`#reseña-autor-${i}`)?.value || "";
                const estrellas = parseFloat(block.querySelector(`#reseña-estrellas-${i}`)?.value) || 0;
                const texto = block.querySelector(`#reseña-texto-${i}`)?.value || "";
                const existente = block.querySelector(`#reseña-existente-${i}`)?.value === "true";
                reseñas.push({ titulo, autor, estrellas, texto, existente });
            });
        }

        let filaExistente = null;
        document.querySelectorAll("#tabla-productos tbody tr").forEach(tr => {
            const producto = JSON.parse(tr.dataset.producto);
            if (producto.id_product == id_product) {
                filaExistente = tr;
            }
        });

        const payload = {
            id_product,
            nombre_producto,
            img_url,
            descripcion_larga,
            meta_title,
            meta_description,
            reseñas,
            sincronizar
        };

        let url, method;
        if (filaExistente) {
            url = `/producto/${id_product}`;
            method = "PUT";
        } else {
            url = "/guardar_datos_seo";
            method = "POST";
        }

        fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert("✅ Datos guardados correctamente.");
                if (filaExistente) {
                    const producto = JSON.parse(filaExistente.dataset.producto);
                    producto.nombre_producto = nombre_producto;
                    producto.img_url = img_url;
                    producto.descripcion_larga = descripcion_larga;
                    producto.meta_title = meta_title;
                    producto.meta_description = meta_description;
                    producto.ya_existe_en_seo = true;
                    filaExistente.dataset.producto = JSON.stringify(producto);
                    filaExistente.querySelector("td:nth-child(1)").innerHTML =
                        producto.ya_existe_en_seo
                            ? '<i class="bi bi-check-circle-fill text-success"></i>'
                            : '<i class="bi bi-x-circle-fill text-danger"></i>';
                    filaExistente.querySelector("td:nth-child(2) img").src = img_url || 'https://via.placeholder.com/80?text=No+Image';
                    filaExistente.querySelector("td:nth-child(3)").textContent = producto.id_product;
                    filaExistente.querySelector("td:nth-child(4)").textContent = nombre_producto;
                    filaExistente.querySelector("td:nth-child(5)").textContent = descripcion_larga ? "✔" : "✘";
                    filaExistente.querySelector("td:nth-child(6)").textContent = meta_title ? "✔" : "✘";
                    filaExistente.querySelector("td:nth-child(7)").textContent = meta_description ? "✔" : "✘";
                    filaExistente.querySelector("td:nth-child(8)").innerHTML =
                        `<button class="btn btn-primary btn-editar">Editar</button>`;
                    filaExistente.classList.add("producto-existe-seo");
                } else {
                    insertarFilaEnTabla(payload);
                    $tabla.DataTable().draw();
                }
                bootstrap.Modal.getInstance(document.getElementById("modalEditar")).hide();
            } else {
                alert("❌ Error al guardar datos: " + data.error);
            }
        })
        .catch(err => {
            console.error(err);
            alert("❌ Error comunicándose con el servidor.");
        });
    }
    // Filtros para columnas Desc. Larga, Meta Title y Meta Description
    $("#filtro-desc-larga, #filtro-meta-title, #filtro-meta-description").on("change", function () {
        filtrarCamposVacios();
    });

    function filtrarCamposVacios() {
        const descLarga = $("#filtro-desc-larga").is(":checked");
        const metaTitle = $("#filtro-meta-title").is(":checked");
        const metaDesc = $("#filtro-meta-description").is(":checked");

        // Limpiar filtros existentes
        const tabla = $('#tabla-productos').DataTable();
        tabla.columns().search('');

        if (descLarga) {
            tabla.column(4).search("✘", true, false);
        }

        if (metaTitle) {
            tabla.column(5).search("✘", true, false);
        }

        if (metaDesc) {
            tabla.column(6).search("✘", true, false);
        }

        tabla.draw();
    }
});

function insertarFilaEnTabla(producto) {
    const imagenUrl = producto.img_url || 'https://via.placeholder.com/80?text=No+Image';

    const $tr = $("<tr>").attr("data-producto", JSON.stringify(producto));

    if (producto.ya_existe_en_seo) {
        $tr.addClass("producto-existe-seo");
    }

    $tr.append(`
        <td class="text-center">
            ${
                producto.ya_existe_en_seo
                    ? '<i class="bi bi-check-circle-fill text-success fs-3"></i>'
                    : '<i class="bi bi-x-circle-fill text-danger fs-3"></i>'
            }
        </td>
    `);

    $tr.append(`<td><img src="${imagenUrl}" width="80"></td>`);
    $tr.append(`<td class="text-center">${producto.id_product}</td>`);
    $tr.append(`<td class="text-center">${producto.nombre_producto}</td>`);
    $tr.append(`<td class="text-center">${producto.descripcion_larga ? "✔" : "✘"}</td>`);
    $tr.append(`<td class="text-center">${producto.meta_title ? "✔" : "✘"}</td>`);
    $tr.append(`<td class="text-center">${producto.meta_description ? "✔" : "✘"}</td>`);
    $tr.append(`
        <td class="text-center">
            <button class="btn btn-sm btn-primary btn-editar">Editar</button>
        </td>
    `);

    $('#tabla-productos').DataTable().row.add($tr);
}

function mostrarReseñasModal(reseñas, esNuevo = false) {
    const div = document.getElementById("modal-reseñas");
    div.innerHTML = "<h5>Reseñas generadas:</h5>";

    if (!reseñas || !reseñas.length) {
        div.innerHTML += "<p>No se generaron reseñas.</p>";
        return;
    }

    reseñas.forEach((r, i) => {
        div.innerHTML += `
            <div class="mb-3 border rounded p-2">
                <label>Título</label>
                <input type="text" class="form-control mb-2" value="${r.titulo || ""}" id="reseña-titulo-${i}">
                
                <label>Autor</label>
                <input type="text" class="form-control mb-2" value="${r.autor || ""}" id="reseña-autor-${i}" ${esNuevo ? "" : "readonly"}>
                <input type="hidden" id="reseña-existente-${i}" value="${esNuevo ? "false" : "true"}">

                <label>Estrellas</label>
                <input type="text" class="form-control mb-2" value="${r.estrellas || ""}" id="reseña-estrellas-${i}">
                
                <label>Texto</label>
                <textarea class="form-control" rows="2" id="reseña-texto-${i}">${r.texto || ""}</textarea>
            </div>
        `;
    });
}

function añadirReseñaAlModal(reseña) {
    const div = document.getElementById("modal-reseñas");
    const index = div.querySelectorAll(".mb-3.border").length;

    div.innerHTML += `
        <div class="mb-3 border rounded p-2">
            <label>Título</label>
            <input type="text" class="form-control mb-2" value="${reseña.titulo || ""}" id="reseña-titulo-${index}">
            
            <label>Autor</label>
            <input type="text" class="form-control mb-2" value="${reseña.autor || ""}" id="reseña-autor-${index}">
            <input type="hidden" id="reseña-existente-${index}" value="false">

            <label>Estrellas</label>
            <input type="text" class="form-control mb-2" value="${reseña.estrellas || ""}" id="reseña-estrellas-${index}">
            
            <label>Texto</label>
            <textarea class="form-control" rows="2" id="reseña-texto-${index}">${reseña.texto || ""}</textarea>
        </div>
    `;
}