# Updating the I3CBlaster firmware

The firmware file is [`bin/i3cblaster.uf2`](../bin/i3cblaster.uf2). There are four ways to load it:

| Method | Needs | USB drive appears? | BOOTSEL button? |
|--------|-------|--------------------|-----------------|
| **A** Python helper `update_firmware.py` | Python 3 + pyserial, picotool | no | no |
| **B** Manual with picotool (`bootloader 1` + `picotool load`) | serial terminal, picotool | no | no |
| **C** Classic drive copy (`bootloader` + copy file) | nothing extra | yes | no |
| **D** Recovery (hold BOOTSEL while plugging in) | nothing extra | yes | yes |

Methods A and B use the RP2040 bootloader's **PICOBOOT** interface: the firmware command `bootloader 1` reboots into the bootloader with the USB mass storage drive disabled, so no RPI-RP2 drive pops up.

USB IDs used below:
- `2e8a:000a`: I3CBlaster running (USB serial port plus the pico-sdk "reset" interface).
- `2e8a:0003`: RP2040 in BOOTSEL mode (drive and/or PICOBOOT).

> The picotool command syntax below was checked against `picotool help load` / `help reboot` / `help info` of picotool 2.2.0-a4 and 2.3.1. The update flow hasn't been tested on hardware by the author of this guide yet. If something behaves differently, method D always works.

---

## 1. One-time setup

### Linux (PC, laptop, Raspberry Pi)

1. **Install picotool.** Use one of these:
   - From your distribution, if it packages picotool (e.g. Debian 13 "trixie" and newer):
     ```sh
     apt-cache policy picotool        # check whether a package exists
     sudo apt install picotool
     ```
   - The prebuilt binary from the Raspberry Pi [pico-sdk-tools releases](https://github.com/raspberrypi/pico-sdk-tools/releases): `picotool-<version>-x86_64-lin.tar.gz` for PCs, `picotool-<version>-aarch64-lin.tar.gz` for a Raspberry Pi with **64-bit** Raspberry Pi OS. It needs libusb:
     ```sh
     sudo apt install libusb-1.0-0
     mkdir -p ~/picotool && tar xzf picotool-*-lin.tar.gz -C ~/picotool
     ~/picotool/picotool/picotool version
     ```
     Then either use the full path `~/picotool/picotool/picotool`, or add `~/picotool/picotool` to your `PATH`.
   - 32-bit Raspberry Pi OS has no prebuilt binary. Use the apt package if available, or build picotool from source (see picotool's [BUILDING.md](https://github.com/raspberrypi/picotool/blob/master/BUILDING.md); it needs `build-essential pkg-config libusb-1.0-0-dev cmake` and a pico-sdk checkout).

2. **Allow USB access without sudo (udev rule).** Create `/etc/udev/rules.d/60-picotool.rules` with this content (the same as picotool's own `udev/60-picotool.rules`, shortened to the RP2040 IDs):
   ```
   SUBSYSTEM=="usb", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="0003", TAG+="uaccess", MODE="660", GROUP="plugdev"
   SUBSYSTEM=="usb", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="000a", TAG+="uaccess", MODE="660", GROUP="plugdev"
   ```
   Then reload the rules and replug the board:
   ```sh
   sudo udevadm control --reload
   sudo udevadm trigger
   ```
   - The `0003` line is the bootloader (PICOBOOT). The `000a` line lets picotool talk to the running I3CBlaster (needed only for `picotool ... -f`, see the tip below).
   - Make sure your user is in the `plugdev` group (`groups`; if not: `sudo usermod -aG plugdev $USER`, then log out and in).

3. **Serial port access** (for the terminal and Python). The I3CBlaster appears as `/dev/ttyACM0` (or `ttyACM1`, ...). On Debian / Raspberry Pi OS these belong to the `dialout` group:
   ```sh
   sudo usermod -aG dialout $USER   # then log out and in again
   ```

4. **For method A:** `sudo apt install python3-serial` (or `pip install pyserial`).

### Windows

1. **Install picotool.** Download `picotool-<version>-x64-win.zip` from the [pico-sdk-tools releases](https://github.com/raspberrypi/pico-sdk-tools/releases) and extract it, e.g. to `C:\tools\`. The program is `C:\tools\picotool\picotool.exe`. Add `C:\tools\picotool` to your `PATH`, or call it with the full path. If you use the Raspberry Pi Pico VS Code extension, it already downloads a picotool into `%USERPROFILE%\.pico-sdk\picotool\<version>\picotool\`, and you can use that one.

2. **Install the WinUSB driver for the RP2040 bootloader (Zadig).** On Windows, picotool can only talk to an **RP2040** bootloader after its PICOBOOT interface has the WinUSB driver. This is a one-time step:
   1. Put the I3CBlaster into the bootloader: send `bootloader` in a terminal (method C), or hold BOOTSEL while plugging in.
   2. Download and run Zadig from https://zadig.akeo.ie/
   3. Select **"RP2 Boot (Interface 1)"** in the drop-down. If it isn't listed, enable *Options → List All Devices*.
   4. Choose **WinUSB** as the driver (not libusb-win32), then click *Install Driver* / *Replace Driver*.
   5. **Do not** change "RP2 Boot (Interface 0)"; that is the USB drive and must stay *USBSTOR*.

   After `bootloader 1` (no drive) Windows may list the boot device differently. If `picotool info` then reports *"appears to be in BOOTSEL mode, but picotool was unable to connect"*, run Zadig again in that state and install WinUSB for the RP2 Boot entry that is shown.

3. **Serial port:** the I3CBlaster appears as a `COMx` port (see Device Manager → Ports). No driver is needed.

4. **For method A:** install Python 3 from python.org, then run `py -m pip install pyserial`.

---

## 2. Method A: Python helper (recommended)

From the repository folder:

```sh
# Linux / Raspberry Pi
python3 python/update_firmware.py bin/i3cblaster.uf2
python3 python/update_firmware.py --port /dev/ttyACM0 --picotool ~/picotool/picotool/picotool bin/i3cblaster.uf2
```
```bat
:: Windows
py python\update_firmware.py bin\i3cblaster.uf2
py python\update_firmware.py --port COM5 --picotool C:\tools\picotool\picotool.exe bin\i3cblaster.uf2
```

What it does:
1. Finds the I3CBlaster (USB `2e8a:000a`, or `--port` / `--serial`) and sends `bootloader 1`.
2. Waits until `picotool info` finds the bootloader.
3. Runs `picotool load -v -x <uf2>`: loads, verifies (`-v`) and starts the new firmware (`-x`).
4. Waits until the I3CBlaster serial port is back, then prints `Firmware update done, I3CBlaster is back.`

Options: `--timeout <s>` (default 20 s per step), `--no-verify` (skips `-v`).

Typical error messages:

| Message | What to do |
|---------|-----------|
| `picotool not found ('picotool')` | Install picotool or pass `--picotool <full path>`. |
| `RP2040 bootloader (PICOBOOT, USB 2e8a:0003) not found within 20s` | Linux: udev rule / plugdev group (or try once with `sudo`). Windows: Zadig/WinUSB step. |
| `no I3CBlaster serial port and no RP2040 in BOOTSEL mode found` | Board not connected, wrong `--port`, or no access to the serial port (Linux: `dialout` group). |
| `picotool load failed ...` | The picotool output is shown. Try again, or use method D. |

From your own Python code:
```python
import i3cblaster
i3c = i3cblaster.i3cblaster()
i3c.init(port='COM5')        # optional; default: auto-detect
print(i3c.update_firmware('bin/i3cblaster.uf2', picotool='picotool', timeout=20, verify=True))
```

---

## 3. Method B: manual with picotool

1. Open the I3CBlaster serial port in a terminal (PuTTY, `screen /dev/ttyACM0`, `minicom -D /dev/ttyACM0`, ...) and type:
   ```
   > bootloader 1
   OK(0)
   ```
   The serial port disappears. **No** USB drive appears; this is expected.
   Close the terminal program now so it doesn't keep the port busy.
2. Check that picotool sees the bootloader:
   ```sh
   picotool info
   ```
   It should list the RP2040 device and the program currently in flash (name `i3cblaster`).
3. Load the new firmware, verify it and start it:
   ```sh
   picotool load -v -x bin/i3cblaster.uf2
   ```
   `-v` = verify after writing, `-x` = execute (start) the program after loading.
4. The I3CBlaster restarts and its serial port comes back. Open the terminal again; the welcome banner shows the new `Version:`. `info` also prints it.

You can also check a `.uf2` file before loading it, without a device: `picotool info -a bin/i3cblaster.uf2`.

**Tip (no terminal step):** the firmware also contains the pico-sdk USB reset interface, which picotool's `-f` / `--force` option uses ("Force a device not in BOOTSEL mode but running compatible code to reset so the command can be executed"). So this should work in one step:
```sh
picotool load -v -x -f bin/i3cblaster.uf2
```
On Linux it needs the `000a` udev line from the setup. This is how picotool and the pico-sdk work in general, but it hasn't been tried with the I3CBlaster yet. If it fails, use steps 1-3.

---

## 4. Method C: classic USB drive copy

1. In the terminal type `bootloader` (or `bootloader 0`). The I3CBlaster answers `OK(0)` and the **RPI-RP2** drive appears.
2. Copy `bin/i3cblaster.uf2` onto that drive, e.g. by drag-and-drop or `cp bin/i3cblaster.uf2 /media/$USER/RPI-RP2/`.
3. The drive disappears by itself and the new firmware starts.

---

## 5. Method D: recovery if the board is stuck

If the I3CBlaster doesn't answer any more (no serial port, a bad firmware, or an update was interrupted):

1. Unplug the USB cable.
2. **Hold the BOOTSEL button** (on the Raspberry Pi Pico, or the "B" button on the Seeed Xiao RP2040) and plug the USB cable in.
3. Release the button. The RP2040 ROM bootloader always starts this way, regardless of the flash content. It offers both the RPI-RP2 drive and PICOBOOT.
4. Copy `i3cblaster.uf2` onto the drive (method C, step 2), **or** run `picotool load -v -x bin/i3cblaster.uf2` (method B, step 3).

The RP2040 bootloader is in ROM, so a failed firmware update can't brick the board; method D always gets it back.

---

## Command reference

- [`bootloader [no_drive]`](COMMANDS.md#bootloader): `bootloader` / `bootloader 0` = drive + PICOBOOT, `bootloader 1` = PICOBOOT only.
- [`reset [bootloader]`](COMMANDS.md#reset): `reset 1` = same as `bootloader` (drive + PICOBOOT).
