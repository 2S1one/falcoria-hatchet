import pytest
from pydantic import ValidationError

from falcoria_contracts.enums import PortProtocol
from falcoria_contracts.scan_options import OpenPortsOpts, ServiceOpts


@pytest.mark.parametrize("ports", [["22"], ["1000-2000"], ["22", "80", "1-65535"]])
def test_open_ports_accepts_valid_ports(ports: list[str]) -> None:
    assert OpenPortsOpts(ports=ports).ports == ports


@pytest.mark.parametrize(
    "ports",
    [[], ["0"], ["65536"], ["abc"], ["10-"], ["1-2-3"], ["2000-1000"], ["0-10"], ["1-65536"]],
)
def test_open_ports_rejects_invalid_ports(ports: list[str]) -> None:
    with pytest.raises(ValidationError):
        OpenPortsOpts(ports=ports)


def test_service_opts_rejects_out_of_range_intensity() -> None:
    with pytest.raises(ValidationError):
        ServiceOpts(version_intensity=10)


def test_open_ports_defaults() -> None:
    opts = OpenPortsOpts(ports=["22", "80"])

    assert opts.transport_protocol is PortProtocol.TCP
    assert opts.skip_host_discovery is True


def test_service_opts_defaults() -> None:
    opts = ServiceOpts()

    assert opts.aggressive_scan is False
    assert opts.traceroute is False
