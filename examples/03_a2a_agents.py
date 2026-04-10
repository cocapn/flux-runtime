#!/usr/bin/env python3
"""FLUX A2A Agents — Agent-to-Agent Communication Protocol.

Demonstrates FLUX's agent-to-agent messaging system using the binary
A2A message format with trust tokens, capabilities, and priority levels.

Run:
    PYTHONPATH=src python3 examples/03_a2a_agents.py
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

# ── ANSI helpers ──────────────────────────────────────────────────────────

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(text: str) -> None:
    width = 64
    print()
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")
    print(f"{BOLD}{MAGENTA}  {text}{RESET}")
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")


def info(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}")


def warn(text: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {text}")


def detail(text: str) -> None:
    print(f"    {DIM}{text}{RESET}")


def section(text: str) -> None:
    print()
    print(f"{BOLD}{CYAN}── {text} {'─' * (56 - len(text))}{RESET}")


# ══════════════════════════════════════════════════════════════════════════
# Simulated Agent
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class SimulatedAgent:
    """A simulated FLUX agent that can send/receive A2A messages."""
    name: str
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    trust_scores: dict = field(default_factory=dict)  # peer_id → score (0-1000)
    inbox: list = field(default_factory=list)
    messages_sent: int = 0
    messages_received: int = 0

    def send_tell(self, receiver: "SimulatedAgent", payload: bytes,
                  priority: int = 5, trust_token: int = 500,
                  capability_token: int = 100) -> bytes:
        """Send a TELL message (fire-and-forget) to another agent."""
        from flux.a2a.messages import A2AMessage
        from flux.bytecode.opcodes import Op

        msg = A2AMessage(
            sender=self.agent_id,
            receiver=receiver.agent_id,
            conversation_id=uuid.uuid4(),
            in_reply_to=None,
            message_type=Op.TELL,
            priority=priority,
            trust_token=trust_token,
            capability_token=capability_token,
            payload=payload,
        )
        raw = msg.to_bytes()
        receiver.inbox.append(msg)
        self.messages_sent += 1
        receiver.messages_received += 1

        # Update trust: small increase for successful sends
        self.trust_scores[receiver.agent_id] = min(
            1000, self.trust_scores.get(receiver.agent_id, 500) + 10
        )
        return raw

    def send_ask(self, receiver: "SimulatedAgent", payload: bytes,
                 priority: int = 8, trust_token: int = 700,
                 capability_token: int = 200) -> bytes:
        """Send an ASK message (request-response) to another agent."""
        from flux.a2a.messages import A2AMessage
        from flux.bytecode.opcodes import Op

        msg = A2AMessage(
            sender=self.agent_id,
            receiver=receiver.agent_id,
            conversation_id=uuid.uuid4(),
            in_reply_to=None,
            message_type=Op.ASK,
            priority=priority,
            trust_token=trust_token,
            capability_token=capability_token,
            payload=payload,
        )
        raw = msg.to_bytes()
        receiver.inbox.append(msg)
        self.messages_sent += 1
        receiver.messages_received += 1

        # Higher trust needed for ASK
        self.trust_scores[receiver.agent_id] = min(
            1000, self.trust_scores.get(receiver.agent_id, 500) + 20
        )
        return raw

    def reply(self, original: "A2AMessage", payload: bytes,
              trust_token: int = 0, capability_token: int = 0) -> bytes:
        """Reply to a received message."""
        from flux.a2a.messages import A2AMessage
        from flux.bytecode.opcodes import Op

        reply_msg = A2AMessage(
            sender=self.agent_id,
            receiver=original.sender,
            conversation_id=original.conversation_id,
            in_reply_to=original.sender,
            message_type=Op.DELEGATE_RESULT,
            priority=original.priority,
            trust_token=trust_token,
            capability_token=capability_token,
            payload=payload,
        )
        raw = reply_msg.to_bytes()
        self.messages_sent += 1
        return raw

    def process_inbox(self) -> list:
        """Process all messages in the inbox."""
        processed = list(self.inbox)
        self.inbox.clear()
        return processed

    @property
    def trust_score(self) -> float:
        """Average trust score."""
        if not self.trust_scores:
            return 0.0
        return sum(self.trust_scores.values()) / len(self.trust_scores)


# ══════════════════════════════════════════════════════════════════════════
# Main Demo
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print(f"{BOLD}{YELLOW}{'╔' + '═' * 62 + '╗'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  FLUX A2A Agents — Agent-to-Agent Protocol          {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  Binary messages with trust, capabilities & priority {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'╚' + '═' * 62 + '╝'}{RESET}")

    from flux.a2a.messages import A2AMessage
    from flux.bytecode.opcodes import Op

    # ── Create agents ─────────────────────────────────────────────────
    section("Step 1: Create Agent Trio")

    producer = SimulatedAgent(name="Producer")
    transformer = SimulatedAgent(name="Transformer")
    consumer = SimulatedAgent(name="Consumer")

    info(f"Created 3 agents:")
    for agent in [producer, transformer, consumer]:
        detail(f"  {agent.name:12s}  UUID={str(agent.agent_id)[:8]}...")

    # ── Demonstrate message creation ──────────────────────────────────
    section("Step 2: A2A Message Anatomy")

    msg = A2AMessage(
        sender=producer.agent_id,
        receiver=transformer.agent_id,
        conversation_id=uuid.uuid4(),
        in_reply_to=None,
        message_type=Op.TELL,
        priority=5,
        trust_token=750,
        capability_token=100,
        payload=b"DATA:[42, 43, 44, 45]",
    )

    info(f"Created A2A TELL message:")
    detail(f"  Sender:       {str(msg.sender)[:16]}...")
    detail(f"  Receiver:     {str(msg.receiver)[:16]}...")
    detail(f"  Conv ID:      {str(msg.conversation_id)[:16]}...")
    detail(f"  Message Type: 0x{msg.message_type:02X} (TELL)")
    detail(f"  Priority:     {msg.priority} (0-15)")
    detail(f"  Trust Token:  {msg.trust_token} (uint32)")
    detail(f"  Cap Token:    {msg.capability_token} (uint32)")
    detail(f"  Payload:      {msg.payload}")
    detail(f"  Header Size:  {msg.HEADER_SIZE} bytes")

    # ── Serialize / deserialize round-trip ────────────────────────────
    section("Step 3: Binary Serialization Round-Trip")

    raw_bytes = msg.to_bytes()
    info(f"Serialized: {len(raw_bytes)} bytes")
    detail(f"  " + " ".join(f"{b:02X}" for b in raw_bytes[:20]) + " ...")

    reconstructed = A2AMessage.from_bytes(raw_bytes)
    info(f"Deserialized successfully!")
    info(f"  Sender matches:    {reconstructed.sender == msg.sender}")
    info(f"  Receiver matches:  {reconstructed.receiver == msg.receiver}")
    info(f"  Type matches:      {reconstructed.message_type == msg.message_type}")
    info(f"  Payload matches:   {reconstructed.payload == msg.payload}")
    info(f"  Size match:        {len(raw_bytes) >= A2AMessage.HEADER_SIZE}")

    # ── Multi-agent communication ─────────────────────────────────────
    section("Step 4: Multi-Agent Communication Flow")

    info("Producer → Transformer (TELL): send raw data")
    raw = producer.send_tell(transformer, b"BATCH:[1,2,3,4,5]")
    detail(f"  Wire format: {len(raw)} bytes")

    info("Transformer → Consumer (ASK): request processing")
    raw = transformer.send_ask(consumer, b"PROCESS:BATCH")
    detail(f"  Wire format: {len(raw)} bytes")

    msgs = consumer.process_inbox()
    info(f"Consumer received {len(msgs)} message(s)")

    if msgs:
        last_msg = msgs[-1]
        info("Consumer replies to Transformer:")
        reply_raw = consumer.reply(last_msg, b"RESULT:sum=15,avg=3.0")
        detail(f"  Reply wire format: {len(reply_raw)} bytes")

    # ── Trust score evolution ────────────────────────────────────────
    section("Step 5: Trust Score Evolution")

    info("Simulating 10 message exchanges to observe trust growth...")

    trust_history = []
    for i in range(10):
        producer.send_tell(transformer, f"MSG_{i}".encode())
        transformer.send_tell(consumer, f"MSG_{i}".encode())
        avg_trust = (producer.trust_score + transformer.trust_score + consumer.trust_score) / 3
        trust_history.append(avg_trust)

    info("Trust history (average across all agents):")
    print(f"    {DIM}Gen  {'Trust':>8s}  Bar{RESET}")
    for i, t in enumerate(trust_history):
        bar_len = int(t / 1000 * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        color = GREEN if t > 700 else YELLOW if t > 500 else RED
        print(f"    {i+1:3d}  {t:7.1f}  {color}{bar}{RESET}")

    # ── Protocol opcodes summary ──────────────────────────────────────
    section("Step 6: A2A Protocol Opcodes")

    a2a_opcodes = {
        "TELL": Op.TELL,
        "ASK": Op.ASK,
        "DELEGATE": Op.DELEGATE,
        "DELEGATE_RESULT": Op.DELEGATE_RESULT,
        "REPORT_STATUS": Op.REPORT_STATUS,
        "BROADCAST": Op.BROADCAST,
        "REDUCE": Op.REDUCE,
        "DECLARE_INTENT": Op.DECLARE_INTENT,
        "TRUST_CHECK": Op.TRUST_CHECK,
        "TRUST_UPDATE": Op.TRUST_UPDATE,
        "CAP_REQUIRE": Op.CAP_REQUIRE,
        "CAP_GRANT": Op.CAP_GRANT,
        "BARRIER": Op.BARRIER,
    }

    info(f"A2A protocol opcodes (0x60-0x7B range):")
    for name, opcode in a2a_opcodes.items():
        detail(f"  0x{opcode:02X}  {name}")

    # ── Summary ───────────────────────────────────────────────────────
    section("Summary")
    info("Messages sent:")
    detail(f"  Producer:    {producer.messages_sent}")
    detail(f"  Transformer: {transformer.messages_sent}")
    detail(f"  Consumer:    {consumer.messages_sent}")

    info("Messages received:")
    detail(f"  Producer:    {producer.messages_received}")
    detail(f"  Transformer: {transformer.messages_received}")
    detail(f"  Consumer:    {consumer.messages_received}")

    info("Average trust scores:")
    detail(f"  Producer:    {producer.trust_score:.1f} / 1000")
    detail(f"  Transformer: {transformer.trust_score:.1f} / 1000")
    detail(f"  Consumer:    {consumer.trust_score:.1f} / 1000")

    print()
    print(f"{BOLD}{GREEN}── Done! ──{RESET}")
    print()
