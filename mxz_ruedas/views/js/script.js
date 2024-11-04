document.addEventListener("DOMContentLoaded", function () {
    // Establecer la configuración predeterminada al cargar la página
    initializeColorDisplays("husqvarna");
    updatePreviewImage("husqvarna", "plata", "plata", "plata", "plata");
});

// Manejador de eventos para clicks en los cuadros de modelos y colores
document.addEventListener("click", function (event) {
    if (event.target.classList.contains("color-square") ||
        event.target.classList.contains("model-square")) {
        updateWheelConfiguration(event.target);
    }
});

function updateWheelConfiguration(target) {
    // Identificar si se ha seleccionado un modelo o un color
    if (target.classList.contains("model-square")) {
        const modelSquares = document.querySelectorAll(".model-square");
        modelSquares.forEach((square) => square.classList.remove("selected"));
        target.classList.add("selected");
    } else if (target.classList.contains("color-square")) {
        const parent = target.parentNode;
        const colorName = target.title; // Asumiendo que 'title' contiene el nombre del color
        const partId = parent.id;

        parent.querySelectorAll(".color-square").forEach((square) => square.classList.remove("selected"));
        target.classList.add("selected");

        // Usamos setTimeout para asegurarnos de que el DOM se ha actualizado antes de aplicar la clase
        setTimeout(() => {
            const colorSpan = document.getElementById(`${partId}-color-name`);
            colorSpan.textContent = `Color ${colorName}`;
            colorSpan.className = "color-name";
        }, 0);
    }
    updatePreview();
}

function updatePreview() {
    // Obtener el modelo y los colores seleccionados
    const model = document.querySelector(".model-square.selected")?.dataset.value || "husqvarna";
    const rim = document.querySelector("#rim .color-square.selected")?.dataset.value || "plata";
    const hub = document.querySelector("#hub .color-square.selected")?.dataset.value || "plata";
    const spoke = document.querySelector("#spoke .color-square.selected")?.dataset.value || "plata";
    const nipple = document.querySelector("#nipple .color-square.selected")?.dataset.value || "plata";

    updatePreviewImage(model, rim, hub, spoke, nipple);
}

function updatePreviewImage(model, rim, hub, spoke, nipple) {
    // Actualizar la imagen en el canvas según las selecciones
    const canvas = document.getElementById("configImageCanvas");
    const ctx = canvas.getContext("2d");
    canvas.width = 1000;
    canvas.height = 800;

    const imagesToLoad = [
        `${basePath}${model}.png`, // Imagen base del modelo
        `${basePath}aro-${rim}.png`, // Imagen del aro
        `${basePath}buje-${hub}.png`, // Imagen del buje
        `${basePath}radio-${spoke}.png`, // Imagen del radio
        `${basePath}tuerca-${nipple}.png`, // Imagen de la tuerca
    ];

    let loadedImages = 0;
    const images = [];

    imagesToLoad.forEach((src, index) => {
        const img = new Image();
        img.onload = () => {
            images[index] = img;
            loadedImages++;
            if (loadedImages === imagesToLoad.length) {
                // Una vez todas las imágenes estén cargadas, dibujarlas en el canvas
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                images.forEach((image) => {
                    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
                });
            }
        };
        img.src = src;
    });
}

function initializeColorDisplays(model) {
    // Inicializar los cuadros de selección por defecto para el modelo y colores
    document.querySelector(`.model-square[data-value="${model}"]`).classList.add("selected");
    document.querySelector('#rim .color-square[data-value="plata"]').classList.add("selected");
    document.querySelector('#hub .color-square[data-value="plata"]').classList.add("selected");
    document.querySelector('#spoke .color-square[data-value="plata"]').classList.add("selected");
    document.querySelector('#nipple .color-square[data-value="plata"]').classList.add("selected");
}
