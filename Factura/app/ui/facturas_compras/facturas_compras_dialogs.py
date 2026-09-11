import customtkinter as ctk
from tkinter import messagebox
from tkcalendar import DateEntry

from app.services.facturas_compras_service import (
    crear_factura_compra,
    añadir_linea_factura_compra,
)

from app.services.proveedores_service import (
    obtener_proveedores,
    crear_proveedor,
)

# NUEVO IMPORTADOR
from app.ui.importadores.importar_excel_dialog import ImportarExcelDialog

from app.utils.validators import (
    validar_no_vacio,
    validar_float,
    validar_iva,
    validar_fecha,
)


class NuevaFacturaCompraDialog(ctk.CTkToplevel):

    def __init__(self, master, on_created=None):
        super().__init__(master)

        self.on_created = on_created

        self.title("Nueva factura de compra")
        self.geometry("900x700")
        self.grab_set()

        self.proveedor = {"id": None, "nombre": None}
        self.lineas = []

        # =====================================================
        # PANEL PRINCIPAL
        # =====================================================
        panel = ctk.CTkFrame(
            self,
            corner_radius=14,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        panel.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            panel,
            text="Nueva factura de compra",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(20, 10))

        # =====================================================
        # PROVEEDOR
        # =====================================================
        fila_prov = ctk.CTkFrame(panel, fg_color="transparent")
        fila_prov.pack(fill="x", padx=20, pady=(10, 10))

        ctk.CTkLabel(fila_prov, text="Proveedor", width=120).pack(side="left")

        self.entry_prov = ctk.CTkEntry(
            fila_prov,
            placeholder_text="Seleccionar proveedor",
            state="readonly",
        )
        self.entry_prov.pack(side="left", fill="x", expand=True, padx=6)

        ctk.CTkButton(
            fila_prov,
            text="Seleccionar",
            width=120,
            command=self._seleccionar_proveedor,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            fila_prov,
            text="+",
            width=40,
            command=self._nuevo_proveedor,
        ).pack(side="left")

        # =====================================================
        # NUMERO FACTURA
        # =====================================================
        fila_num = ctk.CTkFrame(panel, fg_color="transparent")
        fila_num.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(fila_num, text="Número factura", width=120).pack(side="left")

        self.e_num = ctk.CTkEntry(fila_num)
        self.e_num.pack(side="left", fill="x", expand=True)

        # =====================================================
        # FECHAS
        # =====================================================
        fila_fechas = ctk.CTkFrame(panel, fg_color="transparent")
        fila_fechas.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(fila_fechas, text="Fecha", width=120).pack(side="left")

        self.e_fecha = DateEntry(
            fila_fechas,
            date_pattern="dd/mm/yyyy",
            width=12,
        )
        self.e_fecha.pack(side="left", padx=6)

        ctk.CTkLabel(fila_fechas, text="Vencimiento").pack(side="left", padx=(20, 4))

        self.e_venc = DateEntry(
            fila_fechas,
            date_pattern="dd/mm/yyyy",
            width=12,
        )
        self.e_venc.pack(side="left")

        # =====================================================
        # LINEAS
        # =====================================================
        ctk.CTkLabel(
            panel,
            text="Líneas de la factura",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(14, 6))

        self.frame_lineas = ctk.CTkScrollableFrame(
            panel,
            height=260,
            corner_radius=10,
            fg_color="#252525",
        )
        self.frame_lineas.pack(fill="both", expand=True, padx=20)

        # =====================================================
        # TOTAL
        # =====================================================
        self.lbl_total = ctk.CTkLabel(
            panel,
            text="TOTAL: 0.00 €",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.lbl_total.pack(anchor="e", padx=20, pady=(10, 6))

        # =====================================================
        # BOTONES
        # =====================================================
        botones = ctk.CTkFrame(panel, fg_color="transparent")
        botones.pack(pady=8)

        ctk.CTkButton(
            botones,
            text="+ Añadir línea",
            command=self._add_linea,
        ).pack(side="left", padx=6)

        # NUEVO BOTON IMPORTAR EXCEL
        ctk.CTkButton(
            botones,
            text="Importar Excel",
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=self._importar_excel,
        ).pack(side="left", padx=6)

        # =====================================================
        # BOTON CREAR
        # =====================================================
        ctk.CTkButton(
            panel,
            text="Crear factura",
            height=40,
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=self._crear_factura,
        ).pack(pady=12)

        self._add_linea()

    # =====================================================
    # IMPORTAR EXCEL
    # =====================================================
    def _importar_excel(self):

        def on_import(productos):

            # eliminar linea inicial vacía si existe
            if len(self.lineas) == 1:
                l = self.lineas[0]
                if not l["d"].get().strip():
                    l["fila"].destroy()
                    self.lineas.clear()

            for p in productos:

                # saltar productos con cantidad 0 o negativa
                if not p["cantidad"] or float(p["cantidad"]) <= 0:
                    continue

                self._add_linea()

                linea = self.lineas[-1]

                linea["d"].delete(0, "end")
                linea["d"].insert(0, p["nombre"])

                linea["c"].delete(0, "end")
                linea["c"].insert(0, str(p["cantidad"]))

                linea["p"].delete(0, "end")
                linea["p"].insert(0, str(p["precio"]))

                linea["i"].delete(0, "end")
                linea["i"].insert(0, "21")

            self._recalcular_total()

        ImportarExcelDialog(self, on_import)

    # =====================================================
    # PROVEEDOR
    # =====================================================
    def _seleccionar_proveedor(self):

        win = ctk.CTkToplevel(self)
        win.title("Seleccionar proveedor")
        win.geometry("420x420")
        win.grab_set()

        buscar = ctk.CTkEntry(win, placeholder_text="Buscar proveedor...")
        buscar.pack(fill="x", padx=20, pady=(20, 10))

        lista = ctk.CTkScrollableFrame(win)
        lista.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        proveedores = sorted(obtener_proveedores(), key=lambda x: x[1])

        def cargar(filtro=""):

            for w in lista.winfo_children():
                w.destroy()

            for p in proveedores:

                pid = p[0]
                nombre = p[1]

                if filtro.lower() not in nombre.lower():
                    continue

                def elegir(pid=pid, nombre=nombre):

                    self.proveedor["id"] = pid
                    self.proveedor["nombre"] = nombre

                    self.entry_prov.configure(state="normal")
                    self.entry_prov.delete(0, "end")
                    self.entry_prov.insert(0, nombre)
                    self.entry_prov.configure(state="readonly")

                    win.destroy()

                btn = ctk.CTkButton(
                    lista,
                    text=nombre,
                    anchor="w",
                    fg_color="transparent",
                    hover_color="#333333",
                    command=elegir,
                )
                btn.pack(fill="x", pady=2)

        buscar.bind("<KeyRelease>", lambda e: cargar(buscar.get()))
        cargar()

    # =====================================================
    # NUEVO PROVEEDOR
    # =====================================================
    def _nuevo_proveedor(self):

        win = ctk.CTkToplevel(self)
        win.title("Nuevo proveedor")
        win.geometry("400x380")
        win.grab_set()

        frame = ctk.CTkFrame(win)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        e_nombre = ctk.CTkEntry(frame, placeholder_text="Nombre")
        e_nombre.pack(fill="x", pady=6)

        e_cif = ctk.CTkEntry(frame, placeholder_text="CIF")
        e_cif.pack(fill="x", pady=6)

        e_email = ctk.CTkEntry(frame, placeholder_text="Email")
        e_email.pack(fill="x", pady=6)

        e_tel = ctk.CTkEntry(frame, placeholder_text="Teléfono")
        e_tel.pack(fill="x", pady=6)

        e_iban = ctk.CTkEntry(frame, placeholder_text="IBAN")
        e_iban.pack(fill="x", pady=6)

        def guardar():

            try:

                nombre = validar_no_vacio(e_nombre.get(), "Nombre")

                crear_proveedor(
                    nombre,
                    e_cif.get(),
                    e_email.get(),
                    e_tel.get(),
                    "",
                    e_iban.get(),
                )

                messagebox.showinfo("Proveedor", "Proveedor creado correctamente")

                win.destroy()

            except Exception as e:
                messagebox.showerror("Error", str(e))

        ctk.CTkButton(
            frame,
            text="Guardar proveedor",
            command=guardar,
        ).pack(pady=14)

    # =====================================================
    # LINEAS
    # =====================================================
    def _add_linea(self):

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

        data = {"d": e_desc, "c": e_cant, "p": e_precio, "i": e_iva, "fila": fila}
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

    # =====================================================
    # TOTAL
    # =====================================================
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

    # =====================================================
    # CREAR FACTURA
    # =====================================================
    def _crear_factura(self):

        try:

            proveedor_id = self.proveedor["id"]

            if not proveedor_id:
                raise ValueError("Selecciona un proveedor.")

            numero = validar_no_vacio(self.e_num.get(), "Número factura")

            fecha_db = validar_fecha(self.e_fecha.get())
            venc_db = validar_fecha(self.e_venc.get())

            factura_id = crear_factura_compra(
                proveedor_id,
                numero,
                fecha_db,
                venc_db,
                "TRANSFERENCIA",
            )

            for linea in self.lineas:

                desc = validar_no_vacio(linea["d"].get(), "Descripción")
                cant = validar_float(linea["c"].get(), "Cantidad")
                precio = validar_float(linea["p"].get(), "Precio", permitir_cero=True)
                iva = validar_iva(linea["i"].get())

                añadir_linea_factura_compra(
                    factura_id,
                    desc,
                    cant,
                    precio,
                    iva,
                )

            if self.on_created:
                self.on_created(factura_id)

            self.destroy()

        except ValueError as e:
            messagebox.showerror("Error de validación", str(e))

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear la factura: {e}")
