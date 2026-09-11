import customtkinter as ctk
from tkinter import messagebox

from app.services.clientes_service import (
    obtener_clientes,
    crear_cliente,
    actualizar_cliente,
    borrar_cliente,
)

from app.utils.validators import (
    validar_no_vacio,
    validar_iban,
)

from app.ui.components.pagination import Pagination
from app.ui.components.split_view import SplitView


class ClientesView(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.cliente_id = None
        self.clientes = []
        self.card_seleccionada = None
        self.modo_vista = "TARJETAS"

        # =========================
        # HEADER
        # =========================
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(25, 15))

        ctk.CTkLabel(
            header,
            text="Clientes",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(side="left")

        self.btn_vista_tarjetas = ctk.CTkButton(
            header,
            text="Tarjetas",
            width=110,
            fg_color="#1f6aa5",
            hover_color="#195a8a",
            command=lambda: self.cambiar_vista("TARJETAS"),
        )
        self.btn_vista_tarjetas.pack(side="left", padx=10)

        self.btn_vista_tabla = ctk.CTkButton(
            header,
            text="Tabla",
            width=110,
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=lambda: self.cambiar_vista("TABLA"),
        )
        self.btn_vista_tabla.pack(side="left")

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
        filtros.pack(fill="x", padx=25, pady=(0, 20))

        self.f_nombre = ctk.CTkEntry(
            filtros, placeholder_text="Buscar por nombre...", width=180
        )
        self.f_email = ctk.CTkEntry(
            filtros, placeholder_text="Buscar por email...", width=180
        )
        self.f_telefono = ctk.CTkEntry(
            filtros, placeholder_text="Buscar por teléfono...", width=160
        )
        self.f_dni = ctk.CTkEntry(
            filtros, placeholder_text="Buscar por DNI/CIF...", width=160
        )

        self.f_nombre.grid(row=0, column=0, padx=8, pady=12)
        self.f_email.grid(row=0, column=1, padx=8, pady=12)
        self.f_telefono.grid(row=0, column=2, padx=8, pady=12)
        self.f_dni.grid(row=0, column=3, padx=8, pady=12)

        ctk.CTkButton(filtros, text="Buscar", width=110, command=self.buscar).grid(
            row=0, column=4, padx=(15, 5)
        )

        ctk.CTkButton(
            filtros, text="Limpiar", width=110, command=self.limpiar_filtros
        ).grid(row=0, column=5, padx=5)

        filtros.grid_columnconfigure(6, weight=1)

        # =========================
        # PAGINACIÓN — se empaqueta ANTES del cuerpo
        # para que expand=True del cuerpo no la oculte
        # =========================
        self.pagination = Pagination(self, on_change=self.on_pagination_change)
        self.pagination.pack(fill="x", padx=25, pady=(0, 10))

        # =========================
        # CUERPO
        # =========================
        self.cuerpo = SplitView(
            self,
            initial_left_width=460,
            left_minsize=300,
            right_minsize=300
        )
        self.cuerpo.pack(fill="both", expand=True, padx=25, pady=(0, 20))

        self.lista_clientes = ctk.CTkScrollableFrame(
            self.cuerpo.left_frame,
            corner_radius=15,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        self.lista_clientes.pack(fill="both", expand=True, pady=5)

        form = ctk.CTkScrollableFrame(
            self.cuerpo.right_frame,
            corner_radius=15,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        form.pack(fill="both", expand=True, pady=5)

        form.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            form,
            text="Datos del cliente",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w", padx=25, pady=(25, 20))

        self.nombre = self._campo(form, "Nombre completo")
        self.dni = self._campo(form, "DNI / CIF")
        self.email = self._campo(form, "Email")
        self.telefono = self._campo(form, "Teléfono")
        self.direccion = self._campo(form, "Dirección")
        self.codigo_postal = self._campo(form, "Código postal")
        self.poblacion = self._campo(form, "Población")
        self.provincia = self._campo(form, "Provincia")
        self.pais = self._campo(form, "País")
        self.iban = self._campo(form, "IBAN (domiciliación)")

        botones = ctk.CTkFrame(form, fg_color="transparent")
        botones.pack(pady=25)

        self.btn_guardar = ctk.CTkButton(
            botones, text="Guardar", width=130, command=self.guardar
        )
        self.btn_guardar.grid(row=0, column=0, padx=10)

        self.btn_actualizar = ctk.CTkButton(
            botones, text="Actualizar", width=130, command=self.actualizar
        )
        self.btn_actualizar.grid(row=0, column=1, padx=10)
        self.btn_actualizar.configure(state="disabled")

        self.btn_eliminar = ctk.CTkButton(
            botones,
            text="Eliminar",
            width=130,
            fg_color="#c0392b",
            hover_color="#992d22",
            command=self.eliminar,
        )
        self.btn_eliminar.grid(row=0, column=2, padx=10)
        self.btn_eliminar.configure(state="disabled")

        self.mensaje = ctk.CTkLabel(form, text="", text_color="#e74c3c")
        self.mensaje.pack(pady=(5, 15))

        self.cargar_clientes()

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
            self.cuerpo.set_left_width(460)
        else:
            self.btn_vista_tabla.configure(fg_color="#1f6aa5")
            self.btn_vista_tarjetas.configure(fg_color="#3a3a3a")
            self.cuerpo.set_left_width(520)

        self.cargar_clientes(self.clientes)

    # =========================
    # CAMPO
    # =========================
    def _campo(self, parent, texto):
        ctk.CTkLabel(
            parent,
            text=texto,
            text_color="#aaaaaa",
            font=ctk.CTkFont(size=13),
        ).pack(anchor="w", padx=25)

        entry = ctk.CTkEntry(parent, height=38)
        entry.pack(fill="x", padx=25, pady=(4, 14))
        return entry

    # =========================
    # CARGAR CLIENTES
    # =========================
    def cargar_clientes(self, datos=None):

        for w in self.lista_clientes.winfo_children():
            w.destroy()

        self.card_seleccionada = None
        self.cliente_id = None
        self.btn_guardar.configure(state="normal")
        self.btn_actualizar.configure(state="disabled")
        self.btn_eliminar.configure(state="disabled")

        if datos is not None:
            self.clientes = datos
        else:
            self.clientes = obtener_clientes(
                nombre=self.f_nombre.get(),
                email=self.f_email.get(),
                telefono=self.f_telefono.get(),
                dni=self.f_dni.get(),
                limit=self.pagination.limit,
                offset=self.pagination.get_offset(),
            )

        if self.modo_vista == "TARJETAS":
            for c in self.clientes:
                self._crear_card_cliente(c)
        else:
            self._crear_tabla_clientes()

        self.pagination.lbl_page.configure(text=f"Página {self.pagination.page}")

    # =========================
    # TARJETAS
    # =========================
    def _crear_card_cliente(self, cliente):

        (
            cid,
            nombre,
            dni,
            email,
            telefono,
            direccion,
            codigo_postal,
            poblacion,
            provincia,
            pais,
            iban,
        ) = cliente

        card = ctk.CTkFrame(
            self.lista_clientes,
            corner_radius=14,
            fg_color="#343434",
            border_width=1,
            border_color="#3a3a3a",
            height=130,
        )
        card.pack(fill="x", pady=10, padx=15)
        card.pack_propagate(False)

        card._cliente_id = cid

        ctk.CTkLabel(
            card,
            text=nombre,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=15, pady=(12, 4))

        linea_info = []
        if dni:
            linea_info.append(f"DNI: {dni}")
        if telefono:
            linea_info.append(f"Tel: {telefono}")

        if linea_info:
            ctk.CTkLabel(
                card,
                text="  |  ".join(linea_info),
                text_color="#bbbbbb",
            ).pack(anchor="w", padx=15)

        if email:
            ctk.CTkLabel(
                card,
                text=email,
                text_color="#9e9e9e",
            ).pack(anchor="w", padx=15)

        direccion_linea = []
        if direccion:
            direccion_linea.append(direccion)
        cp_pob = " ".join(x for x in [codigo_postal or "", poblacion or ""] if x)
        if cp_pob:
            direccion_linea.append(cp_pob)
        prov_pais = " - ".join(x for x in [provincia or "", pais or ""] if x)
        if prov_pais:
            direccion_linea.append(prov_pais)

        if direccion_linea:
            ctk.CTkLabel(
                card,
                text=" | ".join(direccion_linea),
                text_color="#8f8f8f",
            ).pack(anchor="w", padx=15)

        if iban:
            ctk.CTkLabel(
                card,
                text=f"IBAN: {iban}",
                text_color="#7f8c8d",
            ).pack(anchor="w", padx=15, pady=(0, 8))

        card.bind(
            "<Button-1>",
            lambda e, cid=cid, card=card, c=cliente: self.seleccionar_cliente(
                cid, card, c
            ),
        )

        for w in card.winfo_children():
            w.bind(
                "<Button-1>",
                lambda e, cid=cid, card=card, c=cliente: self.seleccionar_cliente(
                    cid, card, c
                ),
            )

    # =========================
    # TABLA
    # =========================
    def _crear_tabla_clientes(self):

        tabla = ctk.CTkFrame(self.lista_clientes)
        tabla.pack(fill="both", expand=True, padx=10, pady=10)

        columnas = ["Nombre", "DNI", "Email", "Teléfono"]

        header = ctk.CTkFrame(tabla)
        header.pack(fill="x")

        for i, col in enumerate(columnas):
            header.grid_columnconfigure(i, weight=1)

            ctk.CTkLabel(
                header,
                text=col,
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=i, padx=10, pady=10, sticky="ew")

        for cliente in self.clientes:

            (
                cid,
                nombre,
                dni,
                email,
                telefono,
                direccion,
                codigo_postal,
                poblacion,
                provincia,
                pais,
                iban,
            ) = cliente

            fila = ctk.CTkFrame(tabla, cursor="hand2")
            fila.pack(fill="x", pady=2)

            fila._cliente_id = cid

            valores = [
                nombre,
                dni or "",
                email or "",
                telefono or "",
            ]

            for i, val in enumerate(valores):
                lbl = ctk.CTkLabel(fila, text=val)
                lbl.grid(row=0, column=i, padx=10, pady=8, sticky="ew")
                fila.grid_columnconfigure(i, weight=1)

                lbl.bind(
                    "<Button-1>",
                    lambda e, cid=cid: self.seleccionar_cliente_por_id(cid),
                )

            fila.bind(
                "<Button-1>",
                lambda e, cid=cid: self.seleccionar_cliente_por_id(cid),
            )

    # =========================
    # SELECCIÓN
    # =========================
    def seleccionar_cliente(self, cliente_id, card, cliente):

        if self.card_seleccionada:
            try:
                self.card_seleccionada.configure(fg_color="#343434")
            except Exception:
                pass

        if card is not None:
            self.card_seleccionada = card
            card.configure(fg_color="#1f6aa5")
        else:
            self.card_seleccionada = None

        self.cliente_id = cliente_id

        self.btn_guardar.configure(state="disabled")
        self.btn_actualizar.configure(state="normal")
        self.btn_eliminar.configure(state="normal")

        (
            _,
            nombre,
            dni,
            email,
            telefono,
            direccion,
            codigo_postal,
            poblacion,
            provincia,
            pais,
            iban,
        ) = cliente

        self.nombre.delete(0, "end")
        self.nombre.insert(0, nombre)

        self.dni.delete(0, "end")
        self.dni.insert(0, dni or "")

        self.email.delete(0, "end")
        self.email.insert(0, email or "")

        self.telefono.delete(0, "end")
        self.telefono.insert(0, telefono or "")

        self.direccion.delete(0, "end")
        self.direccion.insert(0, direccion or "")

        self.codigo_postal.delete(0, "end")
        self.codigo_postal.insert(0, codigo_postal or "")

        self.poblacion.delete(0, "end")
        self.poblacion.insert(0, poblacion or "")

        self.provincia.delete(0, "end")
        self.provincia.insert(0, provincia or "")

        self.pais.delete(0, "end")
        self.pais.insert(0, pais or "")

        self.iban.delete(0, "end")
        self.iban.insert(0, iban or "")

    # =========================
    # SELECCIONAR POR ID
    # =========================
    def seleccionar_cliente_por_id(self, cliente_id):
        for cliente in self.clientes:
            if cliente[0] == cliente_id:
                widget = self._buscar_widget_por_id(cliente_id)
                self.seleccionar_cliente(cliente_id, widget, cliente)
                return

    def _buscar_widget_por_id(self, cliente_id):

        def _buscar(parent):
            for w in parent.winfo_children():
                if getattr(w, "_cliente_id", None) == cliente_id:
                    return w
                resultado = _buscar(w)
                if resultado:
                    return resultado
            return None

        return _buscar(self.lista_clientes)

    # =========================
    # FILTROS
    # =========================
    def buscar(self):

        self.pagination.page = 1

        datos = obtener_clientes(
            nombre=self.f_nombre.get(),
            email=self.f_email.get(),
            telefono=self.f_telefono.get(),
            dni=self.f_dni.get(),
            limit=self.pagination.limit,
            offset=self.pagination.get_offset(),
        )

        self.limpiar_form()
        self.cargar_clientes(datos)

    def limpiar_filtros(self):

        for f in (self.f_nombre, self.f_email, self.f_telefono, self.f_dni):
            f.delete(0, "end")

        self.pagination.page = 1
        self.limpiar_form()
        self.cargar_clientes()

    # =========================
    # CRUD
    # =========================
    def guardar(self):

        try:
            nombre = validar_no_vacio(self.nombre.get(), "Nombre completo")
            iban = validar_iban(self.iban.get()) if self.iban.get() else None

            crear_cliente(
                nombre,
                self.dni.get() or None,
                self.email.get() or None,
                self.telefono.get() or None,
                self.direccion.get() or None,
                self.codigo_postal.get() or None,
                self.poblacion.get() or None,
                self.provincia.get() or None,
                self.pais.get() or None,
                iban,
            )

            self.limpiar_form()
            self.cargar_clientes()
            self.mensaje.configure(
                text="Cliente creado correctamente.", text_color="#2ecc71"
            )

        except ValueError as e:
            messagebox.showerror("Error de validación", str(e))

    def actualizar(self):

        if not self.cliente_id:
            return

        try:
            nombre = validar_no_vacio(self.nombre.get(), "Nombre completo")
            iban = validar_iban(self.iban.get()) if self.iban.get() else None

            actualizar_cliente(
                self.cliente_id,
                nombre,
                self.dni.get() or None,
                self.email.get() or None,
                self.telefono.get() or None,
                self.direccion.get() or None,
                self.codigo_postal.get() or None,
                self.poblacion.get() or None,
                self.provincia.get() or None,
                self.pais.get() or None,
                iban,
            )

            self.limpiar_form()
            self.cargar_clientes()
            self.mensaje.configure(
                text="Cliente actualizado correctamente.", text_color="#2ecc71"
            )

        except ValueError as e:
            messagebox.showerror("Error de validación", str(e))

    def eliminar(self):

        if not self.cliente_id:
            return

        if not messagebox.askyesno("Confirmar", "¿Desactivar este cliente?"):
            return

        borrar_cliente(self.cliente_id)
        self.limpiar_form()
        self.cargar_clientes()
        self.mensaje.configure(
            text="Cliente desactivado correctamente.", text_color="#2ecc71"
        )

    def limpiar_form(self):

        self.cliente_id = None
        self.card_seleccionada = None
        self.btn_guardar.configure(state="normal")
        self.btn_actualizar.configure(state="disabled")
        self.btn_eliminar.configure(state="disabled")
        self.mensaje.configure(text="")

        for campo in (
            self.nombre,
            self.dni,
            self.email,
            self.telefono,
            self.direccion,
            self.codigo_postal,
            self.poblacion,
            self.provincia,
            self.pais,
            self.iban,
        ):
            campo.delete(0, "end")

    # =========================
    # PAGINACIÓN
    # =========================
    def on_pagination_change(self, page, limit):
        self.limpiar_form()
        self.cargar_clientes()
