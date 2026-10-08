import json
from pathlib import Path

import pytest

from asm_contracts.nuclei import NucleiScanParams, NucleiTarget
from asm_execution.command import CommandExecutionError
from asm_nuclei_worker.scan import _parse_findings, nuclei_input, scan_batch

# Trimmed from real nuclei v3.11.1 output.
_HTTP_ROOT = {
    "template-id": "probe-200",
    "info": {"name": "Probe 200", "severity": "info"},
    "type": "http",
    "host": "127.0.0.1",
    "port": "8091",
    "url": "http://127.0.0.1:8091",
    "matched-at": "http://127.0.0.1:8091/",
    "timestamp": "2024-01-01T00:00:00Z",
}
_HTTP_PATH = {
    **_HTTP_ROOT,
    "url": "https://127.0.0.1:8091/admin",
    "matched-at": "https://127.0.0.1:8091/admin/",
}
_TCP_PATH = {
    "template-id": "tcp-http-banner",
    "info": {"name": "TCP HTTP Banner", "severity": "info"},
    "type": "tcp",
    "host": "127.0.0.1",
    "port": "8091",
    "url": "127.0.0.1:8091/app",
    "matched-at": "127.0.0.1:8091",
    "timestamp": "2024-01-01T00:00:00Z",
}
_SSL = {
    "template-id": "tls-version",
    "info": {"name": "TLS Version", "severity": "info"},
    "type": "ssl",
    "host": "127.0.0.1",
    "port": "8091",
    "matched-at": "127.0.0.1:8091",
    "extracted-results": ["tls12"],
    "timestamp": "2024-01-01T00:00:00Z",
}
_HTTP_IPV6 = {
    **_HTTP_ROOT,
    "host": "::1",
    "port": "8092",
    "url": "http://[::1]:8092",
    "matched-at": "http://[::1]:8092/",
}

ROOT = NucleiTarget(host="127.0.0.1", port=8091)
ADMIN = NucleiTarget(host="127.0.0.1", port=8091, path="/admin")
APP = NucleiTarget(host="127.0.0.1", port=8091, path="/app")
IPV6 = NucleiTarget(host="::1", port=8092)


def _stdout(*events: dict[str, object]) -> bytes:
    return "\n".join(json.dumps(e) for e in events).encode("utf-8")


def _by_line(*targets: NucleiTarget) -> dict[str, NucleiTarget]:
    return {nuclei_input(t): t for t in targets}


@pytest.mark.parametrize(
    ("target", "line"),
    [
        (ROOT, "127.0.0.1:8091"),
        (ADMIN, "127.0.0.1:8091/admin"),
        (NucleiTarget(host="shop.com", port=443), "shop.com:443"),
        (IPV6, "[::1]:8092"),
    ],
)
def test_input_line_has_no_scheme_and_no_root_path(target: NucleiTarget, line: str) -> None:
    assert nuclei_input(target) == line


def test_each_event_type_maps_back_to_exactly_its_own_target() -> None:
    stdout = _stdout(_HTTP_ROOT, _HTTP_PATH, _TCP_PATH, _SSL, _HTTP_IPV6)

    findings = _parse_findings(stdout, _by_line(ROOT, ADMIN, APP, IPV6))

    assert [(f.template_id, f.target) for f in findings] == [
        ("probe-200", ROOT),
        ("probe-200", ADMIN),
        ("tcp-http-banner", APP),
        ("tls-version", ROOT),
        ("probe-200", IPV6),
    ]
    assert findings[3].extracted_results == ["tls12"]


def test_a_path_url_never_matches_the_root_target() -> None:
    assert _parse_findings(_stdout(_HTTP_PATH), _by_line(ROOT)) == []


def test_an_event_without_port_or_url_is_dropped_not_fatal() -> None:
    dns = {
        "template-id": "nameserver-fingerprint",
        "info": {"name": "Nameserver Fingerprint", "severity": "info"},
        "type": "dns",
        "host": "127.0.0.1",
        "matched-at": "127.0.0.1",
        "timestamp": "2024-01-01T00:00:00Z",
    }

    findings = _parse_findings(_stdout(dns, _HTTP_ROOT), _by_line(ROOT))

    assert [f.template_id for f in findings] == ["probe-200"]


def test_empty_stdout_means_no_findings() -> None:
    assert _parse_findings(b"", _by_line(ROOT)) == []


def test_a_bad_line_is_dropped_and_the_rest_still_parse() -> None:
    # A non-JSON line, a JSON line missing required fields, and one with an out-of-enum severity —
    # none of them may take down the whole batch; the good event must still come through.
    good = _stdout(_HTTP_ROOT)
    bad_severity = json.dumps(
        {**_HTTP_ROOT, "info": {"name": "Probe 200", "severity": "made-up"}}
    ).encode("utf-8")
    missing_fields = json.dumps({"host": "127.0.0.1", "port": "8091"}).encode("utf-8")
    stdout = b"not json at all\n" + bad_severity + b"\n" + missing_fields + b"\n" + good
    findings = _parse_findings(stdout, _by_line(ROOT))
    assert [f.template_id for f in findings] == ["probe-200"]


def test_null_extracted_results_becomes_empty_list() -> None:
    stdout = _stdout({**_SSL, "extracted-results": None})
    findings = _parse_findings(stdout, _by_line(ROOT))
    assert len(findings) == 1
    assert findings[0].extracted_results == []


class _FakeRunner:
    """Records the -l file as nuclei would see it, then returns `stdout` or raises `error`."""

    def __init__(self, stdout: bytes = b"", error: Exception | None = None) -> None:
        self._stdout = stdout
        self._error = error
        self.list_path: Path | None = None
        self.list_content: str | None = None

    async def run(self, command: list[str], *, timeout: float | None = None) -> bytes:
        self.list_path = Path(command[command.index("-l") + 1])
        self.list_content = self.list_path.read_text(encoding="utf-8")
        if self._error is not None:
            raise self._error
        return self._stdout


_BATCH = [NucleiTarget(host="127.0.0.1", port=8091), NucleiTarget(host="::1", port=443)]


@pytest.mark.anyio
async def test_scan_batch_writes_one_list_line_per_target_and_removes_the_file() -> None:
    runner = _FakeRunner(stdout=json.dumps(_HTTP_ROOT).encode())
    findings = await scan_batch(runner, "nuclei", _BATCH, NucleiScanParams(), 600.0)

    assert runner.list_content == "127.0.0.1:8091\n[::1]:443\n"
    assert runner.list_path is not None
    assert not runner.list_path.exists()
    assert [f.target for f in findings] == [_BATCH[0]]


@pytest.mark.anyio
async def test_scan_batch_removes_the_list_file_when_the_command_fails() -> None:
    runner = _FakeRunner(error=CommandExecutionError("boom"))
    with pytest.raises(CommandExecutionError):
        await scan_batch(runner, "nuclei", _BATCH, NucleiScanParams(), 600.0)

    assert runner.list_path is not None
    assert not runner.list_path.exists()
