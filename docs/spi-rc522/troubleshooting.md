# SPI / RC522 — Troubleshooting

[← Back to SPI Setup](setup.md) | [← Back to Index](../../Readme.md)

---

## Reader did not respond after init

```
nfc_gates: gate N reader did not respond after init (check wiring)
```

The RC522 could not be reached over SPI. Work through these checks in order:

1. **Power** — verify RC522 VCC is connected to Pico 3V3 OUT, not VBUS (5V).
2. **SPI bus** — confirm SCK=GP10, MOSI=GP11, MISO=GP8 on every reader.
3. **CS wire** — verify the SDA wire for gate N is connected to the correct GPIO (GP0–GP3 for gates 0–3, GP6 for gate 4).
4. **Isolation** — disconnect all but gate 0 and test with a single reader. If gate 0 works alone, add readers one at a time.
5. **Module swap** — if one reader never responds but others do, the module may be faulty.

Enable `debug: 2` in `[nfc_gates]` and restart Klipper to see every SPI register read/write.

---

## Klipper does not connect to nfc_pico

```
mcu 'nfc_pico': Unable to connect
```

- Run `~/klippy-env/bin/python ~/klipper/scripts/canbus_query.py can0` — the Pico must appear.
- If it does not appear, the Pico is not running Klipper MCU firmware or is not on the CAN bus.
- Verify the CAN transceiver is wired correctly (GP4=TX, GP5=RX) and the RS pin is tied to GND.
- Check CAN bus termination (120 Ω at each physical end of the bus).
- Reflash the Pico following [setup.md Steps 2–3](setup.md).
- Verify `canbus_uuid` in `nfc_gates_spi_rc522.cfg` matches the UUID from `canbus_query.py`.

---

## Tags detected intermittently

- **Tag size** — small sticker tags (≤25 mm) have a read range of 3 mm or less. Use 50 mm disc tags.
- **Tag positioning** — the antenna must be within 1–3 cm. Misalignment reduces range to near zero.
- **RF bleed** — RC522 antennas are all powered at once. Adjacent gates within 3 cm of each other can interfere. Increase physical separation or add ferrite backing.
- **False removals** — increase `absent_threshold` from 3 to 5 to require more consecutive misses before reporting removal.

---

## Tag detected but no spool ID (`_NFC_TAG_NO_SPOOL` fires)

The tag is in the RF field and the UID is read, but pages 4–7 contain no parseable spool ID.

- Write the spool ID with NFC Tools app: **Add record → Text** → enter the integer ID (e.g. `1042`). See [tag-writing.md](../shared/tag-writing.md).
- If you used an NDEF URL or SmartPoster record type, overwrite with a plain Text record.
- If the tag was written with binary encoding, it should be caught by the fallback uint32 parser — check klippy.log with `debug: 2` to see the raw bytes read from pages 4–7.

---

## SPI bus errors (ErrorReg collisions or CRC errors)

```
nfc_gates: gate N  _transceive -> MI_ERR (ErrorReg=0x1B: collision=1 CRC=1 ...)
```

- More than one tag in the RF field simultaneously on the same gate — only one tag per gate is supported.
- MISO or MOSI wiring fault causing bus corruption — check for shorts between SPI lines.
- Reduce `spi_speed` from 1000000 to 500000 in `[nfc_gates]` if you have very long jumper wires (>30 cm).

---

## All gates report errors after a Klipper reconnect

When Klipper reconnects after a disconnect/restart, the RC522 readers are re-initialised automatically. If init fails on all gates after a reconnect, the Pico MCU may have lost power or rebooted — check the CAN bus and Pico power supply.

---

## Polling thread stops logging

If log output stops for more than 2× `poll_interval`, the background polling thread has likely raised an unhandled exception. Check klippy.log for:

```
nfc_gates: unexpected error in poll cycle
```

Followed by a Python traceback. Report the traceback as a bug.

---

## debug: 2 log reference

| Log pattern | Meaning |
|---|---|
| `W CommandReg = 0x0F` | Soft-reset sent |
| `R TxControlReg -> 0x83` | Antenna TX pins confirmed active |
| `_transceive -> MI_ERR (timer expired, no tag response)` | No tag in field — normal |
| `_transceive -> MI_OK fifo=5 bits=40` | Tag responded to REQA/ANTICOLL |
| `READ page N OK data=[...]` | 4 bytes of user data read from tag page |
| `spool ID parsed as ASCII decimal: 1042` | Spool ID found — primary strategy |
| `spool ID parsed as big-endian uint32: 1042` | Spool ID found — fallback strategy |
