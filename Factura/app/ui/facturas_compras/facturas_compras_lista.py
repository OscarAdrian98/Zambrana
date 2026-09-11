import customtkinter as ctk

from app.ui.components.documentos_lista import DocumentosLista


class FacturasComprasLista(DocumentosLista):
    """
    Lista reutilizable para facturas de compra.

    Hereda del componente común DocumentosLista para evitar
    duplicar la lógica de:
    - tarjetas
    - tabla
    - selección
    - colores de estado
    """

    def __init__(self, master, on_select):
        super().__init__(master, on_select)

    def _color_estado(self, estado):
        """
        Personalizamos colores si quieres distinguir compras
        del resto de documentos.
        """
        return {
            "PENDIENTE": "#f39c12",
            "PAGADA": "#2fa572",
        }.get(str(estado).upper(), "#b0b0b0")
