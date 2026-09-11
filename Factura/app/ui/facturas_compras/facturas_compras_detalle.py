import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime

from app.services.facturas_compras_service import (
    obtener_factura_compra_por_id,
    obtener_lineas_factura_compra,
    marcar_factura_compra_pagada,
    borrar_linea_factura_compra,
    borrar_factura_compra,
)


class FacturasComprasDetalle(ctk.CTkFrame):

    def __init__(
        self,
        master,
        on_factura_actualizada=None,
    ):

        super().__init__(
            master,
            corner_radius=14,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )

        self.on_factura_actualizada = on_factura_actualizada

        self.factura_id = None
        self.factura_estado = None
        self.linea_seleccionada_id = None
        self.linea_card = None

        # =====================================================
        # TITULO
        # =====================================================
        self.lbl_titulo = ctk.CTkLabel(
            self,
            text="Detalle factura compra",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.lbl_titulo.pack(anchor="w", padx=20, pady=(20, 6))

        # =====================================================
        # CABECERA
        # =====================================================
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(5, 10))

        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=1)

        self.lbl_numero = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.lbl_numero.grid(row=0, column=0, sticky="w")

        self.lbl_total = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#4ea8ff",
        )
        self.lbl_total.grid(row=0, column=1, sticky="e")

        self.lbl_proveedor = ctk.CTkLabel(
            header,
            text="",
            text_color="#b0b0b0",
        )
        self.lbl_proveedor.grid(row=1, column=0, sticky="w")

        self.lbl_estado = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(weight="bold"),
        )
        self.lbl_estado.grid(row=1, column=1, sticky="e")

        self.lbl_fechas = ctk.CTkLabel(
            header,
            text="",
            text_color="#b0b0b0",
        )
        self.lbl_fechas.grid(row=2, column=0, columnspan=2, sticky="w")

        # =====================================================
        # LISTA LINEAS
        # =====================================================
        self.lista_lineas = ctk.CTkScrollableFrame(
            self,
            corner_radius=10,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
        )

        self.lista_lineas.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=(10, 10),
        )

        # =====================================================
        # ACCIONES
        # =====================================================
        acciones = ctk.CTkFrame(self, fg_color="transparent")
        acciones.pack(fill="x", padx=20, pady=(0, 12))

        self.btn_borrar_linea = ctk.CTkButton(
            acciones,
            text="Eliminar línea",
            fg_color="#8b2e2e",
            hover_color="#6f2323",
            state="disabled",
            command=self.eliminar_linea,
        )
        self.btn_borrar_linea.pack(side="left", padx=(0, 10))

        self.btn_pagar = ctk.CTkButton(
            acciones,
            text="💰 Marcar pagada",
            fg_color="#2fa572",
            hover_color="#238a5e",
            state="disabled",
            command=self.marcar_pagada,
        )
        self.btn_pagar.pack(side="left", padx=(0, 10))

        self.btn_borrar_factura = ctk.CTkButton(
            acciones,
            text="Eliminar factura",
            fg_color="#8b2e2e",
            hover_color="#6f2323",
            state="disabled",
            command=self.eliminar_factura,
        )
        self.btn_borrar_factura.pack(side="right")

        self.limpiar()

    # =====================================================
    # LIMPIAR
    # =====================================================
    def limpiar(self):

        self.factura_id = None
        self.factura_estado = None

        self.lbl_numero.configure(text="Selecciona una factura")
        self.lbl_total.configure(text="")
        self.lbl_proveedor.configure(text="")
        self.lbl_estado.configure(text="")
        self.lbl_fechas.configure(text="")

        self.linea_seleccionada_id = None
        self.linea_card = None

        self.btn_pagar.configure(state="disabled")
        self.btn_borrar_linea.configure(state="disabled")
        self.btn_borrar_factura.configure(state="disabled")

        for w in self.lista_lineas.winfo_children():
            w.destroy()

    # =====================================================
    # CARGAR FACTURA
    # =====================================================
    def cargar_factura(self, factura_id):

        self.factura_id = factura_id

        factura = obtener_factura_compra_por_id(factura_id)

        if not factura:
            return

        (
            fid,
            numero,
            fecha,
            fecha_venc,
            total,
            estado,
            forma_pago,
            proveedor_id,
            proveedor,
        ) = factura

        self.factura_estado = estado

        fecha_es = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")

        venc_es = (
            datetime.strptime(fecha_venc, "%Y-%m-%d").strftime("%d/%m/%Y")
            if fecha_venc
            else "-"
        )

        self.lbl_numero.configure(text=numero)
        self.lbl_total.configure(text=f"{float(total):.2f} €")
        self.lbl_proveedor.configure(text=f"Proveedor: {proveedor}")
        self.lbl_estado.configure(text=estado)
        self.lbl_fechas.configure(
            text=f"Fecha: {fecha_es} · Vence: {venc_es} · Pago: {forma_pago or '-'}"
        )

        self.btn_pagar.configure(
            state="normal" if estado == "PENDIENTE" else "disabled"
        )

        self.btn_borrar_factura.configure(state="normal")

        self.cargar_lineas()

    # =====================================================
    # CARGAR LINEAS
    # =====================================================
    def cargar_lineas(self):

        for w in self.lista_lineas.winfo_children():
            w.destroy()

        self.linea_seleccionada_id = None
        self.btn_borrar_linea.configure(state="disabled")

        lineas = obtener_lineas_factura_compra(self.factura_id)

        if not lineas:

            ctk.CTkLabel(
                self.lista_lineas,
                text="No hay líneas en esta factura.",
                text_color="#999",
            ).pack(anchor="w", padx=10, pady=10)

            return

        for linea in lineas:

            linea_id, desc, cantidad, precio, iva, total = linea

            fila = ctk.CTkFrame(
                self.lista_lineas,
                corner_radius=10,
                fg_color="#2c2c2c",
                border_width=1,
                border_color="#3a3a3a",
            )

            fila.pack(fill="x", padx=8, pady=6)

            ctk.CTkLabel(
                fila,
                text=str(desc),
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w", padx=12, pady=(10, 2))

            ctk.CTkLabel(
                fila,
                text=f"{cantidad} x {float(precio):.2f} € · IVA {iva}%",
                text_color="#b0b0b0",
            ).pack(anchor="w", padx=12)

            ctk.CTkLabel(
                fila,
                text=f"{float(total):.2f} €",
                font=ctk.CTkFont(weight="bold"),
                text_color="#4ea8ff",
            ).pack(anchor="e", padx=12, pady=(0, 10))

            def seleccionar(_e=None, lid=linea_id, fr=fila):
                self._seleccionar_linea(lid, fr)

            fila.bind("<Button-1>", seleccionar)

            for w in fila.winfo_children():
                w.bind("<Button-1>", seleccionar)

    # =====================================================
    # SELECCIONAR LINEA
    # =====================================================
    def _seleccionar_linea(self, linea_id, frame):

        if self.linea_card:
            self.linea_card.configure(
                fg_color="#2c2c2c",
                border_color="#3a3a3a",
            )

        self.linea_card = frame
        self.linea_seleccionada_id = linea_id

        frame.configure(
            fg_color="#1f6aa5",
            border_color="#1f6aa5",
        )

        if self.factura_estado == "PENDIENTE":
            self.btn_borrar_linea.configure(state="normal")

    # =====================================================
    # BORRAR LINEA
    # =====================================================
    def eliminar_linea(self):

        if not self.linea_seleccionada_id:
            return

        if not messagebox.askyesno(
            "Confirmar",
            "¿Eliminar esta línea?",
        ):
            return

        try:

            borrar_linea_factura_compra(
                self.linea_seleccionada_id,
                self.factura_id,
            )

            self.cargar_factura(self.factura_id)

            if self.on_factura_actualizada:
                self.on_factura_actualizada(self.factura_id)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # =====================================================
    # BORRAR FACTURA
    # =====================================================
    def eliminar_factura(self):

        if not messagebox.askyesno(
            "Confirmar",
            "¿Eliminar esta factura?",
        ):
            return

        try:

            borrar_factura_compra(self.factura_id)

            if self.on_factura_actualizada:
                self.on_factura_actualizada()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # =====================================================
    # MARCAR PAGADA
    # =====================================================
    def marcar_pagada(self):

        if not messagebox.askyesno(
            "Confirmar",
            "¿Marcar factura como pagada?",
        ):
            return

        try:

            marcar_factura_compra_pagada(self.factura_id)

            if self.on_factura_actualizada:
                self.on_factura_actualizada(self.factura_id)

        except Exception as e:
            messagebox.showerror("Error", str(e))
