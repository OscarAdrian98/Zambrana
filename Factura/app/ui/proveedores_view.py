import customtkinter as ctk
from tkinter import messagebox

from app.services.proveedores_service import (
    obtener_proveedores,
    crear_proveedor,
    actualizar_proveedor,
    borrar_proveedor,
)

from app.utils.validators import (
    validar_no_vacio,
    validar_iban,
)

from app.ui.components.pagination import Pagination
from app.ui.components.split_view import SplitView


class ProveedoresView(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.proveedor_id = None
        self.proveedores = []
        self.card_seleccionada = None
        self.modo_vista = "TARJETAS"

        self.btn_guardar = None
        self.btn_actualizar = None
        self.btn_eliminar = None

        # =========================
        # HEADER
        # =========================
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text="Proveedores",
            font=ctk.CTkFont(size=24, weight="bold"),
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
        filtros.pack(fill="x", padx=25, pady=(0, 15))

        self.f_nombre = ctk.CTkEntry(filtros, placeholder_text="Buscar por nombre")
        self.f_cif = ctk.CTkEntry(filtros, placeholder_text="Buscar por CIF")

        self.f_nombre.grid(row=0, column=0, padx=8, pady=12)
        self.f_cif.grid(row=0, column=1, padx=8, pady=12)

        ctk.CTkButton(filtros, text="Buscar", width=110, command=self.buscar).grid(
            row=0, column=2, padx=(15, 5)
        )

        ctk.CTkButton(
            filtros, text="Limpiar", width=110, command=self.limpiar_filtros
        ).grid(row=0, column=3, padx=5)

        filtros.grid_columnconfigure(4, weight=1)

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

        self.lista_proveedores = ctk.CTkScrollableFrame(
            self.cuerpo.left_frame,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        self.lista_proveedores.pack(fill="both", expand=True, pady=5)

        form = ctk.CTkScrollableFrame(
            self.cuerpo.right_frame,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        form.pack(fill="both", expand=True, pady=5)

        ctk.CTkLabel(
            form,
            text="Datos del proveedor",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(20, 10))

        self._campo(form, "Nombre", "nombre")
        self._campo(form, "CIF", "cif")
        self._campo(form, "Email", "email")
        self._campo(form, "Teléfono", "telefono")
        self._campo(form, "Dirección", "direccion")
        self._campo(form, "Código postal", "codigo_postal")
        self._campo(form, "Población", "poblacion")
        self._campo(form, "Provincia", "provincia")
        self._campo(form, "País", "pais")
        self._campo(form, "IBAN", "iban")

        botones = ctk.CTkFrame(form, fg_color="transparent")
        botones.pack(pady=22)

        self.btn_guardar = ctk.CTkButton(
            botones,
            text="Guardar",
            width=140,
            command=self.guardar,
        )
        self.btn_guardar.grid(row=0, column=0, padx=8)

        self.btn_actualizar = ctk.CTkButton(
            botones,
            text="Actualizar",
            width=140,
            command=self.actualizar,
        )
        self.btn_actualizar.grid(row=0, column=1, padx=8)

        self.btn_eliminar = ctk.CTkButton(
            botones,
            text="Eliminar",
            width=140,
            fg_color="#c0392b",
            hover_color="#992d22",
            command=self.eliminar,
        )
        self.btn_eliminar.grid(row=0, column=2, padx=8)

        self._set_modo_creacion()

        self.cargar_proveedores()

    # ==================================================
    # CAMBIAR VISTA
    # ==================================================
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

        self.cargar_proveedores(self.proveedores)

    # ==================================================
    # HELPERS UI
    # ==================================================
    def _campo(self, parent, label, attr_name):
        ctk.CTkLabel(
            parent,
            text=label,
            text_color="#bdbdbd",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=20, pady=(10, 4))

        entry = ctk.CTkEntry(parent, placeholder_text=label)
        entry.pack(fill="x", padx=20, pady=(0, 6))
        setattr(self, attr_name, entry)

    def _set_modo_creacion(self):
        self.btn_guardar.configure(state="normal")
        self.btn_actualizar.configure(state="disabled")
        self.btn_eliminar.configure(state="disabled")

    def _set_modo_edicion(self):
        self.btn_guardar.configure(state="disabled")
        self.btn_actualizar.configure(state="normal")
        self.btn_eliminar.configure(state="normal")

    def _limpiar_seleccion_visual(self):
        if self.card_seleccionada:
            try:
                self.card_seleccionada.configure(
                    fg_color="#343434",
                    border_color="#3a3a3a",
                )
            except Exception:
                pass
        self.card_seleccionada = None

    # =========================
    # CARGAR
    # =========================
    def cargar_proveedores(self, datos=None):

        for w in self.lista_proveedores.winfo_children():
            w.destroy()

        self.proveedor_id = None
        self._limpiar_seleccion_visual()

        if datos is not None:
            self.proveedores = datos
        else:
            self.proveedores = obtener_proveedores(
                nombre=self.f_nombre.get(),
                cif=self.f_cif.get(),
                limit=self.pagination.limit,
                offset=self.pagination.get_offset(),
            )

        if self.modo_vista == "TARJETAS":
            for p in self.proveedores:
                self._crear_card_proveedor(p)
        else:
            self._crear_tabla_proveedores()

        self.pagination.lbl_page.configure(text=f"Página {self.pagination.page}")

    # =========================
    # TARJETAS
    # =========================
    def _crear_card_proveedor(self, proveedor):

        (
            pid,
            nombre,
            cif,
            email,
            telefono,
            direccion,
            codigo_postal,
            poblacion,
            provincia,
            pais,
            iban,
        ) = proveedor

        card = ctk.CTkFrame(
            self.lista_proveedores,
            corner_radius=12,
            fg_color="#343434",
            border_width=1,
            border_color="#3a3a3a",
        )
        card.pack(fill="x", pady=8, padx=10)

        card._proveedor_id = pid

        ctk.CTkLabel(
            card,
            text=nombre,
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(12, 4))

        linea1 = []
        if cif:
            linea1.append(f"CIF: {cif}")
        if telefono:
            linea1.append(f"Tel: {telefono}")

        if linea1:
            ctk.CTkLabel(
                card,
                text="  |  ".join(linea1),
                text_color="#bdbdbd",
            ).pack(anchor="w", padx=14)

        if email:
            ctk.CTkLabel(
                card,
                text=email,
                text_color="#9a9a9a",
            ).pack(anchor="w", padx=14, pady=(4, 0))

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
            ).pack(anchor="w", padx=14)

        if iban:
            ctk.CTkLabel(
                card,
                text=f"IBAN: {iban}",
                text_color="#8a8a8a",
            ).pack(anchor="w", padx=14, pady=(4, 12))

        card.bind(
            "<Button-1>",
            lambda e, pid=pid, card=card, p=proveedor: self.seleccionar_proveedor(
                pid, card, p
            ),
        )

        for w in card.winfo_children():
            w.bind(
                "<Button-1>",
                lambda e, pid=pid, card=card, p=proveedor: self.seleccionar_proveedor(
                    pid, card, p
                ),
            )

    # =========================
    # TABLA
    # =========================
    def _crear_tabla_proveedores(self):

        tabla = ctk.CTkFrame(self.lista_proveedores)
        tabla.pack(fill="both", expand=True, padx=10, pady=10)

        columnas = ["Nombre", "CIF", "Email", "Teléfono"]

        header = ctk.CTkFrame(tabla)
        header.pack(fill="x")

        for i, col in enumerate(columnas):
            header.grid_columnconfigure(i, weight=1)

            ctk.CTkLabel(
                header,
                text=col,
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=i, padx=10, pady=10, sticky="ew")

        for proveedor in self.proveedores:

            (
                pid,
                nombre,
                cif,
                email,
                telefono,
                direccion,
                codigo_postal,
                poblacion,
                provincia,
                pais,
                iban,
            ) = proveedor

            fila = ctk.CTkFrame(tabla, cursor="hand2")
            fila.pack(fill="x", pady=2)

            fila._proveedor_id = pid

            valores = [
                nombre,
                cif or "",
                email or "",
                telefono or "",
            ]

            for i, val in enumerate(valores):
                lbl = ctk.CTkLabel(fila, text=val)
                lbl.grid(row=0, column=i, padx=10, pady=8, sticky="ew")
                fila.grid_columnconfigure(i, weight=1)

                lbl.bind(
                    "<Button-1>",
                    lambda e, pid=pid: self.seleccionar_proveedor_por_id(pid),
                )

            fila.bind(
                "<Button-1>",
                lambda e, pid=pid: self.seleccionar_proveedor_por_id(pid),
            )

    # =========================
    # SELECCIÓN
    # =========================
    def seleccionar_proveedor(self, proveedor_id, card, proveedor):

        if self.card_seleccionada and self.card_seleccionada != card:
            try:
                self.card_seleccionada.configure(
                    fg_color="#343434",
                    border_color="#3a3a3a",
                )
            except Exception:
                pass

        if card is not None:
            self.card_seleccionada = card
            card.configure(
                fg_color="#1f6aa5",
                border_color="#1f6aa5",
            )
        else:
            self.card_seleccionada = None

        self.proveedor_id = proveedor_id

        (
            _,
            nombre,
            cif,
            email,
            telefono,
            direccion,
            codigo_postal,
            poblacion,
            provincia,
            pais,
            iban,
        ) = proveedor

        self.nombre.delete(0, "end")
        self.nombre.insert(0, nombre or "")

        self.cif.delete(0, "end")
        self.cif.insert(0, cif or "")

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

        self._set_modo_edicion()

    def seleccionar_proveedor_por_id(self, proveedor_id):

        for proveedor in self.proveedores:
            if proveedor[0] == proveedor_id:
                widget = self._buscar_widget_por_id(proveedor_id)
                self.seleccionar_proveedor(proveedor_id, widget, proveedor)
                return

    def _buscar_widget_por_id(self, proveedor_id):

        def _buscar(parent):
            for w in parent.winfo_children():
                if getattr(w, "_proveedor_id", None) == proveedor_id:
                    return w
                resultado = _buscar(w)
                if resultado:
                    return resultado
            return None

        return _buscar(self.lista_proveedores)

    # =========================
    # FILTROS
    # =========================
    def buscar(self):

        self.pagination.page = 1

        datos = obtener_proveedores(
            nombre=self.f_nombre.get(),
            cif=self.f_cif.get(),
            limit=self.pagination.limit,
            offset=self.pagination.get_offset(),
        )

        self.limpiar_form()
        self.cargar_proveedores(datos)

    def limpiar_filtros(self):

        self.f_nombre.delete(0, "end")
        self.f_cif.delete(0, "end")

        self.pagination.page = 1
        self.limpiar_form()
        self.cargar_proveedores()

    # =========================
    # CRUD
    # =========================
    def guardar(self):

        if self.proveedor_id:
            return

        try:
            nombre = validar_no_vacio(self.nombre.get(), "Nombre")

            iban_val = self.iban.get().strip()
            if iban_val:
                iban_val = validar_iban(iban_val)

            crear_proveedor(
                nombre,
                self.cif.get().strip(),
                self.email.get().strip(),
                self.telefono.get().strip(),
                self.direccion.get().strip(),
                self.codigo_postal.get().strip(),
                self.poblacion.get().strip(),
                self.provincia.get().strip(),
                self.pais.get().strip(),
                iban_val,
            )

            messagebox.showinfo("Correcto", "Proveedor creado correctamente.")
            self.limpiar_form()
            self.cargar_proveedores()

        except ValueError as e:
            messagebox.showerror("Error de validación", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el proveedor: {e}")

    def actualizar(self):

        if not self.proveedor_id:
            return

        try:
            nombre = validar_no_vacio(self.nombre.get(), "Nombre")

            iban_val = self.iban.get().strip()
            if iban_val:
                iban_val = validar_iban(iban_val)

            actualizar_proveedor(
                self.proveedor_id,
                nombre,
                self.cif.get().strip(),
                self.email.get().strip(),
                self.telefono.get().strip(),
                self.direccion.get().strip(),
                self.codigo_postal.get().strip(),
                self.poblacion.get().strip(),
                self.provincia.get().strip(),
                self.pais.get().strip(),
                iban_val,
            )

            messagebox.showinfo("Correcto", "Proveedor actualizado correctamente.")
            self.limpiar_form()
            self.cargar_proveedores()

        except ValueError as e:
            messagebox.showerror("Error de validación", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo actualizar el proveedor: {e}")

    def eliminar(self):

        if not self.proveedor_id:
            return

        dialog = ctk.CTkInputDialog(
            title="Confirmar acción",
            text=(
                "⚠ El proveedor se desactivará.\n\n"
                "Si tiene facturas de compra, se conservarán.\n\n"
                "Escribe DESACTIVAR para confirmar:"
            ),
        )

        if dialog.get_input() != "DESACTIVAR":
            return

        try:
            borrar_proveedor(self.proveedor_id)
            messagebox.showinfo("Correcto", "Proveedor desactivado correctamente.")
            self.limpiar_form()
            self.cargar_proveedores()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo desactivar el proveedor: {e}")

    def limpiar_form(self):

        self.proveedor_id = None
        self._limpiar_seleccion_visual()

        for campo in (
            self.nombre,
            self.cif,
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

        self._set_modo_creacion()

    # =========================
    # PAGINACIÓN
    # =========================
    def on_pagination_change(self, page, limit):
        self.limpiar_form()
        self.cargar_proveedores()
