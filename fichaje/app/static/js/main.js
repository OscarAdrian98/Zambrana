document.addEventListener("DOMContentLoaded", function () {
    const toastElements = document.querySelectorAll(".app-toast");

    if (!window.bootstrap || !window.bootstrap.Toast) {
        return;
    }

    toastElements.forEach(function (element) {
        window.bootstrap.Toast.getOrCreateInstance(element).show();
    });
});
