import customtkinter as ctk
from tkinter import messagebox, filedialog, colorchooser
import threading
import shutil
import os

from app.services.empresa_service import obtener_empresa, guardar_empresa
from app.utils.validators import validar_no_vacio


class EmpresaView(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.logo_path = None
        self.color_factura = "#2563EB"

        # ==================================================
        # SCROLL PRINCIPAL
        # ==================================================
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # =========================
        # TITULO
        # =========================
        ctk.CTkLabel(
            scroll,
            text="Configuración de la empresa",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(anchor="w", padx=30, pady=(25, 5))

        ctk.CTkLabel(
            scroll,
            text="Estos datos aparecerán en facturas, albaranes y documentos PDF.",
            text_color="#9a9a9a",
        ).pack(anchor="w", padx=30, pady=(0, 20))

        # =========================
        # TARJETA PRINCIPAL
        # =========================
        card = ctk.CTkFrame(
            scroll,
            corner_radius=14,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        card.pack(fill="x", padx=30, pady=10)

        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=1)

        # ==================================================
        # DATOS FISCALES
        # ==================================================
        ctk.CTkLabel(
            card,
            text="Datos fiscales",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(15, 10))

        self._label(card, "Nombre de la empresa", 1, 0)
        self.nombre = ctk.CTkEntry(card)
        self.nombre.grid(row=2, column=0, padx=15, pady=(0, 10), sticky="ew")

        self._label(card, "CIF / NIF", 1, 1)
        self.cif = ctk.CTkEntry(card)
        self.cif.grid(row=2, column=1, padx=15, pady=(0, 10), sticky="ew")

        # ==================================================
        # DIRECCIÓN
        # ==================================================
        self._label(card, "Dirección fiscal", 3, 0, colspan=2)

        self.direccion = ctk.CTkEntry(card)
        self.direccion.grid(
            row=4,
            column=0,
            columnspan=2,
            padx=15,
            pady=(0, 10),
            sticky="ew",
        )

        self._label(card, "Código postal", 5, 0)
        self.codigo_postal = ctk.CTkEntry(card)
        self.codigo_postal.grid(row=6, column=0, padx=15, pady=(0, 10), sticky="ew")

        self._label(card, "Población", 5, 1)
        self.poblacion = ctk.CTkEntry(card)
        self.poblacion.grid(row=6, column=1, padx=15, pady=(0, 10), sticky="ew")

        self._label(card, "Provincia", 7, 0)
        self.provincia = ctk.CTkEntry(card)
        self.provincia.grid(row=8, column=0, padx=15, pady=(0, 10), sticky="ew")

        self._label(card, "País", 7, 1)
        self.pais = ctk.CTkEntry(card)
        self.pais.grid(row=8, column=1, padx=15, pady=(0, 10), sticky="ew")

        # ==================================================
        # CONTACTO
        # ==================================================
        ctk.CTkLabel(
            card,
            text="Datos de contacto",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=9, column=0, columnspan=2, sticky="w", padx=15, pady=(15, 10))

        self._label(card, "Email", 10, 0)
        self.email = ctk.CTkEntry(card)
        self.email.grid(row=11, column=0, padx=15, pady=(0, 10), sticky="ew")

        self._label(card, "Teléfono", 10, 1)
        self.telefono = ctk.CTkEntry(card)
        self.telefono.grid(row=11, column=1, padx=15, pady=(0, 10), sticky="ew")

        # ==================================================
        # COLOR FACTURA
        # ==================================================
        ctk.CTkLabel(
            card,
            text="Color corporativo de facturas",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=12, column=0, columnspan=2, sticky="w", padx=15, pady=(15, 10))

        self.color_preview = ctk.CTkFrame(
            card,
            width=60,
            height=25,
            corner_radius=6,
            fg_color=self.color_factura,
        )
        self.color_preview.grid(row=13, column=0, padx=15, pady=5, sticky="w")

        btn_color = ctk.CTkButton(
            card,
            text="Elegir color",
            width=140,
            command=self.elegir_color,
        )
        btn_color.grid(row=13, column=1, padx=15, pady=5, sticky="e")

        # ==================================================
        # DATOS BANCARIOS
        # ==================================================
        ctk.CTkLabel(
            card,
            text="Datos bancarios SEPA",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=14, column=0, columnspan=2, sticky="w", padx=15, pady=(15, 10))

        self._label(card, "IBAN empresa", 15, 0)
        self.iban = ctk.CTkEntry(card)
        self.iban.grid(row=16, column=0, padx=15, pady=(0, 10), sticky="ew")

        self._label(card, "BIC banco", 15, 1)
        self.bic = ctk.CTkEntry(card)
        self.bic.grid(row=16, column=1, padx=15, pady=(0, 10), sticky="ew")

        self._label(card, "Creditor ID SEPA", 17, 0, colspan=2)
        self.creditor = ctk.CTkEntry(card)
        self.creditor.grid(
            row=18,
            column=0,
            columnspan=2,
            padx=15,
            pady=(0, 10),
            sticky="ew",
        )

        # ==================================================
        # LOGO
        # ==================================================
        ctk.CTkLabel(
            card,
            text="Logo de la empresa",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=19, column=0, columnspan=2, sticky="w", padx=15, pady=(15, 10))

        self.logo_label = ctk.CTkLabel(
            card,
            text="Sin logo cargado",
            text_color="#9a9a9a",
        )
        self.logo_label.grid(row=20, column=0, padx=15, pady=5, sticky="w")

        btn_logo = ctk.CTkButton(
            card,
            text="Subir logo",
            width=140,
            command=self.subir_logo,
        )
        btn_logo.grid(row=20, column=1, padx=15, pady=5, sticky="e")

        # ==================================================
        # CONFIGURACIÓN SMTP
        # ==================================================
        ctk.CTkLabel(
            card,
            text="Servidor de Correo Saliente (SMTP)",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=21, column=0, columnspan=2, sticky="w", padx=15, pady=(15, 10))

        self._label(card, "Proovedor / Plantilla", 22, 0)
        self.preset_combo = ctk.CTkOptionMenu(
            card,
            values=["Manual (Personalizado)", "Gmail", "Outlook / Hotmail"],
            width=200,
            command=self._on_preset_change
        )
        self.preset_combo.grid(row=23, column=0, padx=15, pady=(0, 10), sticky="w")
        self.preset_combo.set("Manual (Personalizado)")

        self._label(card, "Servidor SMTP", 24, 0)
        self.smtp_server = ctk.CTkEntry(card)
        self.smtp_server.grid(row=25, column=0, padx=15, pady=(0, 10), sticky="ew")

        self._label(card, "Puerto SMTP", 24, 1)
        self.smtp_port = ctk.CTkEntry(card)
        self.smtp_port.grid(row=25, column=1, padx=15, pady=(0, 10), sticky="ew")

        self.smtp_port.bind("<FocusOut>", self._on_port_focus_out)

        self._label(card, "Usuario / Correo Remitente", 26, 0)
        self.smtp_user = ctk.CTkEntry(card)
        self.smtp_user.grid(row=27, column=0, padx=15, pady=(0, 10), sticky="ew")

        self._label(card, "Contraseña (de aplicación)", 26, 1)
        self.smtp_password = ctk.CTkEntry(card, show="*")
        self.smtp_password.grid(row=27, column=1, padx=15, pady=(0, 10), sticky="ew")

        self._label(card, "Tipo de Seguridad SMTP", 28, 0)
        self.smtp_security = ctk.CTkOptionMenu(
            card,
            values=["SSL", "TLS", "NINGUNA"],
            width=200
        )
        self.smtp_security.grid(row=29, column=0, padx=15, pady=(0, 10), sticky="w")
        self.smtp_security.set("TLS")

        self.btn_prueba_correo = ctk.CTkButton(
            card,
            text="Comprobar Conexión Correo SMTP",
            fg_color="#3b8ed0",
            hover_color="#2f6fa0",
            command=self.probar_correo_async
        )
        self.btn_prueba_correo.grid(row=29, column=1, padx=15, pady=(0, 10), sticky="e")

        # ==================================================
        # BOTÓN GUARDAR
        # ==================================================
        self.btn_guardar = ctk.CTkButton(
            scroll,
            text="💾 Guardar configuración",
            height=45,
            corner_radius=8,
            font=ctk.CTkFont(weight="bold"),
            command=self.guardar,
        )
        self.btn_guardar.pack(anchor="e", padx=30, pady=(20, 10))

        self.info = ctk.CTkLabel(
            scroll,
            text="",
            text_color="#4ea8ff",
            font=ctk.CTkFont(size=12),
        )
        self.info.pack(anchor="e", padx=30)

        self.cargar()

    # ==================================================
    # LABEL AUXILIAR
    # ==================================================
    def _label(self, parent, text, row, col, colspan=1):

        ctk.CTkLabel(
            parent,
            text=text,
            text_color="#b0b0b0",
            font=ctk.CTkFont(size=12),
        ).grid(
            row=row,
            column=col,
            columnspan=colspan,
            sticky="w",
            padx=15,
            pady=(10, 3),
        )

    # ==================================================
    # ELEGIR COLOR
    # ==================================================
    def elegir_color(self):

        color = colorchooser.askcolor()[1]

        if color:
            self.color_factura = color
            self.color_preview.configure(fg_color=color)

    # ==================================================
    # SUBIR LOGO
    # ==================================================
    def subir_logo(self):

        file = filedialog.askopenfilename(
            title="Seleccionar logo",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg")],
        )

        if not file:
            return

        from app.utils.config import DATA_DIR

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        destino = DATA_DIR / "logo_empresa.png"

        try:
            shutil.copy(file, destino)

            self.logo_path = str(destino)

            self.logo_label.configure(
                text="Logo cargado correctamente",
                text_color="#2ecc71",
            )

        except Exception as e:
            messagebox.showerror(
                "Error",
                f"No se pudo cargar el logo:\n{e}",
            )

    # ==================================================
    # CARGAR
    # ==================================================
    def cargar(self):

        empresa = obtener_empresa()

        if not empresa:
            return

        (
            nombre,
            cif,
            direccion,
            codigo_postal,
            poblacion,
            provincia,
            pais,
            email,
            telefono,
            logo,
            iban_empresa,
            creditor_id,
            bic,
            color_factura,
            smtp_server,
            smtp_port,
            smtp_user,
            smtp_password,
            smtp_security,
        ) = empresa

        self.nombre.insert(0, nombre or "")
        self.cif.insert(0, cif or "")
        self.direccion.insert(0, direccion or "")
        self.codigo_postal.insert(0, codigo_postal or "")
        self.poblacion.insert(0, poblacion or "")
        self.provincia.insert(0, provincia or "")
        self.pais.insert(0, pais or "")
        self.email.insert(0, email or "")
        self.telefono.insert(0, telefono or "")

        self.iban.insert(0, iban_empresa or "")
        self.creditor.insert(0, creditor_id or "")
        self.bic.insert(0, bic or "")

        self.smtp_server.insert(0, smtp_server or "")
        self.smtp_port.insert(0, str(smtp_port) if smtp_port else "")
        self.smtp_user.insert(0, smtp_user or "")
        self.smtp_password.insert(0, smtp_password or "")
        if smtp_security:
            self.smtp_security.set(smtp_security)

        if color_factura:
            self.color_factura = color_factura
            self.color_preview.configure(fg_color=color_factura)

        if logo and os.path.exists(logo):
            self.logo_path = logo

            self.logo_label.configure(
                text="Logo cargado",
                text_color="#2ecc71",
            )

    # ==================================================
    # GUARDAR
    # ==================================================
    def guardar(self):

        try:

            nombre = validar_no_vacio(
                self.nombre.get(),
                "Nombre de la empresa",
            )

            guardar_empresa(
                nombre,
                self.cif.get().strip() or None,
                self.direccion.get().strip() or None,
                self.codigo_postal.get().strip() or None,
                self.poblacion.get().strip() or None,
                self.provincia.get().strip() or None,
                self.pais.get().strip() or None,
                self.email.get().strip() or None,
                self.telefono.get().strip() or None,
                self.logo_path,
                self.iban.get().strip() or None,
                self.creditor.get().strip() or None,
                self.bic.get().strip() or None,
                self.color_factura,
                self.smtp_server.get().strip() or None,
                int(self.smtp_port.get().strip()) if self.smtp_port.get().strip().isdigit() else None,
                self.smtp_user.get().strip() or None,
                self.smtp_password.get() or None,  # No usamos strip aquí por si tiene espacios la clave
                self.smtp_security.get() or None,
            )

            self.info.configure(
                text="Configuración guardada correctamente ✔",
                text_color="#2ecc71",
            )

        except ValueError as e:

            messagebox.showerror(
                "Error de validación",
                str(e),
            )

    # ==================================================
    # PROBAR CONFIGURACIÓN CORREO SMTP EN HILO
    # ==================================================
    def probar_correo_async(self):
        # Tomar los valores configurados en ese momento UI
        smtp_s = self.smtp_server.get().strip()
        smtp_p = self.smtp_port.get().strip()
        smtp_u = self.smtp_user.get().strip()
        smtp_pw = self.smtp_password.get()
        smtp_sec = self.smtp_security.get()

        if not smtp_s or not smtp_p or not smtp_u or not smtp_pw:
            messagebox.showwarning("Incompleto", "Por favor completa Servidor, Puerto, Usuario y Contraseña para probar SMTP.")
            return

        self.btn_prueba_correo.configure(state="disabled", text="Probando...")

        # Lanzar verificador en back para no bloquear MainThread
        def _worker():
            from app.services.email_service import probar_conexion_smtp
            success, msg = probar_conexion_smtp(smtp_s, smtp_p, smtp_u, smtp_pw, smtp_sec)
            self.after(0, lambda: self._on_prueba_result(success, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_prueba_result(self, success, msg):
        if not self.winfo_exists():
            return

        self.btn_prueba_correo.configure(state="normal", text="Comprobar Conexión Correo SMTP")
        if success:
            messagebox.showinfo("Prueba Exitosa", "La conexión al servidor de correo es correcta.")
        else:
            messagebox.showerror("Error SMTP", f"Fallo al conectar:\n\n{msg}")

    # ==================================================
    # UX SMTP PRESETS & ALERTAS SUAVES
    # ==================================================
    def _on_preset_change(self, value):
        if value == "Gmail":
            self.smtp_server.delete(0, 'end')
            self.smtp_server.insert(0, "smtp.gmail.com")
            self.smtp_port.delete(0, 'end')
            self.smtp_port.insert(0, "587")
            self.smtp_security.set("TLS")
        elif value == "Outlook / Hotmail":
            self.smtp_server.delete(0, 'end')
            self.smtp_server.insert(0, "smtp.office365.com")
            self.smtp_port.delete(0, 'end')
            self.smtp_port.insert(0, "587")
            self.smtp_security.set("TLS")

    def _on_port_focus_out(self, event):
        puerto = self.smtp_port.get().strip()
        seg = self.smtp_security.get()

        if puerto == "465" and seg != "SSL":
            self.info.configure(
                text="Aviso: El puerto 465 suele usar seguridad SSL. Revisa si la configuración es correcta.",
                text_color="#c4a000"
            )
        elif puerto == "587" and seg != "TLS":
            self.info.configure(
                text="Aviso: El puerto 587 suele requerir seguridad TLS. Revisa si la configuración es correcta.",
                text_color="#c4a000"
            )
        else:
            self.info.configure(text="")
