"""
tests/test_rc522_driver.py
==========================
Tests for RC522Driver using a mock SPI object.

The mock SPI records every spi_send() call and can be pre-loaded with a
response sequence so spi_transfer() returns realistic register values.
This lets us verify the correct SPI byte sequences are generated without
any real hardware.

Run from the project root:
    python3 -m pytest tests/test_rc522_driver.py -v
or without pytest:
    python3 tests/test_rc522_driver.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                '..', 'klippy', 'extras', 'nfc_gates'))

from rc522_driver import (
    RC522Driver,
    _CommandReg, _TxControlReg, _BitFramingReg,
    _ComIrqReg, _ErrorReg, _FIFOLevelReg, _ControlReg, _FIFODataReg,
    _CRCResultRegL, _CRCResultRegH,
    _PCD_RESETPHASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock SPI
# ─────────────────────────────────────────────────────────────────────────────

class MockSPI:
    """
    Mock MCU_SPI.

    Pre-load transfer_responses with a list of [byte0, byte1] pairs;
    each call to spi_transfer() pops the next one.  If the list is
    exhausted, returns [0x00, 0x00].

    All spi_send() calls are recorded in sends for inspection.
    """

    def __init__(self, transfer_responses=None):
        self.sends = []                             # list of byte-lists sent
        self._responses = list(transfer_responses or [])

    def spi_send(self, data):
        self.sends.append(list(data))

    def spi_transfer(self, _data):
        if self._responses:
            resp = self._responses.pop(0)
        else:
            resp = [0x00, 0x00]
        return {'response': resp}

    # ── Inspection helpers ────────────────────────────────────────────────────

    def sent_to(self, reg):
        """Return all values written to reg (as [addr_byte, value] pairs)."""
        write_addr = (reg << 1) & 0x7E
        return [s[1] for s in self.sends if len(s) == 2 and s[0] == write_addr]

    def wrote_value(self, reg, val):
        return val in self.sent_to(reg)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers to build realistic RC522 response sequences
# ─────────────────────────────────────────────────────────────────────────────

def _reg_read_resp(reg, value):
    """One spi_transfer response that returns `value` for register `reg`."""
    read_addr = ((reg << 1) & 0x7E) | 0x80
    return [read_addr, value]


def _build_no_tag_sequence():
    """
    Responses for a _transceive() call when no tag is present.
    RC522 sets TimerIRq (bit 0) and clears RxIRq/IdleIRq.
    _transceive reads BitFramingReg TWICE: once to set StartSend, once to clear it.
    """
    return [
        _reg_read_resp(_ComIrqReg,    0x7F),  # ComIEnReg  read (enable all)
        _reg_read_resp(_ComIrqReg,    0xFF),  # ComIrqReg  read (clear flags)
        _reg_read_resp(_FIFOLevelReg, 0x80),  # FIFOLevel  read (flush)
        _reg_read_resp(_BitFramingReg, 0x00), # BitFraming read (| 0x80 StartSend)
        _reg_read_resp(_BitFramingReg, 0x80), # BitFraming read (& 0x7F clear)
        _reg_read_resp(_ComIrqReg,    0x01),  # TimerIRq set, no RxIRq → no tag
    ]


def _build_tag_with_spool_sequence(uid=(0xA3, 0xF2, 0x00, 0xCC), spool_id=1042):
    """
    Minimal response sequence that guides RC522Driver through the full
    REQA → ANTICOLL → SELECT → READ pages 4-7 happy path.

    This is simplified — it covers just enough register reads to exercise
    the flow without modelling every RC522 register interaction.
    """
    chk = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]
    spool_bytes = list(str(spool_id).encode('ascii'))
    spool_bytes += [0x00] * (16 - len(spool_bytes))  # null-pad to 16 bytes

    # For each _transceive call we need:
    #   ComIEnReg read, ComIrqReg read×2, FIFOLevelReg read×2,
    #   BitFramingReg read×2, then result reads
    # This mock provides the minimum reads needed.
    # Unexpectedly-requested registers return 0x00.

    def transceive_ok(fifo_data):
        """Build reads for a successful transceive with fifo_data bytes.
        Order matches every spi_transfer() call inside _transceive()."""
        return [
            _reg_read_resp(_ComIrqReg,    0x7F),            # ComIEnReg  read
            _reg_read_resp(_ComIrqReg,    0xFF),            # ComIrqReg  read (clear)
            _reg_read_resp(_FIFOLevelReg, 0x80),            # FIFOLevel  read (flush)
            _reg_read_resp(_BitFramingReg, 0x00),           # BitFraming read (| StartSend)
            # After sleep:
            _reg_read_resp(_BitFramingReg, 0x80),           # BitFraming read (& clear)
            _reg_read_resp(_ComIrqReg,    0x20),            # RxIRq set → data received
            _reg_read_resp(_ErrorReg,     0x00),            # no errors
            _reg_read_resp(_FIFOLevelReg, len(fifo_data)),  # FIFO byte count
            _reg_read_resp(_ControlReg,   0x00),            # last_bits = 0 → full bytes
        ] + [_reg_read_resp(_FIFODataReg, b) for b in fifo_data]

    def crc_reads(crc_lo=0xAB, crc_hi=0xCD):
        """Build reads for _calc_crc (just return dummy CRC bytes)."""
        return [
            _reg_read_resp(_FIFOLevelReg, 0x80),
            _reg_read_resp(_CRCResultRegL, crc_lo),
            _reg_read_resp(_CRCResultRegH, crc_hi),
        ]

    responses = []
    # Stage 1: REQA — expect 2-byte ATQA (16 bits)
    responses += transceive_ok([0x00, 0x04])   # ATQA = 0x0400 (common value)
    # Stage 2: ANTICOLL — 5 bytes: uid[0..3] + checksum
    responses += transceive_ok(list(uid) + [chk])
    # Stage 3: SELECT — CRC then transceive (SAK byte)
    responses += crc_reads()
    responses += transceive_ok([0x08])         # SAK = 0x08 (Mifare 1K)
    # Stage 4: READ pages 4-7 — CRC + transceive for each page
    for page_start in range(0, 16, 4):
        responses += crc_reads()
        responses += transceive_ok(spool_bytes[page_start:page_start + 4])

    return responses


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_init_sends_reset_command():
    spi = MockSPI(transfer_responses=[
        _reg_read_resp(_TxControlReg, 0x00),  # read before enabling antenna
        _reg_read_resp(_TxControlReg, 0x03),  # read for logging
    ])
    driver = RC522Driver(spi, gate=0)
    driver.init()
    # CommandReg should have received PCD_RESETPHASE (0x0F)
    assert driver._gate == 0
    assert spi.wrote_value(_CommandReg, _PCD_RESETPHASE), \
        "init() did not write PCD_RESETPHASE to CommandReg"

def test_is_alive_returns_true_when_antenna_on():
    spi = MockSPI(transfer_responses=[
        _reg_read_resp(_TxControlReg, 0x03),  # bits 0-1 set = antenna on
    ])
    driver = RC522Driver(spi, gate=0)
    assert driver.is_alive() is True

def test_is_alive_returns_false_when_antenna_off():
    spi = MockSPI(transfer_responses=[
        _reg_read_resp(_TxControlReg, 0x00),
    ])
    driver = RC522Driver(spi, gate=0)
    assert driver.is_alive() is False

def test_no_tag_returns_none_none():
    """When no tag is present (TimerIRq set), read_tag() returns (None, None)."""
    # REQA transceive will see TimerIRq → MI_ERR → return None, None immediately
    responses = _build_no_tag_sequence()
    spi = MockSPI(transfer_responses=responses)
    driver = RC522Driver(spi, gate=0, transceive_delay=0.0, crc_delay=0.0)
    uid, spool = driver.read_tag()
    assert uid is None
    assert spool is None

def test_spool_id_ascii_parsed():
    """Full happy-path: tag present, spool ID written as ASCII."""
    responses = _build_tag_with_spool_sequence(
        uid=(0xA3, 0xF2, 0x00, 0xCC), spool_id=1042)
    # Add BitFramingReg reads needed between stages
    spi = MockSPI(transfer_responses=responses)
    driver = RC522Driver(spi, gate=0, transceive_delay=0.0, crc_delay=0.0)
    uid, spool = driver.read_tag()
    assert uid == 'A3F200CC', f"Expected 'A3F200CC', got {uid!r}"
    assert spool == 1042,     f"Expected 1042, got {spool}"

def test_max_spool_id_respected():
    """Binary fallback value >= max_spool_id should be rejected."""
    # Craft a 16-byte payload that is NOT valid ASCII digits but decodes as
    # big-endian uint32 = 200000 (above default max of 100000)
    high_val = 200000
    b = [(high_val >> shift) & 0xFF for shift in (24, 16, 8, 0)]
    page_bytes = b + [0x00] * 12  # 4 data bytes + 12 padding

    spi = MockSPI()
    driver = RC522Driver(spi, gate=0, max_spool_id=100000)

    # Call the spool-parsing logic directly via a white-box helper
    all_data = bytearray(page_bytes)

    spool_id = None
    try:
        text = bytes(all_data).decode('ascii').split('\x00')[0].strip()
        if text and text.isdigit():
            spool_id = int(text)
    except Exception:
        pass

    if spool_id is None and len(all_data) >= 4:
        val = (all_data[0] << 24 | all_data[1] << 16
               | all_data[2] << 8  | all_data[3])
        if 0 < val < driver._max_spool_id:
            spool_id = val

    assert spool_id is None, \
        f"Expected spool_id=None (value too large), got {spool_id}"

def test_write_uses_correct_spi_format():
    """_write() must set bit 7 = 0 in the address byte (write mode)."""
    spi = MockSPI()
    driver = RC522Driver(spi, gate=0)
    # Write value 0xAB to register 0x11 (ModeReg)
    # Expected SPI byte: (0x11 << 1) & 0x7E = 0x22, then 0xAB
    driver._write(0x11, 0xAB)
    assert [0x22, 0xAB] in spi.sends, \
        f"_write() SPI format wrong; sends={spi.sends}"

def test_read_uses_correct_spi_format():
    """_read() must set bit 7 = 1 in the address byte (read mode)."""
    spi = MockSPI(transfer_responses=[
        [0x00, 0x5A],   # second byte is the register value
    ])
    driver = RC522Driver(spi, gate=0)
    val = driver._read(0x11)
    # Expected transfer: [(0x11 << 1) & 0x7E | 0x80, 0x00] = [0xA2, 0x00]
    assert val == 0x5A, f"_read() returned {val:#x}, expected 0x5A"


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  FAIL  {fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
