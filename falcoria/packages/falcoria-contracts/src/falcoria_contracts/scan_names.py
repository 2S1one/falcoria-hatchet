"""Hatchet workflow name, run-metadata keys, worker roles and limits shared by tasker and worker."""

from datetime import timedelta

SCAN_WORKFLOW_NAME = "scan-target"

# Longest a scan may live: queue wait plus run time. The worker sets its schedule_timeout
# from it, and tasker's run listings look back this far (Hatchet defaults to 24 h).
SCAN_MAX_AGE = timedelta(days=7)

# Run metadata keys. A run filter with several keys matches ANY of them, so every
# filter uses exactly one key; the composite PROJECT_SCAN key identifies one scan.
META_PROJECT = "project"
META_PROJECT_SCAN = "project_scan"
META_IP = "ip"

# Worker label that routes tasks: the scanner runs nmap, the uploader sends reports on.
WORKER_ROLE_LABEL = "role"
ROLE_SCANNER = "scanner"
ROLE_UPLOADER = "uploader"


def project_scan_key(project_id: str, scan_id: str) -> str:
    """Builds the single metadata value that identifies one scan within a project."""
    return f"{project_id}:{scan_id}"


def scan_id_from_key(key: str) -> str:
    """Returns the scan id from a PROJECT_SCAN metadata value."""
    return key.partition(":")[2]


def scan_run_metadata(project_id: str, scan_id: str, ip: str) -> dict[str, str]:
    """Builds the metadata attached to one scan task run."""
    return {
        META_PROJECT: project_id,
        META_PROJECT_SCAN: project_scan_key(project_id, scan_id),
        META_IP: ip,
    }
