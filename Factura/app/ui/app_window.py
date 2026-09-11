import os
import sys
import customtkinter as ctk
import logging
from datetime import datetime

from app.database.models import crear_tablas
from app.utils.backup import backup_automatico
from app.utils.logger import setup_logger
from app.utils.config import DATA_DIR, LICENSE_PATH, LOGS_DIR, BACKUP_DIR
from app.services.integridad_service import verificar_integridad
from app.services.license_service import validar_licencia


# ==========================================================
# RUTAS COMPATIBLES CON PYINSTALLER
# ==========================================================
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ==========================================================
# CONFIGURACIÓN VISUAL GLOBAL
# ==========================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):

    # Ancho del sidebar — debe coincidir con el que usa Sidebar
    SIDEBAR_WIDTH = 230

    def __init__(self):
        super().__init__()

        self.licencia_info = None
        self.dias_restantes = 0

        # ── Icono ─────────────────────────────────────────────────────
        try:
            self.iconbitmap(resource_path("assets/icono.ico"))
        except Exception:
            pass

        # ── Logging ───────────────────────────────────────────────────
        setup_logger()
        logging.info("Aplicación iniciada")

        # ── Directorios base ──────────────────────────────────────────
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        # ── Base de datos + integridad ────────────────────────────────
        try:
            crear_tablas()
            logging.info("Base de datos inicializada correctamente")
            verificar_integridad()
            logging.info("Integridad verificada correctamente")
        except Exception as e:
            logging.critical(f"Error crítico en base de datos: {e}")
            raise

        # ── Ventana ───────────────────────────────────────────────────
        self.title("FacturaPro")

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        ww = min(1500, sw - 80)
        wh = min(900, sh - 80)
        x = (sw - ww) // 2
        y = (sh - wh) // 2

        self.geometry(f"{ww}x{wh}+{x}+{y}")
        self.minsize(1200, 720)
        self.configure(fg_color="#1a1a1a")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Grid raíz ─────────────────────────────────────────────────
        #
        #  columna 0 → sidebar  (ancho FIJO, no se estira nunca)
        #  columna 1 → contenido (se lleva todo el espacio sobrante)
        #
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=self.SIDEBAR_WIDTH)
        self.grid_columnconfigure(1, weight=1)

        # ── Contenedor de vistas ──────────────────────────────────────
        self.container = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color="#202020",
        )
        self.container.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(0, 10),
            pady=10,
        )

        self.current_view = None

        # ── Licencia ──────────────────────────────────────────────────
        if self._licencia_existe():
            try:
                resultado = validar_licencia()
                self.licencia_info = resultado if isinstance(resultado, dict) else {}
                self.dias_restantes = self._calcular_dias_restantes()

                logging.info(f"Licencia válida | días restantes: {self.dias_restantes}")

                self._iniciar_app_normal()

            except Exception as e:
                logging.critical(f"Licencia inválida: {e}")
                self._modo_activacion()
        else:
            logging.info("Sin licencia → modo activación")
            self._modo_activacion()

    # ==================================================================
    # LICENCIA
    # ==================================================================
    def _licencia_existe(self):
        return LICENSE_PATH.exists()

    def _calcular_dias_restantes(self):
        try:
            if not self.licencia_info:
                return 0

            expira = self.licencia_info.get("expira")

            if not expira:
                return 0

            fecha_exp = datetime.strptime(expira, "%Y-%m-%d")
            dias = (fecha_exp - datetime.now()).days

            return max(dias, 0)

        except Exception:
            logging.exception("No se pudo calcular los días restantes de la licencia")
            return 0

    # ==================================================================
    # MODO NORMAL
    # ==================================================================
    def _iniciar_app_normal(self):
        from app.ui.sidebar import Sidebar
        from app.ui.dashboard_view import DashboardView

        self.sidebar = Sidebar(
            self,
            dias_restantes=self.dias_restantes,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.mostrar_vista(DashboardView)

    # ==================================================================
    # MODO ACTIVACIÓN  (sin sidebar, ocupa toda la ventana)
    # ==================================================================
    def _modo_activacion(self):

        self.grid_columnconfigure(0, weight=0, minsize=0)

        self.container.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=0,
            pady=0,
        )

        self.container.configure(corner_radius=0)

        from app.ui.activacion_view import ActivacionView

        self.current_view = ActivacionView(self.container)
        self.current_view.pack(fill="both", expand=True)

    # ==================================================================
    # CAMBIO DE VISTAS
    # ==================================================================
    def mostrar_vista(self, vista_cls):
        if self.current_view is not None:
            try:
                self.current_view.destroy()
            except Exception:
                pass
            self.current_view = None

        try:
            nueva_vista = vista_cls(self.container)
            nueva_vista.pack(fill="both", expand=True)
            self.current_view = nueva_vista
        except Exception as e:
            logging.exception("Error al cargar vista")
            from tkinter import messagebox

            messagebox.showerror("Error", f"No se pudo cargar la vista:\n{e}")

    # ==================================================================
    # CIERRE SEGURO + BACKUP
    # ==================================================================
    def _on_close(self):
        try:
            logging.info("Cierre de aplicación")
            backup_automatico()
            logging.info("Backup realizado al cerrar")
        except Exception:
            logging.exception("Error durante el cierre o el backup")
        finally:
            self.destroy()
