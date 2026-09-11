import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
from tkcalendar import Calendar
from datetime import datetime, date

from app.services.facturas_service import (
    crear_factura_directa,
    crear_factura_rectificativa,
    obtener_lineas_factura,
)


# =========================================================
# DIALOGO NUEVA FACTURA (UI MEJORADA)
# =========================================================
class NuevaFacturaDialog(ctk.CTkToplevel):

    def __init__(self, master, on_created=None):
        super().__init__(master)

        self.on_created = on_created

        self.focus_force()
        self.lift()

        self.title("Nueva factura")
        self.minsize(900, 600)
        self.resizable(True, True)
        self.grab_set()

        self.cliente_seleccionado = None
        self.lineas = []

        container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # =====================================================
        # HEADER DOCUMENTO
        # =====================================================
        header = ctk.CTkFrame(
            container,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
            corner_radius=10,
        )
        header.pack(fill="x", padx=10, pady=(10, 10))

        ctk.CTkLabel(
            header,
            text="Nueva factura",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=15, pady=(10, 0))

        ctk.CTkLabel(
            header,
            text="Serie automática",
            text_color="#b0b0b0",
        ).pack(anchor="w", padx=15, pady=(0, 10))

        # =====================================================
        # DATOS FACTURA
        # =====================================================
        datos_frame = ctk.CTkFrame(
            container,
            corner_radius=10,
            fg_color="#262626",
            border_width=1,
            border_color="#3a3a3a",
        )
        datos_frame.pack(fill="x", padx=10, pady=(0, 10))

        for col in range(9):
            datos_frame.grid_columnconfigure(col, weight=0)

        # FECHA
        ctk.CTkLabel(datos_frame, text="Fecha factura").grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )

        self.fecha_var = tk.StringVar()
        self.fecha_var.set(date.today().strftime("%d/%m/%Y"))

        self.entry_fecha = ctk.CTkEntry(datos_frame, width=140)
        self.entry_fecha.insert(0, self.fecha_var.get())
        self.entry_fecha.configure(state="readonly")
        self.entry_fecha.grid(row=0, column=1, padx=10, pady=10, sticky="w")

        ctk.CTkButton(
            datos_frame,
            text="📅",
            width=40,
            command=self._abrir_calendario,
        ).grid(row=0, column=2, padx=(0, 15), pady=10, sticky="w")

        # FORMA PAGO
        ctk.CTkLabel(datos_frame, text="Forma de pago").grid(
            row=0, column=3, padx=10, pady=10, sticky="w"
        )

        self.combo_pago = ctk.CTkOptionMenu(
            datos_frame,
            values=["CONTADO", "TRANSFERENCIA", "TARJETA", "BIZUM", "DOMICILIACION"],
            width=170,
        )
        self.combo_pago.set("CONTADO")
        self.combo_pago.grid(row=0, column=4, padx=10, pady=10, sticky="w")

        # VENCIMIENTO
        ctk.CTkLabel(datos_frame, text="Vencimiento").grid(
            row=0, column=5, padx=10, pady=10, sticky="w"
        )

        self.combo_venc = ctk.CTkOptionMenu(
            datos_frame,
            values=["10D", "15D", "30D", "60D", "90D"],
            width=120,
        )
        self.combo_venc.set("30D")
        self.combo_venc.grid(row=0, column=6, padx=10, pady=10, sticky="w")

        # DIA DE PAGO
        ctk.CTkLabel(datos_frame, text="Día de pago").grid(
            row=0, column=7, padx=10, pady=10, sticky="w"
        )

        self.entry_dia_pago = ctk.CTkEntry(datos_frame, width=60)
        self.entry_dia_pago.grid(row=0, column=8, padx=10, pady=10, sticky="w")
        self.entry_dia_pago.insert(0, "")

        # =====================================================
        # BLOQUE CLIENTE
        # =====================================================
        cliente_box = ctk.CTkFrame(
            container,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
            corner_radius=10,
        )
        cliente_box.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(
            cliente_box,
            text="Cliente",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 0))

        self.lbl_cliente = ctk.CTkLabel(
            cliente_box,
            text="Ningún cliente seleccionado",
            text_color="#b0b0b0",
        )
        self.lbl_cliente.pack(anchor="w", padx=10, pady=(0, 5))

        ctk.CTkButton(
            cliente_box,
            text="Seleccionar cliente",
            command=self._seleccionar_cliente,
            fg_color="#2b6ca3",
            hover_color="#235781",
        ).pack(anchor="w", padx=10, pady=(0, 10))

        # =====================================================
        # LINEAS
        # =====================================================
        lineas_container = ctk.CTkFrame(
            container,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
            corner_radius=10,
        )
        lineas_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        ctk.CTkLabel(
            lineas_container,
            text="Líneas de factura",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 5))

        # Cabecera de columnas
        cabecera = ctk.CTkFrame(lineas_container, fg_color="transparent")
        cabecera.pack(fill="x", padx=14)

        ctk.CTkLabel(cabecera, text="Descripción", text_color="#b0b0b0").pack(
            side="left", fill="x", expand=True, padx=4
        )
        ctk.CTkLabel(cabecera, text="Cant", text_color="#b0b0b0", width=60).pack(
            side="left", padx=4
        )
        ctk.CTkLabel(cabecera, text="Precio", text_color="#b0b0b0", width=100).pack(
            side="left", padx=4
        )
        ctk.CTkLabel(cabecera, text="IVA %", text_color="#b0b0b0", width=60).pack(
            side="left", padx=4
        )
        ctk.CTkLabel(cabecera, text="", width=40).pack(side="left", padx=4)

        self.frame_lineas = ctk.CTkScrollableFrame(
            lineas_container,
            height=200,
            fg_color="#252525",
        )
        self.frame_lineas.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        # Total
        self.lbl_total = ctk.CTkLabel(
            lineas_container,
            text="TOTAL: 0.00 €",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.lbl_total.pack(anchor="e", padx=20, pady=(4, 8))

        botones_lineas = ctk.CTkFrame(lineas_container, fg_color="transparent")
        botones_lineas.pack(pady=(0, 10))

        ctk.CTkButton(
            botones_lineas,
            text="➕ Añadir producto",
            command=self._añadir_producto,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            botones_lineas,
            text="✏ Añadir línea manual",
            fg_color="#3a7a3a",
            hover_color="#2e632e",
            command=self._add_linea,
        ).pack(side="left", padx=5)

        self._add_linea()

        # =====================================================
        # BOTON CREAR
        # =====================================================
        self.btn_crear = ctk.CTkButton(
            container,
            text="💾 Crear factura",
            height=42,
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._crear_factura,
        )
        self.btn_crear.pack(pady=(0, 10))

    # =========================================================
    # CALENDARIO
    # =========================================================
    def _abrir_calendario(self):

        top_cal = tk.Toplevel()
        top_cal.title("Seleccionar fecha")
        top_cal.geometry("320x340")
        top_cal.resizable(False, False)
        top_cal.grab_set()

        cal = Calendar(
            top_cal,
            selectmode="day",
            date_pattern="dd/mm/yyyy",
        )
        cal.pack(padx=10, pady=10, fill="both", expand=True)

        def seleccionar_fecha():
            f = cal.get_date()
            self.fecha_var.set(f)
            self.entry_fecha.configure(state="normal")
            self.entry_fecha.delete(0, "end")
            self.entry_fecha.insert(0, f)
            self.entry_fecha.configure(state="readonly")
            top_cal.destroy()

        tk.Button(top_cal, text="Seleccionar", command=seleccionar_fecha).pack(
            pady=(0, 10)
        )

    # =========================================================
    # CLIENTE
    # =========================================================
    def _seleccionar_cliente(self):

        from app.ui.selector_clientes_window import SelectorClientesWindow

        def on_select(cliente):
            self.cliente_seleccionado = cliente
            nombre = cliente.get("nombre") or "(sin nombre)"
            email = cliente.get("email") or ""
            tel = cliente.get("telefono") or ""
            self.lbl_cliente.configure(text=f"{nombre}  {email} {tel}")

        SelectorClientesWindow(self, on_select)

    # =========================================================
    # AÑADIR LÍNEA EDITABLE (unifica producto + manual)
    # =========================================================
    def _add_linea(self, producto_id=None):

        fila = ctk.CTkFrame(self.frame_lineas)
        fila.pack(fill="x", pady=4, padx=4)

        e_desc = ctk.CTkEntry(fila, placeholder_text="Descripción")
        e_desc.pack(side="left", fill="x", expand=True, padx=4)

        e_cant = ctk.CTkEntry(fila, width=60)
        e_cant.insert(0, "1")
        e_cant.pack(side="left", padx=4)

        e_precio = ctk.CTkEntry(fila, width=100, placeholder_text="Precio")
        e_precio.pack(side="left", padx=4)

        e_iva = ctk.CTkEntry(fila, width=60)
        e_iva.insert(0, "21")
        e_iva.pack(side="left", padx=4)

        data = {
            "producto_id": producto_id,
            "d": e_desc,
            "c": e_cant,
            "p": e_precio,
            "i": e_iva,
            "fila": fila,
        }
        self.lineas.append(data)

        def eliminar():
            fila.destroy()
            self.lineas.remove(data)
            self._recalcular_total()

        ctk.CTkButton(
            fila,
            text="X",
            width=40,
            fg_color="#8b2e2e",
            hover_color="#6f2323",
            command=eliminar,
        ).pack(side="left", padx=4)

        e_cant.bind("<KeyRelease>", lambda e: self._recalcular_total())
        e_precio.bind("<KeyRelease>", lambda e: self._recalcular_total())
        e_iva.bind("<KeyRelease>", lambda e: self._recalcular_total())

        return data

    # =========================================================
    # AÑADIR PRODUCTO (selección + rellena fila editable)
    # =========================================================
    def _añadir_producto(self):

        from app.ui.selector_productos_window import SelectorProductosWindow

        def on_select(producto):

            data = self._add_linea(producto_id=producto.get("id"))

            data["d"].insert(0, producto.get("nombre", ""))
            data["c"].delete(0, "end")
            data["c"].insert(0, "1")
            data["p"].delete(0, "end")
            data["p"].insert(0, str(float(producto.get("precio", 0))))
            data["i"].delete(0, "end")
            data["i"].insert(0, str(float(producto.get("iva", 21))))

            self._recalcular_total()

        SelectorProductosWindow(self, on_select)

    # =========================================================
    # RECALCULAR TOTAL
    # =========================================================
    def _recalcular_total(self):

        total = 0

        for l in self.lineas:
            try:
                c = float(l["c"].get())
                p = float(l["p"].get())
                iva = float(l["i"].get())
                total += c * p * (1 + iva / 100)
            except:
                pass

        self.lbl_total.configure(text=f"TOTAL: {total:.2f} €")

    # =========================================================
    # CREAR FACTURA
    # =========================================================
    def _crear_factura(self):

        if not self.cliente_seleccionado:
            messagebox.showwarning("Falta cliente", "Selecciona un cliente.")
            return

        if not self.lineas:
            messagebox.showwarning("Sin líneas", "Añade al menos una línea.")
            return

        try:

            fecha_ui = self.fecha_var.get().strip()
            fecha_iso = datetime.strptime(fecha_ui, "%d/%m/%Y").strftime("%Y-%m-%d")

            dia_pago_txt = self.entry_dia_pago.get().strip()

            if dia_pago_txt:
                if not dia_pago_txt.isdigit():
                    messagebox.showerror("Error", "El día de pago debe ser un número.")
                    return

                dia_pago = int(dia_pago_txt)

                if dia_pago < 1 or dia_pago > 31:
                    messagebox.showerror(
                        "Error", "El día de pago debe estar entre 1 y 31."
                    )
                    return
            else:
                dia_pago = None

            # Leer valores de los widgets de cada línea
            lineas_data = []
            for l in self.lineas:
                desc = l["d"].get().strip()
                if not desc:
                    raise ValueError("Hay una línea sin descripción.")
                lineas_data.append(
                    {
                        "producto_id": l["producto_id"],
                        "descripcion": desc,
                        "cantidad": float(l["c"].get()),
                        "precio": float(l["p"].get()),
                        "iva": float(l["i"].get()),
                    }
                )

            factura_id = crear_factura_directa(
                cliente_id=int(self.cliente_seleccionado["id"]),
                lineas=lineas_data,
                forma_pago=self.combo_pago.get(),
                tipo_vencimiento=self.combo_venc.get(),
                fecha=fecha_iso,
                dia_pago=dia_pago,
            )

            if hasattr(self, "on_created") and self.on_created:
                self.on_created(factura_id)

            self.destroy()

        except Exception as e:
            messagebox.showerror("Error", str(e))


# =========================================================
# DIALOGO RECTIFICAR FACTURA
# =========================================================
class RectificarFacturaDialog(ctk.CTkToplevel):

    def __init__(self, master, factura_id, on_created=None):
        super().__init__(master)

        self.factura_id = factura_id
        self.on_created = on_created

        self.title("Crear factura rectificativa")
        self.geometry("500x450")
        self.grab_set()

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        self.lineas_rectificar = []

        # ============================
        # LINEAS DE FACTURA
        # ============================

        lineas = obtener_lineas_factura(self.factura_id)

        ctk.CTkLabel(
            frame,
            text="Líneas a rectificar",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", pady=(10, 5))

        lineas_frame = ctk.CTkFrame(frame)
        lineas_frame.pack(fill="x", pady=(0, 10))

        for producto_id, desc, cant, precio, iva, total in lineas:

            fila = ctk.CTkFrame(lineas_frame)
            fila.pack(fill="x", pady=3)

            ctk.CTkLabel(
                fila,
                text=f"{desc} | Facturado: {int(cant) if float(cant).is_integer() else cant}",
                width=200,
                anchor="w",
            ).pack(side="left")

            entry = ctk.CTkEntry(fila, width=60)
            entry.insert(0, "0")
            entry.pack(side="left", padx=5)

            self.lineas_rectificar.append(
                {
                    "producto_id": producto_id,
                    "descripcion": desc,
                    "cantidad": entry,
                    "precio": precio,
                    "iva": iva,
                    "max": cant,
                }
            )

        ctk.CTkLabel(
            frame,
            text="Motivo de la rectificación",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", pady=(5, 5))

        self.entry_motivo = ctk.CTkEntry(frame)
        self.entry_motivo.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            frame,
            text="Fecha",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", pady=(0, 5))

        self.fecha_var = tk.StringVar()
        self.fecha_var.set(date.today().strftime("%d/%m/%Y"))

        self.entry_fecha = ctk.CTkEntry(frame, textvariable=self.fecha_var)
        self.entry_fecha.pack(fill="x", pady=(0, 20))

        botones = ctk.CTkFrame(frame, fg_color="transparent")
        botones.pack(fill="x")

        ctk.CTkButton(
            botones,
            text="Cancelar",
            command=self.destroy,
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))

        ctk.CTkButton(
            botones,
            text="Crear rectificativa",
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=self._crear_rectificativa,
        ).pack(side="left", expand=True, fill="x", padx=(5, 0))

    def _crear_rectificativa(self):

        motivo = self.entry_motivo.get().strip()

        if not motivo:
            messagebox.showerror("Error", "Debes indicar un motivo.")
            return

        try:

            fecha_iso = datetime.strptime(self.fecha_var.get(), "%d/%m/%Y").strftime(
                "%Y-%m-%d"
            )

            # =========================================
            # OBTENER LINEAS SELECCIONADAS
            # =========================================
            lineas_rectificar = []

            for l in self.lineas_rectificar:

                try:
                    cantidad = float(l["cantidad"].get())
                except:
                    raise Exception("Cantidad inválida.")

                if cantidad < 0:
                    raise Exception("La cantidad no puede ser negativa.")

                if cantidad > l["max"]:
                    raise Exception(
                        f"No puedes rectificar más de {l['max']} unidades de {l['descripcion']}"
                    )

                if cantidad > 0:
                    lineas_rectificar.append(
                        {
                            "producto_id": l["producto_id"],
                            "descripcion": l["descripcion"],
                            "cantidad": cantidad,
                            "precio": l["precio"],
                            "iva": l["iva"],
                        }
                    )

            if not lineas_rectificar:
                messagebox.showerror(
                    "Error",
                    "Debes indicar al menos una línea a rectificar.",
                )
                return

            crear_factura_rectificativa(
                self.factura_id,
                motivo,
                lineas_rectificar,
                fecha_iso,
            )

            if self.on_created:
                self.on_created()

            self.destroy()

        except Exception as e:
            messagebox.showerror("Error", str(e))
