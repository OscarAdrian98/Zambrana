"""
Servicio para cambiar estado de pedidos en PrestaShop via bridge HTTP seguro.
No usa SQL directo para respetar la logica interna de PrestaShop.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CambiarEstadoPSResult:
    ok: bool
    mensaje: str
    detalle: str = ""
    estado_aplicado: int | None = None


def cambiar_estado_pedido(
    bridge_url: str,
    bridge_token: str,
    id_order: int,
    id_order_state: int,
    send_email: bool = False,
    timeout_sec: int = 8,
) -> CambiarEstadoPSResult:
    logger.info(
        "Bridge PrestaShop request id_order=%s id_order_state=%s send_email=%s url=%s token_set=%s",
        id_order,
        id_order_state,
        send_email,
        bridge_url or "-",
        bool((bridge_token or "").strip()),
    )
    if not bridge_url.strip():
        return CambiarEstadoPSResult(
            ok=False,
            mensaje="Bridge de PrestaShop no configurado.",
            detalle="Defina PS_STATE_BRIDGE_URL en .env.",
        )
    if not bridge_token.strip():
        return CambiarEstadoPSResult(
            ok=False,
            mensaje="Token del bridge de PrestaShop no configurado.",
            detalle="Defina PS_STATE_BRIDGE_TOKEN en .env.",
        )

    payload = {
        "token": bridge_token,
        "id_order": str(id_order),
        "id_order_state": str(id_order_state),
        "send_email": "1" if send_email else "0",
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        bridge_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(req, timeout=max(2, int(timeout_sec))) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            logger.info(
                "Bridge PrestaShop HTTP ok status=%s body_preview=%s",
                getattr(resp, "status", "-"),
                raw[:300].replace("\n", " "),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("Bridge PrestaShop HTTP %s: %s", exc.code, body[:300])
        return CambiarEstadoPSResult(
            ok=False,
            mensaje=f"Error HTTP bridge PrestaShop ({exc.code}).",
            detalle=body[:300],
        )
    except urllib.error.URLError as exc:
        logger.warning("Bridge PrestaShop no alcanzable: %s", exc)
        return CambiarEstadoPSResult(
            ok=False,
            mensaje="No se pudo conectar con bridge de PrestaShop.",
            detalle=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensa adicional
        logger.exception("Error inesperado en bridge PrestaShop")
        return CambiarEstadoPSResult(
            ok=False,
            mensaje="Error inesperado al cambiar estado en PrestaShop.",
            detalle=str(exc),
        )

    try:
        parsed = json.loads(raw.lstrip("\ufeff").strip())
    except json.JSONDecodeError:
        logger.warning("Bridge PrestaShop JSON invalido body=%s", raw[:300].replace("\n", " "))
        return CambiarEstadoPSResult(
            ok=False,
            mensaje="Respuesta invalida del bridge de PrestaShop.",
            detalle=raw[:300],
        )
    logger.info("Bridge PrestaShop parsed ok=%s message=%s", bool(parsed.get("ok")), parsed.get("message"))

    ok = bool(parsed.get("ok"))
    mensaje = str(parsed.get("message") or ("Estado actualizado." if ok else "No se pudo cambiar estado."))
    detalle = str(parsed.get("detail") or "")
    estado_aplicado = parsed.get("id_order_state")
    try:
        estado_aplicado = int(estado_aplicado) if estado_aplicado is not None else None
    except (TypeError, ValueError):
        estado_aplicado = None
    return CambiarEstadoPSResult(
        ok=ok,
        mensaje=mensaje,
        detalle=detalle,
        estado_aplicado=estado_aplicado,
    )
