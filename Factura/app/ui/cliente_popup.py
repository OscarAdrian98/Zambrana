import customtkinter as ctk
from tkinter import messagebox
import threading

from app.services.facturas_service import obtener_facturas
from app.services.clientes_service import obtener_cliente_por_id


class ClientePopup(ctk.CTkToplevel):

    def __init__(self, master, cliente_id):
        super().__init__(master)

        self.cliente_id = cliente_id

        self.title("Cliente")
        self.geometry("540x600")
        self.resizable(False, False)
        self.grab_set()

        # =========================
        # CONTENEDOR PRINCIPAL
        # =========================
        container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color="#2f2f2f",
            border_width=1,
            border_color="#3a3a3a",
        )
        container.pack(fill="both", expand=True, padx=15, pady=15)

        # =========================
        # CABECERA CLIENTE
        # =========================
        self.lbl_nombre = ctk.CTkLabel(
            container,
            text="Cliente",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        self.lbl_nombre.pack(anchor="w", padx=15, pady=(15, 5))

        self.lbl_datos = ctk.CTkLabel(
            container,
            text="",
            text_color="#b0b0b0",
        )
        self.lbl_datos.pack(anchor="w", padx=15)

        self.lbl_contacto = ctk.CTkLabel(
            container,
            text="",
            text_color="#b0b0b0",
        )
        self.lbl_contacto.pack(anchor="w", padx=15, pady=(0, 10))

        # =========================
        # BLOQUE ESTADÍSTICAS
        # =========================
        stats = ctk.CTkFrame(
            container,
            fg_color="#262626",
            corner_radius=10,
            border_width=1,
            border_color="#3a3a3a",
        )
        stats.pack(fill="x", padx=15, pady=10)

        stats.grid_columnconfigure(0, weight=1)
        stats.grid_columnconfigure(1, weight=1)

        self.lbl_total_facturas = ctk.CTkLabel(
            stats,
            text="Facturas: 0",
            font=ctk.CTkFont(weight="bold"),
        )
        self.lbl_total_facturas.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.lbl_total_importe = ctk.CTkLabel(
            stats,
            text="Total facturado: 0 €",
            font=ctk.CTkFont(weight="bold"),
        )
        self.lbl_total_importe.grid(row=0, column=1, padx=10, pady=10, sticky="e")

        self.lbl_pendientes = ctk.CTkLabel(
            stats,
            text="Pendientes: 0",
            text_color="#4ea8ff",
        )
        self.lbl_pendientes.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="w")

        # =========================
        # TITULO FACTURAS
        # =========================
        ctk.CTkLabel(
            container,
            text="Últimas facturas",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=15, pady=(10, 5))

        # =========================
        # LISTA FACTURAS
        # =========================
        self.lista = ctk.CTkScrollableFrame(
            container,
            corner_radius=10,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
            height=280,
        )
        self.lista.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # =========================
        # BOTONES
        # =========================
        botones = ctk.CTkFrame(container, fg_color="transparent")
        botones.pack(fill="x", padx=15, pady=(5, 15))

        ctk.CTkButton(
            botones,
            text="Cerrar",
            command=self.destroy,
        ).pack(side="right")

        # =========================
        # CARGA DATOS
        # =========================
        threading.Thread(target=self._cargar_datos, daemon=True).start()

    # =================================================
    # CARGAR DATOS
    # =================================================

    def _cargar_datos(self):

        try:
            cliente = obtener_cliente_por_id(self.cliente_id)
            facturas = obtener_facturas(cliente_id=self.cliente_id)
        except Exception:
            cliente = None
            facturas = []

        self.after(0, lambda: self._render(cliente, facturas))

    # =================================================
    # RENDER
    # =================================================

    def _render(self, cliente, facturas):

        if not cliente:
            messagebox.showerror("Error", "No se pudo cargar el cliente")
            self.destroy()
            return

        nombre = cliente.get("nombre")
        dni = cliente.get("dni") or ""
        email = cliente.get("email") or ""
        telefono = cliente.get("telefono") or ""

        direccion = cliente.get("direccion") or ""
        cp = cliente.get("codigo_postal") or ""
        poblacion = cliente.get("poblacion") or ""
        provincia = cliente.get("provincia") or ""
        pais = cliente.get("pais") or ""

        direccion_completa = direccion

        if cp or poblacion:
            direccion_completa += f", {cp} {poblacion}".strip()

        if provincia:
            direccion_completa += f", {provincia}"

        if pais:
            direccion_completa += f" {pais}"

        self.lbl_nombre.configure(text=nombre)
        self.lbl_datos.configure(
            text=f"DNI: {dni}   |   Dirección: {direccion_completa}"
        )
        self.lbl_contacto.configure(text=f"📧 {email}   |   📞 {telefono}")

        total_importe = 0
        pendientes = 0

        for f in facturas:
            total_importe += float(f[5] or 0)

            if f[6] == "PENDIENTE":
                pendientes += 1

        self.lbl_total_facturas.configure(text=f"Facturas: {len(facturas)}")
        self.lbl_total_importe.configure(text=f"Total facturado: {total_importe:.2f} €")
        self.lbl_pendientes.configure(text=f"Pendientes: {pendientes}")

        # =========================
        # RENDER FACTURAS
        # =========================

        for f in facturas[:10]:

            numero = f[1]
            total = float(f[5] or 0)
            estado = f[6]

            color_estado = {
                "PENDIENTE": "#4ea8ff",
                "PAGADA": "#4eff7a",
                "VENCIDA": "#ff6b6b",
            }.get(estado, "#b0b0b0")

            item = ctk.CTkFrame(
                self.lista,
                corner_radius=8,
                fg_color="#303030",
                border_width=1,
                border_color="#3a3a3a",
            )
            item.pack(fill="x", padx=6, pady=4)

            top = ctk.CTkFrame(item, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=6)

            ctk.CTkLabel(
                top,
                text=numero,
                font=ctk.CTkFont(weight="bold"),
            ).pack(side="left")

            ctk.CTkLabel(
                top,
                text=f"{total:.2f} €",
                font=ctk.CTkFont(weight="bold"),
            ).pack(side="right")

            ctk.CTkLabel(
                item,
                text=estado,
                text_color=color_estado,
                font=ctk.CTkFont(size=11, weight="bold"),
            ).pack(anchor="w", padx=10, pady=(0, 6))
