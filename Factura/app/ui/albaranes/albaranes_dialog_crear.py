import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import tkinter.ttk as ttk
from tkcalendar import Calendar

from app.utils.validators import (
    validar_no_vacio,
    validar_float,
    validar_iva,
    validar_fecha,
)

from app.services.albaranes_service import crear_albaran, añadir_linea


class AlbaranCrearDialog(ctk.CTkToplevel):

    def __init__(self, master, on_created=None):
        super().__init__(master)

        self.on_created = on_created

        self.title("Nuevo albarán")
        self.minsize(980, 650)
        self.resizable(True, True)
        self.grab_set()
        self.focus_force()
        self.lift()

        self.cliente_seleccionado = None
        self.producto_seleccionado = None
        self.lineas = []

        self._build_ui()
        self._toggle_modo_linea()
        self._render_lineas()

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self):

        container = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color="#2b2b2b",
            border_width=1,
            border_color="#3a3a3a",
        )
        container.pack(fill="both", expand=True, padx=18, pady=18)

        # HEADER
        header = ctk.CTkFrame(
            container,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
            corner_radius=10,
        )
        header.pack(fill="x", padx=14, pady=(14, 10))

        top = ctk.CTkFrame(header, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            top,
            text="Nuevo albarán",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left")

        self.lbl_total_header = ctk.CTkLabel(
            top,
            text="0.00 €",
            text_color="#4ea8ff",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        self.lbl_total_header.pack(side="right")

        ctk.CTkLabel(
            header,
            text="Selecciona cliente, fecha, añade líneas y confirma la creación del albarán.",
            text_color="#b0b0b0",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        cuerpo = ctk.CTkFrame(container, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        cuerpo.grid_columnconfigure(0, weight=0, minsize=360)
        cuerpo.grid_columnconfigure(1, weight=1)

        # ======================================================
        # COLUMNA IZQUIERDA
        # ======================================================

        izquierda = ctk.CTkFrame(
            cuerpo,
            corner_radius=12,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
        )
        izquierda.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        # CLIENTE
        box_cliente = ctk.CTkFrame(
            izquierda,
            corner_radius=10,
            fg_color="#2d2d2d",
            border_width=1,
            border_color="#3a3a3a",
        )
        box_cliente.pack(fill="x", padx=14, pady=(14, 10))

        ctk.CTkLabel(
            box_cliente,
            text="Cliente",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))

        self.lbl_cliente = ctk.CTkLabel(
            box_cliente,
            text="Ningún cliente seleccionado",
            text_color="#b0b0b0",
            justify="left",
            wraplength=300,
        )
        self.lbl_cliente.pack(anchor="w", padx=12, pady=(0, 8))

        ctk.CTkButton(
            box_cliente,
            text="Seleccionar cliente",
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=self._abrir_selector_clientes,
        ).pack(fill="x", padx=12, pady=(0, 12))

        # ======================================================
        # FECHA DEL ALBARAN (CON CALENDARIO PROFESIONAL)
        # ======================================================

        box_fecha = ctk.CTkFrame(
            izquierda,
            corner_radius=10,
            fg_color="#2d2d2d",
            border_width=1,
            border_color="#3a3a3a",
        )
        box_fecha.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(
            box_fecha,
            text="Fecha del albarán",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 6))

        fila_fecha = ctk.CTkFrame(box_fecha, fg_color="transparent")
        fila_fecha.pack(fill="x", padx=12, pady=(0, 12))

        self.entry_fecha = ctk.CTkEntry(
            fila_fecha,
            placeholder_text="dd/mm/yyyy",
        )
        self.entry_fecha.pack(side="left", fill="x", expand=True)

        self.entry_fecha.insert(0, datetime.now().strftime("%d/%m/%Y"))

        ctk.CTkButton(
            fila_fecha,
            text="📅",
            width=40,
            command=self._abrir_calendario,
        ).pack(side="left", padx=(6, 0))

        # ======================================================
        # MODO LINEA
        # ======================================================

        box_linea = ctk.CTkFrame(
            izquierda,
            corner_radius=10,
            fg_color="#2d2d2d",
            border_width=1,
            border_color="#3a3a3a",
        )
        box_linea.pack(fill="x", padx=14, pady=(0, 10))

        fila_modo = ctk.CTkFrame(box_linea, fg_color="transparent")
        fila_modo.pack(fill="x", padx=12, pady=(12, 8))

        ctk.CTkLabel(
            fila_modo,
            text="Línea manual",
            text_color="#d4d4d4",
            font=ctk.CTkFont(weight="bold"),
        ).pack(side="left")

        self.modo_manual = ctk.BooleanVar(value=False)
        self.switch_manual = ctk.CTkSwitch(
            fila_modo,
            text="",
            variable=self.modo_manual,
            command=self._toggle_modo_linea,
        )
        self.switch_manual.pack(side="right")

        # PRODUCTO
        self.bloque_producto = ctk.CTkFrame(
            box_linea,
            corner_radius=10,
            fg_color="#303030",
        )
        self.bloque_producto.pack(fill="x", padx=12, pady=(0, 10))

        self.lbl_producto = ctk.CTkLabel(
            self.bloque_producto,
            text="Producto: ninguno seleccionado",
            text_color="#b0b0b0",
            justify="left",
            wraplength=280,
        )
        self.lbl_producto.pack(fill="x", padx=10, pady=(10, 8))

        ctk.CTkButton(
            self.bloque_producto,
            text="Seleccionar producto",
            command=self._abrir_selector_productos,
        ).pack(fill="x", padx=10, pady=(0, 8))

        self.entry_cantidad = ctk.CTkEntry(
            self.bloque_producto,
            placeholder_text="Cantidad",
        )
        self.entry_cantidad.pack(fill="x", padx=10, pady=(0, 10))

        # MANUAL
        self.bloque_manual = ctk.CTkFrame(
            box_linea,
            corner_radius=10,
            fg_color="#303030",
        )

        self.manual_desc = ctk.CTkEntry(
            self.bloque_manual,
            placeholder_text="Descripción",
        )
        self.manual_desc.pack(fill="x", padx=10, pady=(10, 8))

        fila_manual = ctk.CTkFrame(self.bloque_manual, fg_color="transparent")
        fila_manual.pack(fill="x", padx=10, pady=(0, 10))

        self.manual_cantidad = ctk.CTkEntry(
            fila_manual,
            placeholder_text="Cantidad",
            width=110,
        )
        self.manual_cantidad.pack(side="left", padx=(0, 8))

        self.manual_precio = ctk.CTkEntry(
            fila_manual,
            placeholder_text="Precio",
            width=130,
        )
        self.manual_precio.pack(side="left", padx=(0, 8))

        self.manual_iva = ctk.CTkEntry(
            fila_manual,
            placeholder_text="IVA %",
            width=90,
        )
        self.manual_iva.insert(0, "21")
        self.manual_iva.pack(side="left")

        ctk.CTkButton(
            box_linea,
            text="Añadir línea",
            fg_color="#2fa572",
            hover_color="#238a5e",
            command=self._agregar_linea,
        ).pack(fill="x", padx=12, pady=(0, 12))

        # ======================================================
        # DERECHA
        # ======================================================

        derecha = ctk.CTkFrame(
            cuerpo,
            corner_radius=12,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
        )
        derecha.grid(row=0, column=1, sticky="nsew")

        top_lineas = ctk.CTkFrame(derecha, fg_color="transparent")
        top_lineas.pack(fill="x", padx=14, pady=(14, 8))

        ctk.CTkLabel(
            top_lineas,
            text="Líneas del albarán",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left")

        self.lbl_resumen = ctk.CTkLabel(
            top_lineas,
            text="0 líneas",
            text_color="#b0b0b0",
        )
        self.lbl_resumen.pack(side="right")

        self.lista_lineas = ctk.CTkScrollableFrame(
            derecha,
            fg_color="#252525",
            corner_radius=10,
            border_width=1,
            border_color="#3a3a3a",
        )
        self.lista_lineas.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        footer = ctk.CTkFrame(
            derecha,
            fg_color="#2d2d2d",
            corner_radius=10,
            border_width=1,
            border_color="#3a3a3a",
        )
        footer.pack(fill="x", padx=14, pady=(0, 14))

        fila_total = ctk.CTkFrame(footer, fg_color="transparent")
        fila_total.pack(fill="x", padx=14, pady=(12, 8))

        ctk.CTkLabel(
            fila_total,
            text="Total albarán",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")

        self.lbl_total_footer = ctk.CTkLabel(
            fila_total,
            text="0.00 €",
            text_color="#4ea8ff",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.lbl_total_footer.pack(side="right")

        fila_botones = ctk.CTkFrame(footer, fg_color="transparent")
        fila_botones.pack(fill="x", padx=14, pady=(0, 14))

        ctk.CTkButton(
            fila_botones,
            text="Cancelar",
            fg_color="#4a4a4a",
            hover_color="#3a3a3a",
            command=self.destroy,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            fila_botones,
            text="Crear albarán",
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=self._crear_albaran,
        ).pack(side="right")

    # =========================================================
    # SELECTORES
    # =========================================================

    def _abrir_selector_clientes(self):
        from app.ui.selector_clientes_window import SelectorClientesWindow

        def on_select(cliente: dict):
            self.cliente_seleccionado = cliente

            nombre = cliente.get("nombre") or "(sin nombre)"
            cid = cliente.get("id")

            texto = f"ID {cid} · {nombre}"

            self.lbl_cliente.configure(text=texto)

        SelectorClientesWindow(self, on_select)

    def _abrir_selector_productos(self):
        from app.ui.selector_productos_window import SelectorProductosWindow

        def on_select(producto: dict):
            self.producto_seleccionado = producto

            nombre = producto.get("nombre") or "(sin nombre)"
            precio = float(producto.get("precio") or 0)
            iva = float(producto.get("iva") or 21)

            self.lbl_producto.configure(
                text=f"{nombre}\nPrecio: {precio:.2f} € · IVA {iva:g}%"
            )

        SelectorProductosWindow(self, on_select)

    # =========================================================
    # MODO LINEA
    # =========================================================

    def _toggle_modo_linea(self):
        if self.modo_manual.get():
            self.bloque_producto.pack_forget()
            self.bloque_manual.pack(fill="x", padx=12, pady=(0, 10))
        else:
            self.bloque_manual.pack_forget()
            self.bloque_producto.pack(fill="x", padx=12, pady=(0, 10))

    # =========================================================
    # LINEAS
    # =========================================================

    def _agregar_linea(self):

        try:

            if self.modo_manual.get():

                descripcion = validar_no_vacio(self.manual_desc.get(), "Descripción")
                cantidad = validar_float(self.manual_cantidad.get(), "Cantidad")
                precio = validar_float(
                    self.manual_precio.get(), "Precio", permitir_cero=True
                )
                iva = validar_iva(self.manual_iva.get())

                if cantidad <= 0:
                    raise ValueError("La cantidad debe ser mayor que 0.")

                linea = {
                    "producto_id": None,
                    "descripcion": descripcion,
                    "cantidad": cantidad,
                    "precio": precio,
                    "iva": iva,
                }

            else:

                if not self.producto_seleccionado:
                    messagebox.showwarning("Falta producto", "Selecciona un producto.")
                    return

                cantidad = validar_float(self.entry_cantidad.get(), "Cantidad")

                if cantidad <= 0:
                    raise ValueError("La cantidad debe ser mayor que 0.")

                linea = {
                    "producto_id": self.producto_seleccionado.get("id"),
                    "descripcion": self.producto_seleccionado.get("nombre"),
                    "cantidad": cantidad,
                    "precio": float(self.producto_seleccionado.get("precio")),
                    "iva": float(self.producto_seleccionado.get("iva")),
                }

            self.lineas.append(linea)

            self._render_lineas()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _render_lineas(self):

        for w in self.lista_lineas.winfo_children():
            w.destroy()

        if not self.lineas:

            ctk.CTkLabel(
                self.lista_lineas,
                text="No hay líneas añadidas todavía.",
                text_color="#b0b0b0",
            ).pack(anchor="w", padx=10, pady=10)

        else:

            for idx, l in enumerate(self.lineas):

                card = ctk.CTkFrame(
                    self.lista_lineas,
                    corner_radius=10,
                    fg_color="#303030",
                    border_width=1,
                    border_color="#3a3a3a",
                )
                card.pack(fill="x", pady=6, padx=6)

                top = ctk.CTkFrame(card, fg_color="transparent")
                top.pack(fill="x", padx=10, pady=(10, 4))

                ctk.CTkLabel(
                    top,
                    text=l["descripcion"],
                    font=ctk.CTkFont(weight="bold"),
                ).pack(side="left")

                ctk.CTkButton(
                    top,
                    text="✕",
                    width=28,
                    height=28,
                    fg_color="#8b2e2e",
                    hover_color="#6f2323",
                    command=lambda i=idx: self._eliminar_linea(i),
                ).pack(side="right")

                ctk.CTkLabel(
                    card,
                    text=f'{l["cantidad"]:g} x {l["precio"]:.2f} € · IVA {l["iva"]:g}%',
                    text_color="#b0b0b0",
                ).pack(anchor="w", padx=10)

                total_linea = l["cantidad"] * l["precio"] * (1 + l["iva"] / 100)

                ctk.CTkLabel(
                    card,
                    text=f"{total_linea:.2f} €",
                    text_color="#4ea8ff",
                    font=ctk.CTkFont(weight="bold"),
                ).pack(anchor="e", padx=10, pady=(0, 10))

        total = self._calcular_total()

        self.lbl_total_header.configure(text=f"{total:.2f} €")
        self.lbl_total_footer.configure(text=f"{total:.2f} €")

        self.lbl_resumen.configure(
            text=(
                f"{len(self.lineas)} línea"
                if len(self.lineas) == 1
                else f"{len(self.lineas)} líneas"
            )
        )

    def _eliminar_linea(self, idx):
        if 0 <= idx < len(self.lineas):
            self.lineas.pop(idx)
            self._render_lineas()

    def _calcular_total(self):
        total = 0.0
        for l in self.lineas:
            total += l["cantidad"] * l["precio"] * (1 + l["iva"] / 100)
        return total

    # =========================================================
    # CREAR ALBARAN
    # =========================================================

    def _crear_albaran(self):

        if not self.cliente_seleccionado:
            messagebox.showwarning("Falta cliente", "Selecciona un cliente.")
            return

        if not self.lineas:
            messagebox.showwarning("Sin líneas", "Añade al menos una línea.")
            return

        try:

            cliente_id = int(self.cliente_seleccionado["id"])

            fecha = self.entry_fecha.get()

            albaran_id = crear_albaran(cliente_id, fecha)

            for l in self.lineas:

                añadir_linea(
                    albaran_id,
                    l["descripcion"],
                    l["cantidad"],
                    l["precio"],
                    l["iva"],
                    l.get("producto_id"),
                )

            if self.on_created:
                self.on_created(albaran_id)

            self.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear el albarán:\n\n{e}")

    def _abrir_calendario(self):

        top = tk.Toplevel(self)
        top.title("Seleccionar fecha")
        top.transient(self)
        top.grab_set()

        cal = Calendar(top, selectmode="day")
        cal.pack(padx=10, pady=10)

        def seleccionar():

            fecha = cal.selection_get()

            self.entry_fecha.delete(0, "end")
            self.entry_fecha.insert(0, fecha.strftime("%d/%m/%Y"))

            top.destroy()

        ttk.Button(top, text="Seleccionar", command=seleccionar).pack(pady=10)
