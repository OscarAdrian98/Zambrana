import mimetypes

import pytest

from test_exportaciones import libro_desde_respuesta, login


@pytest.mark.parametrize(
    ("endpoint", "actor"),
    [
        ("/admin/exportar_excel", "administrador"),
        ("/exportar_mis_fichajes", "usuario"),
    ],
)
def test_excel_declara_mime_aunque_el_sistema_use_octet_stream(
    client, request, monkeypatch, endpoint, actor
):
    original_guess_type = mimetypes.guess_type

    def system_guess_type(url, strict=True):
        if str(url).lower().endswith(".xlsx"):
            return "application/octet-stream", None
        return original_guess_type(url, strict=strict)

    monkeypatch.setattr(mimetypes, "guess_type", system_guess_type)
    login(client, request.getfixturevalue(actor))

    response = client.get(endpoint)

    assert "attachment;" in response.headers["Content-Disposition"]
    assert "Fichajes" in libro_desde_respuesta(response).sheetnames
