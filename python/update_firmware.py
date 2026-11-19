#!/usr/bin/env python3
"""Update the I3CBlaster firmware with picotool (no USB drive needed).

Examples:
    python update_firmware.py ../bin/i3cblaster.uf2
    python update_firmware.py --port COM5 ../bin/i3cblaster.uf2
    python update_firmware.py --port /dev/ttyACM0 --picotool ~/picotool/picotool ../bin/i3cblaster.uf2

Steps: sends 'bootloader 1' (bootloader with the PICOBOOT interface only), runs
'picotool load -v -x <uf2>', then waits for the I3CBlaster serial port to come back.
See docs/FIRMWARE_UPDATE.md for installing picotool and the USB permissions/driver.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import i3cblaster  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description='Update the I3CBlaster firmware with picotool.')
    ap.add_argument('uf2', help='firmware file, e.g. ../bin/i3cblaster.uf2')
    ap.add_argument('--port', help='serial port of the I3CBlaster (e.g. COM5 or /dev/ttyACM0). '
                                   'Default: auto-detect by USB VID:PID 2e8a:000a')
    ap.add_argument('--serial', help='select the I3CBlaster by USB serial number (if several are connected)')
    ap.add_argument('--picotool', default='picotool', help='picotool executable or full path (default: picotool)')
    ap.add_argument('--timeout', type=float, default=20, help='seconds to wait for each step (default: 20)')
    ap.add_argument('--no-verify', action='store_true', help='do not pass -v (verify) to picotool load')
    args = ap.parse_args()

    dev = i3cblaster.i3cblaster()
    dev.init(serialnumber=args.serial, port=args.port)
    try:
        out = dev.update_firmware(args.uf2, picotool=args.picotool, timeout=args.timeout,
                                  verify=not args.no_verify)
    except Exception as e:
        print('ERROR: %s' % e, file=sys.stderr)
        return 1
    print(out.strip())
    print('Firmware update done, I3CBlaster is back.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
