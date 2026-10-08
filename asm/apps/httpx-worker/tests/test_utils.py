from asm_contracts.httpx import HttpxTarget, Scheme
from asm_httpx_worker.utils import build_url


def test_build_url_uses_hostname_when_present() -> None:
    target = HttpxTarget(target_id=1, ip="1.2.3.4", port=443, hostname="example.com")
    assert build_url(target, Scheme.HTTPS) == "https://example.com/"


def test_build_url_falls_back_to_ip_without_hostname() -> None:
    target = HttpxTarget(target_id=1, ip="1.2.3.4", port=8080)
    assert build_url(target, Scheme.HTTP) == "http://1.2.3.4:8080/"


def test_build_url_omits_default_port() -> None:
    target = HttpxTarget(target_id=1, ip="1.2.3.4", port=80, hostname="example.com")
    assert build_url(target, Scheme.HTTP) == "http://example.com/"


def test_build_url_includes_non_default_port() -> None:
    target = HttpxTarget(target_id=1, ip="1.2.3.4", port=8443, hostname="example.com")
    assert build_url(target, Scheme.HTTPS) == "https://example.com:8443/"


def test_build_url_includes_path() -> None:
    target = HttpxTarget(
        target_id=1, ip="1.2.3.4", port=443, hostname="example.com", path="/health"
    )
    assert build_url(target, Scheme.HTTPS) == "https://example.com/health"
