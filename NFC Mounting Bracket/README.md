# NFC Mounting Bracket Files

These files are PN532 reader mounts for the EMU lane LED holder area.

## Standard Height

Use the standard NFC bracket files when your tag placement is not tied to the
factory Bambu spool tag height, or when you are tuning the reader position for
your own spool/tag layout.

- `LED_holder_No_cover_with_NFC.stl`
- `LED_holder_No_cover_with_NFC.step`
- `LED_holder_NFC_Guard.stl`
- `LED_holder_NFC_Guard.step`

## Bambu Height

The `Bambu_height` variants place the PN532 reader center at the same height as
the RFID/NFC tags on standard Bambu spools. Use these when you want the reader
antenna aligned to Bambu spool tags without modifying tag placement.

- `LED_holder_with_NFC_Bambu_height.stl`
- `LED_holder_NFC_Guard_Bambu_height.stl`

## Guard vs No Cover

The guard version protects the PN532 reader DIP switches. This is especially
useful with open-sided spools, where the spool edge can otherwise catch on the
reader's switches as the spool turns and stall the lane's stepper. The no-cover
version keeps the reader more exposed and may be useful for fit checks, tuning,
or tight clearance builds.
