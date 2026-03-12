# I2C / PN532 — Troubleshooting

[← Back to I2C Setup](setup.md) | [← Back to Index](../../Readme.md)

---

## PN532 did not respond after init

```
nfc_gate: [laneN] PN532 did not respond after init — check wiring and I2C address (default 0x24)
```

Work through these checks in order:

1. **Mode selection** — the PN532 module must be set to I2C mode via its DIP switch or solder jumper. SPI and UART modes will not respond at an I2C address. See [wiring.md](wiring.md).
2. **Wiring** — confirm SDA is on PB4 and SCL is on PB3 on the correct EBB42 board.
3. **Power** — verify VCC is connected to the EBB42's 3V3 rail, not a 5V pin.
4. **Address** — the default PN532 I2C address is `0x24` (36 decimal). If the address pads have been bridged, adjust `i2c_address` in the config section.
5. **Pull-ups** — if your PN532 module does not have onboard pull-up resistors, add 4.7 kΩ between SDA/SCL and 3V3. Do not add pull-ups if the module already has them.
6. **Lane MCU** — verify the `i2c_mcu` name in the config matches the MCU name in `mmu_hardware.cfg`. Run `NFC_GATE_STATUS` to see which gates failed vs which connected.

Enable `debug: 2` in the failing `[nfc_gate]` section and restart Klipper to see every I2C frame.

---

## Lane MCU name not found

```
Option 'i2c_mcu' in section 'nfc_gate lane2' is not a valid MCU name
```

The `i2c_mcu` value must exactly match an MCU name defined in `mmu_hardware.cfg`. Check:

```bash
grep "\[mcu" ~/printer_data/config/mmu/base/mmu_hardware.cfg
```

Common names are `lane0`, `lane1`, etc. Update the `[nfc_gate]` section to match.

---

## BME280 stops working after adding PN532

Both devices share the software I2C bus on PB3/PB4. They must use different I2C addresses:
- BME280: `0x76`
- PN532: `0x24`

If the BME280 stops responding:
- Verify the PN532 is not mis-configured as a different address that collides with 0x76.
- Check that SDA/SCL wires are not shorted.
- Check the PN532 module's mode jumper — a mis-set PN532 may pull SDA or SCL in unexpected ways.

---

## Tags detected intermittently

- **Tag size** — use 50 mm disc tags. Small sticker tags have a read range of a few mm against a PN532.
- **Tag positioning** — hold the tag flat against the PN532 antenna. The PN532 has a smaller effective range than an RC522 at low read power settings.
- **False removals** — increase `absent_threshold` from 3 to 5 in the failing `[nfc_gate]` section.

---

## Tag detected but no spool ID (`_NFC_TAG_NO_SPOOL` fires)

The PN532 read the UID successfully but pages 4–7 contain no recognisable spool ID.

- Write the spool ID with NFC Tools: **Add record → Text** → enter the integer ID. See [tag-writing.md](../shared/tag-writing.md).
- Enable `debug: 2` to see the raw bytes read from the tag in klippy.log.

---

## Polling thread not starting (reader init failed)

If a reader fails during `_handle_connect`, its polling thread never starts. The gate
will show `READER FAILED` in `NFC_GATE_STATUS`. Correct the wiring and restart Klipper
to retry initialisation — init is attempted fresh on every connect.

---

## debug: 2 log reference

| Log pattern | Meaning |
|---|---|
| `PN532 GetFirmwareVersion OK` | PN532 is alive and communicating |
| `SAMConfiguration OK` | PN532 configured for ISO14443A passive mode |
| `InListPassiveTarget -> no tag` | No tag in field — normal |
| `InListPassiveTarget -> UID=A3F200CC` | Tag detected |
| `InDataExchange READ page 4 -> [31 30 34 32...]` | 16 bytes of user data |
| `InRelease OK` | Tag deselected |
| `spool ID parsed as ASCII decimal: 1042` | Spool ID found |
