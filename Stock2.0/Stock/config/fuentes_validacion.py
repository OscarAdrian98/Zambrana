"""Captura y repeticion verificable de fuentes del lote de validacion."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


VARIABLE_RAIZ = "STOCK_VALIDATION_BATCH_ROOT"
VARIABLE_MODO = "STOCK_VALIDATION_BATCH_SOURCE_MODE"
MODO_CAPTURA = "capture"
MODO_REPETICION = "replay"
MODOS_PERMITIDOS = {MODO_CAPTURA, MODO_REPETICION}


def _sha256(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _nombre_seguro(nombre_original: str | None) -> str | None:
    if not nombre_original:
        return None
    valor = str(nombre_original).strip()
    analizado = urlsplit(valor)
    ruta = analizado.path if analizado.scheme else valor
    nombre = Path(ruta.replace("\\", "/")).name
    if not re.fullmatch(r"[A-Za-z0-9._ -]{1,255}", nombre):
        return None
    return nombre


def calcular_identidad_configuracion(
    excel_config: dict,
    config_descarga: dict,
) -> str:
    """Fija los parametros sin persistir credenciales ni URLs sensibles."""

    contenido = json.dumps(
        {
            "excel": excel_config,
            "descarga": config_descarga,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return _sha256(contenido)


class AlmacenFuentesValidacion:
    """Mantiene una fuente distinta por proveedor y configuracion."""

    def __init__(self, raiz: Path, modo: str, *, raiz_proyecto=None):
        proyecto = (
            Path(raiz_proyecto).resolve()
            if raiz_proyecto is not None
            else Path(__file__).resolve().parents[2]
        )
        carpeta_tmp = (proyecto / "tmp").resolve()
        self.raiz = Path(raiz).resolve()
        try:
            self.raiz.relative_to(carpeta_tmp)
        except ValueError as error:
            raise RuntimeError(
                "El directorio del lote debe estar dentro de tmp/"
            ) from error
        if modo not in MODOS_PERMITIDOS:
            raise ValueError(f"Modo de fuentes no permitido: {modo!r}")
        self.modo = modo
        self.manifiesto_ruta = self.raiz / "fuentes_manifest.json"
        self._manifiesto = self._cargar_manifiesto()

    @classmethod
    def desde_entorno(cls):
        valor = os.environ.get(VARIABLE_RAIZ)
        if not valor:
            return None
        proyecto = Path(__file__).resolve().parents[2]
        raiz = Path(valor)
        if not raiz.is_absolute():
            raiz = proyecto / raiz
        modo = os.environ.get(VARIABLE_MODO, MODO_REPETICION)
        return cls(raiz, modo, raiz_proyecto=proyecto)

    def _cargar_manifiesto(self) -> dict:
        if not self.manifiesto_ruta.exists():
            if self.modo == MODO_REPETICION:
                raise RuntimeError(
                    f"No existe el manifiesto de fuentes: {self.manifiesto_ruta}"
                )
            return {"version": 1, "fuentes": {}}
        try:
            manifiesto = json.loads(
                self.manifiesto_ruta.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("El manifiesto de fuentes no es valido") from error
        if manifiesto.get("version") != 1:
            raise RuntimeError("Version de manifiesto no soportada")
        if not isinstance(manifiesto.get("fuentes"), dict):
            raise RuntimeError("El manifiesto no contiene fuentes validas")
        return manifiesto

    @staticmethod
    def _clave(id_proveedor: int, numero_configuracion: int) -> str:
        return f"{int(id_proveedor)}:{int(numero_configuracion)}"

    def _ruta_relativa(self, id_proveedor, numero_configuracion) -> Path:
        return Path("fuentes") / str(int(id_proveedor)) / (
            f"configuracion_{int(numero_configuracion)}.bin"
        )

    def contiene(self, id_proveedor: int, numero_configuracion: int) -> bool:
        """Indica si la asignacion ya existe sin omitir su validacion al leer."""

        clave = self._clave(id_proveedor, numero_configuracion)
        return clave in self._manifiesto["fuentes"]

    def _resolver_ruta(self, ruta_relativa: str) -> Path:
        ruta = (self.raiz / ruta_relativa).resolve()
        try:
            ruta.relative_to(self.raiz)
        except ValueError as error:
            raise RuntimeError(
                "Ruta de fuente fuera del directorio del lote"
            ) from error
        return ruta

    def capturar(
        self,
        id_proveedor: int,
        numero_configuracion: int,
        contenido: bytes,
        *,
        nombre_original: str | None = None,
        identidad_configuracion: str | None = None,
    ) -> dict:
        if self.modo != MODO_CAPTURA:
            raise RuntimeError("El almacen no esta en modo captura")
        if not contenido:
            raise RuntimeError("No se puede capturar una fuente vacia")
        clave = self._clave(id_proveedor, numero_configuracion)
        relativa = self._ruta_relativa(id_proveedor, numero_configuracion)
        ruta = self._resolver_ruta(relativa.as_posix())
        digest = _sha256(contenido)
        existente = self._manifiesto["fuentes"].get(clave)
        if existente:
            if (
                existente.get("ruta_relativa") != relativa.as_posix()
                or existente.get("sha256") != digest
                or existente.get("tamano") != len(contenido)
                or existente.get("nombre_original")
                != _nombre_seguro(nombre_original)
                or existente.get("sha256_configuracion")
                != identidad_configuracion
            ):
                raise RuntimeError(
                    "La fuente ya estaba asignada con otra identidad o contenido"
                )
            self.leer(id_proveedor, numero_configuracion)
            return existente
        if ruta.exists():
            raise RuntimeError(
                "Existe una fuente sin identidad valida en el manifiesto"
            )

        nombre_seguro = _nombre_seguro(nombre_original)
        entrada = {
            "id_proveedor": int(id_proveedor),
            "numero_configuracion": int(numero_configuracion),
            "ruta_relativa": relativa.as_posix(),
            "tamano": len(contenido),
            "sha256": digest,
            "fecha_captura": datetime.now(timezone.utc).isoformat(),
            "nombre_original": nombre_seguro,
            "sha256_configuracion": identidad_configuracion,
        }
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        self._manifiesto["fuentes"][clave] = entrada
        self._guardar_manifiesto()
        return entrada

    def leer(
        self,
        id_proveedor: int,
        numero_configuracion: int,
        *,
        nombre_original: str | None = None,
        identidad_configuracion: str | None = None,
    ) -> bytes:
        clave = self._clave(id_proveedor, numero_configuracion)
        entrada = self._manifiesto["fuentes"].get(clave)
        if not entrada:
            raise RuntimeError(
                "Falta la fuente asignada al proveedor/configuracion " + clave
            )
        relativa_esperada = self._ruta_relativa(
            id_proveedor,
            numero_configuracion,
        ).as_posix()
        if (
            entrada.get("id_proveedor") != int(id_proveedor)
            or entrada.get("numero_configuracion")
            != int(numero_configuracion)
            or entrada.get("ruta_relativa") != relativa_esperada
        ):
            raise RuntimeError("Conflicto de identidad en el manifiesto de fuentes")
        nombre_esperado = _nombre_seguro(nombre_original)
        if nombre_original is not None and (
            entrada.get("nombre_original") != nombre_esperado
        ):
            raise RuntimeError("Cambio de identidad del fichero configurado")
        if entrada.get("sha256_configuracion") != identidad_configuracion:
            raise RuntimeError("Cambio silencioso de la configuracion")
        ruta = self._resolver_ruta(entrada["ruta_relativa"])
        if not ruta.is_file():
            raise RuntimeError(f"Falta el fichero capturado: {ruta}")
        contenido = ruta.read_bytes()
        if (
            len(contenido) != entrada.get("tamano")
            or _sha256(contenido) != entrada.get("sha256")
        ):
            raise RuntimeError("La fuente capturada no supera la verificacion SHA-256")
        return contenido

    def _guardar_manifiesto(self) -> None:
        self.raiz.mkdir(parents=True, exist_ok=True)
        temporal = self.manifiesto_ruta.with_suffix(".json.tmp")
        temporal.write_text(
            json.dumps(self._manifiesto, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporal.replace(self.manifiesto_ruta)
