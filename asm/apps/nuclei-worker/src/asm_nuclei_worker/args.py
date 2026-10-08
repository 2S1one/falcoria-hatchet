"""Pure nuclei command building: batch inputs -> argv for a shell-free subprocess."""

from pathlib import Path

from asm_contracts.nuclei import NucleiScanParams

FIXED_ARGS: tuple[str, ...] = ("-jsonl", "-omit-raw", "-omit-template", "-silent", "-no-color")
"""Always-on nuclei flags: compact JSONL output the result parser reads, and plain console output."""


def build_command(nuclei_path: str, list_path: Path, params: NucleiScanParams) -> list[str]:
    """Builds the full nuclei invocation for a batch; one list item per shell word."""
    args = [
        nuclei_path,
        "-l",
        str(list_path),
        *FIXED_ARGS,
        "-rl",
        str(params.rate_limit),
        "-rld",
        params.rate_limit_duration,
        "-bs",
        str(params.bulk_size),
        "-c",
        str(params.concurrency),
        # "-hbs" / "-headc": commented out with NucleiProtocolType.HEADLESS until headless is supported.
        "-jsc",
        str(params.js_concurrency),
        "-pc",
        str(params.payload_concurrency),
        "-prc",
        str(params.probe_concurrency),
        "-tlc",
        str(params.template_loading_concurrency),
        "-timeout",
        str(params.timeout),
        "-retries",
        str(params.retries),
    ]
    if params.templates:
        args += ["-t", ",".join(params.templates)]
    if params.severity:
        args += ["-s", ",".join(params.severity)]
    if params.exclude_severity:
        args += ["-es", ",".join(params.exclude_severity)]
    if params.protocol_types:
        args += ["-pt", ",".join(params.protocol_types)]
    if params.tags:
        args += ["-tags", ",".join(params.tags)]
    if params.headers:
        for name, value in params.headers.items():
            args += ["-H", f"{name}: {value}"]
    if params.sni is not None:
        args += ["-sni", params.sni]
    if params.no_interactsh:
        args.append("-ni")
    if params.disable_update_check:
        args.append("-duc")
    return args
