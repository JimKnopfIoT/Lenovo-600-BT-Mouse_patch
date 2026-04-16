#!/usr/bin/env python3
"""
Lenovo BT-600 Bluetooth Mouse — Firmware Patcher
=================================================
Fixes the bug in the original nRF52810 firmware:
  1. Mouse lag for 3 seconds after around 15 seconds of inactivity
  
Usage:
  python3 patch_lenovo_bt600.py <input_firmware.bin> <output_firmware.bin>

Example:
  python3 patch_lenovo_bt600.py nrf52810_flash.bin nrf52810_flash_patched.bin

The input file must be a full 192 KB (196608 byte) flash dump of the nRF52810.
The NVM area (0x2C000–0x2FFFF) is left untouched — bonding data is preserved.

Flashing (requires OpenOCD + ST-Link):
  openocd -f interface/stlink.cfg -f target/nrf52.cfg \\
    -c "init; halt; nrf5 mass_erase; \\
        program <output_firmware.bin> 0x00000000; \\
        reset; shutdown"

Note: mass_erase will erase the NVM (bonding data). After flashing, re-pair the mouse.

---

Lenovo BT-600 Bluetooth Maus — Firmware Patcher
================================================
Behebt einen Fehler in der originalen nRF52810 Firmware:
  1. Maus verzögert um 3 Sekunden wenn sie ca. 15 Sekunden nicht bewegt wurde (Stromsparfunktion? Sehr lästig)
  
Verwendung:
  python3 patch_lenovo_bt600.py <eingabe_firmware.bin> <ausgabe_firmware.bin>

Die Eingabedatei muss ein vollständiges 192-KB-Flash-Image (196608 Bytes) sein.
Der NVM-Bereich (0x2C000–0x2FFFF) wird nicht verändert — Bonding-Daten bleiben erhalten.
"""

import sys
import hashlib

EXPECTED_SIZE = 196608  # 192 KB

# Each patch: (offset, old_bytes, new_bytes, description)
# old_bytes are verified before patching — ensures correct firmware version.
PATCHES = [
    # --- Lag fixes (connection interval, SYSTEMOFF) ---
    (0x01a4e0, bytes.fromhex("4ff41661"), bytes.fromhex("40f22031"),
     "Connection interval: reduce 2400->800 units (part 1)"),

    (0x01a920, bytes.fromhex("10b5"),     bytes.fromhex("7047"),
     "Block SYSTEMOFF (prevents wake-up lag)"),

    (0x01af9f, bytes.fromhex("f5c86f"),   bytes.fromhex("f1000f"),
     "Connection interval fix (part 2)"),

    (0x01b2b0, bytes.fromhex("00b585b0"), bytes.fromhex("704700bf"),
     "Block conn_params retry handler"),

    (0x01b626, bytes.fromhex("03"),       bytes.fromhex("3c"),
     "Connection interval fix (part 3)"),

    (0x01b7cc, bytes.fromhex("fff720f8"), bytes.fromhex("00bf00bf"),
     "Block SYSTEMOFF call (part 2)"),

    (0x01b7e9, bytes.fromhex("f098fe"),   bytes.fromhex("bf00bf"),
     "Block SYSTEMOFF call (part 3)"),

    (0x01b890, bytes.fromhex("80"),       bytes.fromhex("ff"),
     "Connection interval fix (part 4a)"),

    (0x01b893, bytes.fromhex("d1"),       bytes.fromhex("e7"),
     "Connection interval fix (part 4b)"),

    (0x01bf9a, bytes.fromhex("4ff41661"), bytes.fromhex("40f22031"),
     "Connection interval fix (part 5)"),

    (0x01c5c0, bytes.fromhex("4ff41660"), bytes.fromhex("40f22030"),
     "Connection interval fix (part 6)"),

    (0x01c748, bytes.fromhex("fef7c0b8"), bytes.fromhex("704700bf"),
     "Block SYSTEMOFF call (part 4)"),

    (0x02048c, bytes.fromhex("2de9f041"), bytes.fromhex("704700bf"),
     "Block legacy disconnect handler"),

    (0x022ed8, bytes.fromhex("0ab1"),     bytes.fromhex("01e0"),
     "Block FUN_0x22ed4"),

    (0x024bf4, bytes.fromhex("01780229"), bytes.fromhex("704700bf"),
     "Block FUN_0x24bf4"),

    # --- Patch E: idle timer disconnect ---
    (0x01a79c, bytes.fromhex("07d0"),     bytes.fromhex("1cd0"),
     "Patch E: block idle timer disconnect"),

    # --- Patch F: GATT timeout self-disconnect (main 25s fix) ---
    (0x0199a2, bytes.fromhex("76df"),     bytes.fromhex("00bf"),
     "Patch F: NOP disconnect on BLE_GATTC_EVT_TIMEOUT (fixes 25s drop)"),

    # --- Patch G: advertising duration = 0 (no timeout, fixes reconnect) ---
    (0x01da58, bytes.fromhex("208b"),     bytes.fromhex("0020"),
     "Patch G1: advertising duration = 0, no timeout (fixes auto-reconnect, set 1)"),

    (0x01dc88, bytes.fromhex("208c"),     bytes.fromhex("0020"),
     "Patch G2: advertising duration = 0, no timeout (fixes auto-reconnect, set 2)"),
]


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        print(f"\nUsage: {sys.argv[0]} <input.bin> <output.bin>")
        sys.exit(1)

    input_path  = sys.argv[1]
    output_path = sys.argv[2]

    print(f"Reading {input_path} ...")
    try:
        with open(input_path, "rb") as f:
            data = bytearray(f.read())
    except FileNotFoundError:
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    # Size check
    if len(data) != EXPECTED_SIZE:
        print(f"ERROR: Unexpected file size {len(data)} bytes (expected {EXPECTED_SIZE}).")
        print("       Make sure this is a full 192 KB nRF52810 flash dump.")
        sys.exit(1)

    print(f"File size: {len(data)} bytes — OK")

    # Verify and apply patches
    print("\nVerifying and applying patches...")
    errors = []
    for offset, old, new, desc in PATCHES:
        actual = bytes(data[offset:offset+len(old)])
        if actual == new:
            print(f"  [SKIP]  0x{offset:06x}  already patched — {desc}")
        elif actual == old:
            data[offset:offset+len(new)] = new
            print(f"  [PATCH] 0x{offset:06x}  {old.hex()} -> {new.hex()} — {desc}")
        else:
            errors.append((offset, old, actual, desc))
            print(f"  [ERROR] 0x{offset:06x}  expected {old.hex()}, found {actual.hex()} — {desc}")

    if errors:
        print(f"\nERROR: {len(errors)} patch(es) could not be applied.")
        print("       This firmware may be a different version or already modified.")
        sys.exit(1)

    # Write output
    print(f"\nWriting {output_path} ...")
    with open(output_path, "wb") as f:
        f.write(data)

    md5 = hashlib.md5(data).hexdigest()
    print(f"MD5: {md5}")
    print("\nDone. All patches applied successfully.")
    print("\nNext steps:")
    print("  1. Flash with OpenOCD:")
    print(f"     openocd -f interface/stlink.cfg -f target/nrf52.cfg \\")
    print(f"       -c \"init; halt; nrf5 mass_erase; program {output_path} 0x00000000; reset; shutdown\"")
    print("  2. Re-pair the mouse with your host (bonding data was erased by mass_erase).")
    print("  3. On Linux: bluetoothctl trust <address>")


if __name__ == "__main__":
    main()
