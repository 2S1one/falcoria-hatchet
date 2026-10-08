from pathlib import Path

import pytest
from pydantic import ValidationError

from asm_contracts.nuclei import NucleiProtocolType, NucleiScanParams, NucleiSeverity
from asm_nuclei_worker.args import FIXED_ARGS, build_command


def _command(params: NucleiScanParams) -> list[str]:
    return build_command("nuclei", Path("in.txt"), params)


def _values_of(command: list[str], flag: str) -> list[str]:
    return [command[i + 1] for i, arg in enumerate(command) if arg == flag]


def test_required_flags_only_when_optionals_are_none() -> None:
    command = _command(NucleiScanParams())

    assert command == [
        "nuclei",
        "-l",
        "in.txt",
        *FIXED_ARGS,
        "-rl",
        "150",
        "-rld",
        "1s",
        "-bs",
        "25",
        "-c",
        "25",
        "-jsc",
        "120",
        "-pc",
        "25",
        "-prc",
        "50",
        "-tlc",
        "50",
        "-timeout",
        "10",
        "-retries",
        "1",
        "-ni",
        "-duc",
    ]


def test_toggles_follow_params() -> None:
    command = _command(NucleiScanParams(no_interactsh=True, disable_update_check=False))

    assert "-ni" in command
    assert "-duc" not in command


def test_templates_are_comma_joined() -> None:
    command = _command(NucleiScanParams(templates=["a/", "b/"]))

    assert _values_of(command, "-t") == ["a/,b/"]


def test_severity_is_comma_joined() -> None:
    command = _command(
        NucleiScanParams(templates=["a/"], severity=[NucleiSeverity.HIGH, NucleiSeverity.CRITICAL])
    )

    assert _values_of(command, "-s") == ["high,critical"]


def test_new_filters_are_comma_joined() -> None:
    params = NucleiScanParams(
        exclude_severity=[NucleiSeverity.INFO, NucleiSeverity.LOW],
        protocol_types=[NucleiProtocolType.HTTP, NucleiProtocolType.SSL],
        tags=["cve", "rce"],
    )
    command = _command(params)

    assert _values_of(command, "-es") == ["info,low"]
    assert _values_of(command, "-pt") == ["http,ssl"]
    assert _values_of(command, "-tags") == ["cve,rce"]


def test_speed_fields_are_passed_as_given() -> None:
    command = _command(NucleiScanParams(concurrency=5, rate_limit_duration="500ms"))

    assert _values_of(command, "-c") == ["5"]
    assert _values_of(command, "-rld") == ["500ms"]


@pytest.mark.parametrize(
    "bad",
    [{"rate_limit": 0}, {"concurrency": 1001}, {"retries": -1}, {"rate_limit_duration": "1h"}],
)
def test_out_of_range_params_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        NucleiScanParams.model_validate(bad)


def test_each_header_is_its_own_repeated_flag() -> None:
    params = NucleiScanParams(templates=["a/"], headers={"Host": "x.com", "Scan": "Falcoria"})

    assert _values_of(_command(params), "-H") == ["Host: x.com", "Scan: Falcoria"]


def test_sni_is_passed_when_set() -> None:
    command = _command(NucleiScanParams(templates=["a/"], sni="x.com"))

    assert _values_of(command, "-sni") == ["x.com"]


def test_redirects_are_left_to_templates() -> None:
    assert "-dr" not in _command(NucleiScanParams(templates=["a/"]))
