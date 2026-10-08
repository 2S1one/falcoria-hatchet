from enum import StrEnum


class ScannerName(StrEnum):
    """Which scanner produced a result.

    Not carried on task inputs — each scanner has its own task type, and the task's registered
    name is what selects which scanner runs a given task.
    """

    HTTPX = "httpx"
    NUCLEI = "nuclei"
