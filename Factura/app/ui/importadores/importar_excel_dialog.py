import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter.ttk as ttk

from app.services.importador_excel_service import (
    leer_excel,
    obtener_columnas,
    mapear_excel,
    generar_preview,
    validar_productos,
)


class ImportarExcelDialog(ctk.CTkToplevel):

    # =========================================================
    # INIT
    # =========================================================
    def __init__(self, master, on_import=None):
        super().__init__(master)

        self.on_import = on_import

        self.title("Importar Excel")
        self.geometry("1000x650")
        self.grab_set()

        self.df = None
        self.productos = []

        self._build_ui()

    # =========================================================
    # UI
    # =========================================================
    def _build_ui(self):

        # -----------------------------------------
        # Titulo
        # -----------------------------------------
        ctk.CTkLabel(
            self,
            text="Importar Excel de productos / compras",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(20, 10))

        # -----------------------------------------
        # Boton seleccionar archivo
        # -----------------------------------------
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=20, pady=10)

        ctk.CTkButton(
            top,
            text="Seleccionar Excel",
            command=self.seleccionar_excel,
        ).pack(side="left")

        self.label_archivo = ctk.CTkLabel(top, text="Ningún archivo seleccionado")
        self.label_archivo.pack(side="left", padx=15)

        # -----------------------------------------
        # Selección columnas
        # -----------------------------------------
        columnas_frame = ctk.CTkFrame(self)
        columnas_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(columnas_frame, text="Referencia").grid(row=0, column=0, padx=10)
        ctk.CTkLabel(columnas_frame, text="Nombre").grid(row=0, column=1, padx=10)
        ctk.CTkLabel(columnas_frame, text="Cantidad").grid(row=0, column=2, padx=10)
        ctk.CTkLabel(columnas_frame, text="Precio").grid(row=0, column=3, padx=10)
        ctk.CTkLabel(columnas_frame, text="EAN").grid(row=0, column=4, padx=10)

        self.combo_referencia = ctk.CTkComboBox(columnas_frame, values=[])
        self.combo_nombre = ctk.CTkComboBox(columnas_frame, values=[])
        self.combo_cantidad = ctk.CTkComboBox(columnas_frame, values=[])
        self.combo_precio = ctk.CTkComboBox(columnas_frame, values=[])
        self.combo_ean = ctk.CTkComboBox(columnas_frame, values=[])

        self.combo_referencia.grid(row=1, column=0, padx=10, pady=5)
        self.combo_nombre.grid(row=1, column=1, padx=10)
        self.combo_cantidad.grid(row=1, column=2, padx=10)
        self.combo_precio.grid(row=1, column=3, padx=10)
        self.combo_ean.grid(row=1, column=4, padx=10)

        # -----------------------------------------
        # Botón preview
        # -----------------------------------------
        ctk.CTkButton(
            self,
            text="Generar preview",
            command=self.generar_preview,
        ).pack(pady=10)

        # -----------------------------------------
        # Tabla preview
        # -----------------------------------------
        tabla_frame = ctk.CTkFrame(self)
        tabla_frame.pack(fill="both", expand=True, padx=20, pady=10)

        columnas = ("referencia", "nombre", "cantidad", "precio", "ean")

        self.tree = ttk.Treeview(
            tabla_frame,
            columns=columnas,
            show="headings",
            height=15,
        )

        for col in columnas:
            self.tree.heading(col, text=col.upper())
            self.tree.column(col, width=150)

        scrollbar = ttk.Scrollbar(
            tabla_frame,
            orient="vertical",
            command=self.tree.yview,
        )

        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # -----------------------------------------
        # Botones finales
        # -----------------------------------------
        botones = ctk.CTkFrame(self)
        botones.pack(pady=15)

        ctk.CTkButton(
            botones,
            text="Importar",
            command=self.importar,
            width=160,
        ).grid(row=0, column=0, padx=10)

        ctk.CTkButton(
            botones,
            text="Cancelar",
            command=self.destroy,
            fg_color="#c0392b",
            hover_color="#992d22",
            width=160,
        ).grid(row=0, column=1, padx=10)

    # =========================================================
    # SELECCIONAR EXCEL
    # =========================================================
    def seleccionar_excel(self):

        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])

        if not path:
            return

        try:

            self.df = leer_excel(path)

            columnas = obtener_columnas(self.df)

            self.combo_referencia.configure(values=columnas)
            self.combo_nombre.configure(values=columnas)
            self.combo_cantidad.configure(values=columnas)
            self.combo_precio.configure(values=columnas)
            self.combo_ean.configure(values=columnas)

            self.label_archivo.configure(text=path)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # =========================================================
    # PREVIEW
    # =========================================================
    def generar_preview(self):

        if self.df is None:
            messagebox.showwarning("Atención", "Selecciona primero un Excel")
            return

        columnas = {
            "referencia": self.combo_referencia.get(),
            "nombre": self.combo_nombre.get(),
            "cantidad": self.combo_cantidad.get(),
            "precio": self.combo_precio.get(),
            "ean": self.combo_ean.get(),
        }

        self.productos = mapear_excel(self.df, columnas)

        preview = generar_preview(self.productos)

        for row in self.tree.get_children():
            self.tree.delete(row)

        for p in preview:
            self.tree.insert(
                "",
                "end",
                values=(
                    p["referencia"],
                    p["nombre"],
                    p["cantidad"],
                    p["precio"],
                    p["ean"],
                ),
            )

    # =========================================================
    # IMPORTAR
    # =========================================================
    def importar(self):

        if not self.productos:
            messagebox.showwarning("Atención", "Primero genera el preview")
            return

        errores = validar_productos(self.productos)

        if errores:

            texto = "\n".join(errores[:10])

            messagebox.showerror(
                "Errores en Excel",
                texto,
            )

            return

        if self.on_import:
            self.on_import(self.productos)

        messagebox.showinfo(
            "Importación",
            f"{len(self.productos)} productos preparados para importar",
        )

        self.destroy()
