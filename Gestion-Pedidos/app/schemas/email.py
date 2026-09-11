"""
schemas/email.py - DTOs para envio de correo desde pedido.
"""
from pydantic import BaseModel, field_validator


class EmailPedidoRequestDTO(BaseModel):
    id_pedido: int
    to_email: str
    subject: str
    body: str

    @field_validator("to_email")
    @classmethod
    def validar_to_email(cls, value: str) -> str:
        email = (value or "").strip()
        if not email or "@" not in email or "." not in email.split("@")[-1]:
            raise ValueError("Email destino invalido.")
        return email

    @field_validator("subject")
    @classmethod
    def validar_subject(cls, value: str) -> str:
        subject = (value or "").strip()
        if not subject:
            raise ValueError("El asunto no puede estar vacio.")
        return subject

    @field_validator("body")
    @classmethod
    def validar_body(cls, value: str) -> str:
        body = (value or "").strip()
        if not body:
            raise ValueError("El cuerpo del correo no puede estar vacio.")
        return body
