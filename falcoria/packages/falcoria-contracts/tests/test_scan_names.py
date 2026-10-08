from falcoria_contracts.scan_names import (
    META_IP,
    META_PROJECT,
    META_PROJECT_SCAN,
    project_scan_key,
    scan_id_from_key,
    scan_run_metadata,
)


def test_project_scan_key_joins_ids() -> None:
    assert project_scan_key("p1", "s1") == "p1:s1"


def test_project_scan_key_differs_when_ids_swap() -> None:
    assert project_scan_key("a", "b") != project_scan_key("b", "a")


def test_scan_run_metadata_has_one_value_per_key() -> None:
    assert scan_run_metadata("p1", "s1", "10.0.0.1") == {
        META_PROJECT: "p1",
        META_PROJECT_SCAN: "p1:s1",
        META_IP: "10.0.0.1",
    }


def test_scan_id_from_key_inverts_project_scan_key() -> None:
    assert scan_id_from_key(project_scan_key("p1", "s1")) == "s1"
