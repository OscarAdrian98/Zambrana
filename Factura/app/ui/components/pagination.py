import customtkinter as ctk


class Pagination(ctk.CTkFrame):
    def __init__(
        self,
        master,
        on_change,
        initial_page=1,
        initial_limit=10,
    ):
        super().__init__(master, fg_color="transparent")

        self.on_change = on_change
        self.page = initial_page
        self.limit = initial_limit

        # =========================
        # BOTÓN ANTERIOR
        # =========================
        self.btn_prev = ctk.CTkButton(
            self,
            text="⬅",
            width=40,
            command=self.prev_page,
        )
        self.btn_prev.pack(side="left", padx=5)

        # =========================
        # LABEL PÁGINA
        # =========================
        self.lbl_page = ctk.CTkLabel(
            self,
            text=f"Página {self.page}",
        )
        self.lbl_page.pack(side="left", padx=10)

        # =========================
        # BOTÓN SIGUIENTE
        # =========================
        self.btn_next = ctk.CTkButton(
            self,
            text="➡",
            width=40,
            command=self.next_page,
        )
        self.btn_next.pack(side="left", padx=5)

        # =========================
        # SELECT LIMIT
        # =========================
        self.combo_limit = ctk.CTkComboBox(
            self,
            values=["5", "10", "25", "50"],
            width=80,
            command=self.change_limit,
        )
        self.combo_limit.set(str(self.limit))
        self.combo_limit.pack(side="right", padx=10)

    # =========================
    # EVENTOS
    # =========================

    def next_page(self):
        self.page += 1
        self.trigger()

    def prev_page(self):
        if self.page > 1:
            self.page -= 1
            self.trigger()

    def change_limit(self, value):
        self.limit = int(value)
        self.page = 1
        self.trigger()

    def trigger(self):
        self.lbl_page.configure(text=f"Página {self.page}")
        if self.on_change:
            self.on_change(self.page, self.limit)

    # =========================
    # UTIL
    # =========================

    def get_offset(self):
        return (self.page - 1) * self.limit
