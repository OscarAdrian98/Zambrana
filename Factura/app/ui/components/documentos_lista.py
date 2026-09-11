import customtkinter as ctk
from datetime import datetime


class DocumentosLista(ctk.CTkScrollableFrame):

    def __init__(self, master, on_select):

        super().__init__(
            master,
            corner_radius=14,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
        )

        self.on_select = on_select
        self.documentos = []
        self.modo = "TARJETAS"
        self.documento_seleccionado = None

        # ======================================
        # PISCINAS DE OBJETOS V2 (ZERO-GEOMETRY LAG)
        # ======================================
        self._pool_cards = []
        self._pool_filas = []

        self._no_docs_lbl = ctk.CTkLabel(
            self, text="No hay documentos para mostrar.", text_color="#b0b0b0"
        )

        # 1. Mega-Contenedor estático para TARJETAS
        self._cards_container = ctk.CTkFrame(self, fg_color="transparent")

        # 2. Mega-Contenedor estático para la TABLA
        self._tabla_container = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color="#252525",
            border_width=1,
            border_color="#3a3a3a",
        )

        self._tabla_cols = ["Nº", "Fecha", "Cliente/Proveedor", "Total", "Estado"]
        self._header = ctk.CTkFrame(self._tabla_container, fg_color="#2c2c2c", corner_radius=8)
        self._header.pack(fill="x", padx=6, pady=(6, 2))

        for i, col in enumerate(self._tabla_cols):
            self._header.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(
                self._header, text=col, font=ctk.CTkFont(weight="bold")
            ).grid(row=0, column=i, padx=10, pady=10, sticky="ew")

    # ======================================
    # NORMALIZAR DOCUMENTO
    # ======================================
    def _normalizar_doc(self, doc):
        """Convierte (albaranes/facturas) estándar a 7 parámetros"""
        if len(doc) == 5:
            # ALBARAN
            doc_id, numero, fecha, nombre, total = doc
            return (doc_id, numero, fecha, None, nombre, total, "ALBARAN")
        if len(doc) >= 7:
            return doc[:7]
        raise ValueError("Formato de documento no reconocido")

    # ======================================
    # CAMBIAR MODO
    # ======================================
    def set_modo(self, modo):
        self.modo = modo

    # ======================================
    # LIMPIAR VISTA RÁPIDO
    # ======================================
    def limpiar(self):
        """Oculta visualmente los contenedores masivos (1 cálculo en lugar de 50 iterativos)"""
        self._no_docs_lbl.pack_forget()
        self._tabla_container.pack_forget()
        self._cards_container.pack_forget()
        self.documento_seleccionado = None

    # ======================================
    # RENDER BLAZING FAST O(1)
    # ======================================
    def render(self, documentos):
        self.documentos = documentos or []
        self.limpiar()

        if not self.documentos:
            self._no_docs_lbl.pack(anchor="w", padx=14, pady=14)
            return

        if self.modo == "TARJETAS":
            self._render_cards()
        else:
            self._render_tabla()

    # ======================================
    # COLOR ESTADO
    # ======================================
    def _color_estado(self, estado):
        return {
            "PENDIENTE": "#4ea8ff",
            "VENCIDA": "#ff4e4e",
            "PAGADA": "#4eff7a",
            "ALBARAN": "#f0a500",
        }.get(str(estado).upper(), "#b0b0b0")

    # ======================================
    # SELECCION DE FILA O TARJETA
    # ======================================
    def _seleccionar(self, documento_id, widget):
        if self.documento_seleccionado and self.documento_seleccionado.winfo_exists():
            if getattr(self.documento_seleccionado, "_modo", "") == "TABLA":
                base_color = getattr(self.documento_seleccionado, "_base_color", "#292929")
                self.documento_seleccionado.configure(fg_color=base_color)
            else:
                self.documento_seleccionado.configure(fg_color="#303030", border_color="#3a3a3a")

        self.documento_seleccionado = widget
        widget._modo = self.modo

        if self.modo == "TABLA":
            widget.configure(fg_color="#2d6da3")
        else:
            widget.configure(fg_color="#2d6da3", border_color="#2d6da3")

        if self.on_select:
            self.on_select(documento_id)

    def seleccionar_por_id(self, documento_id):
        if self.modo == "TABLA":
            for fila in self._pool_filas:
                if fila.winfo_ismapped() and getattr(fila, "_documento_id", None) == documento_id:
                    self._seleccionar(documento_id, fila)
                    return
        else:
            for card in self._pool_cards:
                if card.winfo_ismapped() and getattr(card, "_documento_id", None) == documento_id:
                    self._seleccionar(documento_id, card)
                    return

    # ======================================
    # OBJECT POOLS V2 Y RENDERIZADORES
    # ======================================

    def _get_card_widget(self, index):
        """Retorna una tarjeta existente o crea una nueva incrustada en el MEGA-Contenedor _cards_container."""
        if index < len(self._pool_cards):
            card = self._pool_cards[index]
            if not card.winfo_ismapped():
                card.pack(fill="x", pady=8, padx=8)
            return card

        card = ctk.CTkFrame(
            self._cards_container, corner_radius=10, fg_color="#303030", border_width=1, border_color="#3a3a3a"
        )
        card.pack(fill="x", pady=8, padx=8)
        card._documento_id = None

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 2))

        lbl_numero = ctk.CTkLabel(top, font=ctk.CTkFont(weight="bold"))
        lbl_numero.pack(side="left")

        lbl_estado = ctk.CTkLabel(top, font=ctk.CTkFont(weight="bold"))
        lbl_estado.pack(side="right")

        lbl_nombre = ctk.CTkLabel(card, text_color="#b0b0b0")
        lbl_nombre.pack(anchor="w", padx=12)

        lbl_fechas = ctk.CTkLabel(card, text_color="#b0b0b0")
        lbl_fechas.pack(anchor="w", padx=12)

        lbl_total = ctk.CTkLabel(card, font=ctk.CTkFont(weight="bold"))
        lbl_total.pack(anchor="e", padx=12, pady=(0, 10))

        card._lbl_numero = lbl_numero
        card._lbl_estado = lbl_estado
        card._lbl_nombre = lbl_nombre
        card._lbl_fechas = lbl_fechas
        card._lbl_total = lbl_total

        def click(e):
            self._seleccionar(card._documento_id, card)

        def bind_click(w):
            w.bind("<Button-1>", click)
            for child in w.winfo_children():
                bind_click(child)

        bind_click(card)
        self._pool_cards.append(card)
        return card

    def _render_cards(self):
        # 1. Empaqueta todo el bloque en una sola llamada de re-posicionamiento masivo
        self._cards_container.pack(fill="both", expand=True)

        # 2. Oculta SOLO las tarjetas sobrantes del _cards_container si la nueva página tiene menos facturas
        num_docs = len(self.documentos)
        for i in range(num_docs, len(self._pool_cards)):
            self._pool_cards[i].pack_forget()

        # 3. Solo re-escribe los literales sin usar la CPU geométrica de CustomTkinter
        for i, raw_doc in enumerate(self.documentos):
            doc = self._normalizar_doc(raw_doc)
            doc_id, numero, fecha, fecha_venc, nombre, total, estado = doc

            try:
                fecha_es = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                fecha_es = fecha

            venc_es = (
                datetime.strptime(fecha_venc, "%Y-%m-%d").strftime("%d/%m/%Y")
                if fecha_venc
                else "-"
            )

            card = self._get_card_widget(i)
            card._documento_id = doc_id

            card.configure(fg_color="#303030", border_color="#3a3a3a")
            card._lbl_numero.configure(text=numero)
            card._lbl_estado.configure(text=estado, text_color=self._color_estado(estado))
            card._lbl_nombre.configure(text=nombre)
            card._lbl_fechas.configure(text=f"Fecha: {fecha_es} · Vence: {venc_es}")
            card._lbl_total.configure(text=f"{float(total):.2f} €")

    def _get_fila_widget(self, index, base_color):
        """Retorna una fila existente y la muestra, o la crea dentro del MEGA-Contenedor _tabla_container."""
        if index < len(self._pool_filas):
            fila = self._pool_filas[index]
            fila.configure(fg_color=base_color)
            if not fila.winfo_ismapped():
                fila.pack(fill="x", padx=6, pady=2)
            return fila

        fila = ctk.CTkFrame(self._tabla_container, fg_color=base_color, corner_radius=8)
        fila.pack(fill="x", padx=6, pady=2)
        fila._documento_id = None
        fila._base_color = base_color

        fila._etiquetas = []
        for i in range(len(self._tabla_cols)):
            fila.grid_columnconfigure(i, weight=1)
            lbl = ctk.CTkLabel(fila, text="")
            lbl.grid(row=0, column=i, padx=10, pady=10, sticky="ew")
            fila._etiquetas.append(lbl)

        def click(e):
            self._seleccionar(fila._documento_id, fila)

        fila.bind("<Button-1>", click)
        for lbl in fila._etiquetas:
            lbl.bind("<Button-1>", click)

        self._pool_filas.append(fila)
        return fila

    def _render_tabla(self):
        # 1. Empaqueta la tabla completa en 1 instrucción (Cero Layout Lag)
        self._tabla_container.pack(fill="both", expand=True, padx=8, pady=8)

        # 2. Oculta el exceso de filas recicladas (si la página actual es corta)
        num_docs = len(self.documentos)
        for i in range(num_docs, len(self._pool_filas)):
            self._pool_filas[i].pack_forget()

        # 3. Modifica los textos al instante de las filas rescatadas sin recalcular 'paths'
        for i, raw_doc in enumerate(self.documentos):
            doc = self._normalizar_doc(raw_doc)
            doc_id, numero, fecha, _, nombre, total, estado = doc

            base = "#292929" if i % 2 == 0 else "#2c2c2c"
            fila = self._get_fila_widget(i, base)

            fila._documento_id = doc_id
            fila._base_color = base

            try:
                fecha_es = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                fecha_es = fecha

            valores = [numero, fecha_es, nombre, f"{float(total):.2f} €", estado]

            for j, val in enumerate(valores):
                color = self._color_estado(val) if j == 4 else "white"
                fila._etiquetas[j].configure(text=val, text_color=color)
