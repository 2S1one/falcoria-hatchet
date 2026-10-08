from asm_contracts.httpx import HttpxTarget, Scheme


def build_url(target: HttpxTarget, scheme: Scheme) -> str:
    """Build the request URL for one scheme attempt.

    Host is `hostname` if known, else `ip` — this only decides what's presented as the Host header/SNI.
    Where the connection actually goes is decided separately, in transport.pinned_client (always `ip`).
    """
    host = target.hostname or target.ip
    is_default_port = (scheme == Scheme.HTTP and target.port == 80) or (
        scheme == Scheme.HTTPS and target.port == 443
    )
    base = f"{scheme}://{host}" if is_default_port else f"{scheme}://{host}:{target.port}"
    return base + target.path
