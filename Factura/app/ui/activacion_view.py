import customtkinter as ctk
import logging
import subprocess

from app.database.db import get_connection
from app.utils.config import DATA_DIR, LICENSE_PATH


class ActivacionView(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self._crear_interfaz()

    # ==========================================================
    # INTERFAZ
    # ==========================================================
    def _crear_interfaz(self):

        container = ctk.CTkFrame(self, width=520, corner_radius=12)
        container.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            container,
            text="FacturaPro",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).pack(pady=(30, 10))

        ctk.CTkLabel(
            container,
            text="Activación requerida",
            font=ctk.CTkFont(size=18),
        ).pack(pady=(0, 25))

        # Nombre empresa
        self.entry_empresa = ctk.CTkEntry(
            container,
            placeholder_text="Nombre empresa",
            width=380,
            height=42,
        )
        self.entry_empresa.pack(pady=10)

        # CIF / NIF
        self.entry_cif = ctk.CTkEntry(
            container,
            placeholder_text="CIF / NIF",
            width=380,
            height=42,
        )
        self.entry_cif.pack(pady=10)

        # Botón guardar
        ctk.CTkButton(
            container,
            text="Guardar datos",
            width=220,
            height=42,
            command=self._guardar_empresa,
        ).pack(pady=(25, 10))

        # Botón abrir carpeta (nivel profesional UX)
        ctk.CTkButton(
            container,
            text="Abrir carpeta de licencia",
            width=220,
            height=36,
            fg_color="#444444",
            hover_color="#555555",
            command=self._abrir_carpeta_licencia,
        ).pack(pady=(0, 20))

        self.label_info = ctk.CTkLabel(
            container,
            text="",
            text_color="#888888",
            wraplength=450,
            justify="center",
        )
        self.label_info.pack(pady=(0, 30))

    # ==========================================================
    # GUARDAR EMPRESA
    # ==========================================================
    def _guardar_empresa(self):

        nombre = self.entry_empresa.get().strip()
        cif = self.entry_cif.get().strip()

        if not nombre or not cif:
            self.label_info.configure(
                text="Debe completar nombre empresa y CIF/NIF.",
                text_color="red",
            )
            return

        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM empresa")

            cursor.execute(
                """
                INSERT INTO empresa (id, nombre, cif)
                VALUES (1, ?, ?)
                """,
                (nombre, cif),
            )

            conn.commit()
            conn.close()

            logging.info("Datos empresa guardados para activación")

            self.label_info.configure(
                text=(
                    "Datos guardados correctamente.\n\n"
                    "Envíe estos datos al proveedor para recibir su licencia.\n\n"
                    f"Cuando reciba el archivo license.key, colóquelo en:\n\n"
                    f"{LICENSE_PATH}\n\n"
                    "Después reinicie el programa."
                ),
                text_color="#2fa572",
            )

        except Exception:
            logging.exception("Error al guardar datos empresa")

            self.label_info.configure(
                text="Error al guardar los datos.",
                text_color="red",
            )

    # ==========================================================
    # ABRIR CARPETA LICENCIA
    # ==========================================================
    def _abrir_carpeta_licencia(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.run(["explorer", str(DATA_DIR)])
        except Exception:
            logging.exception("No se pudo abrir la carpeta de licencia")
