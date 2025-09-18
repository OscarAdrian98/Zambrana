# 🕒 Proyecto: Sistema de Control Horario (Fichaje)

## 📌 Descripción

Este proyecto es una aplicación web desarrollada en **Python + Flask** que permite gestionar el control horario de los empleados de una empresa. Está diseñado para registrar las entradas y salidas diarias (mañana y tarde), controlar las ausencias (vacaciones, enfermedad, etc.) y generar avisos si los empleados no han fichado.

Incluye también **scripts automatizados** para enviar avisos por **Discord** y **notificaciones push al móvil** a los empleados que aún no han fichado según su horario previsto, con reglas adaptadas al mes de agosto y a los sábados.

---

## 🚀 Funcionalidades Principales

- Registro de fichajes por tramos: entrada/salida mañana y tarde.
- Panel de administrador para:
  - Ver historial de fichajes.
  - Registrar ausencias.
  - Asignar sábados laborales.
  - Consultar hoja diaria de asistencia.
- Visualización del perfil del usuario y sábados asignados.
- Exportación de fichajes en PDF y Excel.
- Avisos automáticos por Discord y notificaciones push:
  - A los 10 minutos de la hora objetivo si no han fichado.
  - Reglas personalizadas por usuario, día de la semana, agosto y sábados.
- Logs completos de actividad para auditoría.

---

## 🧰 Tecnologías utilizadas

- **Backend:** Python 3.11, Flask, SQLAlchemy, Waitress
- **Frontend:** HTML, Bootstrap 5, jQuery
- **Base de datos:** MySQL (con SQLAlchemy ORM)
- **Notificaciones:** Discord Webhooks + Web Push (pywebpush)
- **Otros:** logging, datetime, requests, pytz

---

## 📂 Estructura del Proyecto

```
📂 fichaje/
├── app/
│   ├── models.py          # Modelos: Usuario, Fichaje, Ausencia, etc.
│   ├── routes.py          # Rutas principales de la app Flask
│   ├── templates/         # Plantillas HTML (fichar, resumen, perfil, admin)
│   ├── static/            # Archivos CSS, JS, logos
├── scripts/
│   ├── avisos_discord.py      # Script que avisa si no han fichado (por tramo)
│   └── notificaciones_push.py # Script que envía notificaciones web push
├── run_server.py          # Lanzador principal con Waitress
├── config.py              # Configuración del sistema
└── requirements.txt
```

---

## ⚙️ Automatización de avisos

El sistema incluye dos scripts ejecutables automáticamente con **cron** (Linux) o **NSSM** (Windows):

### 🔔 `avisos_discord.py`

- Envía avisos a un canal de Discord si un empleado no ha fichado en el tramo correspondiente.
- Considera:
  - Usuarios con jornada completa o solo mañana.
  - Si es agosto, se omite el tramo de tarde.
  - Si es sábado, solo notifica a los asignados ese día.
  - Vacaciones (consultadas en la base de datos).
- Genera logs (`log_avisos_fichaje.log`).

### 📲 `notificaciones_push.py`

- Lee el archivo `avisos.json` con los avisos pendientes (generado por el anterior).
- Carga las suscripciones Web Push desde una URL (`suscripciones.json`).
- Envía una notificación push personalizada a cada dispositivo registrado.

---

## 🏁 Ejecución

### ▶️ Local (desarrollo)

```bash
python run_server.py
```

### ⚙️ Producción

```bash
waitress-serve --host 0.0.0.0 --port 5000 app:app
```

---

## ✅ Estado actual

- Sistema en producción, operativo y en uso real.
- Uso diario por empleados y administradores.
- Totalmente responsive para dispositivos móviles.

---

## 🔒 Seguridad y privacidad

- Contraseñas cifradas.
- Logs de todas las acciones.
- Separación de permisos entre usuarios y administrador.
- Sistema de eliminación lógica (soft delete) para trazabilidad legal.

---

## 🧐 Futuras mejoras

- Panel de métricas con gráficos de asistencia.
- Gestión de permisos por rol.
- Integración con calendario de Google o Outlook.
- Control de fichaje por ubicación/IP.

---

## 📩 Contacto

Si quieres saber más sobre este sistema o colaborar:

- **Autor:** Oscar Adrián Ramírez
- **Email:** oscar@mxzambrana.com
- **LinkedIn:** [linkedin.com/in/oscarbackend](https://www.linkedin.com/in/oscarbackend)