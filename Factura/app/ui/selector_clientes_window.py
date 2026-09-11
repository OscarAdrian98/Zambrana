import customtkinter as ctk
from app.services.clientes_service import obtener_clientes


class SelectorClientesWindow(ctk.CTkToplevel):

    def __init__(self, master, on_select):
        super().__init__(master)

        self.on_select = on_select
        self.cliente_seleccionado = None

        # =========================
        # CONFIG VENTANA
        # =========================
        self.title("Seleccionar cliente")
        self.geometry("600x550")
        self.resizable(False, False)
        self.grab_set()

        self.configure(fg_color="#1f1f1f")

        # Centrar ventana
        self.update_idletasks()
        x = master.winfo_rootx() + 100
        y = master.winfo_rooty() + 80
        self.geometry(f"+{x}+{y}")

        # =========================
        # TÍTULO
        # =========================
        ctk.CTkLabel(
            self,
            text="Seleccionar cliente",
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
            placeholder_text="Buscar por nombre, DNI, email…",
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

        raw = obtener_clientes()
        self.clientes = [self._normalizar(c) for c in raw]
        self.pintar_lista(self.clientes)

    # =========================
    # NORMALIZAR — acepta cualquier número de columnas
    # =========================
    def _normalizar(self, fila):
        """Convierte una fila (tupla o lista) en un dict seguro."""
        f = list(fila)
        return {
            "id": f[0] if len(f) > 0 else None,
            "nombre": f[1] if len(f) > 1 else "",
            "dni": f[2] if len(f) > 2 else "",
            "email": f[3] if len(f) > 3 else "",
            "telefono": f[4] if len(f) > 4 else "",
            "direccion": f[5] if len(f) > 5 else "",
            "iban": f[6] if len(f) > 6 else "",
        }

    # =========================
    # BUSCAR
    # =========================
    def buscar(self, event=None):
        texto = self.buscador.get().lower()

        filtrados = [
            c
            for c in self.clientes
            if texto in f"{c['nombre']} {c['dni']} {c['email']}".lower()
        ]

        self.pintar_lista(filtrados)

    # =========================
    # PINTAR LISTA
    # =========================
    def pintar_lista(self, clientes):

        for w in self.lista.winfo_children():
            w.destroy()

        if not clientes:
            ctk.CTkLabel(
                self.lista,
                text="No se encontraron clientes",
                text_color="#9a9a9a",
            ).pack(anchor="w", padx=12, pady=20)
            return

        for cliente in clientes:

            nombre = cliente["nombre"] or "(sin nombre)"
            dni = cliente["dni"] or ""
            email = cliente["email"] or ""

            card = ctk.CTkFrame(
                self.lista,
                corner_radius=10,
                fg_color="#2c2c2c",
                border_width=1,
                border_color="#3a3a3a",
            )
            card.pack(fill="x", pady=8, padx=8)

            # ---- Nombre
            ctk.CTkLabel(
                card,
                text=nombre,
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w", padx=12, pady=(10, 4))

            # ---- Info secundaria
            ctk.CTkLabel(
                card,
                text=f"DNI: {dni} · {email}",
                text_color="#9a9a9a",
            ).pack(anchor="w", padx=12, pady=(0, 10))

            # Hover effect
            card.bind("<Enter>", lambda e, c=card: c.configure(border_color="#1f6aa5"))
            card.bind("<Leave>", lambda e, c=card: c.configure(border_color="#3a3a3a"))

            # Click simple → marcar selección
            card.bind(
                "<Button-1>",
                lambda e, c=card: self._marcar_seleccion(c),
            )

            # Doble click → confirmar selección
            card.bind(
                "<Double-Button-1>",
                lambda e, c=cliente: self.seleccionar(c),
            )

            for w in card.winfo_children():
                w.bind(
                    "<Double-Button-1>",
                    lambda e, c=cliente: self.seleccionar(c),
                )

    # =========================
    # MARCAR SELECCIÓN
    # =========================
    def _marcar_seleccion(self, card):

        if self.cliente_seleccionado:
            self.cliente_seleccionado.configure(
                fg_color="#2c2c2c",
                border_color="#3a3a3a",
            )

        self.cliente_seleccionado = card

        card.configure(
            fg_color="#1f6aa5",
            border_color="#1f6aa5",
        )

    # =========================
    # CONFIRMAR
    # =========================
    def seleccionar(self, cliente):

        self.on_select(
            {
                "id": cliente["id"],
                "nombre": cliente["nombre"],
                "dni": cliente["dni"],
                "email": cliente["email"],
                "telefono": cliente["telefono"],
            }
        )
        self.destroy()
