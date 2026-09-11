import customtkinter as ctk

from app.ui.components.documentos_lista import DocumentosLista


class AlbaranesLista(DocumentosLista):

    def __init__(self, master, on_select):
        super().__init__(master, on_select)

    # =========================
    # NORMALIZAR DATOS
    # =========================
    def render(self, albaranes):
        """
        Adaptamos estructura de albaranes al formato
        usado por DocumentosLista
        """

        datos = []

        for a in albaranes:

            aid, numero, fecha, cliente, total = a

            datos.append(
                (
                    aid,
                    numero,
                    fecha,
                    None,  # fecha vencimiento
                    cliente,
                    total,
                    "ALBARAN",  # estado ficticio
                    None,
                )
            )

        super().render(datos)

    # =========================
    # COLOR ESTADO
    # =========================
    def _color_estado(self, estado):

        if estado == "ALBARAN":
            return "#f0a500"

        return "#b0b0b0"
