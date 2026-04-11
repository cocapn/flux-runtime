"""Tests for FORMAT_A-G unified instruction encoding."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flux.bytecode.formats import (
    Format, Opcode, TypeField,
    encode_format_a, encode_format_b, encode_format_c,
    encode_format_d, encode_format_e, encode_format_f, encode_format_g,
    decode_instruction, opcode_table, OPCODE_FORMAT,
)


class TestFormatA:
    def test_halt(self):
        b = encode_format_a(Opcode.HALT)
        assert b == bytes([0x00])
        assert len(b) == 1
    
    def test_nop(self):
        b = encode_format_a(Opcode.NOP)
        assert b == bytes([0x01])
    
    def test_decode_halt(self):
        op, fields = decode_instruction(bytes([0x00]))
        assert op == 0x00
        assert fields["format"] == "A"
        assert fields["size"] == 1


class TestFormatB:
    def test_inc(self):
        b = encode_format_b(Opcode.INC, 3)
        assert b == bytes([0x08, 0x03])
        assert len(b) == 2
    
    def test_push(self):
        b = encode_format_b(Opcode.PUSH, 5)
        assert b == bytes([0x0C, 0x05])
    
    def test_decode_inc(self):
        op, fields = decode_instruction(bytes([0x08, 0x03]))
        assert op == 0x08
        assert fields["rd"] == 3


class TestFormatC:
    def test_sys(self):
        b = encode_format_c(Opcode.SYS, 0x01)
        assert b == bytes([0x10, 0x01])
        assert len(b) == 2
    
    def test_stripconf(self):
        b = encode_format_c(Opcode.STRIPCONF, 4)
        assert b == bytes([0x17, 0x04])
    
    def test_decode_sys(self):
        op, fields = decode_instruction(bytes([0x10, 0x02]))
        assert op == 0x10
        assert fields["imm8"] == 2


class TestFormatD:
    def test_movi(self):
        b = encode_format_d(Opcode.MOVI, 2, 42)
        assert b == bytes([0x18, 0x02, 42])
        assert len(b) == 3
    
    def test_addi(self):
        b = encode_format_d(Opcode.ADDI, 0, 10)
        assert b == bytes([0x19, 0x00, 10])
    
    def test_decode_movi(self):
        op, fields = decode_instruction(bytes([0x18, 0x02, 42]))
        assert op == 0x18
        assert fields["rd"] == 2
        assert fields["imm8"] == 42


class TestFormatE:
    def test_add(self):
        b = encode_format_e(Opcode.ADD, 0, 1, 2)
        assert b == bytes([0x20, 0x00, 0x01, 0x02])
        assert len(b) == 4
    
    def test_mul(self):
        b = encode_format_e(Opcode.MUL, 3, 4, 5)
        assert b == bytes([0x22, 0x03, 0x04, 0x05])
    
    def test_fadd(self):
        b = encode_format_e(Opcode.FADD, 0, 1, 2)
        assert b[0] == 0x30
    
    def test_conf_add(self):
        b = encode_format_e(Opcode.CONF_ADD, 0, 1, 2)
        assert b[0] == 0x60
        assert len(b) == 4
    
    def test_decode_add(self):
        op, fields = decode_instruction(bytes([0x20, 0x03, 0x04, 0x05]))
        assert op == 0x20
        assert fields["rd"] == 3
        assert fields["rs1"] == 4
        assert fields["rs2"] == 5


class TestFormatF:
    def test_movi16(self):
        b = encode_format_f(Opcode.MOVI16, 0, 1000)
        assert b[0] == 0x40
        assert len(b) == 4
        imm16 = (b[2] << 8) | b[3]
        assert imm16 == 1000
    
    def test_jmp(self):
        b = encode_format_f(Opcode.JMP, 0, -16 & 0xFFFF)
        assert b[0] == 0x43
    
    def test_decode_movi16(self):
        op, fields = decode_instruction(bytes([0x40, 0x01, 0x03, 0xE8]))
        assert op == 0x40
        assert fields["rd"] == 1
        assert fields["imm16"] == 1000


class TestFormatG:
    def test_loadoff(self):
        b = encode_format_g(Opcode.LOADOFF, 0, 1, 256)
        assert b[0] == 0x48
        assert len(b) == 5
    
    def test_decode_loadoff(self):
        op, fields = decode_instruction(bytes([0x48, 0x00, 0x01, 0x01, 0x00]))
        assert op == 0x48
        assert fields["rd"] == 0
        assert fields["rs1"] == 1
        assert fields["imm16"] == 256


class TestOpcodeTable:
    def test_table_complete(self):
        table = opcode_table()
        assert len(table) >= 60
    
    def test_confidence_flagged(self):
        table = opcode_table()
        conf_ops = [t for t in table if t["confidence"]]
        assert len(conf_ops) >= 8
        for op in conf_ops:
            assert op["hex"].startswith("0x6")
    
    def test_all_formats_represented(self):
        table = opcode_table()
        formats = {t["format"] for t in table}
        assert "A" in formats
        assert "E" in formats
        assert "F" in formats


class TestRoundTrip:
    def test_encode_decode_add(self):
        original = encode_format_e(Opcode.ADD, 3, 4, 5)
        op, fields = decode_instruction(original)
        assert op == 0x20
        assert fields["rd"] == 3
        assert fields["rs1"] == 4
        assert fields["rs2"] == 5
    
    def test_encode_decode_conf_mul(self):
        original = encode_format_e(Opcode.CONF_MUL, 0, 1, 2)
        op, fields = decode_instruction(original)
        assert op == 0x62
        assert fields["format"] == "E"
    
    def test_fibonacci_program(self):
        """Encode a small fibonacci program and verify bytecodes."""
        code = b""
        code += encode_format_d(Opcode.MOVI, 0, 1)   # R0 = 1 (a)
        code += encode_format_d(Opcode.MOVI, 1, 1)   # R1 = 1 (b)
        code += encode_format_d(Opcode.MOVI, 2, 10)   # R2 = 10 (count)
        # loop:
        code += encode_format_e(Opcode.ADD, 3, 0, 1)  # R3 = R0 + R1
        code += encode_format_e(Opcode.MOV, 0, 1, 0)   # R0 = R1
        code += encode_format_e(Opcode.MOV, 1, 3, 0)   # R1 = R3
        code += encode_format_d(Opcode.SUBI, 2, 1)     # R2 -= 1
        code += encode_format_e(Opcode.JNZ, 2, 0, 0)   # if R2 != 0: jump back
        code += encode_format_a(Opcode.HALT)
        
        # Verify it's valid bytecode
        assert len(code) == 29
        assert code[0] == 0x18  # MOVI
        assert code[-1] == 0x00  # HALT
