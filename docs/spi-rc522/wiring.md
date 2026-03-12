# SPI / RC522 — Wiring Diagram & Pin Reference

[← Back to SPI Setup](setup.md) | [← Back to Index](../../Readme.md)

---

## Overview

One **Raspberry Pi Pico** connects to the CAN bus and hosts up to 8 RC522 readers
on its hardware SPI1 bus. All readers share SCK, MOSI, MISO, RST, VCC, and GND.
Each reader has its own CS (chip-select) GPIO.

---

## CAN Bus Transceiver

The Pico cannot drive CAN bus directly. A 3.3V CAN transceiver module
(e.g. SN65HVD230) is required between the Pico GPIO and the CAN bus differential pair.

> Use a **3.3V** transceiver. Do **not** use a 5V module (e.g. MCP2551) —
> the Pico's GPIO is not 5V tolerant.

> Tie the transceiver's RS / slope-control pin to GND for high-speed mode
> (required at 1 Mbit/s).

> The CAN bus must be terminated with 120 Ω between CANH and CANL at each physical
> end of the bus. Most EBB toolhead boards have a termination jumper for one end.

```
Raspberry Pi Pico          SN65HVD230
┌─────────────┐            ┌──────────────────┐
│  GP4 (TX) ──┼────────────┼─► TXD            │
│  GP5 (RX) ──┼────────────┼─◄ RXD            │
│  3V3 OUT  ──┼────────────┼─► VCC (3.3V)     │
│  GND      ──┼────────────┼─► GND            │
└─────────────┘            │   CANH ──────────┼──► CAN bus (CANH)
                           │   CANL ──────────┼──► CAN bus (CANL)
                           └──────────────────┘
```

---

## Full Wiring Diagram (5-gate example)

```
Raspberry Pi Pico
┌──────────────────────────────────────────┐
│                                          │
│  GP4 (CAN TX) ────────────────────────── TXD  SN65HVD230
│  GP5 (CAN RX) ────────────────────────── RXD  SN65HVD230
│                                          │
│  GP0  ──────────────────────────────── SDA  RC522 Gate 0
│  GP1  ──────────────────────────────── SDA  RC522 Gate 1
│  GP2  ──────────────────────────────── SDA  RC522 Gate 2
│  GP3  ──────────────────────────────── SDA  RC522 Gate 3
│  GP6  ──────────────────────────────── SDA  RC522 Gate 4
│                                          │
│  GP7  ─────────────────────────┬──────── RST  RC522 Gate 0
│  (or tie RST to 3V3)           ├──────── RST  RC522 Gate 1
│                                ├──────── RST  RC522 Gate 2
│                                ├──────── RST  RC522 Gate 3
│                                └──────── RST  RC522 Gate 4
│                                          │
│  GP8  (SPI1 MISO) ─────────────┬──────── MISO RC522 Gate 0
│                                ├──────── MISO RC522 Gate 1
│                                ├──────── MISO RC522 Gate 2
│                                ├──────── MISO RC522 Gate 3
│                                └──────── MISO RC522 Gate 4
│                                          │
│  GP10 (SPI1 SCK)  ─────────────┬──────── SCK  RC522 Gate 0
│                                ├──────── SCK  RC522 Gate 1
│                                ├──────── SCK  RC522 Gate 2
│                                ├──────── SCK  RC522 Gate 3
│                                └──────── SCK  RC522 Gate 4
│                                          │
│  GP11 (SPI1 MOSI) ─────────────┬──────── MOSI RC522 Gate 0
│                                ├──────── MOSI RC522 Gate 1
│                                ├──────── MOSI RC522 Gate 2
│                                ├──────── MOSI RC522 Gate 3
│                                └──────── MOSI RC522 Gate 4
│                                          │
│  3V3 OUT ──────────────────────┬──────── VCC  RC522 Gate 0
│                       (also ──►│ VCC SN65HVD230)
│                                ├──────── VCC  RC522 Gate 1
│                                ├──────── VCC  RC522 Gate 2
│                                ├──────── VCC  RC522 Gate 3
│                                └──────── VCC  RC522 Gate 4
│                                          │
│  GND ──────────────────────────┬──────── GND  RC522 Gate 0
│                       (also ──►│ GND SN65HVD230)
│                                ├──────── GND  RC522 Gate 1
│                                ├──────── GND  RC522 Gate 2
│                                ├──────── GND  RC522 Gate 3
│                                └──────── GND  RC522 Gate 4
└──────────────────────────────────────────┘
```

---

## Pin Reference Table

| Pico GPIO | Function | Connected To | Notes |
|---|---|---|---|
| GP0 | RC522 CS (Gate 0) | RC522 Gate 0 SDA | Chip select — active low |
| GP1 | RC522 CS (Gate 1) | RC522 Gate 1 SDA | Chip select — active low |
| GP2 | RC522 CS (Gate 2) | RC522 Gate 2 SDA | Chip select — active low |
| GP3 | RC522 CS (Gate 3) | RC522 Gate 3 SDA | Chip select — active low |
| **GP4** | **CAN TX** | **SN65HVD230 TXD** | **CAN bus transmit** |
| **GP5** | **CAN RX** | **SN65HVD230 RXD** | **CAN bus receive** |
| GP6 | RC522 CS (Gate 4) | RC522 Gate 4 SDA | Chip select — active low |
| GP7 | RC522 RST | All RC522 RST | Shared reset — or tie all RST to 3V3 |
| GP8 | SPI1 MISO | All RC522 MISO | Shared data in |
| GP10 | SPI1 SCK | All RC522 SCK | Shared clock — 1 MHz |
| GP11 | SPI1 MOSI | All RC522 MOSI | Shared data out |
| 3V3 OUT | — | RC522 VCC + transceiver VCC | 3.3V rail — do not use 5V |
| GND | — | RC522 GND + transceiver GND | Common ground |

---

## RC522 Module Pinout

Each RC522 board has 8 pins:

| RC522 Pin | Function | Connect to |
|---|---|---|
| VCC | Power | Pico 3V3 OUT |
| GND | Ground | Pico GND |
| RST | Reset (active low) | Pico GP7 — or tie to 3V3 |
| SDA | SPI Chip Select | Unique Pico GPIO per gate (GP0–GP6) |
| SCK | SPI Clock | Pico GP10 (shared) |
| MOSI | SPI data out from Pico | Pico GP11 (shared) |
| MISO | SPI data in to Pico | Pico GP8 (shared) |
| IRQ | Interrupt | Not used — leave unconnected |

> **Voltage:** RC522 modules run at 3.3V. The Pico's GPIO is 3.3V native — no level
> shifters required. Do **not** connect RC522 VCC to the Pico's VBUS (5V) pin.

---

## Notes on Shared Lines

SCK, MOSI, MISO, RST, VCC, and GND are shared across all RC522 modules.
Only the SDA (CS) line is unique per module — daisy-chain the shared lines across
all boards and run individual wires only for SDA.

**RST pin:** A hardware reset pulse is not required. The software init sequence sends
a `PCD_RESETPHASE` command over SPI to soft-reset each reader. You can tie all RC522
RST pins directly to 3.3V (permanently deasserted). If you do wire RST to GP7,
configure it as a static high output — no toggling is needed.

**RF isolation:** All RC522 antenna coils are powered simultaneously. The CS pin
provides software isolation only — only one reader is selected on SPI at a time.
For physical RF isolation between adjacent gates, maintain at least **3 cm** separation
between antenna coils, or use ferrite backing behind each antenna.
