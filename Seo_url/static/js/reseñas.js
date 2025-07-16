document.addEventListener("DOMContentLoaded", () => {
    // ✅ Inicializa DataTable de nuevo
    let tabla = $("#tabla-productos").DataTable({
        responsive: false,
        autoWidth: false,
        pageLength: 10,
        order: [[7, "desc"]],   // ✅ NUEVO → ordena por columna 7 (última fecha reseña)
        language: {
            url: "//cdn.datatables.net/plug-ins/1.13.6/i18n/es-ES.json",
            lengthMenu: "Mostrar _MENU_ registros por página",
            zeroRecords: "No se encontraron resultados",
            info: "Mostrando _START_ a _END_ de _TOTAL_ registros",
            infoEmpty: "No hay registros disponibles",
            infoFiltered: "(filtrado de _MAX_ registros totales)",
            search: "Buscar:",
            paginate: {
                first: "Primero",
                last: "Último",
                next: "Siguiente",
                previous: "Anterior"
            }
        },
        columnDefs: [
            { targets: [7], visible: false } // ✅ NUEVO → oculta la columna Última Fecha Reseña
        ]
    });

    // ✅ Filtro SEO
    $("#filtro-seo").on("change", function () {
        const val = $(this).val();
        if (val === "") {
            tabla.column(0).search("").draw();
        } else {
            tabla.column(0).search(val, true, false).draw();
        }
    });

    fetch("/prestashop/reviews/productos")
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                data.productos.forEach(producto => {
                    insertarFilaEnTabla(producto);
                });
                tabla.draw();
            } else {
                alert("Error cargando productos con reseñas.");
            }
        })
        .catch(err => {
            console.error(err);
            alert("Error obteniendo productos con reseñas.");
        });

    $("#tabla-productos").on("click", ".btn-editar", function () {
        const fila = $(this).closest("tr")[0];
        const producto = JSON.parse(fila.dataset.producto);

        document.getElementById("modal-id-product").textContent = producto.id_product || "";
        document.getElementById("modal-id-product").setAttribute("data-id", producto.id_product || "");

        document.getElementById("modal-nombre-producto").textContent = producto.nombre_producto || "";
        document.getElementById("modal-nombre-producto").setAttribute("data-nombre", producto.nombre_producto || "");

        mostrarSpinnerEnReseñas();

        new bootstrap.Modal(document.getElementById("modalEditar")).show();

        fetch(`/prestashop/reviews/producto/${producto.id_product}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    mostrarReseñasModal(data.reseñas);
                } else {
                    document.getElementById("modal-reseñas").innerHTML = "<p>Error obteniendo reseñas.</p>";
                }
            })
            .catch(err => {
                console.error(err);
                document.getElementById("modal-reseñas").innerHTML = "<p>Error obteniendo reseñas.</p>";
            });
    });

    const btnGenerarOtraReseña = document.getElementById("btn-generar-otra-reseña");
    if (btnGenerarOtraReseña) {
        btnGenerarOtraReseña.addEventListener("click", () => {
            const id_product = document.getElementById("modal-id-product").getAttribute("data-id");
            const nombre_producto = document.getElementById("modal-nombre-producto").getAttribute("data-nombre");

            mostrarSpinnerSobreModal();

            fetch("/generar_reseñas", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    id_product,
                    nombre_producto,
                    descripcion_larga: ""
                })
            })
            .then(res => {
                if (!res.ok) {
                    throw new Error(`HTTP error ${res.status}`);
                }
                return res.json();
            })
            .then(data => {
                if (data.success && data.reseñas?.length) {
                    const div = document.getElementById("modal-reseñas");
                    if (!div.querySelector("h5")) {
                        div.insertAdjacentHTML("beforeend", "<h5>Reseñas:</h5>");
                    }
                    añadirReseñaAlModal(data.reseñas[0]);
                    alert("✅ Otra reseña generada.");
                } else {
                    alert("❌ Error generando reseña IA.");
                }
            })
            .catch(err => {
                console.error(err);
                alert("❌ Error generando reseña IA.");
            })
            .finally(() => {
                ocultarSpinnerSobreModal();
            });
        });
    }

    const btnGuardar = document.getElementById("btn-guardar-reseñas");
    if (btnGuardar) {
        btnGuardar.addEventListener("click", () => {
            guardarCambios();
        });
    }
});

function insertarFilaEnTabla(producto) {
    const textoSeo = producto.ya_existe_en_seo ? "Sí" : "No";
    const iconSeo = producto.ya_existe_en_seo
        ? '<span class="d-none">Sí</span><i class="bi bi-check-circle-fill text-success fs-4"></i>'
        : '<span class="d-none">No</span><i class="bi bi-x-circle-fill text-danger fs-4"></i>';

    const mediaEstrellas = producto.media_estrellas
        ? producto.media_estrellas.toFixed(1)
        : "0.0";

    let textoActivas = producto.total_reseñas_activas || 0;

    let iconoActivas;
    if (producto.total_reseñas === 0) {
        iconoActivas = '<i class="bi bi-x-circle-fill text-danger fs-5 ms-1"></i>';
    } else if (producto.total_reseñas === producto.total_reseñas_activas) {
        iconoActivas = '<i class="bi bi-check-circle-fill text-success fs-5 ms-1"></i>';
    } else {
        iconoActivas = '<i class="bi bi-x-circle-fill text-danger fs-5 ms-1"></i>';
    }

    const $tr = $("<tr>").attr("data-producto", JSON.stringify(producto));

    $tr.append(`
        <td class="text-center" data-order="${textoSeo}">
            ${iconSeo}
        </td>
    `);
    $tr.append(`<td class="text-center">${producto.id_product}</td>`);
    $tr.append(`<td class="text-center">${producto.nombre_producto || ""}</td>`);
    $tr.append(`<td class="text-center">${producto.total_reseñas || 0}</td>`);
    $tr.append(`
        <td class="text-center">
            ${textoActivas} ${iconoActivas}
        </td>
    `);
    $tr.append(`<td class="text-center">${mediaEstrellas}</td>`);
    $tr.append(`
        <td class="text-center">
            <button class="btn btn-sm btn-primary btn-editar">Editar</button>
        </td>
    `);

    // ✅ NUEVO → insertar columna oculta con la fecha
    $tr.append(`
        <td class="text-center d-none">${producto.ultima_fecha_reseña || ""}</td>
    `);

    $("#tabla-productos").DataTable().row.add($tr);
}

function mostrarReseñasModal(reseñas) {
    const div = document.getElementById("modal-reseñas");
    div.innerHTML = "<h5>Reseñas:</h5>";

    if (!reseñas || !reseñas.length) {
        div.insertAdjacentHTML("beforeend", "<p>No hay reseñas registradas.</p>");
        return;
    }

    reseñas.forEach((r, i) => {
        div.insertAdjacentHTML("beforeend", generarHTMLReseña(r, i, true));
    });
}

function añadirReseñaAlModal(reseña) {
    const div = document.getElementById("modal-reseñas");
    div.insertAdjacentHTML("beforeend", generarHTMLReseña(reseña, 0, false));
}

function generarHTMLReseña(r, i, existente) {
    return `
        <div class="mb-3 border rounded p-2">
            <label>Título</label>
            <input type="text" class="form-control mb-2 reseña-titulo" value="${r.titulo || ""}">
            
            <label>Autor</label>
            <input type="text" class="form-control mb-2 reseña-autor" value="${r.autor || ""}" ${existente ? "readonly" : ""}>
            <input type="hidden" class="reseña-existente" value="${existente}">

            <label>Estrellas</label>
            <input type="number" class="form-control mb-2 reseña-estrellas" value="${r.estrellas || ""}" step="0.1" min="0" max="5">
            
            <label>Texto</label>
            <textarea class="form-control reseña-texto" rows="2">${r.texto || ""}</textarea>

            <label class="mt-2">
            <input type="checkbox" class="reseña-status" ${r.status == 1 ? "checked" : ""}>
            Activo
            </label>

            <button class="btn btn-danger btn-sm mt-2" onclick="this.closest('.mb-3').remove()">
                Eliminar
            </button>
        </div>
    `;
}

function guardarCambios() {
    const id_product = document.getElementById("modal-id-product").getAttribute("data-id");

    const reseñas = [];
    const blocks = document.querySelectorAll("#modal-reseñas .mb-3.border");

    blocks.forEach(block => {
        const titulo = block.querySelector(".reseña-titulo")?.value || "";
        const autor = block.querySelector(".reseña-autor")?.value || "";
        const estrellas = parseFloat(block.querySelector(".reseña-estrellas")?.value) || 0;
        const texto = block.querySelector(".reseña-texto")?.value || "";
        const existente = block.querySelector(".reseña-existente")?.value === "true";
        const status = block.querySelector(".reseña-status")?.checked ? 1 : 0;
    
        reseñas.push({
            titulo,
            autor,
            estrellas,
            texto,
            status,
            existente
        });
    });

    mostrarSpinnerEnReseñas();

    fetch("/prestashop/reviews/guardar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            id_product,
            reseñas
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert("✅ Reseñas guardadas correctamente.");
            $("#modalEditar").modal("hide");
            location.reload();
        } else {
            alert("❌ Error al guardar reseñas.");
        }
    })
    .catch(err => {
        console.error(err);
        alert("❌ Error al guardar reseñas.");
    })
    .finally(() => {
        ocultarSpinnerEnReseñas();
    });
}

function mostrarSpinnerEnReseñas() {
    const div = document.getElementById("modal-reseñas");
    div.innerHTML = `
        <div class="text-center p-3">
            <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;"></div>
        </div>
    `;
}

function ocultarSpinnerEnReseñas() {
    // Spinner se sustituye automáticamente al volver a cargar reseñas
}

function mostrarSpinnerSobreModal() {
    if (!document.getElementById("spinner-overlay")) {
        const overlay = document.createElement("div");
        overlay.id = "spinner-overlay";
        overlay.style.position = "absolute";
        overlay.style.top = 0;
        overlay.style.left = 0;
        overlay.style.width = "100%";
        overlay.style.height = "100%";
        overlay.style.backgroundColor = "rgba(255, 255, 255, 0.6)";
        overlay.style.display = "flex";
        overlay.style.alignItems = "center";
        overlay.style.justifyContent = "center";
        overlay.innerHTML = `
            <div class="spinner-border text-primary" style="width: 3rem; height: 3rem;" role="status"></div>
        `;
        document.querySelector("#modalEditar .modal-content").appendChild(overlay);
    }
}

function ocultarSpinnerSobreModal() {
    const overlay = document.getElementById("spinner-overlay");
    if (overlay) {
        overlay.remove();
    }
}