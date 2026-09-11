import customtkinter as ctk
from tkinter import messagebox
import threading

from app.services.email_service import enviar_email_con_adjunto


class EmailDialog(ctk.CTkToplevel):
    def __init__(self, master, remitente_nombre, destinatario_email, asunto_default, mensaje_default, ruta_pdf, on_enviado=None, borrar_pdf_al_terminar=False):
        super().__init__(master)

        self.borrar_pdf_al_terminar = borrar_pdf_al_terminar

        self.title("Redactar correo electrónico")
        self.geometry("550x500")

        # Bloquear interacciones con el fondo
        self.grab_set()

        # Centrar ventana
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (550 // 2)
        y = (self.winfo_screenheight() // 2) - (500 // 2)
        self.geometry(f"+{x}+{y}")

        self.ruta_pdf = ruta_pdf
        self.on_enviado = on_enviado

        # =========================
        # CONTENIDO
        # =========================
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            container,
            text="✉ Enviar Documento por Correo",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", pady=(0, 15))

        # Destinatario
        ctk.CTkLabel(container, text="Destinatario (Email del cliente):", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.entry_destinatario = ctk.CTkEntry(container)
        self.entry_destinatario.pack(fill="x", pady=(2, 10))
        self.entry_destinatario.insert(0, destinatario_email or "")

        # Asunto
        ctk.CTkLabel(container, text="Asunto:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.entry_asunto = ctk.CTkEntry(container)
        self.entry_asunto.pack(fill="x", pady=(2, 10))
        self.entry_asunto.insert(0, asunto_default)

        # Mensaje
        ctk.CTkLabel(container, text="Mensaje:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.text_mensaje = ctk.CTkTextbox(container, height=120)
        self.text_mensaje.pack(fill="both", expand=True, pady=(2, 10))
        self.text_mensaje.insert("1.0", mensaje_default)

        # Info Adjunto
        import os
        filename = os.path.basename(ruta_pdf) if ruta_pdf else "Archivo no disponible"
        ctk.CTkLabel(
            container,
            text=f"📎 Adjunto: {filename}",
            text_color="#1f6aa5",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", pady=(0, 15))

        # =========================
        # BOTONES
        # =========================
        botones = ctk.CTkFrame(container, fg_color="transparent")
        botones.pack(fill="x", side="bottom")

        self.btn_cancelar = ctk.CTkButton(
            botones,
            text="Cancelar",
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=self.destroy
        )
        self.btn_cancelar.pack(side="left", expand=True, padx=5)

        self.btn_enviar = ctk.CTkButton(
            botones,
            text="Enviar Correo",
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=self.enviar
        )
        self.btn_enviar.pack(side="right", expand=True, padx=5)

    def enviar(self):
        destinatario = self.entry_destinatario.get().strip()
        asunto = self.entry_asunto.get().strip()
        mensaje = self.text_mensaje.get("1.0", "end-1c")

        if not destinatario:
            messagebox.showerror("Campos incompletos", "Por favor, especifica un destinatario.", parent=self)
            return

        if not asunto:
            messagebox.showerror("Campos incompletos", "Por favor, especifica un asunto.", parent=self)
            return

        # Bloquear interfaz mientras se envía
        self.btn_enviar.configure(state="disabled", text="Enviando...")
        self.btn_cancelar.configure(state="disabled")

        def _worker():
            try:
                success, msg = enviar_email_con_adjunto(destinatario, asunto, mensaje, self.ruta_pdf)
                self.after(0, lambda: self._on_result(success, msg))
            finally:
                if self.borrar_pdf_al_terminar:
                    import os
                    try:
                        if self.ruta_pdf and os.path.exists(self.ruta_pdf):
                            os.remove(self.ruta_pdf)
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_result(self, success, error_msg):
        if self.winfo_exists():
            if success:
                messagebox.showinfo("Éxito", "El correo se ha enviado correctamente.", parent=self)
                if self.on_enviado:
                    self.on_enviado()
                self.destroy()
            else:
                self.btn_enviar.configure(state="normal", text="Enviar Correo")
                self.btn_cancelar.configure(state="normal")
                messagebox.showerror("Error de Envío", f"No se pudo completar el envío.\n\nDetalle: {error_msg}\n\nRevisa la configuración SMTP intercediendo en Empresa.", parent=self)
