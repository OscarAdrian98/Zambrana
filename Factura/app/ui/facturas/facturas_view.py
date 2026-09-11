import customtkinter as ctk
from tkinter import messagebox

from app.services.facturas_service import obtener_facturas
from app.utils.validators import validar_fecha

# Módulos UI
from app.ui.facturas.facturas_lista import FacturasLista
from app.ui.facturas.facturas_detalle import FacturasDetalle
from app.ui.facturas.facturas_dialogs import (
    NuevaFacturaDialog,
    RectificarFacturaDialog,
)
from app.ui.components.pagination import Pagination
from app.ui.components.split_view import SplitView


class FacturasView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.pack(fill="both", expand=True)

        # =========================
        # ESTADO
        # =========================
        self.facturas = []
        self.factura_id = None
        self.modo_vista = "TARJETAS"

        # =========================
        # HEADER SUPERIOR
        # =========================
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(20, 10))

        izquierda = ctk.CTkFrame(header, fg_color="transparent")
        izquierda.pack(side="left")

        ctk.CTkLabel(
            izquierda,
            text="Facturas",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left", padx=(0, 20))

        # BOTONES MODO
        self.btn_vista_tarjetas = ctk.CTkButton(
            izquierda,
            text="Tarjetas",
            width=110,
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=lambda: self.cambiar_vista("TARJETAS"),
        )
        self.btn_vista_tarjetas.pack(side="left", padx=5)

        self.btn_vista_tabla = ctk.CTkButton(
            izquierda,
            text="Tabla",
            width=110,
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=lambda: self.cambiar_vista("TABLA"),
        )
        self.btn_vista_tabla.pack(side="left", padx=5)

        # BOTON NUEVA FACTURA
        ctk.CTkButton(
            header,
            text="+ Nueva factura",
            width=170,
            height=36,
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=self.nueva_factura,
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
        filtros.pack(fill="x", padx=25, pady=10)

        for col in range(12):
            filtros.grid_columnconfigure(col, weight=0)

        filtros.grid_columnconfigure(9, weight=1)

        self.f_numero = ctk.CTkEntry(filtros, placeholder_text="Factura")
        self.f_cliente = ctk.CTkEntry(filtros, placeholder_text="Cliente")
        self.f_cliente_id = ctk.CTkEntry(
            filtros, placeholder_text="ID Cliente", width=120
        )
        self.f_desde = ctk.CTkEntry(filtros, placeholder_text="Desde (dd/mm/yyyy)")
        self.f_hasta = ctk.CTkEntry(filtros, placeholder_text="Hasta (dd/mm/yyyy)")

        self.f_estado = ctk.CTkComboBox(
            filtros,
            values=["TODAS", "PENDIENTE", "PAGADA", "VENCIDA"],
            width=160,
        )
        self.f_estado.set("TODAS")

        self.f_numero.grid(row=0, column=0, padx=8, pady=10, sticky="w")
        self.f_cliente.grid(row=0, column=1, padx=8, pady=10, sticky="w")
        self.f_cliente_id.grid(row=0, column=2, padx=8, pady=10, sticky="w")
        self.f_desde.grid(row=0, column=3, padx=8, pady=10, sticky="w")
        self.f_hasta.grid(row=0, column=4, padx=8, pady=10, sticky="w")
        self.f_estado.grid(row=0, column=5, padx=8, pady=10, sticky="w")

        ctk.CTkButton(
            filtros,
            text="Buscar",
            width=110,
            command=self.buscar,
        ).grid(row=0, column=6, padx=(15, 5), pady=10)

        ctk.CTkButton(
            filtros,
            text="Limpiar",
            width=110,
            command=self.limpiar,
        ).grid(row=0, column=7, padx=5, pady=10)

        # =========================
        # PAGINACIÓN — se empaqueta ANTES del contenedor
        # para que expand=True del contenedor no la oculte
        # =========================
        self.pagination = Pagination(self, on_change=self.on_pagination_change)
        self.pagination.pack(fill="x", padx=25, pady=(0, 10))

        # =========================
        # CUERPO (SplitView)
        # =========================
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True)

        self.cuerpo = SplitView(
            contenedor,
            view_name="facturas",
            initial_left_width=460,
            left_minsize=300,
            right_minsize=300
        )

        self.cuerpo.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=(0, 20),
        )

        # =========================
        # LISTA
        # =========================
        self.lista = FacturasLista(
            self.cuerpo.left_frame,
            on_select=self.seleccionar_factura,
        )

        self.lista.pack(
            fill="both",
            expand=True,
            pady=10,
        )

        # =========================
        # DETALLE
        # =========================
        self.detalle = FacturasDetalle(
            self.cuerpo.right_frame,
            on_rectificar=self.rectificar_factura,
            on_abrir_cliente=self.abrir_cliente,
            on_ver_facturas_cliente=self.ver_facturas_cliente,
            on_factura_actualizada=self.refrescar_factura_actual,
            on_ir_factura=self.seleccionar_factura,
        )

        self.detalle.pack(
            fill="both",
            expand=True,
            pady=10,
        )

        # =========================
        # CARGA INICIAL
        # =========================
        self.cargar_facturas()

    # =========================
    # CAMBIAR VISTA
    # =========================
    def cambiar_vista(self, modo):

        if self.modo_vista == modo:
            return

        self.modo_vista = modo

        if modo == "TARJETAS":
            self.btn_vista_tarjetas.configure(fg_color="#1f6aa5")
            self.btn_vista_tabla.configure(fg_color="#3a3a3a")
            self.cuerpo.set_mode_width("TARJETAS", 460)
        else:
            self.btn_vista_tabla.configure(fg_color="#1f6aa5")
            self.btn_vista_tarjetas.configure(fg_color="#3a3a3a")
            self.cuerpo.set_mode_width("TABLA", 520)

        self.lista.set_modo(modo)
        self.lista.render(self.facturas)

    # =========================
    # CARGAR FACTURAS
    # =========================
    def cargar_facturas(self, datos=None):

        # =========================
        # SI VIENEN DATOS EXTERNOS (ej: desde cliente)
        # =========================
        if datos is not None:
            self.facturas = datos

        else:
            # =========================
            # PAGINACIÓN
            # =========================
            offset = self.pagination.get_offset()

            # =========================
            # ESTADO
            # =========================
            estado = self.f_estado.get()
            if estado == "TODAS":
                estado = None

            # =========================
            # FECHAS
            # =========================
            fecha_desde = None
            fecha_hasta = None

            try:
                if self.f_desde.get().strip():
                    fecha_desde = validar_fecha(self.f_desde.get().strip())

                if self.f_hasta.get().strip():
                    fecha_hasta = validar_fecha(self.f_hasta.get().strip())
            except:
                # Evita romper la paginación si hay error puntual
                pass

            # =========================
            # CONSULTA
            # =========================
            self.facturas = obtener_facturas(
                numero=self.f_numero.get(),
                cliente=self.f_cliente.get(),
                cliente_id=self.f_cliente_id.get(),
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                estado=estado,
                limit=self.pagination.limit,
                offset=offset,
            )

        # =========================
        # RENDER
        # =========================
        self.lista.render(self.facturas)
        self.detalle.limpiar()

        # =========================
        # ACTUALIZAR TEXTO PAGINA
        # =========================
        self.pagination.lbl_page.configure(text=f"Página {self.pagination.page}")

    # =========================
    # SELECCION
    # =========================
    def seleccionar_factura(self, factura_id):

        self.factura_id = factura_id

        if hasattr(self, "_debounce_timer") and self._debounce_timer is not None:
            self.after_cancel(self._debounce_timer)

        def _cargar():
            factura = next((f for f in self.facturas if f[0] == self.factura_id), None)
            if not factura:
                return
            self.detalle.cargar_factura(self.factura_id, factura)

        self._debounce_timer = self.after(150, _cargar)

    # =========================
    # REFRESCAR FACTURA
    # =========================
    def refrescar_factura_actual(self, factura_id=None):

        factura_id = factura_id or self.factura_id

        # reutiliza lógica completa
        self.cargar_facturas()

        if factura_id:
            self.after(50, lambda: self.seleccionar_factura(factura_id))

    # =========================
    # NUEVA FACTURA
    # =========================
    def nueva_factura(self):

        def on_created(factura_id):
            self.cargar_facturas()
            self.after(200, lambda: self.seleccionar_factura(factura_id))

        NuevaFacturaDialog(self, on_created)

    # =========================
    # RECTIFICAR
    # =========================
    def rectificar_factura(self, factura_id):

        def on_created():
            self.cargar_facturas()

        RectificarFacturaDialog(self, factura_id, on_created)

    # =========================
    # BUSCAR
    # =========================
    def buscar(self):

        self.pagination.page = 1

        estado = self.f_estado.get()

        if estado == "TODAS":
            estado = None

        fecha_desde = None
        fecha_hasta = None

        try:
            if self.f_desde.get().strip():
                fecha_desde = validar_fecha(self.f_desde.get().strip())

            if self.f_hasta.get().strip():
                fecha_hasta = validar_fecha(self.f_hasta.get().strip())

        except ValueError as e:
            messagebox.showerror("Fecha inválida", str(e))
            return

        offset = self.pagination.get_offset()

        self.facturas = obtener_facturas(
            numero=self.f_numero.get(),
            cliente=self.f_cliente.get(),
            cliente_id=self.f_cliente_id.get(),
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            limit=self.pagination.limit,
            offset=offset,
        )

        self.lista.render(self.facturas)
        self.detalle.limpiar()

    # =========================
    # LIMPIAR
    # =========================
    def limpiar(self):

        for f in (
            self.f_numero,
            self.f_cliente,
            self.f_cliente_id,
            self.f_desde,
            self.f_hasta,
        ):
            f.delete(0, "end")

        self.f_estado.set("TODAS")

        self.pagination.page = 1

        self.cargar_facturas()

    # =========================
    # ABRIR CLIENTE
    # =========================
    def abrir_cliente(self, cliente_id):

        try:
            from app.ui.clientes_view import ClientesView

            self.master.master.mostrar_vista(ClientesView)

            clientes_view = self.master.master.current_view

            clientes_view.seleccionar_cliente_por_id(cliente_id)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # =========================
    # VER FACTURAS CLIENTE
    # =========================
    def ver_facturas_cliente(self, cliente_id):

        try:
            from app.ui.facturas.facturas_view import FacturasView

            self.master.master.mostrar_vista(FacturasView)

            facturas_view = self.master.master.current_view

            facturas_view.cargar_facturas(obtener_facturas(cliente_id=cliente_id))

            facturas_view.f_cliente_id.delete(0, "end")
            facturas_view.f_cliente_id.insert(0, str(cliente_id))

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_pagination_change(self, page, limit):
        self.cargar_facturas()
