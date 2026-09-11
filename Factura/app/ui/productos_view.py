import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime

from app.services.productos_service import (
    obtener_productos,
    crear_producto,
    actualizar_producto,
    borrar_producto,
    ajustar_stock,
    obtener_movimientos_stock,
)

from app.utils.validators import (
    validar_no_vacio,
    validar_float,
    validar_iva,
)

from app.ui.components.pagination import Pagination
from app.ui.components.split_view import SplitView


class ProductosView(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.producto_id = None
        self.productos = []
        self.card_seleccionada = None
        self.modo_vista = "TARJETAS"

        # =====================================================
        # HEADER
        # =====================================================
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text="Productos",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")

        self.btn_vista_tarjetas = ctk.CTkButton(
            header,
            text="Tarjetas",
            width=110,
            fg_color="#1f6aa5",
            command=lambda: self.cambiar_vista("TARJETAS"),
        )
        self.btn_vista_tarjetas.pack(side="left", padx=10)

        self.btn_vista_tabla = ctk.CTkButton(
            header,
            text="Tabla",
            width=110,
            fg_color="#3a3a3a",
            command=lambda: self.cambiar_vista("TABLA"),
        )
        self.btn_vista_tabla.pack(side="left")

        # =====================================================
        # FILTROS
        # =====================================================
        filtros = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        filtros.pack(fill="x", padx=25, pady=(0, 15))

        self.f_nombre = ctk.CTkEntry(filtros, placeholder_text="Buscar por nombre")
        self.f_referencia = ctk.CTkEntry(
            filtros, placeholder_text="Buscar por referencia"
        )
        self.f_precio_min = ctk.CTkEntry(filtros, placeholder_text="Precio mín.")
        self.f_precio_max = ctk.CTkEntry(filtros, placeholder_text="Precio máx.")
        self.f_iva = ctk.CTkEntry(filtros, placeholder_text="IVA %")

        self.f_nombre.grid(row=0, column=0, padx=8, pady=12)
        self.f_referencia.grid(row=0, column=1, padx=8, pady=12)
        self.f_precio_min.grid(row=0, column=2, padx=8, pady=12)
        self.f_precio_max.grid(row=0, column=3, padx=8, pady=12)
        self.f_iva.grid(row=0, column=4, padx=8, pady=12)

        ctk.CTkButton(filtros, text="Buscar", width=110, command=self.buscar).grid(
            row=0, column=5, padx=(15, 5)
        )
        ctk.CTkButton(
            filtros, text="Limpiar", width=110, command=self.limpiar_filtros
        ).grid(row=0, column=6, padx=5)

        filtros.grid_columnconfigure(7, weight=1)

        # =====================================================
        # PAGINACIÓN — se empaqueta ANTES del contenedor
        # para que expand=True del contenedor no la oculte
        # =====================================================
        self.pagination = Pagination(self, on_change=self.on_pagination_change)
        self.pagination.pack(fill="x", padx=25, pady=(0, 10))

        # =====================================================
        # CONTENEDOR CENTRAL
        # =====================================================
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True, padx=25, pady=(0, 10))

        # =====================================================
        # CUERPO
        # =====================================================
        self.cuerpo = SplitView(
            contenedor,
            initial_left_width=520,
            left_minsize=300,
            right_minsize=300
        )
        self.cuerpo.pack(fill="both", expand=True)

        self.lista_productos = ctk.CTkScrollableFrame(
            self.cuerpo.left_frame,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        self.lista_productos.pack(fill="both", expand=True, pady=5)

        panel = ctk.CTkFrame(
            self.cuerpo.right_frame,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        panel.pack(fill="both", expand=True, pady=5)

        # =====================================================
        # FORMULARIO
        # =====================================================
        ctk.CTkLabel(
            panel, text="Datos del producto", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", padx=20, pady=(20, 15))

        self.referencia = self._campo(panel, "Referencia (SKU)")
        self.ean = self._campo(panel, "EAN / Código de barras")
        self.nombre = self._campo(panel, "Nombre del producto")
        self.precio = self._campo(panel, "Precio (€)")
        self.iva = self._campo(panel, "IVA %")
        self.stock = self._campo(panel, "Stock inicial")

        self.iva.insert(0, "21")
        self.stock.insert(0, "0")

        self.control_stock_var = ctk.BooleanVar(value=True)

        ctk.CTkCheckBox(
            panel,
            text="Controlar stock automáticamente",
            variable=self.control_stock_var,
        ).pack(anchor="w", padx=20, pady=(10, 0))

        # =====================================================
        # BOTONES
        # =====================================================
        botones = ctk.CTkFrame(panel, fg_color="transparent")
        botones.pack(pady=25)

        self.btn_guardar = ctk.CTkButton(
            botones, text="Guardar", width=120, command=self.guardar
        )
        self.btn_guardar.grid(row=0, column=0, padx=8)

        self.btn_actualizar = ctk.CTkButton(
            botones,
            text="Actualizar",
            width=120,
            command=self.actualizar,
            state="disabled",
        )
        self.btn_actualizar.grid(row=0, column=1, padx=8)

        self.btn_eliminar = ctk.CTkButton(
            botones,
            text="Eliminar",
            width=120,
            fg_color="#c0392b",
            hover_color="#992d22",
            command=self.eliminar,
            state="disabled",
        )
        self.btn_eliminar.grid(row=0, column=2, padx=8)

        # =====================================================
        # STOCK
        # =====================================================
        stock_frame = ctk.CTkFrame(panel, fg_color="transparent")
        stock_frame.pack(pady=(5, 10))

        self.btn_entrada_stock = ctk.CTkButton(
            stock_frame,
            text="Entrada stock",
            width=150,
            command=lambda: self._ajustar_stock_dialog("ENTRADA"),
        )
        self.btn_entrada_stock.grid(row=0, column=0, padx=6)

        self.btn_salida_stock = ctk.CTkButton(
            stock_frame,
            text="Salida stock",
            width=150,
            command=lambda: self._ajustar_stock_dialog("SALIDA"),
        )
        self.btn_salida_stock.grid(row=0, column=1, padx=6)

        # =====================================================
        # MOVIMIENTOS
        # =====================================================
        ctk.CTkLabel(
            panel, text="Movimientos de stock", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=20, pady=(15, 5))

        self.movimientos_frame = ctk.CTkScrollableFrame(
            panel, height=180, corner_radius=8, fg_color="#252525"
        )
        self.movimientos_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        self.cargar_productos()

    # =====================================================
    # CAMBIAR VISTA
    # =====================================================
    def cambiar_vista(self, modo):

        if self.modo_vista == modo:
            return

        self.modo_vista = modo

        if modo == "TARJETAS":
            self.btn_vista_tarjetas.configure(fg_color="#1f6aa5")
            self.btn_vista_tabla.configure(fg_color="#3a3a3a")
            self.cuerpo.set_left_width(520)
        else:
            self.btn_vista_tabla.configure(fg_color="#1f6aa5")
            self.btn_vista_tarjetas.configure(fg_color="#3a3a3a")
            self.cuerpo.set_left_width(600)

        self.cargar_productos(self.productos)

    # =====================================================
    # CAMPO
    # =====================================================
    def _campo(self, parent, texto):

        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(
            frame, text=texto, text_color="#bdbdbd", font=ctk.CTkFont(size=12)
        ).pack(anchor="w")

        entry = ctk.CTkEntry(frame)
        entry.pack(fill="x", pady=(4, 0))

        return entry

    # =====================================================
    # CARGAR
    # =====================================================
    def cargar_productos(self, datos=None):

        for w in self.lista_productos.winfo_children():
            w.destroy()

        self._deseleccionar()
        self.limpiar_form()

        if datos is not None:
            self.productos = datos
        else:
            self.productos = obtener_productos(
                nombre=self.f_nombre.get().strip(),
                referencia=self.f_referencia.get().strip(),
                precio_min=(
                    validar_float(
                        self.f_precio_min.get(), "Precio mínimo", permitir_cero=True
                    )
                    if self.f_precio_min.get().strip()
                    else None
                ),
                precio_max=(
                    validar_float(
                        self.f_precio_max.get(), "Precio máximo", permitir_cero=True
                    )
                    if self.f_precio_max.get().strip()
                    else None
                ),
                iva=validar_iva(self.f_iva.get()) if self.f_iva.get().strip() else None,
                limit=self.pagination.limit,
                offset=self.pagination.get_offset(),
            )

        if self.modo_vista == "TARJETAS":

            for producto in self.productos:
                self._crear_card(producto)

        else:

            self._crear_tabla_productos()

        self.pagination.lbl_page.configure(text=f"Página {self.pagination.page}")

    # =====================================================
    # NORMALIZAR
    # =====================================================
    def _normalizar(self, producto):

        if len(producto) == 8:
            return producto

        raise Exception(f"Formato producto desconocido: {producto}")

    # =====================================================
    # CARD
    # =====================================================
    def _crear_card(self, producto):

        pid, ref, ean, nombre, precio, iva, stock, control = self._normalizar(producto)

        card = ctk.CTkFrame(
            self.lista_productos,
            corner_radius=12,
            fg_color="#343434",
            border_width=1,
            border_color="#3a3a3a",
        )
        card.pack(fill="x", pady=8, padx=10)

        card._producto_id = pid

        titulo = f"{ref} - {nombre}" if ref else nombre
        stock_txt = stock if control else "—"

        ctk.CTkLabel(card, text=titulo, font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=15, pady=(12, 4)
        )

        extra = f"EAN: {ean}" if ean else ""

        ctk.CTkLabel(
            card,
            text=f"Precio: {precio:.2f} € | IVA: {iva}% | Stock: {stock_txt} {extra}",
            text_color="#bbbbbb",
        ).pack(anchor="w", padx=15, pady=(0, 12))

        def _click(_e=None, producto_id=pid, tarjeta=card, prod=producto):
            self.seleccionar(producto_id, tarjeta, prod)

        card.bind("<Button-1>", _click)
        for widget in card.winfo_children():
            widget.bind("<Button-1>", _click)

    # =====================================================
    # TABLA
    # =====================================================
    def _crear_tabla_productos(self):

        tabla = ctk.CTkFrame(self.lista_productos)
        tabla.pack(fill="both", expand=True, padx=10, pady=10)

        columnas = ["Referencia", "Nombre", "Precio", "IVA", "Stock"]

        header = ctk.CTkFrame(tabla)
        header.pack(fill="x")

        for i, col in enumerate(columnas):

            header.grid_columnconfigure(i, weight=1)

            ctk.CTkLabel(header, text=col, font=ctk.CTkFont(weight="bold")).grid(
                row=0, column=i, padx=10, pady=10, sticky="ew"
            )

        for producto in self.productos:

            pid, ref, ean, nombre, precio, iva, stock, control = self._normalizar(
                producto
            )

            fila = ctk.CTkFrame(tabla, cursor="hand2")
            fila.pack(fill="x", pady=2)

            fila._producto_id = pid

            valores = [
                ref or "",
                nombre,
                f"{precio:.2f} €",
                f"{iva}%",
                stock if control else "—",
            ]

            for i, val in enumerate(valores):

                lbl = ctk.CTkLabel(fila, text=val)
                lbl.grid(row=0, column=i, padx=10, pady=8, sticky="ew")
                fila.grid_columnconfigure(i, weight=1)

                lbl.bind("<Button-1>", lambda e, p=pid: self._seleccionar_por_id(p))

            fila.bind("<Button-1>", lambda e, p=pid: self._seleccionar_por_id(p))

    # =====================================================
    # SELECCION
    # =====================================================
    def seleccionar(self, producto_id, card, producto):

        self._deseleccionar()

        if card is not None:
            self.card_seleccionada = card
            card.configure(fg_color="#1f6aa5")

        _, ref, ean, nombre, precio, iva, stock, control = self._normalizar(producto)

        self.producto_id = producto_id

        self.referencia.delete(0, "end")
        self.referencia.insert(0, ref or "")

        self.ean.delete(0, "end")
        self.ean.insert(0, ean or "")

        self.nombre.delete(0, "end")
        self.nombre.insert(0, nombre)

        self.precio.delete(0, "end")
        self.precio.insert(0, str(precio))

        self.iva.delete(0, "end")
        self.iva.insert(0, str(iva))

        self.stock.delete(0, "end")
        self.stock.insert(0, str(stock))

        self.control_stock_var.set(bool(control))

        self._estado_edicion()
        self.cargar_movimientos()

    def _seleccionar_por_id(self, producto_id):
        """Busca el producto en self.productos y su widget de forma recursiva."""

        for producto in self.productos:
            pid, *_ = self._normalizar(producto)
            if pid == producto_id:
                widget = self._buscar_widget_por_id(producto_id)
                self.seleccionar(producto_id, widget, producto)
                return

    def _buscar_widget_por_id(self, producto_id):
        """Busca recursivamente el widget con _producto_id dado dentro de lista_productos."""

        def _buscar(parent):
            for w in parent.winfo_children():
                if getattr(w, "_producto_id", None) == producto_id:
                    return w
                resultado = _buscar(w)
                if resultado:
                    return resultado
            return None

        return _buscar(self.lista_productos)

    # =====================================================
    # MOVIMIENTOS
    # =====================================================
    def cargar_movimientos(self):

        for w in self.movimientos_frame.winfo_children():
            w.destroy()

        if not self.producto_id:
            return

        movimientos = obtener_movimientos_stock(self.producto_id)

        if not movimientos:
            ctk.CTkLabel(
                self.movimientos_frame, text="Sin movimientos", text_color="#999"
            ).pack(anchor="w", padx=10, pady=5)
            return

        for tipo, cantidad, fecha, detalle in movimientos:

            try:
                fecha_fmt = datetime.strptime(fecha, "%Y-%m-%d %H:%M:%S").strftime(
                    "%d/%m/%Y %H:%M"
                )
            except Exception:
                fecha_fmt = fecha

            icono = ""
            color = "#bbbbbb"

            if tipo == "ENTRADA":
                icono = "🟢"
                color = "#27ae60"
            elif tipo == "SALIDA":
                icono = "🔴"
                color = "#e74c3c"
            elif tipo == "AJUSTE":
                icono = "🟠"
                color = "#f39c12"

            try:
                cantidad_fmt = f"{cantidad:+.2f}"
            except Exception:
                cantidad_fmt = str(cantidad)

            texto = f"{icono} {fecha_fmt}  |  {tipo}  |  {cantidad_fmt}"

            frame = ctk.CTkFrame(self.movimientos_frame, fg_color="transparent")
            frame.pack(fill="x", pady=2)

            ctk.CTkLabel(frame, text=texto, text_color=color, anchor="w").pack(
                side="left", padx=5
            )

            if detalle:
                ctk.CTkLabel(frame, text=detalle, text_color="#888").pack(
                    side="right", padx=5
                )

    # =====================================================
    # DESELECCION
    # =====================================================
    def _deseleccionar(self):

        if self.card_seleccionada:
            try:
                self.card_seleccionada.configure(fg_color="#343434")
            except Exception:
                pass

        self.card_seleccionada = None

    # =====================================================
    # ESTADOS
    # =====================================================
    def _estado_nuevo(self):

        self.btn_guardar.configure(state="normal")
        self.btn_actualizar.configure(state="disabled")
        self.btn_eliminar.configure(state="disabled")

    def _estado_edicion(self):

        self.btn_guardar.configure(state="disabled")
        self.btn_actualizar.configure(state="normal")
        self.btn_eliminar.configure(state="normal")

    # =====================================================
    # BUSCAR
    # =====================================================
    def buscar(self):

        try:
            self.pagination.page = 1

            precio_min = (
                validar_float(
                    self.f_precio_min.get(), "Precio mínimo", permitir_cero=True
                )
                if self.f_precio_min.get().strip()
                else None
            )
            precio_max = (
                validar_float(
                    self.f_precio_max.get(), "Precio máximo", permitir_cero=True
                )
                if self.f_precio_max.get().strip()
                else None
            )
            iva = validar_iva(self.f_iva.get()) if self.f_iva.get().strip() else None

            datos = obtener_productos(
                nombre=self.f_nombre.get().strip(),
                referencia=self.f_referencia.get().strip(),
                precio_min=precio_min,
                precio_max=precio_max,
                iva=iva,
                limit=self.pagination.limit,
                offset=self.pagination.get_offset(),
            )

            self.cargar_productos(datos)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # =====================================================
    # LIMPIAR
    # =====================================================
    def limpiar_filtros(self):

        for campo in (
            self.f_nombre,
            self.f_referencia,
            self.f_precio_min,
            self.f_precio_max,
            self.f_iva,
        ):
            campo.delete(0, "end")

        self.pagination.page = 1
        self.cargar_productos()

    # =====================================================
    # CRUD
    # =====================================================
    def guardar(self):
        try:
            nombre = validar_no_vacio(self.nombre.get(), "Nombre")
            precio = validar_float(self.precio.get(), "Precio", permitir_cero=True)
            iva = validar_iva(self.iva.get())
            stock = validar_float(self.stock.get(), "Stock", permitir_cero=True)

            crear_producto(
                nombre=nombre,
                precio=precio,
                iva=iva,
                referencia=self.referencia.get().strip() or None,
                ean=self.ean.get().strip() or None,
                stock_inicial=stock,
                control_stock=1 if self.control_stock_var.get() else 0,
            )

            self.pagination.page = 1
            messagebox.showinfo("Correcto", "Producto creado")
            self.cargar_productos()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def actualizar(self):

        if not self.producto_id:
            return

        try:
            nombre = validar_no_vacio(self.nombre.get(), "Nombre")
            precio = validar_float(self.precio.get(), "Precio", permitir_cero=True)
            iva = validar_iva(self.iva.get())

            actualizar_producto(
                producto_id=self.producto_id,
                nombre=nombre,
                precio=precio,
                iva=iva,
                referencia=self.referencia.get().strip() or None,
                ean=self.ean.get().strip() or None,
                control_stock=1 if self.control_stock_var.get() else 0,
            )

            producto_id_actual = self.producto_id
            self.cargar_productos()
            self.after(100, lambda: self._reseleccionar_producto(producto_id_actual))

            messagebox.showinfo("Correcto", "Producto actualizado")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def eliminar(self):

        if not self.producto_id:
            return

        dialog = ctk.CTkInputDialog(
            title="Confirmar acción", text="Escribe DESACTIVAR para confirmar"
        )

        confirmacion = dialog.get_input()
        if confirmacion != "DESACTIVAR":
            return

        try:
            borrar_producto(self.producto_id)
            self.pagination.page = 1
            messagebox.showinfo("Correcto", "Producto desactivado")
            self.cargar_productos()

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # =====================================================
    # STOCK
    # =====================================================
    def _ajustar_stock_dialog(self, tipo):

        if not self.producto_id:
            messagebox.showwarning("Atención", "Selecciona un producto")
            return

        dialog = ctk.CTkInputDialog(title="Ajustar stock", text="Cantidad:")

        valor = dialog.get_input()
        if valor is None or valor == "":
            return

        try:
            cantidad = validar_float(valor, "Cantidad", permitir_cero=True)

            if cantidad <= 0:
                raise Exception("La cantidad debe ser mayor que 0.")

            if tipo == "SALIDA":
                cantidad = -abs(cantidad)
            else:
                cantidad = abs(cantidad)

            producto_id_actual = self.producto_id

            ajustar_stock(
                producto_id=producto_id_actual,
                cantidad=cantidad,
                tipo=tipo,
                detalle="Ajuste manual",
            )

            self.productos = obtener_productos(
                nombre=self.f_nombre.get().strip(),
                referencia=self.f_referencia.get().strip(),
                precio_min=(
                    validar_float(
                        self.f_precio_min.get(), "Precio mínimo", permitir_cero=True
                    )
                    if self.f_precio_min.get().strip()
                    else None
                ),
                precio_max=(
                    validar_float(
                        self.f_precio_max.get(), "Precio máximo", permitir_cero=True
                    )
                    if self.f_precio_max.get().strip()
                    else None
                ),
                iva=validar_iva(self.f_iva.get()) if self.f_iva.get().strip() else None,
                limit=self.pagination.limit,
                offset=self.pagination.get_offset(),
            )
            self._refrescar_solo_lista()
            self.after(100, lambda: self._reseleccionar_producto(producto_id_actual))

            messagebox.showinfo("Correcto", "Stock actualizado correctamente.")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # =====================================================
    # REFRESCAR
    # =====================================================
    def _refrescar_solo_lista(self):

        for w in self.lista_productos.winfo_children():
            w.destroy()

        for producto in self.productos:

            if self.modo_vista == "TARJETAS":
                self._crear_card(producto)
            else:
                self._crear_tabla_productos()
                break

    # =====================================================
    # RESELECCIONAR
    # =====================================================
    def _reseleccionar_producto(self, producto_id):

        for producto in self.productos:
            pid, *_ = self._normalizar(producto)
            if pid == producto_id:
                widget = self._buscar_widget_por_id(producto_id)
                self.seleccionar(producto_id, widget, producto)
                return

    # =====================================================
    # LIMPIAR FORM
    # =====================================================
    def limpiar_form(self):

        self.producto_id = None

        for campo in (
            self.referencia,
            self.ean,
            self.nombre,
            self.precio,
            self.iva,
            self.stock,
        ):
            campo.delete(0, "end")

        self.iva.insert(0, "21")
        self.stock.insert(0, "0")
        self.control_stock_var.set(True)

        for w in self.movimientos_frame.winfo_children():
            w.destroy()

        self._estado_nuevo()

    # =====================================================
    # PAGINACIÓN
    # =====================================================
    def on_pagination_change(self, page, limit):
        self.cargar_productos()
