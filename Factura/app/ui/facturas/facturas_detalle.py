import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import threading
import os
from app.ui.cliente_popup import ClientePopup
from tkcalendar import Calendar
from app.ui.email_dialog import EmailDialog

from app.services.facturas_service import (
    obtener_factura_por_id,
    obtener_lineas_factura,
    marcar_factura_pagada,
    actualizar_pago_factura,
)

from app.services.clientes_service import obtener_email_cliente

from app.services.pdf_service import generar_pdf_factura


# =========================================================
# STATUS BADGE (UI más profesional)
# =========================================================
class StatusBadge(ctk.CTkLabel):

    MAP = {
        "PENDIENTE": ("#10324b", "#66b9ff"),
        "VENCIDA": ("#4b1515", "#ff7474"),
        "PAGADA": ("#133826", "#6dff9f"),
        "RECTIFICATIVA": ("#4b3310", "#ffbf59"),
    }

    def __init__(self, master, text):

        key = str(text).upper()
        bg, fg = self.MAP.get(key, ("#313131", "#d6d6d6"))

        super().__init__(
            master,
            text=text,
            fg_color=bg,
            text_color=fg,
            corner_radius=100,
            padx=10,
            pady=3,
            font=ctk.CTkFont(size=11, weight="bold"),
        )


class FacturasDetalle(ctk.CTkFrame):

    def __init__(
        self,
        master,
        on_rectificar=None,
        on_abrir_cliente=None,
        on_ver_facturas_cliente=None,
        on_factura_actualizada=None,
        on_ir_factura=None,
    ):

        super().__init__(
            master,
            corner_radius=14,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )

        self.on_rectificar = on_rectificar
        self.on_abrir_cliente = on_abrir_cliente
        self.on_ver_facturas_cliente = on_ver_facturas_cliente
        self.on_factura_actualizada = on_factura_actualizada
        self.on_ir_factura = on_ir_factura

        self.factura_id = None
        self.cliente_id = None
        self._detalle_token = 0

        # =====================================================
        # TITULO
        # =====================================================
        self.lbl_titulo = ctk.CTkLabel(
            self,
            text="Detalle de factura",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.lbl_titulo.pack(anchor="w", padx=20, pady=(20, 6))

        # =====================================================
        # CABECERA
        # =====================================================
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=20, pady=(5, 6))

        self.header.grid_columnconfigure(0, weight=1)
        self.header.grid_columnconfigure(1, weight=1)

        self.lbl_numero = ctk.CTkLabel(
            self.header,
            text="",
            font=ctk.CTkFont(size=19, weight="bold"),
        )
        self.lbl_numero.grid(row=0, column=0, sticky="w")

        self.lbl_total = ctk.CTkLabel(
            self.header,
            text="",
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color="#4ea8ff",
        )
        self.lbl_total.grid(row=0, column=1, sticky="e")

        self.lbl_cliente = ctk.CTkLabel(
            self.header,
            text="",
            text_color="#b0b0b0",
        )
        self.lbl_cliente.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.estado_slot = ctk.CTkFrame(self.header, fg_color="transparent")
        self.estado_slot.grid(row=1, column=1, sticky="e", pady=(2, 0))

        self.lbl_fechas = ctk.CTkLabel(
            self.header,
            text="",
            text_color="#b0b0b0",
        )
        self.lbl_fechas.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # =====================================================
        # BOTONES CLIENTE
        # =====================================================
        botones_cliente = ctk.CTkFrame(self, fg_color="transparent")
        botones_cliente.pack(anchor="w", padx=20, pady=(8, 10))

        self.btn_cliente = ctk.CTkButton(
            botones_cliente,
            text="👤 Abrir ficha cliente",
            height=30,
            fg_color="#3a7a3a",
            hover_color="#2e632e",
            command=self.abrir_cliente,
            state="disabled",
        )
        self.btn_cliente.pack(side="left", padx=(0, 10))

        self.btn_facturas_cliente = ctk.CTkButton(
            botones_cliente,
            text="📄 Ver facturas del cliente",
            height=30,
            fg_color="#3b8ed0",
            hover_color="#2f6fa0",
            command=self.ver_facturas_cliente,
            state="disabled",
        )
        self.btn_facturas_cliente.pack(side="left")

        # =====================================================
        # SCROLL AREA
        # =====================================================
        self.scroll_container = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
        )
        self.scroll_container.pack(fill="both", expand=True, padx=20, pady=(12, 8))

        self.canvas = tk.Canvas(
            self.scroll_container,
            bg="#252525",
            highlightthickness=0,
            bd=0,
            relief="flat",
        )

        self.scrollbar = ctk.CTkScrollbar(
            self.scroll_container,
            orientation="vertical",
            command=self.canvas.yview,
        )

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.lista_lineas = ctk.CTkFrame(self.canvas, fg_color="transparent")

        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.lista_lineas,
            anchor="nw",
        )

        self.lista_lineas.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # =====================================================
        # ACCIONES
        # =====================================================
        acciones = ctk.CTkFrame(self, fg_color="transparent")
        acciones.pack(side="bottom", fill="x", padx=20, pady=(0, 12))

        self.combo_pago = ctk.CTkComboBox(
            acciones,
            values=["CONTADO", "TARJETA", "TRANSFERENCIA", "BIZUM", "DOMICILIACION"],
            width=180,
        )
        self.combo_pago.set("CONTADO")
        self.combo_pago.pack(side="left", padx=(0, 10))

        self.btn_guardar_pago = ctk.CTkButton(
            acciones,
            text="💾 Guardar forma de pago",
            state="disabled",
            command=self.guardar_forma_pago,
        )
        self.btn_guardar_pago.pack(side="left", padx=(0, 10))

        self.btn_pagar = ctk.CTkButton(
            acciones,
            text="💰 Marcar como pagada",
            fg_color="#2fa572",
            hover_color="#238a5e",
            state="disabled",
            command=self.marcar_pagada,
        )
        self.btn_pagar.pack(side="left", padx=(0, 10))

        self.btn_rectificar = ctk.CTkButton(
            acciones,
            text="↩ Rectificar factura",
            fg_color="#c47a00",
            hover_color="#a96500",
            state="disabled",
            command=self.rectificar,
        )
        self.btn_rectificar.pack(side="left", padx=(0, 10))

        self.btn_pdf = ctk.CTkButton(
            acciones,
            text="📄 PDF",
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            state="disabled",
            command=self.generar_pdf,
        )
        self.btn_pdf.pack(side="right")

        self.btn_email = ctk.CTkButton(
            acciones,
            text="✉ Email",
            fg_color="#3b8ed0",
            hover_color="#2f6fa0",
            state="disabled",
            command=self.accion_email,
        )
        self.btn_email.pack(side="right", padx=(0, 10))

        self.limpiar()

    # =====================================================
    # SCROLL HELPERS
    # =====================================================

    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    # =====================================================
    # LIMPIAR
    # =====================================================

    def limpiar(self):

        self.factura_id = None
        self.cliente_id = None

        self.lbl_numero.configure(text="Selecciona una factura")
        self.lbl_total.configure(text="")
        self.lbl_cliente.configure(text="")
        self.lbl_fechas.configure(text="")

        for w in self.estado_slot.winfo_children():
            w.destroy()

        for w in self.lista_lineas.winfo_children():
            w.destroy()

        self.btn_pdf.configure(state="disabled")
        self.btn_email.configure(state="disabled")
        self.btn_pagar.configure(state="disabled")
        self.btn_rectificar.configure(state="disabled")
        self.btn_guardar_pago.configure(state="disabled")
        self.btn_cliente.configure(state="disabled")
        self.btn_facturas_cliente.configure(state="disabled")

    # =====================================================
    # CARGAR FACTURA
    # =====================================================

    def cargar_factura(self, factura_id, factura_lista):

        # =========================
        # TOKEN PARA EVITAR RACE CONDITIONS
        # =========================
        self._detalle_token += 1
        token = self._detalle_token

        self.factura_id = factura_id

        # =========================
        # BOTONES
        # =========================
        self.btn_pdf.configure(state="normal")
        self.btn_email.configure(state="disabled") # Se habilita en _render_detalle
        self.btn_guardar_pago.configure(state="normal")

        estado = factura_lista[6]
        rectif = factura_lista[7]

        # =========================
        # PAGAR
        # =========================
        if not rectif and estado in ("PENDIENTE", "VENCIDA"):
            self.btn_pagar.configure(state="normal")
        else:
            self.btn_pagar.configure(state="disabled")

        # =========================
        # RECTIFICAR
        # =========================
        self.btn_rectificar.configure(state="disabled" if rectif else "normal")

        # =========================
        # GUARDAR SI ES RECTIFICATIVA
        # =========================
        # factura_lista[7] normalmente es factura_rectificada_id
        # RESET SIEMPRE PRIMERO
        self.factura_rectificada_id = None

        # SOLO asignar si tiene valor real
        if rectif:
            self.factura_rectificada_id = rectif

        # =========================
        # CARGA DETALLE EN THREAD
        # =========================
        threading.Thread(
            target=self._worker_detalle,
            args=(token, factura_id),
            daemon=True,
        ).start()

    # =====================================================
    # WORKER
    # =====================================================

    def _worker_detalle(self, token, factura_id):

        try:
            factura = obtener_factura_por_id(factura_id)
            lineas = obtener_lineas_factura(factura_id) or []
        except Exception:
            factura = None
            lineas = []

        self.after(
            0,
            lambda: self._render_detalle(token, factura_id, factura, lineas),
        )

    # =====================================================
    # RENDER
    # =====================================================

    def _render_detalle(self, token, factura_id, factura, lineas):

        # limpiar botones/labels de rectificativa anteriores
        for attr in ["btn_ver_original", "lbl_rectificativa_info"]:
            if hasattr(self, attr):
                getattr(self, attr).destroy()
                delattr(self, attr)

        if token != self._detalle_token or self.factura_id != factura_id:
            return

        # limpiar líneas
        for w in self.lista_lineas.winfo_children():
            w.destroy()

        # limpiar info extra (por si cambias de factura)
        if hasattr(self, "lbl_rectificativa_info"):
            self.lbl_rectificativa_info.destroy()
            del self.lbl_rectificativa_info

        if factura:

            numero = factura[0]
            fecha = factura[1]
            fecha_venc = factura[2]
            estado = factura[3]
            self.cliente_id = factura[4]
            cliente = factura[5]
            total = factura[6] if len(factura) > 6 else 0
            fecha_pago = factura[7] if len(factura) > 7 else None

            # Consultamos atómicamente el email para no ensuciar el CORE SQL
            self.factura_email = obtener_email_cliente(self.cliente_id)

            # IMPORTANTE: viene de la lista (ya lo tienes en obtener_facturas)
            factura_rectificada_id = self.factura_rectificada_id

            # =========================================
            # CABECERA
            # =========================================

            self.lbl_numero.configure(text=numero)
            self.lbl_total.configure(text=f"{total:.2f} €")

            self.lbl_cliente.configure(
                text=f"Cliente: {cliente}  (ID: {self.cliente_id})"
            )

            # =========================================
            # FORMATEAR FECHAS (ESPAÑOL)
            # =========================================

            try:
                fecha_es = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
            except:
                fecha_es = fecha

            if fecha_venc:
                try:
                    venc_es = datetime.strptime(fecha_venc, "%Y-%m-%d").strftime(
                        "%d/%m/%Y"
                    )
                except:
                    venc_es = fecha_venc
            else:
                venc_es = "-"

            # =========================================
            # ESTADO BADGE
            # =========================================

            for w in self.estado_slot.winfo_children():
                w.destroy()

            StatusBadge(self.estado_slot, estado).pack(anchor="e")

            # =========================================
            # TEXTO FECHAS
            # =========================================

            texto_fechas = f"Fecha: {fecha_es}     Vencimiento: {venc_es}"

            if fecha_pago:
                try:
                    pago_es = datetime.strptime(fecha_pago, "%Y-%m-%d").strftime(
                        "%d/%m/%Y"
                    )
                except:
                    pago_es = fecha_pago

                texto_fechas += f"     Pagada: {pago_es}"

            self.lbl_fechas.configure(text=texto_fechas)

            # =========================================
            # INFO RECTIFICATIVA
            # =========================================

            if factura_rectificada_id:

                if self.on_ir_factura:
                    self.btn_ver_original = ctk.CTkButton(
                        self.header,
                        text="🔎 Ver factura original",
                        height=28,
                        fg_color="#3b8ed0",
                        hover_color="#2f6fa0",
                        command=lambda: self.on_ir_factura(factura_rectificada_id),
                    )
                    self.btn_ver_original.grid(row=4, column=0, sticky="w", pady=(4, 0))

                self.lbl_rectificativa_info = ctk.CTkLabel(
                    self.header,
                    text=f"↩ Rectifica factura ID: {factura_rectificada_id}",
                    text_color="#ffbf59",
                    font=ctk.CTkFont(size=12, weight="bold"),
                )
                self.lbl_rectificativa_info.grid(
                    row=3, column=0, columnspan=2, sticky="w", pady=(4, 0)
                )

            self.btn_cliente.configure(state="normal")
            self.btn_facturas_cliente.configure(state="normal")

            # Habilitar el envío de correo si cargó correctamente
            self.btn_email.configure(state="normal")

        # =========================================
        # LÍNEAS
        # =========================================

        if not lineas:

            ctk.CTkLabel(
                self.lista_lineas,
                text="No hay líneas en esta factura.",
                text_color="#b0b0b0",
            ).pack(anchor="w", padx=10, pady=10)

        else:

            for l in lineas:

                if isinstance(l, dict):
                    desc = l.get("descripcion")
                    cant = float(l.get("cantidad", 0))
                    precio = float(l.get("precio", 0))
                    iva = float(l.get("iva", 0))
                    total_l = float(l.get("total", 0))
                else:
                    vals = list(l)
                    desc, cant, precio, iva, total_l = vals[-5:]

                linea = ctk.CTkFrame(
                    self.lista_lineas,
                    corner_radius=10,
                    fg_color="#303030",
                    border_width=1,
                    border_color="#3a3a3a",
                )
                linea.pack(fill="x", pady=6, padx=8)

                ctk.CTkLabel(
                    linea,
                    text=str(desc),
                    font=ctk.CTkFont(weight="bold"),
                ).pack(anchor="w", padx=12, pady=(10, 2))

                ctk.CTkLabel(
                    linea,
                    text=f"{cant:g} x {precio:.2f} € · IVA {iva:g}%",
                    text_color="#b0b0b0",
                ).pack(anchor="w", padx=12)

                ctk.CTkLabel(
                    linea,
                    text=f"{total_l:.2f} €",
                    text_color="#4ea8ff",
                    font=ctk.CTkFont(weight="bold"),
                ).pack(anchor="e", padx=12, pady=(0, 10))

    # =====================================================
    # ACCIONES
    # =====================================================

    def guardar_forma_pago(self):

        if not self.factura_id:
            return

        try:
            actualizar_pago_factura(
                self.factura_id,
                forma_pago=self.combo_pago.get(),
            )

            if self.on_factura_actualizada:
                self.on_factura_actualizada(self.factura_id)
            self._worker_detalle(self._detalle_token, self.factura_id)

            messagebox.showinfo("Correcto", "Forma de pago actualizada.")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def marcar_pagada(self):

        if not self.factura_id:
            return

        # ============================
        # DIALOGO FECHA DE PAGO
        # ============================

        top = tk.Toplevel(self)
        top.title("Fecha de pago")
        top.geometry("300x350")
        top.grab_set()

        cal = Calendar(
            top,
            selectmode="day",
            date_pattern="dd/mm/yyyy",
        )
        cal.pack(padx=10, pady=10, fill="both", expand=True)

        def confirmar():

            fecha_ui = cal.get_date()

            try:
                fecha_iso = datetime.strptime(fecha_ui, "%d/%m/%Y").strftime("%Y-%m-%d")

                marcar_factura_pagada(
                    self.factura_id,
                    self.combo_pago.get(),
                    fecha_iso,
                )

                top.destroy()

                if self.on_factura_actualizada:
                    self.on_factura_actualizada(self.factura_id)

                self._worker_detalle(self._detalle_token, self.factura_id)

                messagebox.showinfo("Correcto", "Factura marcada como pagada.")

            except Exception as e:
                messagebox.showerror("Error", str(e))

        ctk.CTkButton(
            top,
            text="Confirmar pago",
            command=confirmar,
        ).pack(pady=10)

    def rectificar(self):

        if not self.factura_id:
            return

        if self.on_rectificar:
            self.on_rectificar(self.factura_id)

    def accion_email(self):
        if not self.factura_id:
            return

        try:
            pdf_path = generar_pdf_factura(self.factura_id)
            if not pdf_path:
                raise Exception("No se pudo generar el documento PDF adjunto.")

            numero_factura = self.lbl_numero.cget("text")

            EmailDialog(
                self.winfo_toplevel(),
                remitente_nombre="",
                destinatario_email=self.factura_email,
                asunto_default=f"Envío de Factura {numero_factura}",
                mensaje_default=f"Hola,\n\nAdjunto remitimos la factura {numero_factura}.\n\nUn saludo.",
                ruta_pdf=pdf_path
            )
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def generar_pdf(self):

        if not self.factura_id:
            return

        try:
            archivo = generar_pdf_factura(self.factura_id)

            if archivo and os.path.exists(archivo):
                os.startfile(archivo)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # =====================================================
    # NAVEGACION CLIENTE
    # =====================================================

    def abrir_cliente(self):

        if not self.cliente_id:
            return

        ClientePopup(self, self.cliente_id)

    def ver_facturas_cliente(self):
        if self.cliente_id and self.on_ver_facturas_cliente:
            self.on_ver_facturas_cliente(self.cliente_id)
