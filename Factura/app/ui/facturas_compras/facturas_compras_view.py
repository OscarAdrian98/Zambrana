import customtkinter as ctk
from tkinter import messagebox

from app.services.facturas_compras_service import obtener_facturas_compras
from app.utils.validators import validar_fecha

from app.ui.facturas_compras.facturas_compras_lista import FacturasComprasLista
from app.ui.facturas_compras.facturas_compras_detalle import FacturasComprasDetalle
from app.ui.facturas_compras.facturas_compras_dialogs import NuevaFacturaCompraDialog
from app.ui.components.pagination import Pagination
from app.ui.components.split_view import SplitView


class FacturasComprasView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.pack(fill="both", expand=True)

        # =====================================================
        # ESTADO
        # =====================================================
        self.facturas = []
        self.factura_id = None
        self.modo_vista = "TARJETAS"

        # =====================================================
        # HEADER
        # =====================================================
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(20, 10))

        izquierda = ctk.CTkFrame(header, fg_color="transparent")
        izquierda.pack(side="left")

        ctk.CTkLabel(
            izquierda,
            text="Facturas de compra",
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

        # BOTONES DERECHA
        derecha = ctk.CTkFrame(header, fg_color="transparent")
        derecha.pack(side="right")

        ctk.CTkButton(
            derecha,
            text="+ Nueva factura",
            width=170,
            height=36,
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=self.nueva_factura,
        ).pack(side="left")

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
        filtros.pack(fill="x", padx=25, pady=10)

        for col in range(8):
            filtros.grid_columnconfigure(col, weight=0)

        filtros.grid_columnconfigure(7, weight=1)

        self.f_numero = ctk.CTkEntry(filtros, placeholder_text="Factura")
        self.f_proveedor = ctk.CTkEntry(filtros, placeholder_text="Proveedor")

        self.f_estado = ctk.CTkComboBox(
            filtros,
            values=["TODAS", "PENDIENTE", "PAGADA"],
            width=160,
        )
        self.f_estado.set("TODAS")

        self.f_desde = ctk.CTkEntry(filtros, placeholder_text="Desde (dd/mm/yyyy)")
        self.f_hasta = ctk.CTkEntry(filtros, placeholder_text="Hasta (dd/mm/yyyy)")

        self.f_numero.grid(row=0, column=0, padx=8, pady=10)
        self.f_proveedor.grid(row=0, column=1, padx=8, pady=10)
        self.f_desde.grid(row=0, column=2, padx=8, pady=10)
        self.f_hasta.grid(row=0, column=3, padx=8, pady=10)
        self.f_estado.grid(row=0, column=4, padx=8, pady=10)

        ctk.CTkButton(
            filtros,
            text="Buscar",
            width=110,
            command=self.buscar,
        ).grid(row=0, column=5, padx=(15, 5), pady=10)

        ctk.CTkButton(
            filtros,
            text="Limpiar",
            width=110,
            command=self.limpiar,
        ).grid(row=0, column=6, padx=5, pady=10)

        # =====================================================
        # PAGINACIÓN — se empaqueta ANTES del contenedor
        # para que expand=True del contenedor no la oculte
        # =====================================================
        self.pagination = Pagination(self, on_change=self.on_pagination_change)
        self.pagination.pack(fill="x", padx=25, pady=(0, 10))

        # =====================================================
        # CUERPO (SplitView)
        # =====================================================
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True)

        self.cuerpo = SplitView(
            contenedor,
            view_name="compras",
            initial_left_width=460,
            left_minsize=300,
            right_minsize=300
        )
        self.cuerpo.pack(fill="both", expand=True, padx=25, pady=(0, 20))

        # =====================================================
        # LISTA
        # =====================================================
        self.lista = FacturasComprasLista(
            self.cuerpo.left_frame,
            on_select=self.seleccionar_factura,
        )

        self.lista.pack(
            fill="both",
            expand=True,
            pady=10,
        )

        # =====================================================
        # DETALLE
        # =====================================================
        self.detalle = FacturasComprasDetalle(
            self.cuerpo.right_frame,
            on_factura_actualizada=self.refrescar_factura_actual,
        )

        self.detalle.pack(
            fill="both",
            expand=True,
            pady=10,
        )

        # =====================================================
        # CARGA INICIAL
        # =====================================================
        self.cargar_facturas()

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
            self.cuerpo.set_mode_width("TARJETAS", 460)
        else:
            self.btn_vista_tabla.configure(fg_color="#1f6aa5")
            self.btn_vista_tarjetas.configure(fg_color="#3a3a3a")
            self.cuerpo.set_mode_width("TABLA", 520)

        self.lista.set_modo(modo)
        self.lista.render(self.facturas)

    # =====================================================
    # CARGAR FACTURAS
    # =====================================================
    def cargar_facturas(self, datos=None):

        if datos is not None:
            self.facturas = datos
        else:
            offset = self.pagination.get_offset()

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
            except:
                pass

            self.facturas = obtener_facturas_compras(
                proveedor=self.f_proveedor.get(),
                numero=self.f_numero.get(),
                estado=estado,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                limit=self.pagination.limit,
                offset=offset,
            )

        self.lista.render(self.facturas)
        self.detalle.limpiar()

        self.pagination.lbl_page.configure(text=f"Página {self.pagination.page}")

    # =====================================================
    # SELECCION
    # =====================================================
    def seleccionar_factura(self, factura_id):

        self.factura_id = factura_id

        if hasattr(self, "_debounce_timer") and self._debounce_timer is not None:
            self.after_cancel(self._debounce_timer)

        def _cargar():
            self.detalle.cargar_factura(self.factura_id)

        self._debounce_timer = self.after(150, _cargar)

    # =====================================================
    # REFRESCAR FACTURA
    # =====================================================
    def refrescar_factura_actual(self, factura_id=None):

        factura_id = factura_id or self.factura_id

        self.cargar_facturas()

        if factura_id:
            self.after(50, lambda: self.seleccionar_factura(factura_id))

    # =====================================================
    # NUEVA FACTURA
    # =====================================================
    def nueva_factura(self):

        def on_created(factura_id):
            self.cargar_facturas()
            self.after(
                200,
                lambda: self.seleccionar_factura(factura_id),
            )

        NuevaFacturaCompraDialog(self, on_created)

    # =====================================================
    # BUSCAR
    # =====================================================
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

        self.facturas = obtener_facturas_compras(
            proveedor=self.f_proveedor.get(),
            numero=self.f_numero.get(),
            estado=estado,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            limit=self.pagination.limit,
            offset=offset,
        )

        self.lista.render(self.facturas)
        self.detalle.limpiar()

    # =====================================================
    # LIMPIAR
    # =====================================================
    def limpiar(self):

        for f in (
            self.f_numero,
            self.f_proveedor,
            self.f_desde,
            self.f_hasta,
        ):
            f.delete(0, "end")

        self.f_estado.set("TODAS")
        self.pagination.page = 1

        self.cargar_facturas()

    # =====================================================
    # PAGINACIÓN
    # =====================================================
    def on_pagination_change(self, page, limit):
        self.cargar_facturas()
