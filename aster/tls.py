"""自签名 TLS 证书与上下文。"""

from __future__ import annotations

import ipaddress
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from .util import ensure_dir, get_interface_ips


@dataclass
class TLSMaterial:
    cert_path: Path
    key_path: Path
    fingerprint: str
    san_ips: tuple[str, ...]


def _san_names(ips: Iterable[str]) -> tuple[list[str], list[ipaddress.IPv4Address]]:
    dns: list[str] = ["localhost"]
    try:
        host = socket.gethostname()
        if host and host not in dns:
            dns.append(host)
    except OSError:
        pass
    ip_objects: list[ipaddress.IPv4Address] = []
    seen: set[str] = set()
    for raw in ["127.0.0.1", *ips]:
        try:
            addr = ipaddress.ip_address(str(raw))
        except ValueError:
            continue
        if str(addr) not in seen:
            seen.add(str(addr))
            ip_objects.append(addr)  # type: ignore[arg-type]
    return dns, ip_objects


def _cert_covers(cert: x509.Certificate, dns: list[str], ips: list[ipaddress.IPv4Address]) -> bool:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False
    existing_dns = set(san.get_values_for_type(x509.DNSName))
    existing_ips = {str(x) for x in san.get_values_for_type(x509.IPAddress)}
    return set(dns).issubset(existing_dns) and all(str(ip) in existing_ips for ip in ips)


def ensure_cert(data_dir: Path | str, extra_ips: Iterable[str] = ()) -> TLSMaterial:
    """生成/复用自签名证书。IP 变化时重新生成。"""
    cert_dir = ensure_dir(Path(data_dir) / "certs")
    cert_path = cert_dir / "aster-cert.pem"
    key_path = cert_dir / "aster-key.pem"
    ips = list(extra_ips) or get_interface_ips()
    dns, ip_objects = _san_names(ips)
    if cert_path.is_file() and key_path.is_file():
        try:
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            if _cert_covers(cert, dns, ip_objects):
                return TLSMaterial(cert_path, key_path, cert.fingerprint(hashes.SHA256()).hex(), tuple(str(x) for x in ip_objects))
        except Exception:
            pass

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Aster"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Aster 星流"),
        ]
    )
    now = datetime.now(timezone.utc)
    san = x509.SubjectAlternativeName(
        [x509.DNSName(name) for name in dns]
        + [x509.IPAddress(ip) for ip in ip_objects]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(san, critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return TLSMaterial(cert_path, key_path, cert.fingerprint(hashes.SHA256()).hex(), tuple(str(x) for x in ip_objects))


def server_context(material: TLSMaterial) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(material.cert_path), str(material.key_path))
    return ctx


def client_context() -> ssl.SSLContext:
    # 自签名证书：加密传输，但不做 CA 链校验（首次使用需接受浏览器警告）。
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
