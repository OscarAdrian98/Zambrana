import customtkinter as ctk
from app.services.productos_service import obtener_productos


class SelectorProductosWindow(ctk.CTkToplevel):

    def __init__(self, master, on_select):
        super().__init__(master)

        self.on_select = on_select
        self.producto_seleccionado = None

        # =========================
        # CONFIG VENTANA
        # =========================
        self.title("Seleccionar producto")
        self.geometry("650x580")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color="#1f1f1f")

        # Centrar ventana
        self.update_idletasks()
        x = master.winfo_rootx() + 120
        y = master.winfo_rooty() + 90
        self.geometry(f"+{x}+{y}")

        # =========================
        # TÍTULO
        # =========================
        ctk.CTkLabel(
            self,
            text="Seleccionar producto",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(20, 5))

        # =========================
        # BUSCADOR
        # =========================
        buscador_frame = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color="#2c2c2c",
            border_width=1,
            border_color="#3a3a3a",
        )
        buscador_frame.pack(fill="x", padx=20, pady=(5, 10))

        self.buscador = ctk.CTkEntry(
            buscador_frame,
            placeholder_text="Buscar por nombre o referencia…",
        )
        self.buscador.pack(fill="x", padx=10, pady=10)
        self.buscador.bind("<KeyRelease>", self.buscar)

        # =========================
        # LISTA
        # =========================
        self.lista = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
        )
        self.lista.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # =========================
        # CARGAR PRODUCTOS
        # =========================
        self.productos = obtener_productos()
        print("DEBUG PRODUCTOS:", self.productos)

        self.pintar_lista(self.productos)

    # =========================
    # BUSCAR
    # =========================
    def buscar(self, event=None):

        texto = self.buscador.get().lower()

        filtrados = []

        for p in self.productos:

            referencia = (p[1] or "").lower()
            nombre = (p[3] or "").lower()

            if texto in nombre or texto in referencia:
                filtrados.append(p)

        self.pintar_lista(filtrados)

    # =========================
    # PINTAR LISTA
    # =========================
    def pintar_lista(self, productos):

        for w in self.lista.winfo_children():
            w.destroy()

        if not productos:
            ctk.CTkLabel(
                self.lista,
                text="No hay productos disponibles",
                text_color="#888888",
            ).pack(pady=20)
            return

        for producto in productos:

            pid = producto[0]
            referencia = producto[1]
            nombre = producto[3]
            precio = producto[4]
            iva = producto[5]
            stock = producto[6]

            card = ctk.CTkFrame(
                self.lista,
                corner_radius=10,
                fg_color="#2c2c2c",
                border_width=1,
                border_color="#3a3a3a",
            )
            card.pack(fill="x", pady=8, padx=8)

            titulo = f"{referencia or ''} - {nombre}"

            ctk.CTkLabel(
                card,
                text=titulo,
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w", padx=12, pady=(10, 4))

            extra = f"{precio:.2f} € · IVA {iva}%"

            if stock is not None:
                extra += f" · Stock {stock}"

            ctk.CTkLabel(
                card,
                text=extra,
                text_color="#9a9a9a",
            ).pack(anchor="w", padx=12, pady=(0, 10))

            # Hover
            card.bind("<Enter>", lambda e, c=card: c.configure(border_color="#1f6aa5"))
            card.bind("<Leave>", lambda e, c=card: c.configure(border_color="#3a3a3a"))

            # Doble click selecciona
            card.bind(
                "<Double-Button-1>",
                lambda e, p=producto: self.seleccionar(p),
            )

            for w in card.winfo_children():
                w.bind(
                    "<Double-Button-1>",
                    lambda e, p=producto: self.seleccionar(p),
                )

    # =========================
    # CONFIRMAR SELECCIÓN
    # =========================
    def seleccionar(self, producto):

        producto_dict = {
            "id": producto[0],
            "referencia": producto[1],
            "nombre": producto[3],
            "precio": producto[4],
            "iva": producto[5],
            "stock": producto[6],
        }

        self.on_select(producto_dict)
        self.destroy()
