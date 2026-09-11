import customtkinter as ctk
from tkinter import messagebox

from app.utils.validators import validar_no_vacio, validar_float, validar_iva
from app.services.albaranes_service import añadir_linea, actualizar_linea


# =========================================================
# CONFIRMACIONES
# =========================================================


def confirmar_eliminar_linea():
    return messagebox.askyesno(
        "Confirmar",
        "¿Eliminar esta línea?\n\nEsta acción no se puede deshacer.",
    )


def confirmar_eliminar_albaran():
    return messagebox.askyesno(
        "Confirmar eliminación",
        "¿Eliminar este albarán?\n\nEsta acción no se puede deshacer.",
    )


def confirmar_facturar():
    return messagebox.askyesno(
        "Confirmar",
        "¿Convertir este albarán en factura?\n\nEsta acción no se puede deshacer.",
    )


# =========================================================
# AVISOS
# =========================================================


def aviso_albaran_bloqueado():
    messagebox.showinfo(
        "Albarán bloqueado",
        "Este albarán ya está facturado y no se puede modificar.",
    )


def aviso_sin_lineas():
    messagebox.showwarning(
        "Sin líneas",
        "No puedes facturar un albarán sin líneas.",
    )


def aviso_sin_cliente():
    messagebox.showwarning(
        "Falta cliente",
        "Selecciona un cliente antes de crear el albarán.",
    )


def factura_creada():
    messagebox.showinfo(
        "Correcto",
        "Factura creada correctamente.",
    )


# =========================================================
# DIALOGO AÑADIR LINEA
# =========================================================


class AlbaranLineaDialog(ctk.CTkToplevel):

    def __init__(self, master, albaran_id, on_created=None):
        super().__init__(master)

        self.albaran_id = albaran_id
        self.on_created = on_created

        self.title("Añadir línea")
        self.geometry("420x320")
        self.resizable(False, False)

        self.grab_set()
        self.focus_force()

        self._build_ui()

    def _build_ui(self):

        container = ctk.CTkFrame(self, corner_radius=12)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            container,
            text="Nueva línea",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", pady=(0, 15))

        self.entry_desc = ctk.CTkEntry(
            container,
            placeholder_text="Descripción",
        )
        self.entry_desc.pack(fill="x", pady=6)

        self.entry_cantidad = ctk.CTkEntry(
            container,
            placeholder_text="Cantidad",
        )
        self.entry_cantidad.pack(fill="x", pady=6)

        self.entry_precio = ctk.CTkEntry(
            container,
            placeholder_text="Precio",
        )
        self.entry_precio.pack(fill="x", pady=6)

        self.entry_iva = ctk.CTkEntry(
            container,
            placeholder_text="IVA %",
        )
        self.entry_iva.insert(0, "21")
        self.entry_iva.pack(fill="x", pady=6)

        botones = ctk.CTkFrame(container, fg_color="transparent")
        botones.pack(fill="x", pady=(20, 0))

        ctk.CTkButton(
            botones,
            text="Cancelar",
            fg_color="#4a4a4a",
            command=self.destroy,
        ).pack(side="left")

        ctk.CTkButton(
            botones,
            text="Añadir línea",
            fg_color="#2fa572",
            hover_color="#238a5e",
            command=self._crear_linea,
        ).pack(side="right")

    def _crear_linea(self):

        try:

            descripcion = validar_no_vacio(self.entry_desc.get(), "Descripción")
            cantidad = validar_float(self.entry_cantidad.get(), "Cantidad")
            precio = validar_float(
                self.entry_precio.get(), "Precio", permitir_cero=True
            )
            iva = validar_iva(self.entry_iva.get())

            if cantidad <= 0:
                raise Exception("La cantidad debe ser mayor que 0.")

            añadir_linea(
                self.albaran_id,
                descripcion,
                cantidad,
                precio,
                iva,
                None,
            )

            if self.on_created:
                self.on_created()

            self.destroy()

        except Exception as e:

            messagebox.showerror("Error", str(e))


# =========================================================
# DIALOGO EDITAR LINEA
# =========================================================


class AlbaranLineaEditarDialog(ctk.CTkToplevel):

    def __init__(self, master, linea, on_saved=None):
        super().__init__(master)

        self.linea = linea
        self.on_saved = on_saved

        self.title("Editar línea")
        self.geometry("420x320")
        self.resizable(False, False)

        self.grab_set()
        self.focus_force()

        self._build_ui()

    def _build_ui(self):

        container = ctk.CTkFrame(self, corner_radius=12)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            container,
            text="Editar línea",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", pady=(0, 15))

        linea_id, producto_id, desc, cant, precio, iva, total = self.linea

        self.entry_desc = ctk.CTkEntry(container)
        self.entry_desc.insert(0, desc)
        self.entry_desc.pack(fill="x", pady=6)

        self.entry_cantidad = ctk.CTkEntry(container)
        self.entry_cantidad.insert(0, str(cant))
        self.entry_cantidad.pack(fill="x", pady=6)

        self.entry_precio = ctk.CTkEntry(container)
        self.entry_precio.insert(0, str(precio))
        self.entry_precio.pack(fill="x", pady=6)

        self.entry_iva = ctk.CTkEntry(container)
        self.entry_iva.insert(0, str(iva))
        self.entry_iva.pack(fill="x", pady=6)

        botones = ctk.CTkFrame(container, fg_color="transparent")
        botones.pack(fill="x", pady=(20, 0))

        ctk.CTkButton(
            botones,
            text="Cancelar",
            command=self.destroy,
        ).pack(side="left")

        ctk.CTkButton(
            botones,
            text="Guardar",
            fg_color="#2fa572",
            hover_color="#238a5e",
            command=self._guardar,
        ).pack(side="right")

    def _guardar(self):

        try:

            linea_id = self.linea[0]

            desc = validar_no_vacio(self.entry_desc.get(), "Descripción")
            cantidad = validar_float(self.entry_cantidad.get(), "Cantidad")
            precio = validar_float(self.entry_precio.get(), "Precio")
            iva = validar_iva(self.entry_iva.get())

            actualizar_linea(
                linea_id,
                desc,
                cantidad,
                precio,
                iva,
            )

            if self.on_saved:
                self.on_saved()

            self.destroy()

        except Exception as e:

            messagebox.showerror("Error", str(e))
