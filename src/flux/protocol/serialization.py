"""Message serialization to/from bytecode-compatible binary format.

The FLUX protocol uses a compact binary encoding for message envelopes
that is compatible with the bytecode instruction format.  Messages are
serialized as a header followed by a variable-length payload section.
"""

from __future__ import annotations

import json
import struct
import uuid
from typing import Any, Dict, List, Optional

from .message import (
    MessageEnvelope,
    MessageKind,
    MessageId,
    Request,
    Response,
    Event,
    Error,
)


# ── Binary format constants ────────────────────────────────────────────────

# Magic bytes for FLUX protocol messages
PROTOCOL_MAGIC = b"FLXP"

# Header format: magic(4) + version(2) + kind(1) + flags(1) +
#                msg_id(16) + conv_id(16) + sender_len(2) + receiver_len(2) +
#                timestamp(8) + payload_len(4) + metadata_len(4)
# = 4 + 2 + 1 + 1 + 16 + 16 + 2 + 2 + 8 + 4 + 4 = 60 bytes
HEADER_STRUCT = struct.Struct("<4sHBB16s16sHHdII")
HEADER_SIZE = HEADER_STRUCT.size  # 60 bytes

# Protocol version
PROTOCOL_VERSION = 1

# Flags
FLAG_HAS_METADATA = 0x01
FLAG_COMPRESSED = 0x02


# ── Serializer ──────────────────────────────────────────────────────────────


class MessageSerializer:
    """Base class for message serializers."""

    def serialize(self, envelope: MessageEnvelope) -> bytes:
        """Serialize a message envelope to bytes."""
        raise NotImplementedError

    def deserialize(self, data: bytes) -> MessageEnvelope:
        """Deserialize bytes to a message envelope."""
        raise NotImplementedError


# ── Binary codec ────────────────────────────────────────────────────────────


class BinaryMessageCodec(MessageSerializer):
    """Serialize/deserialize message envelopes to a compact binary format.

    Binary layout:

        Offset  Size     Field
        ─────── ──────── ──────────────────────────────────────────
        0       4        Magic (b'FLXP')
        4       2        Protocol version (uint16 LE)
        6       1        Message kind (uint8)
        7       1        Flags (uint8)
        8       16       Message ID (UUID bytes)
        24      16       Conversation ID (first 16 chars as bytes, padded)
        40      2        Sender name length (uint16 LE)
        42      2        Receiver name length (uint16 LE)
        44      8        Timestamp (double LE)
        52      4        Payload length (uint32 LE)
        56      4        Metadata length (uint32 LE)
        60      var      Sender name (UTF-8)
        var     var      Receiver name (UTF-8)
        var     var      Payload (JSON bytes)
        var     var      Metadata (JSON bytes)
    """

    def serialize(self, envelope: MessageEnvelope) -> bytes:
        """Serialize a message envelope to binary."""
        msg_id_bytes = envelope.id.to_bytes()

        # Conversation ID: first 16 chars, zero-padded to 16 bytes
        conv_str = envelope.conversation_id[:16]
        conv_bytes = conv_str.encode("utf-8").ljust(16, b"\x00")[:16]

        sender_bytes = envelope.sender.encode("utf-8")
        receiver_bytes = envelope.receiver.encode("utf-8")

        # Merge type-specific fields into payload for serialization
        payload = dict(envelope.payload)
        if isinstance(envelope, Request):
            payload.setdefault("method", envelope.method)
            payload.setdefault("timeout_ms", envelope.timeout_ms)
        elif isinstance(envelope, Event):
            payload.setdefault("event_type", envelope.event_type)
        elif isinstance(envelope, Response):
            payload.setdefault("success", envelope.success)
        elif isinstance(envelope, Error):
            payload.setdefault("code", envelope.error_code)
            payload.setdefault("message", envelope.error_message)
            payload.setdefault("details", envelope.error_details)

        payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        metadata_json = json.dumps(envelope.metadata, separators=(",", ":")).encode("utf-8")

        flags = 0
        if envelope.metadata:
            flags |= FLAG_HAS_METADATA

        header = HEADER_STRUCT.pack(
            PROTOCOL_MAGIC,
            PROTOCOL_VERSION,
            int(envelope.kind),
            flags,
            msg_id_bytes,
            conv_bytes,
            len(sender_bytes),
            len(receiver_bytes),
            envelope.timestamp,
            len(payload_json),
            len(metadata_json),
        )

        return header + sender_bytes + receiver_bytes + payload_json + metadata_json

    def deserialize(self, data: bytes) -> MessageEnvelope:
        """Deserialize binary data to a message envelope.

        Raises ``ValueError`` if the data is too short or has an invalid magic.
        """
        if len(data) < HEADER_SIZE:
            raise ValueError(
                f"BinaryMessageCodec: need at least {HEADER_SIZE} bytes, "
                f"got {len(data)}"
            )

        (magic, version, kind_val, flags,
         msg_id_bytes, conv_bytes,
         sender_len, receiver_len,
         timestamp, payload_len, metadata_len) = HEADER_STRUCT.unpack_from(data, 0)

        if magic != PROTOCOL_MAGIC:
            raise ValueError(
                f"Invalid magic: expected {PROTOCOL_MAGIC!r}, got {magic!r}"
            )

        if version != PROTOCOL_VERSION:
            raise ValueError(
                f"Unsupported version: expected {PROTOCOL_VERSION}, got {version}"
            )

        offset = HEADER_SIZE

        # Extract sender
        sender_bytes = data[offset:offset + sender_len]
        sender = sender_bytes.decode("utf-8")
        offset += sender_len

        # Extract receiver
        receiver_bytes = data[offset:offset + receiver_len]
        receiver = receiver_bytes.decode("utf-8")
        offset += receiver_len

        # Extract payload
        payload_bytes = data[offset:offset + payload_len]
        payload = json.loads(payload_bytes.decode("utf-8")) if payload_len > 0 else {}
        offset += payload_len

        # Extract metadata
        metadata_bytes = data[offset:offset + metadata_len]
        metadata = json.loads(metadata_bytes.decode("utf-8")) if metadata_len > 0 else {}

        # Reconstruct IDs
        msg_id = MessageId.from_bytes(msg_id_bytes)
        conv_id = conv_bytes.rstrip(b"\x00").decode("utf-8")

        # Determine message kind
        try:
            kind = MessageKind(kind_val)
        except ValueError:
            kind = MessageKind.EVENT

        # Build the envelope — strip type-specific fields from payload
        if kind == MessageKind.REQUEST:
            clean_payload = {k: v for k, v in payload.items()
                           if k not in ("method", "timeout_ms")}
            envelope = Request(
                id=msg_id,
                sender=sender,
                receiver=receiver,
                conversation_id=conv_id,
                timestamp=timestamp,
                payload=clean_payload,
                metadata=metadata,
                method=payload.get("method", ""),
                timeout_ms=payload.get("timeout_ms", 0),
            )
        elif kind == MessageKind.RESPONSE:
            clean_payload = {k: v for k, v in payload.items()
                           if k not in ("success",)}
            envelope = Response(
                id=msg_id,
                sender=sender,
                receiver=receiver,
                conversation_id=conv_id,
                timestamp=timestamp,
                payload=clean_payload,
                metadata=metadata,
                success=payload.get("success", True),
            )
        elif kind == MessageKind.ERROR:
            clean_payload = {k: v for k, v in payload.items()
                           if k not in ("code", "message", "details")}
            envelope = Error(
                id=msg_id,
                sender=sender,
                receiver=receiver,
                conversation_id=conv_id,
                timestamp=timestamp,
                payload=clean_payload,
                metadata=metadata,
                error_code=payload.get("code", 0),
                error_message=payload.get("message", ""),
                error_details=payload.get("details", ""),
            )
        else:
            clean_payload = {k: v for k, v in payload.items()
                           if k not in ("event_type",)}
            envelope = Event(
                id=msg_id,
                sender=sender,
                receiver=receiver,
                conversation_id=conv_id,
                timestamp=timestamp,
                payload=clean_payload,
                metadata=metadata,
                event_type=payload.get("event_type", ""),
            )

        return envelope

    @staticmethod
    def encode_message_batch(messages: List[MessageEnvelope]) -> bytes:
        """Encode a batch of messages as length-prefixed entries.

        Each message is prefixed with its total length (uint32 LE).
        """
        codec = BinaryMessageCodec()
        parts = []
        for msg in messages:
            msg_bytes = codec.serialize(msg)
            parts.append(struct.pack("<I", len(msg_bytes)))
            parts.append(msg_bytes)
        return b"".join(parts)

    @staticmethod
    def decode_message_batch(data: bytes) -> List[MessageEnvelope]:
        """Decode a batch of length-prefixed messages."""
        codec = BinaryMessageCodec()
        messages = []
        offset = 0
        while offset + 4 <= len(data):
            msg_len = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            if offset + msg_len > len(data):
                break
            msg_bytes = data[offset:offset + msg_len]
            offset += msg_len
            try:
                msg = codec.deserialize(msg_bytes)
                messages.append(msg)
            except (ValueError, json.JSONDecodeError):
                continue  # skip malformed messages
        return messages
