"""Local mirror of scanledger's event-feed schema.

This repo doesn't depend on falcoria_scanledger, so only the fields the bridge actually reads are
redefined here.
"""

import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


class PortProtocol(StrEnum):
    """Transport protocol of a scanned port, as scanledger reports it."""

    TCP = "tcp"
    UDP = "udp"


class PortRef(BaseModel):
    """One port on the IP, identified by number and protocol."""

    number: int
    protocol: PortProtocol


class PortDetail(PortRef):
    """An open port with the service fields scanledger includes in `ports.current`."""

    service: str | None = None


class HostnameDelta(BaseModel):
    """Hostnames on the IP after the change, and which ones are new."""

    current: list[str]
    added: list[str]


class PortDelta(BaseModel):
    """Open ports on the IP after the change, and which ones are new."""

    current: list[PortDetail]
    added: list[PortRef]


class ServiceChange(BaseModel):
    """A service field that changed on a port that stayed open."""

    number: int
    protocol: PortProtocol


class IPChangedEvent(BaseModel):
    """One IP's state change, as served by scanledger's event feed."""

    event_id: uuid.UUID
    project_id: uuid.UUID
    ip: str
    scan_id: uuid.UUID | None = Field(description="Null for a manual upload, not a real scan.")
    hostnames: HostnameDelta
    ports: PortDelta
    service_changes: list[ServiceChange] = Field(default_factory=list)


class EventPage(BaseModel):
    """One page of the event feed."""

    items: list[IPChangedEvent]
    next_cursor: str


class Project(BaseModel):
    """A project as scanledger's `/projects` endpoint returns it (only the field the bridge needs)."""

    id: uuid.UUID
