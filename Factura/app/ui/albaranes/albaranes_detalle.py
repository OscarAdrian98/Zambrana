import customtkinter as ctk
from datetime import datetime
from app.ui.email_dialog import EmailDialog
from app.services.pdf_service import generar_pdf_albaran
from app.services.clientes_service import obtener_email_cliente


class AlbaranesDetalle(ctk.CTkFrame):

    def __init__(
        self,
        master,
        on_facturar=None,
        on_borrar_linea=None,
        on_borrar_albaran=None,
        on_pdf=None,
        on_nueva_linea=None,
        on_editar_linea=None,
    ):

        super().__init__(
            master,
            corner_radius=14,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )

        self.on_facturar = on_facturar
        self.on_borrar_linea = on_borrar_linea
        self.on_borrar_albaran = on_borrar_albaran
        self.on_pdf = on_pdf
        self.on_nueva_linea = on_nueva_linea
        self.on_editar_linea = on_editar_linea

        self.albaran_id = None
        self.linea_id = None
        self.cliente_id = None # Added for fetching email
        self.albaran_email = None # Initialize here

        self.card_linea_sel = None

        # =========================
        # CABECERA
        # =========================
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=20, pady=(20, 10))

        self.titulo = ctk.CTkLabel(
            cab,
            text="Detalle del albarán",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.titulo.pack(side="left")

        self.btn_pdf = ctk.CTkButton(
            cab,
            text="📄 PDF",
            width=120,
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            state="disabled",
            command=self._accion_pdf,
        )
        self.btn_pdf.pack(side="right", padx=(0, 10))

        self.btn_email = ctk.CTkButton(
            cab,
            text="✉ Email",
            width=90,
            fg_color="#3b8ed0",
            hover_color="#2f6fa0",
            state="disabled",
            command=self._accion_email,
        )
        self.btn_email.pack(side="right", padx=(0, 10))

        self.btn_borrar_albaran = ctk.CTkButton(
            cab,
            text="Eliminar",
            width=120,
            fg_color="#8b2e2e",
            hover_color="#6f2323",
            state="disabled",
            command=self._accion_borrar_albaran,
        )
        self.btn_borrar_albaran.pack(side="right")

        # =========================
        # INFO
        # =========================
        self.info = ctk.CTkLabel(
            self,
            text="Selecciona un albarán.",
            text_color="#b0b0b0",
        )
        self.info.pack(anchor="w", padx=20, pady=(0, 10))

        # =========================
        # LISTA LINEAS
        # =========================
        self.lista_lineas = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
        )
        self.lista_lineas.pack(fill="both", expand=True, padx=20, pady=10)

        # =========================
        # ACCIONES
        # =========================
        acciones = ctk.CTkFrame(self, fg_color="transparent")
        acciones.pack(fill="x", padx=20, pady=(0, 10))

        self.btn_nueva_linea = ctk.CTkButton(
            acciones,
            text="➕ Añadir línea",
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            width=150,
            state="disabled",
            command=self._accion_nueva_linea,
        )
        self.btn_nueva_linea.pack(side="left", padx=(0, 10))

        self.btn_editar_linea = ctk.CTkButton(
            acciones,
            text="✏ Editar línea",
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            width=150,
            state="disabled",
            command=self._accion_editar_linea,
        )
        self.btn_editar_linea.pack(side="left", padx=(0, 10))

        self.btn_borrar_linea = ctk.CTkButton(
            acciones,
            text="Eliminar línea",
            fg_color="#8b2e2e",
            hover_color="#6f2323",
            width=150,
            state="disabled",
            command=self._accion_borrar_linea,
        )
        self.btn_borrar_linea.pack(side="left")

        self.btn_facturar = ctk.CTkButton(
            acciones,
            text="Convertir en factura",
            height=42,
            fg_color="#2fa572",
            hover_color="#238a5e",
            state="disabled",
            command=self._accion_facturar,
        )
        self.btn_facturar.pack(side="right")

    # =========================
    def cargar_albaran(self, albaran_id, datos):

        self.albaran_id = albaran_id
        self.albaran_email = None # Reset email
        self.cliente_id = None # Reset client ID

        # Assuming datos structure: [albaran_id, numero, fecha, cliente_nombre, total, cliente_id]
        # The original code had an optional 6th element for email, which is now replaced.
        aid = datos[0]
        numero = datos[1]
        fecha = datos[2]
        cliente_nombre = datos[3]
        total = datos[4]
        if len(datos) > 5: # Check if cliente_id is provided
            self.cliente_id = datos[5]
            self.albaran_email = obtener_email_cliente(self.cliente_id)


        try:
            fecha_es = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            fecha_es = fecha

        self.info.configure(text=f"{numero} · {cliente_nombre} · {fecha_es} · {total:.2f} €")

        self.btn_pdf.configure(state="normal")
        self.btn_email.configure(state="normal")
        self.btn_facturar.configure(state="disabled")
        self.btn_borrar_albaran.configure(state="normal")
        self.btn_nueva_linea.configure(state="normal")

    # =========================
    # RENDER LINEAS
    # =========================
    def render_lineas(self, lineas):

        for w in self.lista_lineas.winfo_children():
            w.destroy()

        self.linea_id = None
        self.card_linea_sel = None
        self.btn_borrar_linea.configure(state="disabled")
        self.btn_editar_linea.configure(state="disabled")

        if not lineas:

            ctk.CTkLabel(
                self.lista_lineas,
                text="No hay líneas en este albarán.",
                text_color="#b0b0b0",
            ).pack(anchor="w", padx=10, pady=10)

            self.btn_facturar.configure(state="disabled")
            self.btn_editar_linea.configure(state="disabled")

            return

        for linea in lineas:

            linea_id = linea[0]
            descripcion = linea[2]
            cantidad = linea[3]
            precio = linea[4]
            iva = linea[5]
            total = linea[6]

            card = ctk.CTkFrame(
                self.lista_lineas,
                corner_radius=10,
                fg_color="#2c2c2c",
                border_width=1,
                border_color="#3a3a3a",
            )
            card.pack(fill="x", pady=8, padx=8)

            ctk.CTkLabel(
                card,
                text=descripcion,
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w", padx=12, pady=(10, 2))

            ctk.CTkLabel(
                card,
                text=f"{cantidad} x {precio:.2f} € · IVA {iva}%",
                text_color="#b0b0b0",
            ).pack(anchor="w", padx=12)

            ctk.CTkLabel(
                card,
                text=f"Total: {total:.2f} €",
                text_color="#4ea8ff",
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="e", padx=12, pady=(0, 10))

            def _sel(_e=None, lid=linea_id, c=card):
                self._seleccionar_linea(lid, c)

            card.bind("<Button-1>", _sel)

            for w in card.winfo_children():
                w.bind("<Button-1>", _sel)

        self.btn_facturar.configure(state="normal")

    # =========================
    # SELECCION LINEA
    # =========================
    def _seleccionar_linea(self, linea_id, card):

        if self.card_linea_sel:
            self.card_linea_sel.configure(
                fg_color="#2c2c2c",
                border_color="#3a3a3a",
            )

        self.card_linea_sel = card
        card.configure(fg_color="#1f6aa5", border_color="#1f6aa5")

        self.linea_id = linea_id

        self.btn_borrar_linea.configure(state="normal")
        self.btn_editar_linea.configure(state="normal")

    # =========================
    # ACCIONES
    # =========================

    def _accion_nueva_linea(self):

        if self.albaran_id and self.on_nueva_linea:
            self.on_nueva_linea(self.albaran_id)

    def _accion_editar_linea(self):

        if self.linea_id and self.on_editar_linea:
            self.on_editar_linea(self.linea_id)

    def _accion_borrar_linea(self):

        if self.linea_id and self.on_borrar_linea:
            self.on_borrar_linea(self.linea_id)

    def _accion_borrar_albaran(self):

        if self.albaran_id and self.on_borrar_albaran:
            self.on_borrar_albaran(self.albaran_id)

    def _accion_facturar(self):

        if self.albaran_id and self.on_facturar:
            self.on_facturar(self.albaran_id)

    def _accion_pdf(self):

        if self.albaran_id and self.on_pdf:
            self.on_pdf(self.albaran_id)

    def _accion_email(self):
        if not self.albaran_id:
            return

        try:
            # Generate the PDF to send
            pdf_path = generar_pdf_albaran(self.albaran_id)
            if not pdf_path:
                raise Exception("No se pudo generar el documento PDF adjunto.")

            numero_albaran = self.info.cget("text").split("·")[0].strip()

            # Open Email Dialog
            EmailDialog(
                self.winfo_toplevel(),
                remitente_nombre="", # Se pille desde la config en el backend
                destinatario_email=self.albaran_email,
                asunto_default=f"Envío de Albarán {numero_albaran}",
                mensaje_default=f"Hola,\n\nAdjunto remitimos el albarán {numero_albaran}.\n\nUn saludo.",
                ruta_pdf=pdf_path
            )
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Error", str(e))

    # =========================
    # LIMPIAR
    # =========================
    def limpiar(self):

        self.albaran_id = None
        self.linea_id = None
        self.albaran_email = None

        self.btn_pdf.configure(state="disabled")
        self.btn_email.configure(state="disabled")
        self.btn_facturar.configure(state="disabled")
        self.btn_borrar_albaran.configure(state="disabled")
        self.btn_borrar_linea.configure(state="disabled")
        self.btn_nueva_linea.configure(state="disabled")
        self.btn_editar_linea.configure(state="disabled")

        self.info.configure(text="Selecciona un albarán.")

        for w in self.lista_lineas.winfo_children():
            w.destroy()
