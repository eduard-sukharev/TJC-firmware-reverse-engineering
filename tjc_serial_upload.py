#!/usr/bin/env python3
"""Serial firmware uploader for TJC/Nextion displays (upload protocol v1.2).

Implements the Nextion HMI upload protocol as documented in
nxt-doc/Protocols/Upload Protocol v1.2.md, following the reference
implementations:
  * https://github.com/UNUF/Nexus (Python, v1.2)
  * https://github.com/hagronnestad/nextion-tft-uploader (C#, v1.0)

Verified against a TJC3224T132_011N (Ender-3 V3 SE panel).

Usage:
    python3 tjc_serial_upload.py tjc.tft
    python3 tjc_serial_upload.py tjc.tft -p /dev/ttyUSB0 -c 115200 -u 921600
"""
import argparse
import struct
import sys
import time

import serial

NXEOL = b"\xff\xff\xff"
ACK = 0x05
SKIP = 0x08
BLOCK_SIZE = 4096

# Baud rates the display's bootloader is known to listen on, tried in order.
DEFAULT_SPEEDS = [115200, 9600, 57600, 19200, 38400, 230400, 250000,
                  256000, 460800, 500000, 512000, 921600, 2400, 4800,
                  31250, 74880]


class Nextion:
    def __init__(self, port, connect_speed=0, upload_speed=0):
        self.port = port
        self.connect_speed = connect_speed
        self.upload_speed = upload_speed
        self.address = 0
        self.info = {}
        self.ser = serial.Serial()

    def connect(self):
        speeds = list(DEFAULT_SPEEDS)
        if self.connect_speed:
            if self.connect_speed in speeds:
                speeds.remove(self.connect_speed)
            speeds.insert(0, self.connect_speed)

        for speed in speeds:
            print(f"  probing {self.port} at {speed} baud... ", end="", flush=True)
            self.ser.close()
            self.ser.port = self.port
            self.ser.baudrate = speed
            self.ser.timeout = 1000 / speed + 0.030
            self.ser.open()
            self.ser.reset_input_buffer()

            # Junk prefix wakes a display that is mid-command, then connect
            # is sent twice because the first one is routinely swallowed.
            self.ser.write(b"DRAKJHSUYDGBNCJHGJKSHBDN" + NXEOL
                           + b"connect" + NXEOL + b"\xff\xff"
                           + b"connect" + NXEOL)

            data = b""
            available = -1
            while available != len(data):
                available = self.ser.in_waiting
                new = self.ser.read_until(expected=NXEOL)
                if not new:
                    break
                data = new

            if not data.startswith(b"comok"):
                print("no.")
                continue

            self.ser.write(NXEOL)
            self.ser.read(42)
            print("yes.")
            self._parse_comok(data)
            self.connect_speed = speed
            if not self.upload_speed:
                self.upload_speed = speed
            return True

        return False

    def _parse_comok(self, data):
        fields = data.lstrip(b"comok ").rstrip(NXEOL).split(b",")
        # Field 1 is "reserved-address"; only the address half matters.
        self.address = int(fields[1].split(b"-")[1])
        self.info = {
            "touch": bool(int(fields[0])),
            "model": fields[2].decode("ascii"),
            "fw_version": int(fields[3]),
            "mcu_code": int(fields[4]),
            "serial": fields[5].decode("ascii"),
            "flash_size": int(fields[6]),
        }

    def print_info(self):
        i = self.info
        print()
        print("DEVICE INFO")
        print("=" * 44)
        print(f"Model:         {i['model']}")
        print(f"Touch panel:   {'yes' if i['touch'] else 'no'}")
        print(f"FW version:    {i['fw_version']}")
        print(f"MCU code:      {i['mcu_code']}")
        print(f"Serial number: {i['serial']}")
        print(f"Flash size:    {i['flash_size']} bytes")
        print("=" * 44)
        print()

    def send_cmd(self, cmd):
        payload = cmd.encode("ascii") + NXEOL
        if self.address:
            payload = struct.pack("<H", self.address) + payload
        self.ser.write(payload)

    def ack(self):
        got = self.ser.read_until(bytes([ACK]))
        if not got.endswith(bytes([ACK])):
            raise RuntimeError(f"expected acknowledge 0x05, got {got!r}")

    def upload(self, path):
        with open(path, "rb") as f:
            f.seek(0x3c)
            file_size = struct.unpack("<I", f.read(4))[0]
        print(f"TFT size (from header 0x3c): {file_size} bytes")

        # The first command after connect is always lost; burn it on a no-op.
        self.send_cmd("bs=42")
        self.send_cmd("dims=100")
        self.send_cmd("sleep=0")
        self.ser.reset_input_buffer()

        print(f"Initiating upload at {self.upload_speed} baud... ", end="", flush=True)
        self.send_cmd(f"whmi-wris {file_size},{self.upload_speed},1")

        self.ser.close()
        self.ser.baudrate = self.upload_speed
        self.ser.timeout = 0.5
        self.ser.open()
        self.ack()
        print("ready.")

        remaining = -(-file_size // BLOCK_SIZE)
        first = True
        last_pct = -1
        with open(path, "rb") as f:
            while remaining:
                self.ser.write(f.read(BLOCK_SIZE))
                remaining -= 1

                if first:
                    first = False
                    # Computing the skip offset takes the device about a second.
                    self.ser.timeout = 2
                    reply = self.ser.read(5)
                    self.ser.timeout = 0.5
                    if len(reply) != 5 or reply[0] != SKIP:
                        raise RuntimeError(
                            f"first block: expected 0x08 + offset, got {reply!r}")
                    next_pos = struct.unpack_from("<I", reply, 1)[0]
                    if next_pos:
                        f.seek(next_pos)
                        remaining = -(-(file_size - next_pos) // BLOCK_SIZE)
                        print(f"Device skipped ahead to offset 0x{next_pos:x} "
                              f"(resources already match).")
                else:
                    self.ack()

                pct = 100 * f.tell() // file_size
                if pct != last_pct:
                    print(f"\r  {pct}% ({f.tell()}/{file_size} bytes)   ", end="")
                    sys.stdout.flush()
                    last_pct = pct

        print()
        print("Upload complete. The display will restart.")

    def close(self):
        self.ser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="TFT firmware file to upload")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0",
                    help="serial port (default: /dev/ttyUSB0)")
    ap.add_argument("-c", "--connect-speed", type=int, default=115200,
                    help="baud rate to try first when connecting (default: 115200)")
    ap.add_argument("-u", "--upload-speed", type=int, default=0,
                    help="baud rate for the data transfer (default: same as connect)")
    args = ap.parse_args()

    nx = Nextion(args.port, args.connect_speed, args.upload_speed)
    try:
        print(f"Connecting to display on {args.port}...")
        if not nx.connect():
            sys.exit("Could not find a display on that port at any baud rate.")
        nx.print_info()
        nx.upload(args.file)
    finally:
        nx.close()


if __name__ == "__main__":
    main()
