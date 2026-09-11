from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from base64 import urlsafe_b64encode

# Generar clave privada EC
private_key = ec.generate_private_key(ec.SECP256R1())

# Exportar clave privada en formato PEM
pem_private_key = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
).decode()

# Obtener clave pública
public_key = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)

# Codificar claves en Base64 URL-safe
vapid_private_key_b64 = urlsafe_b64encode(
    private_key.private_numbers().private_value.to_bytes(32, 'big')
).decode()

vapid_public_key_b64 = urlsafe_b64encode(public_key).decode()

print("🔐 Clave privada VAPID:")
print(vapid_private_key_b64)
print("\n🔑 Clave pública VAPID:")
print(vapid_public_key_b64)