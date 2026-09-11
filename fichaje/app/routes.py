from flask import (
    render_template,
    redirect,
    url_for,
    request,
    flash,
    send_file,
    make_response,
    session,
    abort,
)
import io
from flask_login import login_required, current_user
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from app import app, db, login_manager
from app.models import (
    Usuario,
    Fichaje,
    RegistroHorario,
    Ausencia,
    SabadoAsignado,
)
from app.services.horarios import (
    formatear_duracion_corta,
    formatear_horas_minutos_texto,
    formatear_timedelta_hhmm,
    formatear_timedelta_hhmmss,
    formatear_total_horas,
    reconstruir_tramos,
    esta_eliminado,
)
from app.services.exportaciones import (
    configurar_hoja_excel,
    preparar_fila_administrativa,
    preparar_fila_personal,
    sanear_texto_excel,
)
from app.services.edicion_fichajes import (
    crear_snapshot_borrado_firmado,
    crear_snapshot_firmado,
    preparar_edicion,
)
from app.services.fichajes import (
    ADMIN_BORRADO_ADMINISTRADOR_INEXISTENTE,
    ADMIN_BORRADO_CONFLICTO_CONCURRENTE,
    ADMIN_BORRADO_ELIMINADO,
    ADMIN_BORRADO_ERROR_PERSISTENCIA,
    ADMIN_BORRADO_FICHAJE_INEXISTENTE,
    ADMIN_BORRADO_SIN_PERMISOS,
    ADMIN_BORRADO_USUARIO_INEXISTENTE,
    ADMIN_BORRADO_YA_ELIMINADO,
    ADMIN_EDICION_ACTUALIZADA,
    ADMIN_EDICION_ADMINISTRADOR_INEXISTENTE,
    ADMIN_EDICION_CONFLICTO_CONCURRENTE,
    ADMIN_EDICION_ERROR_PERSISTENCIA,
    ADMIN_EDICION_FICHAJE_ELIMINADO,
    ADMIN_EDICION_FICHAJE_INEXISTENTE,
    ADMIN_EDICION_FICHAJES_ACTIVOS_MULTIPLES,
    ADMIN_EDICION_REGISTRO_AJENO,
    ADMIN_EDICION_SIN_CAMBIOS,
    ADMIN_EDICION_SIN_PERMISOS,
    ADMIN_EDICION_TRAMOS_INVALIDOS,
    ADMIN_EDICION_USUARIO_INEXISTENTE,
    ADMIN_ADMINISTRADOR_INEXISTENTE,
    ADMIN_ERROR_PERSISTENCIA,
    ADMIN_FECHA_INVALIDA,
    ADMIN_FICHAJE_CREADO,
    ADMIN_FICHAJE_YA_EXISTENTE,
    ADMIN_FICHAJES_ACTIVOS_MULTIPLES,
    ADMIN_HORAS_INVALIDAS,
    ADMIN_SIN_PERMISOS,
    ADMIN_TRAMO_INVALIDO,
    ADMIN_USUARIO_INEXISTENTE,
    AUSENCIA_BLOQUEANTE,
    ENTRADA_DUPLICADA,
    ERROR_PERSISTENCIA,
    FICHAJES_ACTIVOS_MULTIPLES,
    LECTURA_FICHAJE_ACTIVO_MULTIPLE,
    ORIGEN_INVALIDO,
    SALIDA_DUPLICADA,
    SALIDA_SIN_ENTRADA,
    SECUENCIA_ANOMALA,
    TIPO_INVALIDO,
    EntradaEdicionFichajeAdministrativo,
    ErrorRegistroFichaje,
    analizar_secuencia,
    crear_fichaje_administrativo,
    editar_fichaje_administrativo,
    eliminar_fichaje_administrativo,
    registrar_fichaje_usuario,
    resolver_fichaje_activo,
)
from app.services.autenticacion import (
    ErrorValidacionAutenticacion,
    cerrar_sesion_limpia,
    iniciar_sesion_limpia,
    normalizar_email,
    normalizar_nombre,
    refrescar_sesion_autenticada,
    validar_password,
    validar_puesto,
)
from app.services.usuarios import (
    USUARIO_CREADO,
    USUARIO_EMAIL_DUPLICADO,
    buscar_usuario_por_email,
    persistir_usuario,
)
from app.services.sabados import (
    SABADOS_ERROR_PERSISTENCIA,
    SABADOS_FECHAS_INVALIDAS,
    SABADOS_GUARDADOS,
    SABADOS_USUARIO_INEXISTENTE,
    guardar_sabados_asignados,
    sabados_del_mes,
)
from app.services.ausencias import (
    AUSENCIA_ACTUALIZADA,
    AUSENCIA_ADMINISTRADOR_INEXISTENTE,
    AUSENCIA_BLOQUE_AJENO,
    AUSENCIA_BLOQUE_INEXISTENTE,
    AUSENCIA_CONFLICTO_CONCURRENTE,
    AUSENCIA_CREADA,
    AUSENCIA_DATOS_INVALIDOS,
    AUSENCIA_DUPLICADA,
    AUSENCIA_ELIMINADA,
    AUSENCIA_ERROR_PERSISTENCIA,
    AUSENCIA_SIN_CAMBIOS,
    AUSENCIA_SIN_PERMISOS,
    AUSENCIA_SNAPSHOT_INVALIDO,
    AUSENCIA_USUARIO_INEXISTENTE,
    EntradaAusencia,
    EntradaEdicionAusencia,
    ErrorValidacionAusencia,
    TIPO_ASUNTOS_PROPIOS,
    TIPO_BAJA,
    TIPO_ENFERMEDAD,
    TIPO_MEDICO,
    TIPO_VACACIONES,
    agrupar_ausencias,
    ausencia_bloquea_fichaje,
    calcular_saldo_vacaciones,
    crear_ausencia_administrativa,
    crear_ausencia_usuario,
    crear_snapshot_ausencia_firmado,
    editar_ausencia_usuario as editar_ausencia_usuario_servicio,
    eliminar_ausencia_usuario as eliminar_ausencia_usuario_servicio,
    fecha_hoy_madrid,
    normalizar_tipo_ausencia,
    preparar_edicion_ausencia_usuario,
    seleccionar_ausencia_bloqueante,
    tipo_canonico_existente,
)
from datetime import datetime, date, timedelta
import pandas as pd
from openpyxl.styles import Font, Alignment
import logging
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
import pytz

# Zona horaria de España
zona_es = pytz.timezone("Europe/Madrid")

if not app.testing and os.environ.get("FICHAJE_LOG_TO_FILE") == "1":
    # Crear carpeta logs si no existe
    os.makedirs("logs", exist_ok=True)

    # Configurar logging
    logging.basicConfig(
        filename="logs/flask_app.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]",
    )


def obtener_ausencia_bloqueante_hoy(usuario_id, fecha):
    ausencias_hoy = (
        Ausencia.query.filter_by(usuario_id=usuario_id, fecha=fecha)
        .order_by(Ausencia.id)
        .all()
    )
    return seleccionar_ausencia_bloqueante(ausencias_hoy)


@app.context_processor
def inject_today():
    return {"today": fecha_hoy_madrid()}


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))
        try:
            email = normalizar_email(request.form.get("email"))
        except ErrorValidacionAutenticacion:
            user = None
        else:
            user = (
                Usuario.query.filter(func.lower(Usuario.email) == email)
                .order_by(Usuario.id)
                .first()
            )

        if user and check_password_hash(user.password_hash, password):
            iniciar_sesion_limpia(user, recordar=remember)
            return redirect(url_for("fichar"))

        flash("Usuario o contraseña incorrectos")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    cerrar_sesion_limpia()
    return redirect(url_for("login"))


@app.route("/fichar")
@login_required
def fichar():
    today = fecha_hoy_madrid()
    resultado_fichaje = resolver_fichaje_activo(
        db.session,
        usuario_id=current_user.id,
        fecha=today,
    )
    fichaje = resultado_fichaje.fichaje
    incidencia_fichajes_multiples = (
        resultado_fichaje.estado == LECTURA_FICHAJE_ACTIVO_MULTIPLE
    )
    ausencia_hoy = obtener_ausencia_bloqueante_hoy(current_user.id, today)

    registros_hoy = []

    if fichaje and fichaje.registros:
        registros_hoy = sorted(
            [
                r
                for r in fichaje.registros
                if not esta_eliminado(r)
            ],
            key=lambda r: (r.timestamp, r.id),
        )

    reconstruccion = reconstruir_tramos(registros_hoy)
    siguiente_tipo = (
        "entrada"
        if resultado_fichaje.cantidad_detectada == 0
        else None
    )
    if fichaje is not None:
        try:
            siguiente_tipo = analizar_secuencia(registros_hoy, today).siguiente_tipo
        except ErrorRegistroFichaje:
            siguiente_tipo = None
    entrada_abierta = reconstruccion.entrada_abierta
    accion_disponible = None
    if not ausencia_hoy and not incidencia_fichajes_multiples:
        accion_disponible = siguiente_tipo
    origen_tramo_abierto = (
        (entrada_abierta.origen or "Tienda")
        if entrada_abierta is not None
        else None
    )
    ultima_entrada_str = (
        entrada_abierta.timestamp.isoformat() if entrada_abierta is not None else None
    )
    total_cerrado_segundos = int(reconstruccion.total_trabajado.total_seconds())

    # NUEVO: comprobar si hoy es sábado y está asignado
    es_sabado = today.weekday() == 5 and today.month != 8
    sabado_asignado = (
        SabadoAsignado.query.filter_by(usuario_id=current_user.id, fecha=today).first()
        is not None
    )

    return render_template(
        "fichar.html",
        fichaje=fichaje,
        today=today,
        estado=reconstruccion.estado,
        total_cerrado_hhmm=formatear_timedelta_hhmm(
            reconstruccion.total_trabajado
        ),
        total_cerrado_segundos=total_cerrado_segundos,
        es_sabado=es_sabado,
        sabado_asignado=sabado_asignado,
        ultima_entrada_str=ultima_entrada_str,
        registros_hoy=registros_hoy,
        ultimo_registro=reconstruccion.ultimo_registro,
        entrada_abierta=entrada_abierta,
        incidencias=reconstruccion.incidencias,
        ausencia_hoy=ausencia_hoy,
        siguiente_tipo=siguiente_tipo,
        accion_disponible=accion_disponible,
        origen_tramo_abierto=origen_tramo_abierto,
        incidencia_fichajes_multiples=incidencia_fichajes_multiples,
    )


@app.route("/fichar_registro", methods=["POST"])
@login_required
def fichar_registro():
    try:
        resultado = registrar_fichaje_usuario(
            db.session,
            current_user.id,
            request.form.get("tipo"),
            request.form.get("origen"),
        )
        flash(
            f"{resultado.tipo.capitalize()} registrada correctamente a las "
            f"{resultado.instante.strftime('%H:%M:%S')} ({resultado.origen}).",
            "success",
        )
    except ErrorRegistroFichaje as exc:
        mensajes = {
            TIPO_INVALIDO: "Tipo de fichaje no válido.",
            ORIGEN_INVALIDO: "Origen de fichaje no válido. Debe ser Tienda o Remoto.",
            AUSENCIA_BLOQUEANTE: "No puedes fichar hoy porque estás ausente.",
            SALIDA_SIN_ENTRADA: "No puedes registrar una salida sin haber fichado una entrada antes.",
            ENTRADA_DUPLICADA: (
                "Ya has registrado una entrada como último fichaje. "
                "Debes registrar una salida antes."
            ),
            SALIDA_DUPLICADA: "Ya has registrado una salida como último fichaje.",
            FICHAJES_ACTIVOS_MULTIPLES: (
                "No se puede fichar porque existen varios fichajes activos para hoy."
            ),
            SECUENCIA_ANOMALA: (
                "No se puede fichar porque la secuencia horaria requiere revisión."
            ),
            ERROR_PERSISTENCIA: "Error al registrar el fichaje.",
        }
        flash(mensajes.get(exc.codigo, "No se pudo registrar el fichaje."), "danger")

    return redirect(url_for("fichar"))


@app.route("/resumen")
@login_required
def resumen():
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    hoy = date.today()

    # Si no hay filtros, usamos el primer y último día del mes actual
    if not desde_str:
        desde = hoy.replace(day=1)
        desde_str = desde.strftime("%Y-%m-%d")
    else:
        desde = datetime.strptime(desde_str, "%Y-%m-%d").date()

    if not hasta_str:
        # Para obtener el último día del mes, avanzamos al día 1 del mes siguiente y restamos un día
        if hoy.month == 12:
            siguiente_mes = hoy.replace(year=hoy.year + 1, month=1, day=1)
        else:
            siguiente_mes = hoy.replace(month=hoy.month + 1, day=1)
        hasta = siguiente_mes - timedelta(days=1)
        hasta_str = hasta.strftime("%Y-%m-%d")
    else:
        hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date()

    query = Fichaje.query.filter_by(usuario_id=current_user.id).filter(
        Fichaje.eliminado == False, Fichaje.fecha >= desde, Fichaje.fecha <= hasta
    )

    fichajes = query.order_by(Fichaje.fecha.desc()).all()

    datos = []
    total_global = timedelta()

    for f in fichajes:
        registros = (
            RegistroHorario.query.filter_by(fichaje_id=f.id, eliminado=False)
            .order_by(RegistroHorario.timestamp)
            .all()
        )

        reconstruccion = reconstruir_tramos(registros)
        registros_simplificados = []

        for reg in reconstruccion.registros_activos:
            hora_str = reg.timestamp.strftime("%H:%M:%S")
            registros_simplificados.append(
                {"tipo": reg.tipo, "hora": hora_str, "origen": reg.origen or "Tienda"}
            )

        total_global += reconstruccion.total_trabajado

        datos.append(
            {
                "fecha": f.fecha.strftime("%d/%m/%Y"),
                "registros": registros_simplificados,
                "tramos": reconstruccion.tramos,
                "total": (
                    formatear_timedelta_hhmmss(reconstruccion.total_trabajado)
                    if reconstruccion.total_trabajado.total_seconds() > 0
                    else ""
                ),
                "incidencias": reconstruccion.incidencias,
            }
        )

    total_global_str = formatear_total_horas(total_global)

    return render_template(
        "resumen.html",
        datos=datos,
        desde=desde_str,
        hasta=hasta_str,
        total_global=total_global_str,
    )


@app.route("/admin/usuarios")
@login_required
def admin_usuarios():
    if not current_user.admin:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))

    usuarios = Usuario.query.order_by(Usuario.nombre).all()
    return render_template("admin_usuarios.html", usuarios=usuarios)


@app.route("/admin/fichajes")
@login_required
def admin_fichajes():
    if not current_user.admin:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))

    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    hoy = date.today()

    # Rango por defecto: mes actual
    if not desde_str:
        desde = hoy.replace(day=1)
        desde_str = desde.strftime("%Y-%m-%d")
    else:
        desde = datetime.strptime(desde_str, "%Y-%m-%d").date()

    if not hasta_str:
        if hoy.month == 12:
            siguiente_mes = hoy.replace(year=hoy.year + 1, month=1, day=1)
        else:
            siguiente_mes = hoy.replace(month=hoy.month + 1, day=1)
        hasta = siguiente_mes - timedelta(days=1)
        hasta_str = hasta.strftime("%Y-%m-%d")
    else:
        hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date()

    query = Fichaje.query.join(Usuario).filter(
        Fichaje.eliminado == False, Fichaje.fecha.between(desde, hasta)
    )

    fichajes = query.order_by(Fichaje.fecha.desc()).all()

    datos = []
    for f in fichajes:
        reconstruccion = reconstruir_tramos(f.registros)

        datos.append(
            {
                "usuario_id": f.usuario.id,
                "usuario": f.usuario.nombre,
                "fecha": f.fecha.strftime("%d/%m/%Y"),
                "total": (
                    formatear_timedelta_hhmmss(reconstruccion.total_trabajado)
                    if reconstruccion.total_trabajado.total_seconds() > 0
                    else ""
                ),
                "fichaje_id": f.id,
            }
        )

    return render_template(
        "admin_fichajes.html", datos=datos, desde_str=desde_str, hasta_str=hasta_str
    )


@app.route("/admin/exportar_excel")
@login_required
def exportar_excel():
    if not current_user.admin:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))

    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    query = Fichaje.query.join(Usuario).filter(Fichaje.eliminado == False)

    if desde_str:
        desde = datetime.strptime(desde_str, "%Y-%m-%d").date()
        query = query.filter(Fichaje.fecha >= desde)
    if hasta_str:
        hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date()
        query = query.filter(Fichaje.fecha <= hasta)

    fichajes = query.order_by(Fichaje.fecha.desc()).all()

    data = []
    for f in fichajes:
        resultado = reconstruir_tramos(f.registros)
        data.append(
            preparar_fila_administrativa(
                f.usuario.nombre,
                f.fecha,
                resultado,
            )
        )

    # Generar Excel
    columnas = [
        "Usuario",
        "Fecha",
        "Entrada Mañana",
        "Salida Mañana",
        "Entrada Tarde",
        "Salida Tarde",
        "Total trabajado",
        "Tramos adicionales",
        "Incidencias",
    ]
    df = pd.DataFrame(data, columns=columnas)
    output = io.BytesIO()
    filename = f"fichajes_{desde_str or 'inicio'}_a_{hasta_str or 'hoy'}.xlsx"

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Fichajes")
        configurar_hoja_excel(
            writer.sheets["Fichajes"],
            fila_cabecera=1,
            anchos=(24, 13, 17, 17, 17, 17, 18, 32, 38),
            columnas_multilinea=(8, 9),
            columnas_texto=(1, 8, 9),
        )

    output.seek(0)
    return send_file(output, download_name=filename, as_attachment=True)


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        try:
            nombre = normalizar_nombre(request.form.get("nombre"))
            email = normalizar_email(request.form.get("email"))
            password = validar_password(
                request.form.get("password"),
                request.form.get("confirmar_password"),
            )
            puesto = validar_puesto(request.form.get("puesto"))
        except ErrorValidacionAutenticacion as error:
            flash(str(error), "danger")
            return redirect(url_for("registro"))

        existente = buscar_usuario_por_email(db.session, Usuario, email)
        if existente:
            flash("Ya existe un usuario con ese email.", "danger")
            return redirect(url_for("registro"))

        password_hash = generate_password_hash(password)
        resultado = persistir_usuario(
            db.session,
            Usuario,
            nombre=nombre,
            email=email,
            password_hash=password_hash,
            puesto=puesto,
            admin=False,
        )
        if resultado.codigo == USUARIO_EMAIL_DUPLICADO:
            flash("Ya existe un usuario con ese email.", "danger")
            return redirect(url_for("registro"))
        if resultado.codigo != USUARIO_CREADO:
            app.logger.error(
                "No se pudo completar el registro de empleado "
                "(codigo_motor=%s).",
                resultado.codigo_motor,
            )
            flash(
                "No se pudo completar el registro. Inténtalo de nuevo.",
                "danger",
            )
            return redirect(url_for("registro"))

        nuevo_usuario = resultado.usuario
        iniciar_sesion_limpia(nuevo_usuario)
        flash("Registro exitoso. Bienvenido.")
        return redirect(url_for("fichar"))

    return render_template("registro.html")


@app.route("/exportar_mis_fichajes")
@login_required
def exportar_mis_fichajes():
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    query = Fichaje.query.filter_by(usuario_id=current_user.id).filter(
        Fichaje.eliminado == False
    )

    if desde_str:
        desde = datetime.strptime(desde_str, "%Y-%m-%d").date()
        query = query.filter(Fichaje.fecha >= desde)

    if hasta_str:
        hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date()
        query = query.filter(Fichaje.fecha <= hasta)

    fichajes = query.order_by(Fichaje.fecha).all()

    data = []
    total_general = timedelta()

    for f in fichajes:
        resultado = reconstruir_tramos(f.registros)
        fila = preparar_fila_personal(
            f.fecha,
            resultado,
            sanear_excel=True,
        )
        total_general += fila.total

        data.append(
            {
                "Fecha": fila.fecha,
                "Registros": fila.registros_texto,
                "Total trabajado": fila.total_texto,
                "Incidencias": fila.incidencias_texto,
            }
        )

    df = pd.DataFrame(
        data,
        columns=["Fecha", "Registros", "Total trabajado", "Incidencias"],
    )

    output = io.BytesIO()
    filename = f"fichajes_{current_user.nombre.replace(' ', '_')}.xlsx"

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Fichajes", startrow=2)

        worksheet = writer.sheets["Fichajes"]

        nombre_excel = sanear_texto_excel(current_user.nombre)
        titulo = f"Horario de {nombre_excel}"
        worksheet.merge_cells("A1:D1")
        cell = worksheet["A1"]
        cell.value = titulo
        cell.font = Font(size=14, bold=True)
        cell.alignment = Alignment(horizontal="center")

        configurar_hoja_excel(
            worksheet,
            fila_cabecera=3,
            anchos=(14, 48, 20, 40),
            columnas_multilinea=(2, 4),
            columnas_texto=(1, 2, 4),
        )

        total_filas = len(df) + 4
        worksheet.cell(row=total_filas, column=1, value="Total acumulado:")
        worksheet.cell(
            row=total_filas,
            column=3,
            value=formatear_timedelta_hhmmss(total_general),
        )

    output.seek(0)
    return send_file(output, download_name=filename, as_attachment=True)


@app.route("/admin/fichajes/<int:usuario_id>")
@login_required
def admin_fichajes_usuario(usuario_id):
    if not current_user.admin:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))

    usuario = Usuario.query.get_or_404(usuario_id)

    hoy = date.today()
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    # -------------------------
    # Filtros fechas
    # -------------------------
    if desde_str:
        desde = datetime.strptime(desde_str, "%Y-%m-%d").date()
    else:
        desde = hoy.replace(day=1)
        desde_str = desde.strftime("%Y-%m-%d")

    if hasta_str:
        hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date()
    else:
        if hoy.month == 12:
            siguiente_mes = hoy.replace(year=hoy.year + 1, month=1, day=1)
        else:
            siguiente_mes = hoy.replace(month=hoy.month + 1, day=1)
        hasta = siguiente_mes - timedelta(days=1)
        hasta_str = hasta.strftime("%Y-%m-%d")

    # -------------------------
    # Obtener fichajes
    # -------------------------
    fichajes = (
        Fichaje.query.filter_by(usuario_id=usuario_id, eliminado=False)
        .filter(Fichaje.fecha.between(desde, hasta))
        .order_by(Fichaje.fecha.desc())
        .all()
    )

    datos = []

    total_horas = timedelta()
    total_dias = 0
    dias_incompletos = 0

    # -------------------------
    # Procesar fichajes
    # -------------------------
    for f in fichajes:
        reconstruccion = reconstruir_tramos(f.registros)
        lista_registros = []

        for r in reconstruccion.registros_activos:
            hora_str = r.timestamp.strftime("%H:%M:%S")
            origen = r.origen or "Tienda"
            lista_registros.append(f"{r.tipo.capitalize()} - {hora_str} ({origen})")

        if reconstruccion.incidencias:
            dias_incompletos += 1

        if reconstruccion.tramos:
            total_horas += reconstruccion.total_trabajado
            total_dias += 1

        datos.append(
            {
                "id": f.id,
                "fecha": f.fecha.strftime("%d/%m/%Y"),
                "registros": lista_registros,
                "total": (
                    formatear_timedelta_hhmmss(reconstruccion.total_trabajado)
                    if reconstruccion.total_trabajado.total_seconds() > 0
                    else ""
                ),
                "snapshot_borrado": crear_snapshot_borrado_firmado(
                    f,
                    reconstruccion.registros_activos,
                    app.config["SECRET_KEY"],
                ),
            }
        )

    # -------------------------
    # Calcular media
    # -------------------------
    if total_dias > 0:
        media = total_horas / total_dias
    else:
        media = timedelta()

    total_horas_str = formatear_timedelta_hhmm(total_horas)
    media_horas_str = formatear_timedelta_hhmm(media)

    return render_template(
        "admin_fichajes_usuario.html",
        usuario=usuario,
        datos=datos,
        desde_str=desde_str,
        hasta_str=hasta_str,
        total_dias=total_dias,
        total_horas=total_horas_str,
        media_horas=media_horas_str,
        dias_incompletos=dias_incompletos,
    )


@app.route("/admin/editar_fichaje/<int:fichaje_id>", methods=["GET", "POST"])
@login_required
def editar_fichaje_admin(fichaje_id):
    if not current_user.admin:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))

    if request.method == "POST":
        entrada = EntradaEdicionFichajeAdministrativo(
            snapshot=request.form.get("snapshot", ""),
            campos=tuple(request.form.items(multi=True)),
        )
        resultado = editar_fichaje_administrativo(
            db.session,
            administrador_id=current_user.id,
            fichaje_id=fichaje_id,
            entrada=entrada,
            secret_key=app.config["SECRET_KEY"],
        )

        if resultado.codigo == ADMIN_EDICION_ACTUALIZADA:
            flash("Fichaje actualizado correctamente.", "success")
            return redirect(
                url_for(
                    "admin_fichajes_usuario",
                    usuario_id=resultado.usuario_id,
                )
            )
        if resultado.codigo == ADMIN_EDICION_SIN_CAMBIOS:
            flash("No había cambios que guardar.", "info")
            return redirect(request.url)
        if resultado.codigo in {
            ADMIN_EDICION_ADMINISTRADOR_INEXISTENTE,
            ADMIN_EDICION_SIN_PERMISOS,
        }:
            flash("Acceso denegado.")
            return redirect(url_for("fichar"))
        if resultado.codigo == ADMIN_EDICION_FICHAJE_INEXISTENTE:
            abort(404)
        if resultado.codigo == ADMIN_EDICION_FICHAJE_ELIMINADO:
            flash("No se puede editar un fichaje eliminado.", "danger")
            if resultado.usuario_id is not None:
                return redirect(
                    url_for(
                        "admin_fichajes_usuario",
                        usuario_id=resultado.usuario_id,
                    )
                )
            return redirect(url_for("admin_fichajes"))
        if resultado.codigo == ADMIN_EDICION_USUARIO_INEXISTENTE:
            flash("El usuario del fichaje no existe.", "danger")
            return redirect(url_for("admin_fichajes"))
        if resultado.codigo == ADMIN_EDICION_FICHAJES_ACTIVOS_MULTIPLES:
            flash(
                "Existen varios fichajes activos para ese usuario y fecha.",
                "danger",
            )
            return redirect(request.url)
        if resultado.codigo in {
            ADMIN_EDICION_TRAMOS_INVALIDOS,
            ADMIN_EDICION_REGISTRO_AJENO,
            ADMIN_EDICION_CONFLICTO_CONCURRENTE,
        }:
            flash(
                resultado.mensaje or "La edición solicitada no es válida.",
                "danger",
            )
            return redirect(request.url)
        if resultado.codigo == ADMIN_EDICION_ERROR_PERSISTENCIA:
            logging.error("Error técnico al editar fichaje administrativo.")
            flash("Error procesando la edición del fichaje.", "danger")
            return redirect(request.url)
        flash("Error procesando la edición del fichaje.", "danger")
        return redirect(request.url)

    fichaje = db.get_or_404(Fichaje, fichaje_id)
    if fichaje.eliminado:
        flash("No se puede editar un fichaje eliminado.", "danger")
        return redirect(
            url_for("admin_fichajes_usuario", usuario_id=fichaje.usuario_id)
        )
    if fichaje.usuario is None:
        flash("El usuario del fichaje no existe.", "danger")
        return redirect(url_for("admin_fichajes"))
    registros_activos = (
        RegistroHorario.query.filter_by(fichaje_id=fichaje.id, eliminado=False)
        .order_by(RegistroHorario.timestamp, RegistroHorario.id)
        .all()
    )
    preparacion = preparar_edicion(reconstruir_tramos(registros_activos))
    snapshot = crear_snapshot_firmado(
        fichaje.id,
        registros_activos,
        app.config["SECRET_KEY"],
    )
    return render_template(
        "editar_fichaje_admin.html",
        fichaje=fichaje,
        tramos_editables=preparacion.tramos,
        avisos_incidencias=preparacion.avisos,
        incidencias_editables=preparacion.irregulares,
        origenes_permitidos=("Tienda", "Remoto", "Auto"),
        snapshot=snapshot,
    )


@app.route("/admin/borrar_fichaje/<int:fichaje_id>", methods=["POST"])
@login_required
def borrar_fichaje_admin(fichaje_id):
    if not current_user.admin:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))

    resultado = eliminar_fichaje_administrativo(
        db.session,
        administrador_id=current_user.id,
        fichaje_id=fichaje_id,
        snapshot=request.form.get("snapshot", ""),
        secret_key=app.config["SECRET_KEY"],
    )

    if resultado.codigo == ADMIN_BORRADO_ELIMINADO:
        flash("Fichaje eliminado correctamente.")
    elif resultado.codigo == ADMIN_BORRADO_YA_ELIMINADO:
        flash("El fichaje ya estaba eliminado.", "info")
    elif resultado.codigo in {
        ADMIN_BORRADO_ADMINISTRADOR_INEXISTENTE,
        ADMIN_BORRADO_SIN_PERMISOS,
    }:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))
    elif resultado.codigo == ADMIN_BORRADO_FICHAJE_INEXISTENTE:
        abort(404)
    elif resultado.codigo == ADMIN_BORRADO_USUARIO_INEXISTENTE:
        flash("El usuario del fichaje no existe.", "danger")
        return redirect(url_for("admin_fichajes"))
    elif resultado.codigo == ADMIN_BORRADO_CONFLICTO_CONCURRENTE:
        flash(
            resultado.mensaje or "El fichaje cambió. Recarga la página.",
            "danger",
        )
    elif resultado.codigo == ADMIN_BORRADO_ERROR_PERSISTENCIA:
        logging.error("Error técnico al borrar fichaje administrativo.")
        flash("Error al borrar el fichaje.", "danger")
    else:
        flash("Error al borrar el fichaje.", "danger")

    if resultado.usuario_id is not None:
        return redirect(
            url_for(
                "admin_fichajes_usuario",
                usuario_id=resultado.usuario_id,
            )
        )
    return redirect(url_for("admin_fichajes"))


@app.route("/exportar_mis_fichajes_pdf")
@login_required
def exportar_mis_fichajes_pdf():
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    query = Fichaje.query.filter_by(usuario_id=current_user.id).filter(
        Fichaje.eliminado == False
    )

    if desde_str:
        desde = datetime.strptime(desde_str, "%Y-%m-%d").date()
        query = query.filter(Fichaje.fecha >= desde)

    if hasta_str:
        hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date()
        query = query.filter(Fichaje.fecha <= hasta)

    fichajes = query.order_by(Fichaje.fecha).all()

    data = [["Fecha", "Registros", "Total trabajado", "Incidencias"]]
    total_general = timedelta()

    for f in fichajes:
        resultado = reconstruir_tramos(f.registros)
        fila = preparar_fila_personal(f.fecha, resultado)
        total_general += fila.total

        data.append(
            [
                fila.fecha,
                fila.registros_texto,
                fila.total_texto,
                fila.incidencias_texto,
            ]
        )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=4 * cm,
        bottomMargin=3 * cm,
    )

    styles = getSampleStyleSheet()
    elementos = []

    # Tabla de fichajes
    tabla = Table(data, colWidths=[2.5 * cm, 7 * cm, 3 * cm, 3.5 * cm])
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
            ]
        )
    )

    elementos.append(tabla)
    elementos.append(Spacer(1, 0.5 * cm))

    # Total acumulado
    total_formateado = formatear_timedelta_hhmmss(total_general)

    p_total = Paragraph(f"<b>Total acumulado:</b> {total_formateado}", styles["Normal"])
    elementos.append(p_total)

    # Encabezado y pie para cada página
    def encabezado(canvas, doc):
        width, height = A4
        logo_path = os.path.join(
            os.path.dirname(__file__), "static", "logo-demo.jpg"
        )

        if os.path.exists(logo_path):
            try:
                canvas.drawImage(
                    logo_path,
                    2 * cm,
                    height - 3 * cm,
                    width=6 * cm,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception as e:
                pass  # Evitar que un error del logo rompa todo

        canvas.setFont("Helvetica-Bold", 22)
        canvas.drawCentredString(width / 2, height - 2.8 * cm, "FICHAJES")

        canvas.setFont("Helvetica", 13)
        partes = []
        if desde_str:
            partes.append(
                f"desde {datetime.strptime(desde_str, '%Y-%m-%d').strftime('%d/%m/%Y')}"
            )
        if hasta_str:
            partes.append(
                f"hasta {datetime.strptime(hasta_str, '%Y-%m-%d').strftime('%d/%m/%Y')}"
            )
        subtitulo = f"{' '.join(partes)} - {current_user.nombre}"
        canvas.drawCentredString(width / 2, height - 3.5 * cm, subtitulo)

        canvas.line(2 * cm, height - 3.9 * cm, width - 2 * cm, height - 3.9 * cm)

        # Pie
        fecha_actual = datetime.now(zona_es).strftime("%d/%m/%Y")
        canvas.setFont("Helvetica-Oblique", 8)
        canvas.drawRightString(
            width - 2 * cm, 1.5 * cm, f"Documento generado el {fecha_actual}"
        )
        canvas.drawString(
            2 * cm, 1.5 * cm, "Horario expresado en hora local (Europe/Madrid)"
        )

    # Construcción final
    doc.build(elementos, onFirstPage=encabezado, onLaterPages=encabezado)

    buffer.seek(0)
    filename = f"fichajes_{current_user.nombre.replace(' ', '_')}.pdf"
    return send_file(
        buffer, as_attachment=True, download_name=filename, mimetype="application/pdf"
    )


# Función auxiliar para formatear fechas en español
def formatear_fecha_es(fecha):
    meses = [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]
    return f"{fecha.day} de {meses[fecha.month - 1]} de {fecha.year}"


def _entrada_ausencia_desde_formulario(formulario):
    return EntradaAusencia(
        fecha_desde=formulario.get("fecha_desde"),
        fecha_hasta=formulario.get("fecha_hasta"),
        tipo=formulario.get("tipo"),
        observaciones=formulario.get("observaciones"),
        hora_desde=formulario.get("hora_desde"),
        hora_hasta=formulario.get("hora_hasta"),
    )


def _entrada_edicion_ausencia_desde_formulario(formulario):
    return EntradaEdicionAusencia(
        snapshot=formulario.get("editar_snapshot", ""),
        fecha_desde=formulario.get("fecha_desde"),
        fecha_hasta=formulario.get("fecha_hasta"),
        tipo=formulario.get("tipo"),
        observaciones=formulario.get("observaciones"),
        hora_desde=formulario.get("hora_desde"),
        hora_hasta=formulario.get("hora_hasta"),
    )


def _respuesta_error_escritura_ausencia(resultado, *, destino):
    if resultado.codigo == AUSENCIA_DATOS_INVALIDOS:
        flash(
            resultado.mensaje or "Los datos de la ausencia no son válidos.",
            "danger",
        )
    elif resultado.codigo == AUSENCIA_DUPLICADA:
        flash("Ya existe una ausencia idéntica en esas fechas.", "warning")
    elif resultado.codigo == AUSENCIA_CONFLICTO_CONCURRENTE:
        flash(
            "La ausencia fue modificada por otra operación. Recarga la página.",
            "warning",
        )
    elif resultado.codigo == AUSENCIA_SIN_CAMBIOS:
        flash("No se realizaron cambios en la ausencia.", "info")
    elif resultado.codigo in {
        AUSENCIA_BLOQUE_INEXISTENTE,
        AUSENCIA_BLOQUE_AJENO,
        AUSENCIA_SNAPSHOT_INVALIDO,
        AUSENCIA_USUARIO_INEXISTENTE,
        AUSENCIA_ADMINISTRADOR_INEXISTENTE,
    }:
        abort(404)
    elif resultado.codigo == AUSENCIA_SIN_PERMISOS:
        abort(403)
    elif resultado.codigo == AUSENCIA_ERROR_PERSISTENCIA:
        app.logger.error("No se pudo completar la escritura de la ausencia.")
        flash("No se pudo guardar la ausencia.", "danger")
    else:
        app.logger.error(
            "Resultado de ausencia no reconocido: %s",
            resultado.codigo,
        )
        flash("No se pudo guardar la ausencia.", "danger")
    return redirect(destino)


@app.route("/mis-ausencias", methods=["GET", "POST"])
@login_required
def mis_ausencias():

    if request.method == "POST":
        snapshot_edicion = request.form.get("editar_snapshot", "")
        if snapshot_edicion:
            resultado = editar_ausencia_usuario_servicio(
                usuario_id=current_user.id,
                entrada=_entrada_edicion_ausencia_desde_formulario(
                    request.form
                ),
                secret_key=app.config["SECRET_KEY"],
                session=db.session,
            )
        else:
            resultado = crear_ausencia_usuario(
                usuario_id=current_user.id,
                entrada=_entrada_ausencia_desde_formulario(request.form),
                session=db.session,
            )

        if resultado.codigo == AUSENCIA_ACTUALIZADA:
            flash("Ausencia actualizada correctamente.", "success")
        elif resultado.codigo == AUSENCIA_CREADA and resultado.cantidad == 1:
            flash("1 día de ausencia registrado correctamente.", "success")
        elif resultado.codigo == AUSENCIA_CREADA:
            flash(
                f"{resultado.cantidad} días de ausencia registrados correctamente.",
                "success",
            )
        else:
            return _respuesta_error_escritura_ausencia(
                resultado,
                destino=url_for("mis_ausencias"),
            )
        return redirect(url_for("mis_ausencias"))

    hoy = fecha_hoy_madrid()
    anyo_actual = hoy.year

    primer_dia_anyo = date(anyo_actual, 1, 1)
    ultimo_dia_anyo = date(anyo_actual, 12, 31)

    filtro_desde = request.args.get("desde", "").strip()
    filtro_hasta = request.args.get("hasta", "").strip()
    filtro_tipo = request.args.get("tipo", "").strip()

    hay_filtros = bool(filtro_desde or filtro_hasta or filtro_tipo)

    if not hay_filtros:
        filtro_desde = primer_dia_anyo.strftime("%Y-%m-%d")
        filtro_hasta = ultimo_dia_anyo.strftime("%Y-%m-%d")

    query_listado = Ausencia.query.filter_by(usuario_id=current_user.id)

    if filtro_desde:
        try:
            fecha_desde_filtro = datetime.strptime(filtro_desde, "%Y-%m-%d").date()
            query_listado = query_listado.filter(Ausencia.fecha >= fecha_desde_filtro)
        except ValueError:
            filtro_desde = ""

    if filtro_hasta:
        try:
            fecha_hasta_filtro = datetime.strptime(filtro_hasta, "%Y-%m-%d").date()
            query_listado = query_listado.filter(Ausencia.fecha <= fecha_hasta_filtro)
        except ValueError:
            filtro_hasta = ""

    if filtro_tipo:
        try:
            filtro_tipo = normalizar_tipo_ausencia(filtro_tipo)
        except ErrorValidacionAusencia:
            filtro_tipo = ""

    ausencias = query_listado.order_by(
        Ausencia.tipo,
        Ausencia.observaciones,
        Ausencia.fecha,
        Ausencia.id,
    ).all()
    if filtro_tipo:
        ausencias = [
            ausencia
            for ausencia in ausencias
            if tipo_canonico_existente(ausencia.tipo) == filtro_tipo
        ]

    ausencias_actuales = agrupar_ausencias(ausencias, hoy)
    ausencias_por_id = {ausencia.id: ausencia for ausencia in ausencias}
    for bloque in ausencias_actuales:
        bloque["fecha_texto"] = formatear_fecha_es(bloque["fecha"])
        bloque["fecha_hasta_texto"] = formatear_fecha_es(
            bloque["fecha_hasta"]
        )
        bloque["snapshot"] = crear_snapshot_ausencia_firmado(
            current_user.id,
            [ausencias_por_id[item] for item in bloque["ids"]],
            app.config["SECRET_KEY"],
        )

    ausencias_anyo_actual = (
        Ausencia.query.filter_by(usuario_id=current_user.id)
        .filter(
            Ausencia.fecha >= primer_dia_anyo,
            Ausencia.fecha <= ultimo_dia_anyo,
        )
        .order_by(
            Ausencia.tipo,
            Ausencia.observaciones,
            Ausencia.fecha,
            Ausencia.id,
        )
        .all()
    )
    saldo = calcular_saldo_vacaciones(ausencias_anyo_actual, hoy)
    saldo_utilizado = saldo["saldo_utilizado"]
    saldo_solicitado = saldo["saldo_solicitado"]
    saldo_disponible = saldo["saldo_disponible"]
    editar_tramo = session.pop("editar_tramo", None)

    current_date = hoy

    return render_template(
        "ausencias.html",
        ausencias_actuales=ausencias_actuales,
        saldo_disponible=saldo_disponible,
        saldo_solicitado=saldo_solicitado,
        saldo_utilizado=saldo_utilizado,
        editar_tramo=editar_tramo,
        current_date=current_date,
        filtro_desde=filtro_desde,
        filtro_hasta=filtro_hasta,
        filtro_tipo=filtro_tipo,
    )


# -----------------------------------------
# Eliminar ausencia (usuario)
# -----------------------------------------
@app.route("/eliminar-ausencia", methods=["POST"])
@login_required
def eliminar_ausencia_usuario():
    resultado = eliminar_ausencia_usuario_servicio(
        usuario_id=current_user.id,
        snapshot=request.form.get("snapshot", ""),
        secret_key=app.config["SECRET_KEY"],
        session=db.session,
    )
    if resultado.codigo == AUSENCIA_ELIMINADA:
        flash("Ausencia eliminada correctamente.", "success")
    else:
        return _respuesta_error_escritura_ausencia(
            resultado,
            destino=url_for("mis_ausencias"),
        )
    return redirect(url_for("mis_ausencias"))


# -----------------------------------------
# Preparar edición de ausencia (usuario)
# -----------------------------------------
@app.route("/editar-ausencia", methods=["POST"])
@login_required
def editar_ausencia_usuario():
    resultado = preparar_edicion_ausencia_usuario(
        usuario_id=current_user.id,
        snapshot=request.form.get("snapshot", ""),
        secret_key=app.config["SECRET_KEY"],
        session=db.session,
    )
    if resultado.codigo != AUSENCIA_ACTUALIZADA:
        return _respuesta_error_escritura_ausencia(
            resultado,
            destino=url_for("mis_ausencias"),
        )
    session["editar_tramo"] = resultado.edicion
    return redirect(url_for("mis_ausencias"))


@app.route("/control-horario")
@login_required
def control_horario():
    hoy = date.today()

    resultado_fichaje = resolver_fichaje_activo(
        db.session,
        usuario_id=current_user.id,
        fecha=hoy,
    )
    fichaje = resultado_fichaje.fichaje
    incidencia_fichajes_multiples = (
        resultado_fichaje.estado == LECTURA_FICHAJE_ACTIVO_MULTIPLE
    )

    registros_hoy = []
    if fichaje:
        registros_hoy = (
            RegistroHorario.query.filter_by(fichaje_id=fichaje.id, eliminado=False)
            .order_by(RegistroHorario.timestamp)
            .all()
        )

    reconstruccion = reconstruir_tramos(registros_hoy)
    tramos = [
        {
            "inicio": tramo.entrada.timestamp.strftime("%H:%M"),
            "fin": tramo.salida.timestamp.strftime("%H:%M"),
            "duracion": formatear_duracion_corta(tramo.duracion),
        }
        for tramo in reconstruccion.tramos
    ]

    return render_template(
        "control_horario.html",
        fichaje=fichaje,
        registros_hoy=registros_hoy,
        hoy=hoy,
        estado=reconstruccion.estado,
        ultima_entrada=(
            reconstruccion.ultima_entrada.timestamp
            if reconstruccion.ultima_entrada is not None
            else None
        ),
        ultima_salida=(
            reconstruccion.ultima_salida.timestamp
            if reconstruccion.ultima_salida is not None
            else None
        ),
        total_horas_minutos=formatear_horas_minutos_texto(
            reconstruccion.total_trabajado
        ),
        tramos=tramos,
        incidencias=reconstruccion.incidencias,
        incidencia_fichajes_multiples=incidencia_fichajes_multiples,
    )


@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    hoy = fecha_hoy_madrid()
    primer_dia = hoy.replace(day=1)
    ultimo_dia = (primer_dia + timedelta(days=32)).replace(
        day=1
    ) - timedelta(days=1)

    # puestos_trabajan_sabados = ["Comercial", "Mostrador", "Taller", "Mozo Almacén"]
    mostrar_sabados = True

    sabados_mes = sabados_del_mes(hoy)

    if request.method == "POST" and mostrar_sabados:
        resultado = guardar_sabados_asignados(
            db.session,
            usuario_id=current_user.id,
            fechas_solicitadas=request.form.getlist("sabados[]"),
            fecha_referencia=hoy,
        )
        if resultado.codigo == SABADOS_GUARDADOS:
            flash("Tus sábados asignados se han guardado correctamente.")
        elif resultado.codigo == SABADOS_FECHAS_INVALIDAS:
            flash("La selección de sábados no es válida.", "danger")
        elif resultado.codigo == SABADOS_USUARIO_INEXISTENTE:
            flash("El usuario ya no existe.", "danger")
            cerrar_sesion_limpia()
            return redirect(url_for("login"))
        elif resultado.codigo == SABADOS_ERROR_PERSISTENCIA:
            app.logger.error("No se pudieron guardar los sábados asignados.")
            flash("No se pudieron guardar los sábados.", "danger")
        return redirect(url_for("perfil"))

    asignados = {
        s.fecha
        for s in SabadoAsignado.query.filter_by(usuario_id=current_user.id)
        .filter(SabadoAsignado.fecha.between(primer_dia, ultimo_dia))
        .all()
    }

    return render_template(
        "perfil.html",
        mostrar_sabados=mostrar_sabados,
        sabados=sabados_mes,
        asignados=asignados,
    )


@app.route("/api/debo_fichar")
@login_required
def api_debo_fichar():
    hoy = fecha_hoy_madrid()
    resultado_fichaje = resolver_fichaje_activo(
        db.session,
        usuario_id=current_user.id,
        fecha=hoy,
    )
    if resultado_fichaje.estado == LECTURA_FICHAJE_ACTIVO_MULTIPLE:
        return {
            "debo_fichar": False,
            "estado": "incidencia",
            "codigo": "fichajes_activos_multiples",
        }

    ahora = datetime.now(zona_es).time()
    dia_semana = hoy.weekday()  # 0=lunes, ..., 5=sábado, 6=domingo
    mes = hoy.month  # agosto = 8

    # En agosto, nunca se trabaja los sábados
    if dia_semana == 5 and mes == 8:
        return {"debo_fichar": False}

    # Si hoy es sábado, solo se debe fichar si el usuario está asignado a ese sábado
    if dia_semana == 5:
        asignado = SabadoAsignado.query.filter_by(
            usuario_id=current_user.id, fecha=hoy
        ).first()
        if not asignado:
            return {"debo_fichar": False}

    # Si el usuario tiene una ausencia bloqueante hoy, no debe fichar.
    if obtener_ausencia_bloqueante_hoy(current_user.id, hoy):
        return {"debo_fichar": False}

    # Obtener registros de hoy solo cuando la cabecera es inequívoca.
    fichaje = resultado_fichaje.fichaje
    registros = []
    if fichaje:
        registros = RegistroHorario.query.filter_by(
            fichaje_id=fichaje.id, eliminado=False
        ).all()

    # Comprobar si ya ha fichado por la mañana o por la tarde
    ha_fichado_m = any(
        r.timestamp.time() <= datetime.strptime("14:00", "%H:%M").time()
        for r in registros
    )
    ha_fichado_t = any(
        r.timestamp.time() >= datetime.strptime("16:00", "%H:%M").time()
        for r in registros
    )

    # Franja crítica: 10:20–10:30 y 16:20–16:30
    debo_m = (
        datetime.strptime("10:20", "%H:%M").time()
        <= ahora
        <= datetime.strptime("10:30", "%H:%M").time()
    )
    debo_t = (
        datetime.strptime("16:20", "%H:%M").time()
        <= ahora
        <= datetime.strptime("16:30", "%H:%M").time()
    )

    # En agosto (días laborales), solo se controla la mañana
    if mes == 8:
        if debo_m and not ha_fichado_m:
            return {"debo_fichar": True}
    else:
        if (debo_m and not ha_fichado_m) or (debo_t and not ha_fichado_t):
            return {"debo_fichar": True}

    return {"debo_fichar": False}


@app.route("/admin/ausencias/<int:usuario_id>")
@login_required
def admin_ausencias_usuario(usuario_id):

    if not current_user.admin:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))

    usuario = Usuario.query.get_or_404(usuario_id)

    hoy = fecha_hoy_madrid()
    year = request.args.get("year", type=int) or hoy.year
    filtro_tipo = request.args.get("tipo", "").strip()

    inicio = date(year, 1, 1)
    fin = date(year, 12, 31)

    query = Ausencia.query.filter_by(usuario_id=usuario_id).filter(
        Ausencia.fecha.between(inicio, fin)
    )

    if filtro_tipo:
        try:
            filtro_tipo = normalizar_tipo_ausencia(filtro_tipo)
        except ErrorValidacionAusencia:
            filtro_tipo = ""

    ausencias_query = query.order_by(Ausencia.fecha, Ausencia.id).all()
    if filtro_tipo:
        ausencias_query = [
            ausencia
            for ausencia in ausencias_query
            if tipo_canonico_existente(ausencia.tipo) == filtro_tipo
        ]

    total_utilizados = 0
    total_solicitados = 0
    total_enfermedad = 0
    total_asuntos_propios = 0
    total_baja = 0
    total_medico = 0

    datos = []

    for a in ausencias_query:
        tipo = tipo_canonico_existente(a.tipo)
        if tipo == TIPO_VACACIONES:
            if a.fecha < hoy:
                total_utilizados += 1
            else:
                total_solicitados += 1

        elif tipo == TIPO_ENFERMEDAD:
            total_enfermedad += 1

        elif tipo == TIPO_ASUNTOS_PROPIOS:
            total_asuntos_propios += 1

        elif tipo == TIPO_BAJA:
            total_baja += 1

        elif tipo == TIPO_MEDICO:
            total_medico += 1

        datos.append(
            {
                "fecha": a.fecha.strftime("%d/%m/%Y"),
                "fecha_iso": a.fecha.isoformat(),
                "tipo": tipo,
                "observaciones": a.observaciones or "",
                "creado_por_admin": a.creado_por_admin,
                "hora_desde": a.hora_desde,
                "hora_hasta": a.hora_hasta,
            }
        )

    TOTAL_ANUAL = 30

    saldo_disponible = TOTAL_ANUAL - total_utilizados - total_solicitados
    total_ausencias = len(ausencias_query)

    total_no_vacaciones = (
        total_enfermedad + total_asuntos_propios + total_baja + total_medico
    )

    return render_template(
        "admin_ausencias_usuario.html",
        usuario=usuario,
        year=year,
        filtro_tipo=filtro_tipo,
        ausencias=datos,
        saldo_disponible=saldo_disponible,
        saldo_solicitado=total_solicitados,
        saldo_utilizado=total_utilizados,
        total_ausencias=total_ausencias,
        total_no_vacaciones=total_no_vacaciones,
        total_enfermedad=total_enfermedad,
        total_asuntos_propios=total_asuntos_propios,
        total_baja=total_baja,
        total_medico=total_medico,
    )


@app.route("/admin/registrar-ausencia/<int:usuario_id>", methods=["GET", "POST"])
@login_required
def admin_registrar_ausencia(usuario_id):

    if not current_user.admin:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))

    if request.method == "POST":
        resultado = crear_ausencia_administrativa(
            administrador_id=current_user.id,
            usuario_id=usuario_id,
            entrada=_entrada_ausencia_desde_formulario(request.form),
            session=db.session,
        )
        if resultado.codigo != AUSENCIA_CREADA:
            return _respuesta_error_escritura_ausencia(
                resultado,
                destino=request.url,
            )
        usuario = db.session.get(Usuario, usuario_id)
        if resultado.cantidad == 1:
            flash(
                f"1 día de ausencia registrado para {usuario.nombre}.",
                "success",
            )
        else:
            flash(
                f"{resultado.cantidad} días de ausencia registrados "
                f"para {usuario.nombre}.",
                "success",
            )
        return redirect(url_for("admin_usuarios"))

    usuario = Usuario.query.get_or_404(usuario_id)
    return render_template("admin_registrar_ausencia.html", usuario=usuario)


@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    if not current_user.admin:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))

    hoy = fecha_hoy_madrid()
    EXCLUIDOS_DASHBOARD = [7, 15]
    usuarios = (
        Usuario.query.filter(~Usuario.id.in_(EXCLUIDOS_DASHBOARD))
        .order_by(Usuario.nombre)
        .all()
    )
    datos = []

    for user in usuarios:
        resultado_fichaje = resolver_fichaje_activo(
            db.session,
            usuario_id=user.id,
            fecha=hoy,
        )
        fichaje = resultado_fichaje.fichaje
        entrada_m = salida_m = entrada_t = salida_t = ""
        reconstruccion = reconstruir_tramos(fichaje.registros if fichaje else [])
        incidencia_fichajes_multiples = (
            resultado_fichaje.estado == LECTURA_FICHAJE_ACTIVO_MULTIPLE
        )
        estado = (
            "Incidencia"
            if incidencia_fichajes_multiples
            else reconstruccion.estado
        )
        tramos_adicionales = max(0, len(reconstruccion.tramos) - 2)

        if reconstruccion.tramos:
            primer_tramo = reconstruccion.tramos[0]
            entrada_m = primer_tramo.entrada.timestamp.strftime("%H:%M")
            salida_m = primer_tramo.salida.timestamp.strftime("%H:%M")

        if len(reconstruccion.tramos) > 1:
            segundo_tramo = reconstruccion.tramos[1]
            entrada_t = segundo_tramo.entrada.timestamp.strftime("%H:%M")
            salida_t = segundo_tramo.salida.timestamp.strftime("%H:%M")

        ausencia = (
            Ausencia.query.filter_by(usuario_id=user.id, fecha=hoy)
            .order_by(Ausencia.id)
            .first()
        )
        tipo_ausencia = (
            tipo_canonico_existente(ausencia.tipo) if ausencia else None
        )
        if tipo_ausencia == TIPO_MEDICO:
            tipo_ausencia = "Médico"

        if reconstruccion.total_trabajado.total_seconds() > 0:
            total = formatear_timedelta_hhmmss(reconstruccion.total_trabajado)
            if reconstruccion.entrada_abierta is not None:
                total = f"{total} — En curso"
        elif reconstruccion.entrada_abierta is not None:
            total = "En curso"
        else:
            total = "-"

        datos.append(
            {
                "usuario_id": user.id,
                "usuario": user.nombre,
                "estado": estado,
                "entrada_m": entrada_m,
                "salida_m": salida_m,
                "entrada_t": entrada_t,
                "salida_t": salida_t,
                "total": total,
                "tramos_adicionales": tramos_adicionales,
                "ausencia": tipo_ausencia or "-",
                "incidencia_fichajes_multiples": incidencia_fichajes_multiples,
            }
        )

    return render_template("admin_dashboard.html", datos=datos, hoy=hoy)


@app.route("/cambiar-contrasena", methods=["POST"])
@login_required
def cambiar_contrasena():
    usuario = current_user._get_current_object()
    actual = request.form.get("contrasena_actual", "")
    if not check_password_hash(usuario.password_hash, actual):
        flash("La contraseña actual no es correcta.", "danger")
        return redirect(url_for("perfil"))

    try:
        nueva = validar_password(
            request.form.get("nueva_contrasena"),
            request.form.get("confirmar_contrasena"),
        )
    except ErrorValidacionAutenticacion as error:
        flash(str(error), "danger")
        return redirect(url_for("perfil"))

    try:
        usuario.password_hash = generate_password_hash(nueva)
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.error("No se pudo actualizar la contraseña del usuario.")
        flash("No se pudo actualizar la contraseña.", "danger")
        return redirect(url_for("perfil"))

    refrescar_sesion_autenticada(usuario)
    flash("Contraseña actualizada correctamente.", "success")
    return redirect(url_for("perfil"))


@app.route("/admin/crear-fichaje", methods=["GET", "POST"])
@app.route("/admin/crear-fichaje/<int:usuario_id>", methods=["GET", "POST"])
@login_required
def crear_fichaje_admin(usuario_id=None):
    if not current_user.admin:
        flash("Acceso denegado.")
        return redirect(url_for("fichar"))

    if request.method == "POST":
        usuario_formulario = request.form.get("usuario_id", "")
        try:
            if (
                not isinstance(usuario_formulario, str)
                or not usuario_formulario.isascii()
                or not usuario_formulario.isdecimal()
            ):
                raise ValueError
            usuario_solicitado = int(usuario_formulario)
            if usuario_solicitado <= 0:
                raise ValueError
        except (TypeError, ValueError):
            flash("El usuario seleccionado no existe.", "danger")
            return redirect(request.url)

        resultado = crear_fichaje_administrativo(
            db.session,
            administrador_id=current_user.id,
            usuario_id=usuario_solicitado,
            fecha=request.form.get("fecha"),
            hora_entrada=request.form.get("entrada"),
            hora_salida=request.form.get("salida"),
        )

        if resultado.codigo == ADMIN_FICHAJE_CREADO:
            flash("Fichaje creado correctamente.", "success")
            return redirect(
                url_for(
                    "admin_fichajes_usuario",
                    usuario_id=resultado.usuario_id,
                )
            )
        if resultado.codigo == ADMIN_FICHAJE_YA_EXISTENTE:
            flash(
                "Ya existe un fichaje para ese usuario en esa fecha.",
                "warning",
            )
            return redirect(
                url_for(
                    "editar_fichaje_admin",
                    fichaje_id=resultado.fichaje_id,
                )
            )
        if resultado.codigo == ADMIN_TRAMO_INVALIDO:
            flash("La hora de entrada debe ser anterior a la de salida.", "danger")
        elif resultado.codigo == ADMIN_FECHA_INVALIDA:
            flash("La fecha indicada no es válida.", "danger")
        elif resultado.codigo == ADMIN_HORAS_INVALIDAS:
            flash("Las horas indicadas no son válidas.", "danger")
        elif resultado.codigo == ADMIN_USUARIO_INEXISTENTE:
            flash("El usuario seleccionado no existe.", "danger")
        elif resultado.codigo == ADMIN_FICHAJES_ACTIVOS_MULTIPLES:
            flash(
                "Existen varios fichajes activos para ese usuario y fecha.",
                "danger",
            )
        elif resultado.codigo in {
            ADMIN_ADMINISTRADOR_INEXISTENTE,
            ADMIN_SIN_PERMISOS,
        }:
            flash("Acceso denegado.")
            return redirect(url_for("fichar"))
        elif resultado.codigo == ADMIN_ERROR_PERSISTENCIA:
            flash("Error al crear el fichaje.", "danger")
        else:
            flash("Error al crear el fichaje.", "danger")
        return redirect(request.url)

    usuarios = Usuario.query.order_by(Usuario.nombre).all()
    return render_template(
        "admin_crear_fichaje.html",
        usuarios=usuarios,
        usuario_id_preseleccionado=usuario_id,
    )
