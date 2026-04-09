"""A2A Message Types — Fixed-format binary messages for agent-to-agent communication.

Message layout (binary, 52-byte header):

    Offset  Size   Field
    ─────── ────── ──────────────────────────────────────
    0       16     sender_uuid        (128-bit UUID)
    16      16     receiver_uuid      (128-bit UUID)
    32       8     conversation_id    (compact 64-bit)
    40       1     message_type       (uint8, 0x60–0x7B)
    41       1     priority           (uint8, 0–15)
    42       4     trust_token        (uint32 LE)
    46       4     capability_token   (uint32 LE)
    50       2     in_reply_to        (uint16 LE, 0 = None)
    52      var    payload            (arbitrary bytes)
"""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass, field
from typing import Optional

# Header format: <16s16s8sBBIIH  = 16+16+8+1+1+4+4+2 = 52
_HEADER_STRUCT = struct.Struct("<16s16s8sBBIIH")


# ── A2A Message ───────────────────────────────────────────────────────────


@dataclass
class A2AMessage:
    """Fixed-format binary A2A message with a 52-byte header.

    Attributes
    ----------
    sender : uuid.UUID
        128-bit UUID of the originating agent.
    receiver : uuid.UUID
        128-bit UUID of the target agent.
    conversation_id : uuid.UUID
        128-bit UUID grouping related messages.  Serialized as the first
        8 bytes (time_low + time_mid) for compactness; zero-padded on
        deserialization.
    in_reply_to : Optional[uuid.UUID]
        When set, marks this message as a reply.  Serialized as a uint16
        extracted from the UUID bytes; deserialized as None when zero.
    message_type : int
        Protocol verb in range 0x60–0x7B (A2A opcode space).
    priority : int
        Delivery priority 0–15.
    trust_token : int
        32-bit unsigned trust evidence token.
    capability_token : int
        32-bit unsigned capability evidence token.
    payload : bytes
        Arbitrary application-level payload.
    """

    sender: uuid.UUID
    receiver: uuid.UUID
    conversation_id: uuid.UUID
    in_reply_to: Optional[uuid.UUID]
    message_type: int
    priority: int
    trust_token: int
    capability_token: int
    payload: bytes = b""

    HEADER_SIZE: int = 52  # fixed header length in bytes

    # ── Validation helpers ────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if not (0x60 <= self.message_type <= 0x7B):
            raise ValueError(
                f"message_type must be in 0x60–0x7B, got 0x{self.message_type:02X}"
            )
        if not (0 <= self.priority <= 15):
            raise ValueError(
                f"priority must be 0–15, got {self.priority}"
            )
        if not (0 <= self.trust_token <= 0xFFFFFFFF):
            raise ValueError(
                f"trust_token must fit in uint32, got {self.trust_token}"
            )
        if not (0 <= self.capability_token <= 0xFFFFFFFF):
            raise ValueError(
                f"capability_token must fit in uint32, got {self.capability_token}"
            )

    # ── Serialization ─────────────────────────────────────────────────────

    def to_bytes(self) -> bytes:
        """Serialize to binary (52-byte header + payload).

        The compact header drops the low 8 bytes of *conversation_id* and
        reduces *in_reply_to* to a uint16 tag (0 when None).
        """
        # conversation_id → first 8 bytes of UUID (time_low + time_mid + time_hi)
        conv_bytes = self.conversation_id.bytes[:8]

        # in_reply_to → uint16 from first 2 bytes, 0 if None
        reply_u16 = 0
        if self.in_reply_to is not None:
            reply_u16 = int.from_bytes(
                self.in_reply_to.bytes[:2], byteorder="little"
            )

        header = _HEADER_STRUCT.pack(
            self.sender.bytes,
            self.receiver.bytes,
            conv_bytes,
            self.message_type,
            self.priority,
            self.trust_token,
            self.capability_token,
            reply_u16,
        )
        return header + self.payload

    @classmethod
    def from_bytes(cls, data: bytes) -> A2AMessage:
        """Deserialize from binary.

        Raises ``ValueError`` if the buffer is shorter than 52 bytes.
        """
        if len(data) < cls.HEADER_SIZE:
            raise ValueError(
                f"A2AMessage requires at least {cls.HEADER_SIZE} bytes, "
                f"got {len(data)}"
            )

        (sender_b, receiver_b, conv_b, msg_type, prio,
         trust_tok, cap_tok, reply_u16) = _HEADER_STRUCT.unpack_from(data, 0)

        # Reconstruct full UUIDs from compact fields
        sender = uuid.UUID(bytes=sender_b)
        receiver = uuid.UUID(bytes=receiver_b)
        conversation_id = uuid.UUID(bytes=conv_b + b"\x00" * 8)

        # Reconstruct in_reply_to
        in_reply_to = None
        if reply_u16 != 0:
            in_reply_to = uuid.UUID(
                bytes=reply_u16.to_bytes(2, byteorder="little") + b"\x00" * 14
            )

        payload = data[cls.HEADER_SIZE:]

        return cls(
            sender=sender,
            receiver=receiver,
            conversation_id=conversation_id,
            in_reply_to=in_reply_to,
            message_type=msg_type,
            priority=prio,
            trust_token=trust_tok,
            capability_token=cap_tok,
            payload=payload,
        )

    def __repr__(self) -> str:
        return (
            f"A2AMessage(type=0x{self.message_type:02X}, "
            f"sender={self.sender}, receiver={self.receiver}, "
            f"conv={self.conversation_id}, "
            f"priority={self.priority}, "
            f"payload_len={len(self.payload)})"
        )
