import customtkinter as ctk
from datetime import datetime, date
from tkinter import messagebox
import os

from app.services.domiciliaciones_service import (
    obtener_domiciliaciones,
    marcar_cobro_domiciliacion,
    marcar_devolucion_domiciliacion,
)

from app.services.sepa_service import generar_remesa_sepa


class DomiciliacionesView(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.domiciliaciones = []
        self.seleccionadas = {}

        # =========================
        # TITULO
        # =========================
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text="Domiciliaciones",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Exportar remesa SEPA",
            width=200,
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=self.exportar_sepa,
        ).pack(side="right")

        # =========================
        # FILTROS
        # =========================
        filtros = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        filtros.pack(fill="x", padx=25, pady=(0, 15))

        self.f_cliente = ctk.CTkEntry(filtros, placeholder_text="Cliente")

        self.f_estado = ctk.CTkComboBox(
            filtros,
            values=["TODAS", "PENDIENTE", "COBRADO", "DEVUELTO"],
            width=160,
        )
        self.f_estado.set("TODAS")

        self.chk_vencidas = ctk.CTkCheckBox(filtros, text="Solo vencidas")

        self.f_cliente.grid(row=0, column=0, padx=8, pady=12)
        self.f_estado.grid(row=0, column=1, padx=8, pady=12)
        self.chk_vencidas.grid(row=0, column=2, padx=20)

        ctk.CTkButton(
            filtros,
            text="Buscar",
            command=self.buscar,
        ).grid(row=0, column=3, padx=15)

        filtros.grid_columnconfigure(4, weight=1)

        # =========================
        # LISTA
        # =========================
        self.lista = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        self.lista.pack(fill="both", expand=True, padx=25, pady=(0, 20))

        self.cargar()

    # =========================
    # COLOR ESTADO
    # =========================
    def _color_estado(self, estado):
        return {
            "PENDIENTE": "#4ea8ff",
            "COBRADO": "#4eff7a",
            "DEVUELTO": "#ff4e4e",
        }.get(estado, "#b0b0b0")

    # =========================
    # CARGAR
    # =========================
    def cargar(self, datos=None):

        for w in self.lista.winfo_children():
            w.destroy()

        self.seleccionadas = {}

        self.domiciliaciones = datos if datos is not None else obtener_domiciliaciones()

        for d in self.domiciliaciones:
            self._card_domiciliacion(d)

    # =========================
    # CARD
    # =========================
    def _card_domiciliacion(self, dom):

        (
            fid,
            numero,
            fecha,
            fecha_venc,
            cliente,
            total,
            estado,
            iban,
            tipo_venc,
        ) = dom

        card = ctk.CTkFrame(
            self.lista,
            corner_radius=10,
            fg_color="#343434",
            border_width=1,
            border_color="#3a3a3a",
        )
        card.pack(fill="x", pady=8, padx=12)

        # =========================
        # CHECKBOX SELECCIÓN
        # =========================

        var = ctk.BooleanVar()

        check = ctk.CTkCheckBox(
            card,
            text="",
            variable=var,
            width=20,
        )
        check.pack(side="left", padx=10)

        self.seleccionadas[fid] = (var, dom)

        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
        fecha_es = fecha_dt.strftime("%d/%m/%Y")

        if fecha_venc:
            fecha_venc_dt = datetime.strptime(fecha_venc, "%Y-%m-%d").date()
            venc_es = fecha_venc_dt.strftime("%d/%m/%Y")
        else:
            fecha_venc_dt = None
            venc_es = "-"

        # ================= LEFT INFO =================
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=15, pady=10)

        ctk.CTkLabel(
            info_frame,
            text=numero,
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            info_frame,
            text=cliente,
            text_color="#cccccc",
        ).pack(anchor="w", pady=(2, 6))

        ctk.CTkLabel(
            info_frame,
            text=f"Fecha: {fecha_es} · Vence: {venc_es} ({tipo_venc})",
            text_color="#aaaaaa",
        ).pack(anchor="w")

        ctk.CTkLabel(
            info_frame,
            text=f"IBAN: {iban}",
            text_color="#8a8a8a",
        ).pack(anchor="w", pady=(4, 0))

        # ================= RIGHT INFO =================
        right_frame = ctk.CTkFrame(card, fg_color="transparent")
        right_frame.pack(side="right", padx=15, pady=10)

        ctk.CTkLabel(
            right_frame,
            text=f"{total:.2f} €",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="e")

        badge = ctk.CTkLabel(
            right_frame,
            text=estado,
            fg_color="#2a2a2a",
            corner_radius=100,
            padx=10,
            pady=3,
            text_color=self._color_estado(estado),
            font=ctk.CTkFont(weight="bold"),
        )
        badge.pack(anchor="e", pady=(4, 6))

        if estado == "PENDIENTE" and fecha_venc_dt and fecha_venc_dt < date.today():

            ctk.CTkLabel(
                right_frame,
                text="⚠ VENCIDA",
                text_color="#ff4e4e",
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="e", pady=(0, 6))

        # ================= BOTONES =================
        if estado == "PENDIENTE":

            ctk.CTkButton(
                right_frame,
                text="✔ Cobrado",
                width=120,
                command=lambda i=fid: self.cobrar(i),
            ).pack(pady=3)

            ctk.CTkButton(
                right_frame,
                text="↩ Devuelto",
                width=120,
                fg_color="#b33a3a",
                hover_color="#8f2e2e",
                command=lambda i=fid: self.devolver(i),
            ).pack(pady=3)

    # =========================
    # ACCIONES
    # =========================
    def cobrar(self, factura_id):

        dlg = ctk.CTkInputDialog(
            title="Confirmar cobro",
            text="Escribe COBRAR para confirmar el cobro:",
        )

        respuesta = dlg.get_input()

        if respuesta != "COBRAR":
            return

        marcar_cobro_domiciliacion(factura_id)
        self.buscar()

    def devolver(self, factura_id):

        dlg = ctk.CTkInputDialog(
            title="Confirmar devolución",
            text="Escribe DEVOLVER para confirmar la devolución:",
        )

        respuesta = dlg.get_input()

        if respuesta != "DEVOLVER":
            return

        marcar_devolucion_domiciliacion(factura_id)
        self.buscar()

    # =========================
    # FILTROS
    # =========================
    def buscar(self):

        estado = self.f_estado.get()

        if estado == "TODAS":
            estado = None

        cliente = self.f_cliente.get().strip() or None

        self.cargar(
            obtener_domiciliaciones(
                cliente=cliente,
                estado_cobro=estado,
                vencidas=self.chk_vencidas.get(),
            )
        )

    # =========================
    # EXPORTAR REMESA SEPA
    # =========================
    def exportar_sepa(self):

        facturas = []

        for fid, (var, dom) in self.seleccionadas.items():

            if var.get():

                (
                    fid,
                    numero,
                    fecha,
                    fecha_venc,
                    cliente,
                    total,
                    estado,
                    iban,
                    tipo_venc,
                ) = dom

                if estado != "PENDIENTE":
                    continue

                facturas.append(
                    (
                        fid,
                        numero,
                        total,
                        fecha_venc,
                        cliente,
                        iban,
                        numero,
                        fecha,
                    )
                )

        if not facturas:

            messagebox.showwarning(
                "Nada seleccionado",
                "Selecciona al menos una domiciliación.",
            )

            return

        try:

            archivo = generar_remesa_sepa(facturas)

            messagebox.showinfo(
                "Remesa generada",
                f"Archivo SEPA generado correctamente:\n\n{archivo}",
            )

            try:
                os.startfile(archivo)
            except Exception:
                pass

            self.buscar()

        except Exception as e:

            messagebox.showerror(
                "Error generando remesa",
                str(e),
            )
