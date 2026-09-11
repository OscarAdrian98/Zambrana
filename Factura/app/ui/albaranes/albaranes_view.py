import customtkinter as ctk
from tkinter import messagebox
import os

from app.utils.validators import validar_fecha

from app.services.albaranes_service import (
    obtener_albaranes,
    obtener_lineas_albaran,
    borrar_linea,
    borrar_albaran,
)

from app.services.facturas_service import convertir_albaran_a_factura
from app.services.pdf_service import generar_pdf_albaran

from app.ui.albaranes.albaranes_lista import AlbaranesLista
from app.ui.albaranes.albaranes_detalle import AlbaranesDetalle
from app.ui.albaranes.albaranes_dialog_crear import AlbaranCrearDialog
from app.ui.albaranes.albaranes_dialogs import (
    AlbaranLineaDialog,
    AlbaranLineaEditarDialog,
)
from app.ui.components.pagination import Pagination
from app.ui.components.split_view import SplitView


class AlbaranesView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.pack(fill="both", expand=True)

        # =========================
        # ESTADO
        # =========================
        self.albaranes = []
        self.albaran_id = None
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
            text="Albaranes",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left", padx=(0, 20))

        # =========================
        # BOTONES MODO
        # =========================
        self.btn_tarjetas = ctk.CTkButton(
            izquierda,
            text="Tarjetas",
            width=110,
            fg_color="#1f6aa5",
            command=lambda: self.cambiar_modo("TARJETAS"),
        )
        self.btn_tarjetas.pack(side="left", padx=5)

        self.btn_tabla = ctk.CTkButton(
            izquierda,
            text="Tabla",
            width=110,
            fg_color="#3a3a3a",
            command=lambda: self.cambiar_modo("TABLA"),
        )
        self.btn_tabla.pack(side="left", padx=5)

        # =========================
        # BOTÓN NUEVO
        # =========================
        ctk.CTkButton(
            header,
            text="+ Nuevo albarán",
            width=170,
            height=36,
            fg_color="#1f6aa5",
            command=self.nuevo_albaran,
        ).pack(side="right")

        # =========================
        # FILTROS
        # =========================
        filtros = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=10)
        filtros.pack(fill="x", padx=25, pady=(0, 10))

        self.filtro_numero = ctk.CTkEntry(filtros, placeholder_text="Número")
        self.filtro_numero.pack(side="left", padx=6, pady=8)

        self.filtro_cliente = ctk.CTkEntry(filtros, placeholder_text="Cliente")
        self.filtro_cliente.pack(side="left", padx=6)

        self.filtro_cliente_id = ctk.CTkEntry(
            filtros, placeholder_text="ID Cliente", width=110
        )
        self.filtro_cliente_id.pack(side="left", padx=6)

        self.filtro_desde = ctk.CTkEntry(filtros, placeholder_text="Desde (dd/mm/yyyy)")
        self.filtro_desde.pack(side="left", padx=6)

        self.filtro_hasta = ctk.CTkEntry(filtros, placeholder_text="Hasta (dd/mm/yyyy)")
        self.filtro_hasta.pack(side="left", padx=6)

        ctk.CTkButton(
            filtros,
            text="Buscar",
            width=120,
            command=self.buscar,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            filtros,
            text="Limpiar",
            width=120,
            fg_color="#4a4a4a",
            command=self.limpiar_filtros,
        ).pack(side="left", padx=4)

        # =========================
        # PAGINACIÓN — se empaqueta ANTES del contenedor
        # para que expand=True del contenedor no la oculte
        # =========================
        self.pagination = Pagination(self, on_change=self.on_pagination_change)
        self.pagination.pack(fill="x", padx=25, pady=(0, 10))

        # =========================
        # CONTENEDOR PRINCIPAL (SplitView)
        # =========================
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True)

        self.cuerpo = SplitView(
            contenedor,
            view_name="albaranes",
            initial_left_width=460,
            left_minsize=300,
            right_minsize=300
        )
        self.cuerpo.pack(fill="both", expand=True, padx=25, pady=(0, 20))

        # =========================
        # LISTA ALBARANES
        # =========================
        self.lista = AlbaranesLista(
            self.cuerpo.left_frame,
            on_select=self.seleccionar_albaran,
        )

        self.lista.pack(
            fill="both",
            expand=True,
            pady=10,
        )

        # =========================
        # PANEL DERECHO
        # =========================
        panel_derecha = ctk.CTkFrame(self.cuerpo.right_frame, fg_color="transparent")
        panel_derecha.pack(fill="both", expand=True)

        panel_derecha.grid_rowconfigure(0, weight=1)
        panel_derecha.grid_columnconfigure(0, weight=1)

        # =========================
        # DETALLE
        # =========================
        self.detalle = AlbaranesDetalle(
            panel_derecha,
            on_facturar=self.convertir_factura,
            on_borrar_linea=self.eliminar_linea,
            on_borrar_albaran=self.eliminar_albaran,
            on_pdf=self.generar_pdf,
            on_nueva_linea=self.nueva_linea,
            on_editar_linea=self.editar_linea,
        )

        self.detalle.grid(row=0, column=0, sticky="nsew", pady=10)

        # =========================
        # CARGA INICIAL
        # =========================
        self.cargar_albaranes()

    # =========================================================
    # BUSCAR
    # =========================================================
    def buscar(self):

        self.pagination.page = 1

        numero = self.filtro_numero.get().strip() or None
        cliente = self.filtro_cliente.get().strip() or None
        cliente_id = self.filtro_cliente_id.get().strip() or None

        try:
            desde = (
                validar_fecha(self.filtro_desde.get().strip())
                if self.filtro_desde.get().strip()
                else None
            )
            hasta = (
                validar_fecha(self.filtro_hasta.get().strip())
                if self.filtro_hasta.get().strip()
                else None
            )
        except ValueError as e:
            messagebox.showerror("Fecha inválida", str(e))
            return

        try:
            self.albaranes = obtener_albaranes(
                numero=numero,
                cliente=cliente,
                cliente_id=cliente_id,
                fecha_desde=desde,
                fecha_hasta=hasta,
                limit=self.pagination.limit,
                offset=self.pagination.get_offset(),
            )

            self.lista.render(self.albaranes)
            self.detalle.limpiar()
            self.pagination.lbl_page.configure(text=f"Página {self.pagination.page}")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # =========================================================
    # LIMPIAR FILTROS
    # =========================================================
    def limpiar_filtros(self):

        self.filtro_numero.delete(0, "end")
        self.filtro_cliente.delete(0, "end")
        self.filtro_cliente_id.delete(0, "end")
        self.filtro_desde.delete(0, "end")
        self.filtro_hasta.delete(0, "end")

        self.pagination.page = 1
        self.cargar_albaranes()

    # =========================================================
    # CAMBIAR MODO
    # =========================================================
    def cambiar_modo(self, modo):

        if self.modo_vista == modo:
            return

        self.modo_vista = modo
        self.lista.set_modo(modo)

        if modo == "TARJETAS":
            self.btn_tarjetas.configure(fg_color="#1f6aa5")
            self.btn_tabla.configure(fg_color="#3a3a3a")
            self.cuerpo.set_mode_width("TARJETAS", 460)
        else:
            self.btn_tabla.configure(fg_color="#1f6aa5")
            self.btn_tarjetas.configure(fg_color="#3a3a3a")
            self.cuerpo.set_mode_width("TABLA", 520)

        self.lista.render(self.albaranes)

    # =========================================================
    # CREAR NUEVO ALBARÁN
    # =========================================================
    def nuevo_albaran(self):

        def on_created(albaran_id):
            self.cargar_albaranes()
            self.after(
                200,
                lambda: self.lista.seleccionar_por_id(albaran_id),
            )

        AlbaranCrearDialog(self, on_created)

    # =========================================================
    # CARGAR ALBARANES
    # =========================================================
    def cargar_albaranes(self, datos=None):

        if datos is not None:
            self.albaranes = datos
        else:
            numero = self.filtro_numero.get().strip() or None
            cliente = self.filtro_cliente.get().strip() or None
            cliente_id = self.filtro_cliente_id.get().strip() or None

            desde = None
            hasta = None

            try:
                if self.filtro_desde.get().strip():
                    desde = validar_fecha(self.filtro_desde.get().strip())

                if self.filtro_hasta.get().strip():
                    hasta = validar_fecha(self.filtro_hasta.get().strip())
            except:
                pass

            self.albaranes = obtener_albaranes(
                numero=numero,
                cliente=cliente,
                cliente_id=cliente_id,
                fecha_desde=desde,
                fecha_hasta=hasta,
                limit=self.pagination.limit,
                offset=self.pagination.get_offset(),
            )

        self.lista.render(self.albaranes)
        self.detalle.limpiar()
        self.pagination.lbl_page.configure(text=f"Página {self.pagination.page}")

    # =========================================================
    # SELECCIONAR ALBARÁN
    # =========================================================
    def seleccionar_albaran(self, albaran_id):

        self.albaran_id = albaran_id

        if hasattr(self, "_debounce_timer") and self._debounce_timer is not None:
            self.after_cancel(self._debounce_timer)

        def _cargar():
            albaran = next(
                (a for a in self.albaranes if a[0] == self.albaran_id),
                None,
            )
            if not albaran:
                return

            self.detalle.cargar_albaran(self.albaran_id, albaran)
            lineas = obtener_lineas_albaran(self.albaran_id)
            self.detalle.render_lineas(lineas)

        self._debounce_timer = self.after(150, _cargar)

    # =========================================================
    # BORRAR LINEA
    # =========================================================
    def eliminar_linea(self, linea_id):

        if not messagebox.askyesno(
            "Confirmar",
            "¿Eliminar esta línea?",
        ):
            return

        borrar_linea(linea_id)
        self.refrescar_lineas()

    # =========================================================
    # BORRAR ALBARÁN
    # =========================================================
    def eliminar_albaran(self, albaran_id):

        if not messagebox.askyesno(
            "Confirmar",
            "¿Eliminar este albarán?",
        ):
            return

        if not borrar_albaran(albaran_id):
            messagebox.showwarning(
                "Bloqueado",
                "Este albarán no se puede eliminar.",
            )
            return

        self.albaran_id = None
        self.cargar_albaranes()

    # =========================================================
    # REFRESCAR LINEAS
    # =========================================================
    def refrescar_lineas(self):

        self.cargar_albaranes()

        if self.albaran_id:
            self.after(50, lambda: self.seleccionar_albaran(self.albaran_id))

    # =========================================================
    # CONVERTIR EN FACTURA
    # =========================================================
    def convertir_factura(self, albaran_id):

        if not messagebox.askyesno(
            "Confirmar",
            "¿Convertir este albarán en factura?",
        ):
            return

        try:
            convertir_albaran_a_factura(albaran_id)

        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        messagebox.showinfo(
            "Correcto",
            "Factura creada correctamente.",
        )

        self.albaran_id = None
        self.cargar_albaranes()

    # =========================================================
    # GENERAR PDF
    # =========================================================
    def generar_pdf(self, albaran_id):

        try:
            archivo = generar_pdf_albaran(albaran_id)

            if archivo and os.path.exists(archivo):
                os.startfile(archivo)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # =========================================================
    # NUEVA LINEA
    # =========================================================
    def nueva_linea(self, albaran_id):

        def on_created():
            self.refrescar_lineas()

        AlbaranLineaDialog(self, albaran_id, on_created)

    # =========================================================
    # EDITAR LINEA
    # =========================================================
    def editar_linea(self, linea_id):

        lineas = obtener_lineas_albaran(self.albaran_id)
        linea = next((l for l in lineas if l[0] == linea_id), None)

        if not linea:
            return

        def on_saved():
            self.refrescar_lineas()

        AlbaranLineaEditarDialog(self, linea, on_saved)

    # =========================================================
    # PAGINACIÓN
    # =========================================================
    def on_pagination_change(self, page, limit):
        self.cargar_albaranes()
