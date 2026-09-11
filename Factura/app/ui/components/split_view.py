import customtkinter as ctk


class SplitView(ctk.CTkFrame):
    """
    Componente reutilizable de SplitView.
    Permite panel izquierdo y derecho con divisor arrastrable.
    Conserva la configuración de anchos por vista y modo automáticamente.
    """

    # Diccionario de clase para persistir anchos mientras la app siga abierta.
    # Formato clave: "nombre_vista_MODO", Valor: ancho (int)
    _saved_widths = {}

    def __init__(
        self,
        master,
        view_name="default",
        left_minsize=300,
        right_minsize=300,
        initial_left_width=460,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.view_name = view_name
        self.left_minsize = left_minsize
        self.right_minsize = right_minsize
        self.default_width = initial_left_width
        self.current_mode = "DEFAULT"

        # Recuperar persistencia si existe
        saved = self._saved_widths.get(self._get_storage_key(), initial_left_width)
        self.current_left_width = self.clamp_width(saved, initial_left_width)

        # Configuración del Grid Layout principal
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=self.current_left_width)
        self.grid_columnconfigure(1, weight=0, minsize=14)  # Zona sensible para arrastre
        self.grid_columnconfigure(2, weight=1)

        # -------------------------------------------------------------------
        # 1. PANEL IZQUIERDO
        # -------------------------------------------------------------------
        self.left_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # -------------------------------------------------------------------
        # 2. DIVISOR (SASH) MEJORADO - ZONA SENSIBLE ANCHA CON LÍNEA FINA
        # -------------------------------------------------------------------
        self.sash_container = ctk.CTkFrame(
            self,
            width=14,
            cursor="sb_h_double_arrow",
            fg_color="transparent",
        )
        self.sash_container.grid(row=0, column=1, sticky="ns", pady=10)
        self.sash_container.grid_propagate(False)

        # Feedback visual del sash (línea fina central que cambia de color)
        self.visual_sash = ctk.CTkFrame(
            self.sash_container,
            width=4,
            corner_radius=2,
            fg_color="#3a3a3a",
        )
        self.visual_sash.place(relx=0.5, rely=0.5, relheight=1.0, anchor="center")

        # Bindings para el componente visual y su contenedor sensible
        for w in (self.sash_container, self.visual_sash):
            w.bind("<ButtonPress-1>", self.start_drag)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<ButtonRelease-1>", self.stop_drag)
            w.bind("<Double-Button-1>", self._on_double_click)
            w.bind("<Enter>", self._on_sash_enter)
            w.bind("<Leave>", self._on_sash_leave)

        # -------------------------------------------------------------------
        # 3. PANEL DERECHO
        # -------------------------------------------------------------------
        self.right_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.right_frame.grid(row=0, column=2, sticky="nsew", padx=(5, 0))

        # -------------------------------------------------------------------
        # 4. OPTIMIZADORES VISUALES
        # -------------------------------------------------------------------
        # Línea guía para arrastre opaco súper fluido
        self.drag_indicator = ctk.CTkFrame(self, width=2, fg_color="#1f6aa5")

        # Capturar el evento Resize de la ventana (para repeler roturas de layout)
        self.bind("<Configure>", self._on_configure)

        self._drag_start_x = 0
        self._start_width = 0
        self._sash_start_x = 0
        self._current_drag_width = 0
        self._is_dragging = False

    # =========================================================
    # LÓGICA INTERNA: CÁLCULOS Y ESTADOS
    # =========================================================

    def _get_storage_key(self):
        return f"{self.view_name}_{self.current_mode}"

    def clamp_width(self, width, fallback_total=None):
        """
        Garantiza que el ancho esté dentro de límites respetando min_left y min_right.
        Usado al arrastrar o al redimensionar la ventana principal de la app.
        """
        total_width = getattr(self, "winfo_width", lambda: 0)()

        # Manejo de ventana oculta/inicializada recien
        if total_width <= 1 and fallback_total is None:
            return max(self.left_minsize, width)

        tw = total_width if total_width > 1 else fallback_total
        if tw:
            # Obtener el ancho del sash cuidadosamente porque en el __init__ clamp_width
            # se llama *antes* de crear el sash_container.
            sash_obj = getattr(self, "sash_container", None)
            sash_w = sash_obj.winfo_width() if sash_obj else 14
            max_width = tw - self.right_minsize - sash_w - 10

            if max_width < self.left_minsize:
                max_width = self.left_minsize

            return max(self.left_minsize, min(width, max_width))

        return max(self.left_minsize, width)

    # =========================================================
    # API PÚBLICA (USADA POR LAS VISTAS)
    # =========================================================

    def set_mode_width(self, mode_name, default_mode_width):
        """
        Adapta el ancho de los paneles según una vista concreta (ej: "TARJETAS", "TABLA").
        Actúa de manera inteligente respetando guardados previos de ese mismo modo.
        """
        self.current_mode = mode_name
        self.default_width = default_mode_width

        saved = self._saved_widths.get(self._get_storage_key())
        if saved is not None:
            self.set_left_width(saved)
        else:
            self.set_left_width(default_mode_width)

    def set_left_width(self, width):
        """Asigna, valida un ancho izquierdo y lo guarda en persistencia."""
        valid_width = self.clamp_width(width)
        self.current_left_width = valid_width
        self.grid_columnconfigure(0, minsize=self.current_left_width)

        # La variable _saved_widths al ser de clase comparte estado global en la sesión
        self._saved_widths[self._get_storage_key()] = self.current_left_width

    def get_left_width(self):
        """Retorna el ancho real configurado actualmente."""
        return self.current_left_width

    def reset_to_default(self):
        """Restablece al estado predeterminado visual del panel actual."""
        self.set_left_width(self.default_width)

    # =========================================================
    # EVENTOS: HOVER & DOBLE CLIC
    # =========================================================

    def _on_sash_enter(self, event):
        if not self._is_dragging:
            self.visual_sash.configure(fg_color="#1f6aa5")  # Highlight suave

    def _on_sash_leave(self, event):
        if not self._is_dragging:
            self.visual_sash.configure(fg_color="#3a3a3a")  # Des-highlight

    def _on_double_click(self, event):
        self.reset_to_default()

    # =========================================================
    # EVENTOS DRAGGING ULTRASUAVE (RENDERIZADO OPAGO)
    # =========================================================

    def start_drag(self, event):
        self._is_dragging = True
        self._drag_start_x = event.x_root
        self._start_width = self.current_left_width
        self._current_drag_width = self.current_left_width

        # Destacar fuertemente que está siendo arrastrado
        self.visual_sash.configure(fg_color="#144d7a")

        self._sash_start_x = self.sash_container.winfo_x()
        width_offset = (self.sash_container.winfo_width() - 2) // 2

        self.drag_indicator.place(
            x=self._sash_start_x + width_offset, rely=0, relheight=1
        )

    def on_drag(self, event):
        if not self._is_dragging:
            return

        delta = event.x_root - self._drag_start_x
        new_width = self._start_width + delta

        valid_width = self.clamp_width(new_width)
        self._current_drag_width = valid_width

        clamped_delta = valid_width - self._start_width
        width_offset = (self.sash_container.winfo_width() - 2) // 2

        # Desplaza solamente la línea superpuesta esquivando recálculo en TKinter total
        self.drag_indicator.place(
            x=self._sash_start_x + clamped_delta + width_offset,
            rely=0,
            relheight=1,
        )

    def stop_drag(self, event):
        self._is_dragging = False
        self.drag_indicator.place_forget()
        self.visual_sash.configure(fg_color="#1f6aa5")  # Dejar destacado asumiendo hover

        # Confirmar al layout que hemos finalizado el resize opaco
        self.set_left_width(self._current_drag_width)

    # =========================================================
    # AUTO-CORRECCIÓN AL RESIZE DE LA APP PRINCIPAL
    # =========================================================

    def _on_configure(self, event):
        # Esta llamada salta ante cualquier cambio de la ventana maestra.
        # Si la ventana reduce su tamaño tanto que aplasta al min_size del panel
        # derecho, clamp lo corrige inyectándolo de nuevo hacia la izquierda.
        total_w = event.width
        if total_w > 10:
            clamped = self.clamp_width(self.current_left_width, fallback_total=total_w)
            if clamped != self.current_left_width:
                # Solo disparamos set_left_width si realmente ha sido expulsado del rango legal
                self.current_left_width = clamped
                self.grid_columnconfigure(0, minsize=self.current_left_width)
