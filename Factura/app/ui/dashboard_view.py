"""Panel financiero en el mismo toolkit que la ventana principal."""
from datetime import date
import customtkinter as ctk
from app.services.dashboard_service import obtener_resumen_dashboard

MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
         'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
COLOR_VENTAS = '#3aa6ff'
COLOR_COMPRAS = '#2fa572'
COLOR_RESULTADO = '#bbbbbb'

class DashboardView(ctk.CTkScrollableFrame):
    _vista_nombre = 'dashboard'

    def __init__(self, parent=None):
        super().__init__(parent)
        hoy = date.today()
        self.mes_actual, self.año_actual = hoy.month, hoy.year
        self.titulo = ctk.CTkLabel(self, text='Resumen financiero', font=('', 20, 'bold'))
        self.titulo.pack(pady=20)
        filtros = ctk.CTkFrame(self)
        filtros.pack(pady=10)
        self.combo_mes = ctk.CTkOptionMenu(filtros, values=MESES)
        self.combo_mes.set(MESES[hoy.month - 1])
        self.combo_mes.pack(side='left', padx=8)
        self.combo_año = ctk.CTkOptionMenu(filtros, values=[str(hoy.year-i) for i in range(5)])
        self.combo_año.set(str(hoy.year))
        self.combo_año.pack(side='left', padx=8)
        ctk.CTkButton(filtros, text='Actualizar', command=self.actualizar_dashboard).pack(side='left', padx=8)
        self.grid_widget = ctk.CTkFrame(self)
        self.grid_widget.pack(fill='both', expand=True, padx=20, pady=20)
        self.grid_widget.grid_columnconfigure((0, 1), weight=1)
        self.cargar_dashboard(hoy.month, hoy.year)

    def cargar_dashboard(self, mes, año):
        for widget in self.grid_widget.winfo_children():
            widget.destroy()
        datos = obtener_resumen_dashboard(mes, año)

        # =========================
        # VENTAS
        # =========================

        self._section_label("VENTAS", COLOR_VENTAS, 0)

        self._card("Facturación del mes", datos["facturado"], 1, 0)
        self._card("Cobrado este mes", datos["cobrado"], 1, 1)
        self._card("Pendiente de cobro", datos["pendiente_cobro"], 2, 0)
        self._card("Vencidas (clientes)", datos["vencidas_venta"], 2, 1)

        # =========================
        # COMPRAS
        # =========================

        self._section_label("COMPRAS", COLOR_COMPRAS, 3)

        self._card("Compras del mes", datos["compras_mes"], 4, 0)
        self._card("Pagado a proveedores", datos["pagado_proveedores"], 4, 1)
        self._card("Pendiente de pago", datos["pendiente_pago"], 5, 0)
        self._card("Vencidas (proveedores)", datos["vencidas_compra"], 5, 1)

        # =========================
        # RESULTADO
        # =========================

        self._section_label("RESULTADO", COLOR_RESULTADO, 6)

        resultado = datos["resultado_mes"]
        flujo = datos["flujo_caja"]

        color_res = "#1f5e45" if resultado >= 0 else "#6e2b2b"
        color_flujo = "#1f5e45" if flujo >= 0 else "#6e2b2b"

        self._card(
            "Resultado operativo del mes",
            resultado,
            7,
            0,
            bg=color_res,
            grande=True
        )

        self._card(
            "Flujo de caja real",
            flujo,
            7,
            1,
            bg=color_flujo,
            grande=True
        )


    def actualizar_dashboard(self):
        mes = MESES.index(self.combo_mes.get()) + 1
        año = int(self.combo_año.get())
        self.titulo.configure(text=f'Resumen financiero · {MESES[mes-1]} {año}')
        self.cargar_dashboard(mes, año)

    def _section_label(self, texto, color, row):
        ctk.CTkLabel(self.grid_widget, text=texto, text_color=color,
                     font=('', 14, 'bold')).grid(row=row, column=0, columnspan=2, pady=12)

    def _card(self, titulo, valor, row, col, bg='#1e1e1e', grande=False):
        card = ctk.CTkFrame(self.grid_widget, fg_color=bg)
        card.grid(row=row, column=col, sticky='nsew', padx=8, pady=8)
        ctk.CTkLabel(card, text=titulo).pack(padx=16, pady=(12, 4))
        texto = f'{valor:,.2f} €' if isinstance(valor, (int, float)) else str(valor)
        ctk.CTkLabel(card, text=texto, font=('', 20 if grande else 16, 'bold')).pack(pady=(0, 12))
