# klippy/extras/nfc_gates/gate_state.py
#
# Per-gate state machine with debounce.
#
# This is a direct Python port of the GateState class from pico_nfc_gates.py,
# adapted to return typed event objects instead of serial protocol strings.
# The core logic — silent same-state, debounced removal — is unchanged.

# Event type constants returned by process_read()
EVENT_CHANGED  = 'changed'   # New or replaced spool (uid_hex + spool_id valid)
EVENT_UID_ONLY = 'uid_only'  # Tag present but no spool ID in its memory
EVENT_REMOVED  = 'removed'   # Tag gone after absent_threshold consecutive misses


class GateState:
    """
    Tracks the NFC tag presence and spool assignment for one gate.

    On each poll cycle, call process_read() with the result from
    RC522Driver.read_tag().  The method compares the new result against the
    last known state and returns an event tuple only when something has
    changed.  If nothing changed it returns None — this keeps Klipper GCode
    traffic minimal (same behaviour as the original firmware's change-driven
    serial protocol).

    Removal debounce
    ----------------
    NFC reads can momentarily fail even with a tag present (RF interference,
    tag orientation, reader timing).  A single missed read is not treated as a
    removal.  The tag must be absent for ``absent_threshold`` consecutive polls
    before a REMOVED event is emitted.  At the default 30-second poll interval
    that means ~90 seconds of actual absence before the gate is cleared —
    preventing false removals from brief read failures.

    Parameters
    ----------
    gate : int
        Gate index (0-based), used in returned event tuples.
    absent_threshold : int
        Consecutive polls with no tag before emitting EVENT_REMOVED.
    """

    def __init__(self, gate, absent_threshold=3):
        self.gate              = gate
        self.current_uid       = None   # str  : UID hex string, or None
        self.current_spool     = None   # int  : spool ID, or None
        self.miss_count        = 0      # int  : consecutive polls with no tag
        self.absent_threshold  = absent_threshold

    def process_read(self, uid_hex, spool_id):
        """
        Process one poll result for this gate.

        Parameters
        ----------
        uid_hex : str or None
            8-character hex UID string if a tag was detected, otherwise None.
        spool_id : int or None
            Integer spool ID if tag data was readable, otherwise None.

        Returns
        -------
        (event_type, gate, uid_hex, spool_id) tuple if state changed,
        None if nothing changed (caller should not dispatch anything).
        """
        if uid_hex is not None:
            # ── Tag present ──────────────────────────────────────────────────
            self.miss_count = 0

            # Same tag, same spool — no change, stay silent
            if self.current_uid == uid_hex and self.current_spool == spool_id:
                return None

            # State changed (new tag, or same tag with new spool data)
            self.current_uid   = uid_hex
            self.current_spool = spool_id

            if spool_id is not None:
                return (EVENT_CHANGED, self.gate, uid_hex, spool_id)
            else:
                return (EVENT_UID_ONLY, self.gate, uid_hex, None)

        else:
            # ── No tag detected ───────────────────────────────────────────────
            self.miss_count += 1

            # Debounce: only declare removed after threshold consecutive misses
            if self.miss_count >= self.absent_threshold and self.current_uid is not None:
                old_spool = self.current_spool
                self.current_uid   = None
                self.current_spool = None
                return (EVENT_REMOVED, self.gate, None, old_spool)

            return None

    def __repr__(self):
        if self.current_uid is None:
            return "Gate({} empty, misses={})".format(self.gate, self.miss_count)
        return "Gate({} uid={} spool={} misses={})".format(
            self.gate, self.current_uid, self.current_spool, self.miss_count)
