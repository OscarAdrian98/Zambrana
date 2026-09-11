"""
facturas/facturas_lista.py
Lista de facturas — CustomTkinter
"""


from app.ui.components.documentos_lista import DocumentosLista


class FacturasLista(DocumentosLista):
    """
    Lista de facturas reutilizando el componente base DocumentosLista.

    Este componente ya gestiona:
    - vista TARJETAS
    - vista TABLA
    - selección
    - hover
    - renderizado
    """

    def __init__(self, parent=None, on_select=None):

        super().__init__(parent, on_select)

    # =========================================================
    # COLORES ESTADO FACTURAS
    # =========================================================

    def _color_estado(self, estado):

        estado = str(estado).upper()

        return {
            "PENDIENTE": "#4ea8ff",
            "VENCIDA": "#ff4e4e",
            "PAGADA": "#4eff7a",
        }.get(estado, "#b0b0b0")
