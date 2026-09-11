import shutil
import sys
from tkinter import filedialog, messagebox
from datetime import datetime

from app.utils.config import DB_PATH, BACKUP_DIR

MAX_BACKUPS = 15


# ==================================================
# BACKUP AUTOMÁTICO
# ==================================================
def backup_automatico():
    """
    Crea copia automática diaria de la base de datos.
    Mantiene un máximo de MAX_BACKUPS copias.
    """

    if not DB_PATH.exists():
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    hoy = datetime.now().strftime("%Y-%m-%d")
    backup_path = BACKUP_DIR / f"facturacion_{hoy}.db"

    # Copia diaria
    if not backup_path.exists():
        shutil.copy2(DB_PATH, backup_path)

    # Último estado (siempre se actualiza)
    ultimo_estado = BACKUP_DIR / "ultimo_estado.db"
    shutil.copy2(DB_PATH, ultimo_estado)

    _limpiar_backups()


# ==================================================
# LIMPIAR BACKUPS ANTIGUOS
# ==================================================
def _limpiar_backups():
    if not BACKUP_DIR.exists():
        return

    backups = sorted(
        f
        for f in BACKUP_DIR.iterdir()
        if f.name.startswith("facturacion_") and f.suffix == ".db"
    )

    if len(backups) <= MAX_BACKUPS:
        return

    for backup in backups[:-MAX_BACKUPS]:
        try:
            backup.unlink()
        except Exception:
            pass


# ==================================================
# RESTAURAR COPIA MANUAL
# ==================================================
def restaurar_backup_manual():
    """
    Permite restaurar manualmente una copia de seguridad.
    Hace copia de emergencia antes de reemplazar la actual.
    """

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    hay_backups = any(
        f.suffix == ".db"
        and (f.name.startswith("facturacion_") or f.name.startswith("EMERGENCIA_"))
        for f in BACKUP_DIR.iterdir()
    )

    if not hay_backups:
        messagebox.showerror(
            "Sin copias",
            "No se han encontrado copias de seguridad.",
        )
        return

    archivo = filedialog.askopenfilename(
        title="Seleccionar copia de seguridad",
        initialdir=BACKUP_DIR,
        filetypes=[("Base de datos", "*.db")],
    )

    if not archivo:
        return

    confirmar = messagebox.askyesno(
        "⚠ Confirmar restauración",
        "Esto reemplazará la base de datos actual.\n\n"
        "Se hará una copia de emergencia antes.\n\n"
        "¿Deseas continuar?",
    )

    if not confirmar:
        return

    try:
        if not DB_PATH.exists():
            messagebox.showerror(
                "Error",
                "No se encontró la base de datos actual.",
            )
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        emergency = BACKUP_DIR / f"EMERGENCIA_{timestamp}.db"
        shutil.copy2(DB_PATH, emergency)

        shutil.copy2(archivo, DB_PATH)

        messagebox.showinfo(
            "Restauración completada",
            "La base de datos se ha restaurado.\n\n"
            "El programa se cerrará para aplicar los cambios.",
        )

        sys.exit(0)

    except Exception as e:
        messagebox.showerror(
            "Error",
            f"No se pudo restaurar la copia:\n\n{e}",
        )
