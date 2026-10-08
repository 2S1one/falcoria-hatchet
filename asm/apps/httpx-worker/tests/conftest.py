import shutil
import subprocess

import pytest


@pytest.fixture(scope="session")
def tls_cert(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, str]:
    """Generate a throwaway self-signed cert/key pair for TLS test servers, via the openssl CLI."""
    cert_dir = tmp_path_factory.mktemp("tls")
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"
    openssl = shutil.which("openssl")
    if openssl is None:
        raise RuntimeError("openssl not found on PATH")
    subprocess.run(  # noqa: S603 — fixed argv, no user input; test-only cert generation
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=test",
        ],
        check=True,
        capture_output=True,
    )
    return str(cert_path), str(key_path)
