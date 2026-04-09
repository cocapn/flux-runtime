"""Typed message envelopes for the FLUX agent communication protocol.

Messages are structured as typed envelopes that carry metadata (sender,
receiver, conversation context) alongside a typed payload.  The four
message kinds are:

- **Request**: A callable message expecting a Response.
- **Response**: A reply to a Request, carrying a result or error.
- **Event**: A fire-and-forget notification.
- **Error**: A structured error message with code and details.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ── Message kind enum ───────────────────────────────────────────────────────


class MessageKind(enum.IntEnum):
    """The kind of protocol message."""
    REQUEST = 0x01
    RESPONSE = 0x02
    EVENT = 0x03
    ERROR = 0x04


# ── Message ID ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MessageId:
    """Unique message identifier backed by a UUID."""

    value: uuid.UUID = field(default_factory=uuid.uuid4)

    @classmethod
    def from_bytes(cls, data: bytes) -> MessageId:
        """Create a MessageId from 16 raw bytes."""
        if len(data) != 16:
            raise ValueError(f"MessageId requires exactly 16 bytes, got {len(data)}")
        return cls(value=uuid.UUID(bytes=data))

    @classmethod
    def from_hex(cls, hex_str: str) -> MessageId:
        """Create a MessageId from a hex string."""
        return cls(value=uuid.UUID(hex=hex_str))

    def to_bytes(self) -> bytes:
        """Serialize to 16 bytes."""
        return self.value.bytes

    def __repr__(self) -> str:
        return f"MessageId({self.value})"


# ── Base envelope ───────────────────────────────────────────────────────────


@dataclass
class MessageEnvelope:
    """Base message envelope with routing metadata.

    Attributes
    ----------
    id : MessageId
        Unique message identifier.
    sender : str
        Name of the sending agent.
    receiver : str
        Name of the receiving agent (empty for broadcast).
    conversation_id : str
        Groups related messages together.
    timestamp : float
        Unix timestamp of message creation.
    kind : MessageKind
        The type of message.
    payload : dict
        Structured message payload.
    metadata : dict
        Additional metadata (headers, tracing info, etc.).
    """

    id: MessageId = field(default_factory=MessageId)
    sender: str = ""
    receiver: str = ""
    conversation_id: str = ""
    timestamp: float = field(default_factory=time.time)
    kind: MessageKind = MessageKind.EVENT
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.conversation_id:
            self.conversation_id = self.id.value.hex[:16]

    @property
    def is_request(self) -> bool:
        return self.kind == MessageKind.REQUEST

    @property
    def is_response(self) -> bool:
        return self.kind == MessageKind.RESPONSE

    @property
    def is_error(self) -> bool:
        return self.kind == MessageKind.ERROR

    def reply(self, payload: Dict[str, Any], **metadata) -> MessageEnvelope:
        """Create a response envelope replying to this message."""
        return MessageEnvelope(
            sender=self.receiver,
            receiver=self.sender,
            conversation_id=self.conversation_id,
            kind=MessageKind.RESPONSE,
            payload=payload,
            metadata={"in_reply_to": self.id.to_bytes().hex(), **metadata},
        )

    def as_error(self, code: int, message: str, details: str = "") -> Error:
        """Create an error reply to this message."""
        return Error(
            id=MessageId(),
            sender=self.receiver,
            receiver=self.sender,
            conversation_id=self.conversation_id,
            kind=MessageKind.ERROR,
            payload={"code": code, "message": message, "details": details},
            metadata={"in_reply_to": self.id.to_bytes().hex()},
            error_code=code,
            error_message=message,
            error_details=details,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "id": self.id.to_bytes().hex(),
            "sender": self.sender,
            "receiver": self.receiver,
            "conversation_id": self.conversation_id,
            "timestamp": self.timestamp,
            "kind": int(self.kind),
            "payload": self.payload,
            "metadata": self.metadata,
        }


# ── Request ─────────────────────────────────────────────────────────────────


@dataclass
class Request(MessageEnvelope):
    """A callable message expecting a Response.

    Attributes
    ----------
    method : str
        The method or action being requested.
    expects_reply : bool
        Whether a reply is expected.
    timeout_ms : int
        Request timeout in milliseconds (0 = no timeout).
    """

    method: str = ""
    expects_reply: bool = True
    timeout_ms: int = 0

    def __post_init__(self) -> None:
        self.kind = MessageKind.REQUEST
        super().__post_init__()

    @classmethod
    def create(
        cls,
        sender: str,
        receiver: str,
        method: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 0,
        **metadata,
    ) -> Request:
        """Convenience factory for creating a request."""
        return cls(
            sender=sender,
            receiver=receiver,
            method=method,
            payload=payload or {},
            timeout_ms=timeout_ms,
            metadata=metadata,
        )


# ── Response ────────────────────────────────────────────────────────────────


@dataclass
class Response(MessageEnvelope):
    """A reply to a Request.

    Attributes
    ----------
    success : bool
        Whether the request was handled successfully.
    """

    success: bool = True

    def __post_init__(self) -> None:
        self.kind = MessageKind.RESPONSE
        super().__post_init__()

    @classmethod
    def create(
        cls,
        request: MessageEnvelope,
        payload: Optional[Dict[str, Any]] = None,
        success: bool = True,
        **metadata,
    ) -> Response:
        """Convenience factory for creating a response to a request."""
        return cls(
            sender=request.receiver,
            receiver=request.sender,
            conversation_id=request.conversation_id,
            payload=payload or {},
            success=success,
            metadata={"in_reply_to": request.id.to_bytes().hex(), **metadata},
        )


# ── Event ───────────────────────────────────────────────────────────────────


@dataclass
class Event(MessageEnvelope):
    """A fire-and-forget notification.

    Attributes
    ----------
    event_type : str
        The type/category of event.
    """

    event_type: str = ""

    def __post_init__(self) -> None:
        self.kind = MessageKind.EVENT
        super().__post_init__()

    @classmethod
    def create(
        cls,
        sender: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        receiver: str = "",
        **metadata,
    ) -> Event:
        """Convenience factory for creating an event."""
        return cls(
            sender=sender,
            receiver=receiver,
            event_type=event_type,
            payload=payload or {},
            metadata=metadata,
        )


# ── Error ───────────────────────────────────────────────────────────────────


@dataclass
class Error(MessageEnvelope):
    """A structured error message.

    Attributes
    ----------
    error_code : int
        Machine-readable error code.
    error_message : str
        Human-readable error description.
    error_details : str
        Additional error context.
    """

    error_code: int = 0
    error_message: str = ""
    error_details: str = ""

    def __post_init__(self) -> None:
        self.kind = MessageKind.ERROR
        if not self.payload:
            self.payload = {
                "code": self.error_code,
                "message": self.error_message,
                "details": self.error_details,
            }
        super().__post_init__()

    @classmethod
    def create(
        cls,
        error_code: int,
        error_message: str,
        sender: str = "",
        receiver: str = "",
        details: str = "",
    ) -> Error:
        """Convenience factory for creating an error message."""
        return cls(
            sender=sender,
            receiver=receiver,
            error_code=error_code,
            error_message=error_message,
            error_details=details,
        )
