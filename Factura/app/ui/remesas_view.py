import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
import os

from app.database.db import get_connection


class RemesasView(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.remesas = []

        # ============================================================
        # HEADER
        # ============================================================

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=25, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text="Remesas SEPA",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Actualizar",
            width=120,
            command=self.cargar,
        ).pack(side="right")

        # ============================================================
        # FILTROS
        # ============================================================

        filtros = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )

        filtros.pack(fill="x", padx=25, pady=(0, 15))

        self.f_codigo = ctk.CTkEntry(
            filtros,
            placeholder_text="Código remesa (ej: REMESA20260312...)",
            width=260,
        )

        self.f_desde = ctk.CTkEntry(
            filtros,
            placeholder_text="Fecha desde (DD/MM/YYYY)",
            width=160,
        )

        self.f_hasta = ctk.CTkEntry(
            filtros,
            placeholder_text="Fecha hasta (DD/MM/YYYY)",
            width=160,
        )

        self.f_codigo.grid(row=0, column=0, padx=8, pady=12)
        self.f_desde.grid(row=0, column=1, padx=8, pady=12)
        self.f_hasta.grid(row=0, column=2, padx=8, pady=12)

        ctk.CTkButton(
            filtros,
            text="Buscar",
            width=120,
            command=self.buscar,
        ).grid(row=0, column=3, padx=15)

        filtros.grid_columnconfigure(4, weight=1)

        # ============================================================
        # LISTA
        # ============================================================

        self.lista = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )

        self.lista.pack(fill="both", expand=True, padx=25, pady=(0, 20))

        self.cargar()

    # ============================================================
    # CONVERTIR FECHA ESPAÑOLA A SQL
    # ============================================================

    def _fecha_es_a_sql(self, fecha):

        try:
            return datetime.strptime(fecha, "%d/%m/%Y").strftime("%Y-%m-%d")
        except Exception:
            return None

    # ============================================================
    # CARGAR REMESAS
    # ============================================================

    def cargar(self, query=None, params=None):

        for w in self.lista.winfo_children():
            w.destroy()

        conn = get_connection()
        cursor = conn.cursor()

        if not query:
            query = """
            SELECT id, codigo_remesa, fecha, total, archivo_xml
            FROM remesas
            ORDER BY fecha DESC
            LIMIT 100
            """
            params = ()

        cursor.execute(query, params)

        self.remesas = cursor.fetchall()

        conn.close()

        if not self.remesas:

            ctk.CTkLabel(
                self.lista,
                text="No hay remesas encontradas",
                text_color="#888888",
            ).pack(pady=20)

            return

        for r in self.remesas:
            self._card_remesa(r)

    # ============================================================
    # BUSCAR
    # ============================================================

    def buscar(self):

        query = """
        SELECT id, codigo_remesa, fecha, total, archivo_xml
        FROM remesas
        WHERE 1=1
        """

        params = []

        codigo = self.f_codigo.get().strip()
        desde = self.f_desde.get().strip()
        hasta = self.f_hasta.get().strip()

        if codigo:
            query += " AND codigo_remesa LIKE ?"
            params.append(f"%{codigo}%")

        if desde:
            fecha_sql = self._fecha_es_a_sql(desde)
            if fecha_sql:
                query += " AND fecha >= ?"
                params.append(fecha_sql)

        if hasta:
            fecha_sql = self._fecha_es_a_sql(hasta)
            if fecha_sql:
                query += " AND fecha <= ?"
                params.append(fecha_sql)

        query += " ORDER BY fecha DESC"

        self.cargar(query, params)

    # ============================================================
    # CARD REMESA
    # ============================================================

    def _card_remesa(self, remesa):

        rid, codigo, fecha, total, archivo = remesa

        card = ctk.CTkFrame(
            self.lista,
            corner_radius=10,
            fg_color="#343434",
            border_width=1,
            border_color="#3a3a3a",
        )

        card.pack(fill="x", padx=12, pady=8)

        try:
            fecha_dt = datetime.fromisoformat(fecha)
            fecha_es = fecha_dt.strftime("%d/%m/%Y")
        except Exception:
            fecha_es = fecha

        # ===========================
        # IZQUIERDA
        # ===========================

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=15, pady=10)

        ctk.CTkLabel(
            info,
            text=codigo if codigo else f"REMESA {rid}",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            info,
            text=f"Fecha: {fecha_es}",
            text_color="#aaaaaa",
        ).pack(anchor="w")

        nombre_archivo = os.path.basename(archivo) if archivo else "XML no disponible"

        ctk.CTkLabel(
            info,
            text=f"Archivo: {nombre_archivo}",
            text_color="#777777",
        ).pack(anchor="w", pady=(3, 0))

        # ===========================
        # DERECHA
        # ===========================

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.pack(side="right", padx=15, pady=10)

        ctk.CTkLabel(
            right,
            text=f"{total:.2f} €",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="e")

        ctk.CTkButton(
            right,
            text="📄 Abrir XML",
            width=140,
            command=lambda a=archivo: (
                self.abrir_xml(a)
                if a
                else messagebox.showwarning(
                    "Sin XML", "Esta remesa no tiene archivo XML asociado."
                )
            ),
        ).pack(pady=3)

        ctk.CTkButton(
            right,
            text="📋 Ver facturas",
            width=140,
            command=lambda i=rid: self.ver_facturas(i),
        ).pack(pady=3)

    # ============================================================
    # ABRIR XML
    # ============================================================

    def abrir_xml(self, archivo):

        if not archivo or not os.path.exists(archivo):

            messagebox.showerror(
                "Archivo no encontrado",
                "No se pudo localizar el XML de la remesa.",
            )

            return

        try:
            os.startfile(archivo)
        except Exception as e:
            messagebox.showerror(
                "Error",
                str(e),
            )

    # ============================================================
    # VER FACTURAS DE REMESA
    # ============================================================

    def ver_facturas(self, remesa_id):

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT d.numero_legal, rl.importe
            FROM remesa_lineas rl
            JOIN documentos d ON d.id = rl.factura_id
            WHERE rl.remesa_id = ?
            """,
            (remesa_id,),
        )

        facturas = cursor.fetchall()

        conn.close()

        if not facturas:

            messagebox.showinfo(
                "Sin datos",
                "No hay facturas en esta remesa.",
            )

            return

        texto = ""

        for numero, importe in facturas:
            texto += f"{numero}  -  {importe:.2f} €\n"

        messagebox.showinfo(
            "Facturas de la remesa",
            texto,
        )
