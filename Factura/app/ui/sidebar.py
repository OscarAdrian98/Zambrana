import customtkinter as ctk

from app.ui.dashboard_view import DashboardView
from app.ui.clientes_view import ClientesView
from app.ui.productos_view import ProductosView
from app.ui.albaranes.albaranes_view import AlbaranesView
from app.ui.facturas.facturas_view import FacturasView
from app.ui.domiciliaciones_view import DomiciliacionesView
from app.ui.remesas_view import RemesasView
from app.ui.proveedores_view import ProveedoresView
from app.ui.facturas_compras.facturas_compras_view import FacturasComprasView
from app.ui.empresa_view import EmpresaView

from app.utils.backup import restaurar_backup_manual


class Sidebar(ctk.CTkFrame):

    WIDTH = 230

    def __init__(self, master, dias_restantes=0):
        super().__init__(
            master,
            width=self.WIDTH,
            corner_radius=0,
            fg_color="#111111",
        )

        # Evitar que CTk cambie tamaño
        self.pack_propagate(False)
        self.grid_propagate(False)

        self.master = master
        self._active = None
        self.dias_restantes = dias_restantes

        # Grid interno
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(99, weight=1)

        self._build()

        # Activar Dashboard automáticamente al iniciar
        self.after(150, lambda: self._activate(self.btn_dashboard, DashboardView))

    # ================================================================
    # BUILD UI
    # ================================================================
    def _build(self):

        # ── Header / Logo ───────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 0))

        ctk.CTkLabel(
            header,
            text="FacturaPro",
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color="white",
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="Sistema de gestión",
            font=ctk.CTkFont(size=11),
            text_color="#484848",
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        self._sep(1)

        # ── Dashboard ───────────────────────────────────────────────
        self.btn_dashboard = self._btn("Dashboard", "⊞", DashboardView, 2)

        self._sep(3)

        # ── Ventas ──────────────────────────────────────────────────
        self._section("VENTAS", "#3b8ed0", 4)

        self._btn("Clientes", "👤", ClientesView, 5)
        self._btn("Productos", "📦", ProductosView, 6)
        self._btn("Albaranes", "📋", AlbaranesView, 7)
        self._btn("Facturas", "🧾", FacturasView, 8)
        self._btn("Domiciliaciones", "🏦", DomiciliacionesView, 9)

        self._sep(10)

        # ── Tesorería ───────────────────────────────────────────────
        self._section("TESORERÍA", "#f0a500", 11)

        self._btn("Remesas SEPA", "💳", RemesasView, 12)

        self._sep(13)

        # ── Compras ─────────────────────────────────────────────────
        self._section("COMPRAS", "#2fa572", 14)

        self._btn("Proveedores", "🏭", ProveedoresView, 15)
        self._btn("Facturas compra", "📥", FacturasComprasView, 16)

        self._sep(17)

        # ── Configuración ───────────────────────────────────────────
        self._section("CONFIGURACIÓN", "#555555", 18)

        self._btn("Empresa", "🏢", EmpresaView, 19)

        # ── Restaurar backup ────────────────────────────────────────
        ctk.CTkButton(
            self,
            text="Restaurar copia",
            height=34,
            corner_radius=6,
            fg_color="#6e2222",
            hover_color="#551a1a",
            text_color="#ffaaaa",
            font=ctk.CTkFont(size=12),
            command=restaurar_backup_manual,
        ).grid(row=20, column=0, padx=18, pady=(8, 4), sticky="ew")

        # =========================================================
        # LICENCIA (🔥 NUEVO)
        # =========================================================

        self._sep(21)

        color = (
            "#2fa572"
            if self.dias_restantes > 5
            else "#d4a017" if self.dias_restantes > 0 else "#a33a3a"
        )

        texto = (
            f"Licencia activa\n{self.dias_restantes} días restantes"
            if self.dias_restantes > 0
            else "Licencia caducada"
        )

        ctk.CTkLabel(
            self,
            text=texto,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=color,
            justify="center",
        ).grid(row=22, column=0, pady=(10, 10))

        # ── Footer ──────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="v1.0.0",
            text_color="#2e2e2e",
            font=ctk.CTkFont(size=11),
        ).grid(row=99, column=0, pady=(0, 14))

    # ================================================================
    # BOTONES
    # ================================================================
    def _btn(self, text, icon, view_class, row):

        label = f"  {icon}  {text}"

        btn = ctk.CTkButton(
            self,
            text=label,
            height=36,
            corner_radius=7,
            fg_color="transparent",
            hover_color="#1c1c1c",
            text_color="#b8b8b8",
            font=ctk.CTkFont(size=13),
            anchor="w",
            command=lambda: self._activate(btn, view_class),
        )

        btn.grid(row=row, column=0, padx=14, pady=2, sticky="ew")

        return btn

    # ================================================================
    # ACTIVAR VISTA
    # ================================================================
    def _activate(self, button, view_class):

        # Restaurar botón anterior
        if self._active and self._active != button:
            self._active.configure(
                fg_color="transparent",
                text_color="#b8b8b8",
            )

        # Activar nuevo botón
        button.configure(
            fg_color="#1a3a5c",
            text_color="white",
        )

        self._active = button

        # Mostrar vista
        self.master.mostrar_vista(view_class)

    # ================================================================
    # SECCIONES
    # ================================================================
    def _section(self, text, color, row):

        ctk.CTkLabel(
            self,
            text=text,
            text_color=color,
            font=ctk.CTkFont(size=10, weight="bold"),
            anchor="w",
        ).grid(row=row, column=0, padx=20, pady=(12, 2), sticky="w")

    # ================================================================
    # SEPARADOR
    # ================================================================
    def _sep(self, row):

        ctk.CTkFrame(
            self,
            height=1,
            fg_color="#1e1e1e",
        ).grid(row=row, column=0, sticky="ew", padx=14, pady=8)
