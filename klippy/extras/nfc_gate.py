# klippy/extras/nfc_gate.py
#
# One [nfc_gate laneN] section per EMU gate — mirrors the pattern of
# [temperature_sensor Lane_N] in emu_macros.cfg.
#
# Each section manages a single PN532 NFC reader on the I2C bus of one EBB42
# lane board.  The lane MCUs (lane0, lane1, …) are already declared in
# mmu_hardware.cfg by Happy Hare; this module never re-defines them.
#
# Integration model — UID lookup via Spoolman
# ─────────────────────────────────────────────────────────
# Tags are NEVER written to.  Stick a blank NFC tag on each spool.
# Scan the tag's UID with your phone and paste it into the "rfid" extra
# field on the matching spool record in Spoolman.  When a tag is presented
# the reader reads only the UID (one NFC round-trip), then this module
# queries the Spoolman REST API to find which spool carries that UID.
#
#   tag (blank)  →  PN532 reads UID  →  Spoolman API lookup  →  spool_id
#                                                                     │
#                                                         MMU_GATE_MAP GATE=N SPOOLMAN_ID=X
#
# Spoolman setup (one-time, per spool)
# ─────────────────────────────────────
# 1. In Spoolman: Settings → Extra fields → Spool → Add field
#      Field name: rfid    Type: Text
# 2. For each spool: open the spool record, set "rfid" to the tag UID
#    (uppercase hex, no separators — exactly as NFC_GATE_STATUS reports it,
#     e.g.  04A23BC1D45E80 ).
#    You can scan the tag UID with the NFC Tools app (Android/iOS) or any
#    NFC reader app — you only need the UID, not to write anything.
#
# Architecture
# ────────────
# emu_macros.cfg has BME280 temperature sensors wired to each lane's software
# I2C bus (PB3 = SCL, PB4 = SDA, address 0x76).  The PN532 uses address 0x24,
# so both sensors share the same two wires with no conflict.
#
#   [nfc_gate lane0]          [nfc_gate lane1]          ...
#        │                         │
#   lane0 MCU (EBB42)         lane1 MCU (EBB42)
#   PB3 SCL / PB4 SDA         PB3 SCL / PB4 SDA
#   PN532 @ 0x24               PN532 @ 0x24
#   BME280 @ 0x76 (existing)   BME280 @ 0x76 (existing)
#        │ CAN                      │ CAN
#   ─────┴──────────────────────────┴──── CAN bus ────> klippy (Pi)
#
# Each [nfc_gate] instance has its own background polling thread.
# GCode macros are dispatched to the Klipper reactor thread via
# reactor.register_callback(), keeping the polling thread non-blocking.
#
# NFC_GATE_STATUS reports all configured gates in one command.
#
# Install
# ───────
# 1. Copy klippy/extras/nfc_gates/  to  ~/klipper/klippy/extras/nfc_gates/
# 2. Copy klippy/extras/nfc_gate.py to  ~/klipper/klippy/extras/nfc_gate.py
# 3. Copy config/nfc_macros.cfg to ~/printer_data/config/macros/<id>/nfc_macros.cfg
# 4. Add [include macros/<id>/nfc_macros.cfg] to printer.cfg
# 5. sudo systemctl restart klipper

import logging
import threading

import extras.bus as bus_module

from nfc_gates.pn532_driver      import PN532Driver
from nfc_gates.gate_state        import GateState
from nfc_gates.klipper_interface import KlipperInterface
from nfc_gates.spoolman_client   import SpoolmanClient


# Module-level registry — each load_config() call appends its NfcGate instance.
# NFC_GATE_STATUS iterates this list; it is populated by Klipper's config phase
# before any GCode command can be invoked.
_instances = []


class NfcGate:
    """
    Manages one PN532 NFC reader on one EBB42 lane board.

    Instantiated once per [nfc_gate laneN] config section.
    """

    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()

        # Section name suffix (e.g. "lane0" from "[nfc_gate lane0]")
        self._name = config.get_name().split()[-1]

        # ── Config ───────────────────────────────────────────────────────────
        self._gate = config.getint('gate', minval=0)
        self._poll_interval    = config.getfloat('poll_interval', 30.,
                                                  minval=1., maxval=3600.)
        self._absent_threshold = config.getint('absent_threshold', 3,
                                                minval=1, maxval=255)
        transceive_delay = config.getfloat('transceive_delay', 0.250,
                                            minval=0.050, maxval=2.0)
        crc_delay        = config.getfloat('crc_delay', 0.050,
                                            minval=0.005, maxval=1.0)
        self._debug      = config.getint('debug', 1, minval=0, maxval=2)

        # ── Spoolman integration ──────────────────────────────────────────────
        spoolman_url     = config.get('spoolman_url', '')
        spoolman_rfid_key = config.get('spoolman_rfid_key', 'rfid')
        spoolman_timeout = config.getfloat('spoolman_timeout', 5.0,
                                            minval=0.5, maxval=30.0)
        spoolman_cache_ttl = config.getfloat('spoolman_cache_ttl', 300.0,
                                              minval=0., maxval=3600.)

        if spoolman_url:
            self._spoolman = SpoolmanClient(
                spoolman_url,
                rfid_key=spoolman_rfid_key,
                timeout=spoolman_timeout,
                cache_ttl=spoolman_cache_ttl,
                debug=self._debug)
            logging.info("nfc_gate: [%s] Spoolman enabled — url=%s rfid_key=%s",
                         self._name, spoolman_url, spoolman_rfid_key)
        else:
            self._spoolman = None
            logging.warning(
                "nfc_gate: [%s] spoolman_url not set — gate will report UIDs "
                "but cannot resolve spool IDs.  Add spoolman_url to [nfc_gate %s].",
                self._name, self._name)

        # ── I2C device ────────────────────────────────────────────────────────
        # MCU_I2C.lookup() reads i2c_mcu, i2c_software_scl_pin,
        # i2c_software_sda_pin (or i2c_bus), i2c_address, and i2c_speed from
        # the config section — exactly the same keys used by BME280 sensors
        # in emu_macros.cfg.
        i2c = bus_module.MCU_I2C.lookup(config,
                                         default_addr=0x24,   # PN532 default
                                         default_speed=400000)

        # ── Per-gate objects ─────────────────────────────────────────────────
        self._reader = PN532Driver(i2c, self._gate,
                                   transceive_delay, crc_delay,
                                   self._debug)
        self._state  = GateState(self._gate, self._absent_threshold)
        self._failed = False

        # ── GCode bridge ─────────────────────────────────────────────────────
        self._klipper = KlipperInterface(self.printer, self.reactor)

        # ── Background polling thread ────────────────────────────────────────
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name='nfc-gate-%s' % self._name,
            daemon=True)

        # ── GCode command ────────────────────────────────────────────────────
        # Register NFC_GATE_STATUS once (on the first gate loaded).
        # The command function accesses _instances at call time, so gates
        # loaded after this registration are still included.
        if not _instances:
            gcode = self.printer.lookup_object('gcode')
            gcode.register_command(
                'NFC_GATE_STATUS', _cmd_all_status,
                desc="Report spool state for all configured NFC gates")

        # ── Lifecycle ────────────────────────────────────────────────────────
        self.printer.register_event_handler('klippy:connect',
                                            self._handle_connect)
        self.printer.register_event_handler('klippy:disconnect',
                                            self._handle_disconnect)

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_connect(self):
        logging.info(
            "nfc_gate: [%s] connected — gate=%d, poll=%.0fs, "
            "absent_threshold=%d, debug=%d",
            self._name, self._gate, self._poll_interval,
            self._absent_threshold, self._debug)

        try:
            self._reader.init()
            if self._reader.is_alive():
                logging.info("nfc_gate: [%s] PN532 reader OK", self._name)
            else:
                self._failed = True
                logging.error(
                    "nfc_gate: [%s] PN532 did not respond after init — "
                    "check wiring and I2C address (default 0x24)", self._name)
        except Exception as e:
            self._failed = True
            logging.error("nfc_gate: [%s] init error: %s", self._name, e)

        if not self._failed:
            self._stop_event.clear()
            if not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._poll_loop,
                    name='nfc-gate-%s' % self._name,
                    daemon=True)
                self._thread.start()

    def _handle_disconnect(self):
        self._stop_event.set()

    # ─────────────────────────────────────────────────────────────────────────
    # Background polling loop
    # ─────────────────────────────────────────────────────────────────────────

    def _poll_loop(self):
        logging.info("nfc_gate: [%s] polling thread started", self._name)
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception:
                logging.exception("nfc_gate: [%s] poll error", self._name)
            self._stop_event.wait(timeout=self._poll_interval)
        logging.info("nfc_gate: [%s] polling thread stopped", self._name)

    def _poll(self):
        uid_hex = self._reader.read_tag()

        if self._debug >= 1 and uid_hex is None:
            logging.info("nfc_gate: [%s] gate %d — no tag (miss %d)",
                         self._name, self._gate,
                         self._state.miss_count + 1)

        # ── Spoolman lookup (only when UID is new or changed) ─────────────────
        if uid_hex is not None:
            if uid_hex == self._state.current_uid:
                # Same tag still present — reuse cached state, no API call
                spool_id = self._state.current_spool
            elif self._spoolman is not None:
                spool_id = self._spoolman.lookup_spool_by_uid(uid_hex)
            else:
                spool_id = None
        else:
            spool_id = None

        event = self._state.process_read(uid_hex, spool_id)
        if event is not None:
            event_type, gate, uid, spool = event
            if self._debug >= 1:
                logging.info(
                    "nfc_gate: [%s] gate %d — %s uid=%s spool=%s",
                    self._name, gate, event_type, uid, spool)
            self._klipper.dispatch(event_type, gate, uid, spool)

    # ─────────────────────────────────────────────────────────────────────────
    # Status helpers
    # ─────────────────────────────────────────────────────────────────────────

    def status_line(self):
        """One-line status string for NFC_GATE_STATUS output."""
        if self._failed:
            return ("  Gate %d  [%s]:  READER FAILED "
                    "(check wiring, address 0x24)"
                    % (self._gate, self._name))
        if self._state.current_spool is not None:
            return ("  Gate %d  [%s]:  spool %-6d   UID %s"
                    % (self._gate, self._name,
                       self._state.current_spool, self._state.current_uid))
        if self._state.current_uid is not None:
            return ("  Gate %d  [%s]:  tag %s  (UID not in Spoolman — "
                    "set the 'rfid' field on the spool record)"
                    % (self._gate, self._name, self._state.current_uid))
        return "  Gate %d  [%s]:  empty" % (self._gate, self._name)

    def get_status(self, _eventtime=None):
        """Klipper printer object status (accessible via printer["nfc_gate laneN"])."""
        return {
            'gate':     self._gate,
            'spool_id': self._state.current_spool if self._state.current_spool is not None else -1,
            'uid':      self._state.current_uid   or '',
            'failed':   self._failed,
        }


# ─────────────────────────────────────────────────────────────────────────────
# NFC_GATE_STATUS — aggregate command across all configured gates
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_all_status(gcmd):
    if not _instances:
        gcmd.respond_info("No [nfc_gate] sections are configured.")
        return
    sorted_gates = sorted(_instances, key=lambda g: g._gate)
    lines = ["NFC gate status  (%d gate%s configured):"
             % (len(_instances), 's' if len(_instances) != 1 else '')]
    for gate in sorted_gates:
        lines.append(gate.status_line())
    gcmd.respond_info('\n'.join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def load_config(config):
    gate = NfcGate(config)
    _instances.append(gate)
    return gate
