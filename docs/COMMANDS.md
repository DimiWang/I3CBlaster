# I3CBlaster command reference

This document describes every command that the I3CBlaster firmware registers on its USB serial command line (see `ucli_cmd_register(...)` in `src/main.c` and `src/ucli.c`). For each command it lists the purpose, syntax, parameters and **every response the firmware can return**, together with what the response means.

Everything here was taken from the firmware source (`src/main.c`, `src/i3c_hl.c`, `src/ucli.c`). Where the source behaves in an unexpected way or the intent is unclear, this is marked with **⚠ Note**. Those points are also collected in [Known quirks and unclear points](#known-quirks-and-unclear-points-found-in-the-source).

## Contents

- [Protocol basics](#protocol-basics)
  - [Connection and line format](#connection-and-line-format)
  - [Interactive mode vs. automation mode (`@`)](#interactive-mode-vs-automation-mode-)
  - [Argument format](#argument-format)
  - [Response format](#response-format)
  - [Status / error code table](#status--error-code-table)
  - [Command line parser errors (all commands)](#command-line-parser-errors-all-commands)
  - [Payload parser errors](#payload-parser-errors)
  - [Errors common to all I3C SDR transfers](#errors-common-to-all-i3c-sdr-transfers)
- [Command overview](#command-overview)
- General commands: [help](#help), [info](#info), [reset](#reset), [bootloader](#bootloader), [gpio_write](#gpio_write), [gpio_read](#gpio_read)
- I3C bus setup: [i3c_clk](#i3c_clk), [i3c_drivestrength](#i3c_drivestrength), [i3c_recover](#i3c_recover), [i3c_targetreset](#i3c_targetreset)
- I3C addressing: [i3c_scan](#i3c_scan), [i3c_rstdaa](#i3c_rstdaa), [i3c_entdaa](#i3c_entdaa)
- I3C SDR transfers: [i3c_sdr_write](#i3c_sdr_write), [i3c_sdr_read](#i3c_sdr_read), [i3c_sdr_writeread](#i3c_sdr_writeread)
- I3C CCCs: [i3c_sdr_ccc_bc_write](#i3c_sdr_ccc_bc_write), [i3c_sdr_ccc_direct_write](#i3c_sdr_ccc_direct_write), [i3c_sdr_ccc_direct_read](#i3c_sdr_ccc_direct_read)
- I3C IBI / Hot-Join: [i3c_poll](#i3c_poll)
- I3C HDR-DDR: [i3c_ddr_config](#i3c_ddr_config), [i3c_ddr_write](#i3c_ddr_write), [i3c_ddr_read](#i3c_ddr_read), [i3c_ddr_writeread](#i3c_ddr_writeread)
- I2C: [i2c_clk](#i2c_clk), [i2c_timeout](#i2c_timeout), [i2c_scan](#i2c_scan), [i2c_write](#i2c_write), [i2c_read](#i2c_read), [i2c_writeread](#i2c_writeread)
- [Known quirks and unclear points found in the source](#known-quirks-and-unclear-points-found-in-the-source)

---

## Protocol basics

### Connection and line format

- The I3CBlaster enumerates as a USB CDC serial port (USB VID `0x2E8A`, PID `0x000A`, as used by the Python module). The baud rate setting doesn't matter for USB CDC; the Python module uses 115200.
- When a terminal opens the port, the firmware waits 500 ms. It then clears the screen and prints a welcome banner, a `Version: <git describe>` line and the prompt `> `.
- A command line is executed when **CR (`\r`, 0x0D)** is received. LF (`\n`) is not treated as Enter.
- The maximum command line length is **256 characters**. Characters beyond that are silently dropped, which also limits how many payload bytes fit in one command.
- Command names are case sensitive and must match exactly (`strcmp`). TAB completes command names.
- Arguments are separated by **exactly one space**. Two spaces between arguments, or a trailing space, give `ERROR: Extra whitespace between arguments`. A line that **starts** with a space is silently ignored and nothing is executed.
- An empty line does nothing.

### Interactive mode vs. automation mode (`@`)

| Mode | How | Behaviour |
|------|-----|-----------|
| Interactive | Type the command and press Enter | Typed characters are echoed, the response follows on a new line, then the prompt `> ` is printed. Line editing, history (cursor up) and TAB completion work. Press F1 once so the firmware can detect PuTTY vs. other terminal emulation for the Backspace/Del keys. |
| Automation | Send `@` as the **first** character of the line, e.g. `@i3c_scan\r` | No echo and no prompt, only the response line(s). `@` applies to that one line only. This is what the Python module uses. |

### Argument format

| Type | Format | Notes |
|------|--------|-------|
| integer (`INT`) | Parsed with `strtol(..., 0)`: decimal `48`, hex `0x30`, **octal with leading zero** (`010` = 8) | The whole token must be a number, otherwise you get `ERROR: Invalid value for '<arg>' (<token>)`. Negative numbers are accepted by the parser. Most commands do **not** range-check (see each command). |
| byte list (`STR`, bytes) | Comma separated byte values **without spaces**, e.g. `0x12,0x43,0x56` | Each value 0..255 (any `strtol` base). See [Payload parser errors](#payload-parser-errors). |
| word list (`STR`, 16-bit words) | Comma separated 16-bit values without spaces, e.g. `0x1234,0x5678` | Each value 0..65535. Used by the HDR-DDR commands. |
| optional argument | Shown as `[name]` | Only the **last** argument of a command can be optional. If it is omitted, the firmware uses its internal "not given" value. |

### Response format

Almost every command answers with **one line terminated by `\r\n`**:

```
<STATUS>(<code>)[,<value>[,<value>...]]
```

- `<STATUS>(<code>)` is a text name followed by a numeric code in brackets, e.g. `OK(0)` or `ERR_NAKED(3)`. **`0` means success**. The Python module treats exactly the text `OK(0)` as success.
- Data values follow, separated by commas, with no spaces. Bytes are printed as `0x%02x` (e.g. `0x4a`), 16-bit DDR words as `0x%04x`, counts and GPIO values in decimal.
- Exceptions to the one-line rule:
  - `help`, `info` and the parser/`ucli_error` errors print text (with ANSI colour escape sequences) instead of, or in addition to, a status line.
  - `reset` and `bootloader` reply `OK(0)` and then the USB device disconnects.

### Status / error code table

The status text and code come from `i3c_hl_get_errorstring()` in `src/i3c_hl.c`:

| Code | Response text | Meaning |
|-----:|---------------|---------|
| 0 | `OK(0)` | Success. |
| 1 | `ERR_IBI_ARBITRATION(1)` | Before or during the arbitration header a target pulled SDA low (In-Band Interrupt or Hot-Join request), or a target won address arbitration. **The requested transfer was not executed.** The bus is left without a STOP so that `i3c_poll` can read the IBI. Call [`i3c_poll`](#i3c_poll), then retry. |
| 2 | `ERR_NAKED_DURING_ARBHDR(2)` | Nobody acknowledged the broadcast address `0x7E` in the arbitration header. Usually this means no I3C target is on the bus, the target isn't powered, or the bus has a wiring/level problem. |
| 3 | `ERR_NAKED(3)` | The addressed target did not acknowledge its address in the SDR address phase. Wrong or unassigned dynamic address, or the target is busy. For `i3c_entdaa` this also means "no target left to assign" (see there). |
| 4 | `ERR_INVALID_PARAMETER(4)` | A parameter is outside the range the command accepts. |
| 5 | `WARN_NO_IBI(5)` | Only from `i3c_poll`: no IBI / Hot-Join request is pending. Not an error. |
| 6 | `ERR_NAKED_DDR(6)` | HDR-DDR: the target did not acknowledge the read command. |
| 7 | `WARN_EARLY_TERMINATED(7)` | HDR-DDR write: the target requested early termination. **⚠ Note:** this code is never returned in the current source (see quirks). |
| 8 | `ERR_DDR_INVALID_PREAMBLE(8)` | HDR-DDR read: unexpected preamble bits received (neither data nor CRC). |
| 9 | `ERR_DDR_READ_PARITY_WRONG(9)` | HDR-DDR read: parity bits of a received data word are wrong. |
| 10 | `ERR_DDR_READ_CRC_WRONG(10)` | HDR-DDR read: CRC5 mismatch. **⚠ Note:** this code is never returned in the current source (see quirks). |
| 11 | `ERR_I2C_FAILED(11)` | I2C transfer failed: the address or a data byte was not acknowledged, or the transfer ran into the [`i2c_timeout`](#i2c_timeout). |
| other | `ERR_UNDEFINED(<n>)` | Fallback for unknown codes; not produced by any current command. |

### Command line parser errors (all commands)

These come from `src/ucli.c`. They are printed **instead of** running the command, with ANSI colour codes around the text (`ESC[30;41m ... ESC[0m`, black on red) and a `\r\n` ending. **They have no `(<code>)` part.**

| Response (without colour codes) | When |
|---------------------------------|------|
| `ERROR: Command not found (<name>)` | The first word is not a registered command name. |
| `ERROR: Too many arguments` | More arguments than the command accepts. |
| `ERROR: Too few arguments` | A required argument is missing. |
| `ERROR: Invalid value for '<arg>' (<token>)` | An integer argument isn't a complete number (e.g. `0x3g`, `abc`), or overflows `long`. |
| `ERROR: Extra whitespace between arguments` | Two spaces between arguments, or a trailing space. |
| *(nothing)* | Empty line, or the line starts with a space. |

### Payload parser errors

Byte and word lists are parsed in `parse_array_string()` / `parse_array_string_uint16()` in `src/main.c`. Errors are printed through `ucli_error()` as `ERROR: <message>` with the same colour codes:

| Response | When |
|----------|------|
| `ERROR: payload byte values have to be in range 0..255` | A byte list value is < 0 or > 255. |
| `ERROR: payload byte values have to be in range 0..65535` | A word list value is < 0 or > 65535. |
| `ERROR: payload too long` | More than 1024 values. |

**⚠ Note:** after a payload error, parsing stops but **the command still runs** with the values parsed so far. You then get the error line **followed by** the normal status line (two lines). A non-numeric value inside a list (e.g. `0x12,zz`) isn't detected as invalid: it is stored as `0` repeatedly until the list is full, then `payload too long` is printed. The transfer then runs with that padded payload. Only send well-formed lists.

### Errors common to all I3C SDR transfers

Every I3C SDR command that touches the bus (`i3c_entdaa`, `i3c_sdr_*`, `i3c_sdr_ccc_*`) works like this:

1. Check whether a target already pulls SDA low (a pending IBI or Hot-Join). If so, the result is `ERR_IBI_ARBITRATION(1)` and nothing is sent.
2. START + arbitration header `0x7E`/W in open-drain mode.
   - If a target wins arbitration, the result is `ERR_IBI_ARBITRATION(1)`. No STOP is sent; use `i3c_poll` to collect the IBI.
   - If `0x7E` is not acknowledged, the result is `ERR_NAKED_DURING_ARBHDR(2)`.
3. The command-specific part follows. A NAK of a target address gives `ERR_NAKED(3)`.
4. STOP (except after an IBI arbitration).

Data **bytes** written in SDR mode are not individually acknowledged in I3C. A private or CCC write therefore can't report a "data NAK"; only the address phases can fail.

For SDR **reads**, the target may end the read early using the T-bit. The firmware then returns **fewer bytes than requested**. This is not an error: the status is still `OK(0)`, just with fewer values.

---

## Command overview

| Command | Syntax | Purpose |
|---------|--------|---------|
| [help](#help) | `help [command]` | List commands or show details of one |
| [info](#info) | `info` | Version and debug information |
| [reset](#reset) | `reset [bootloader]` | Software reset of the I3CBlaster |
| [bootloader](#bootloader) | `bootloader` | Reboot into the RP2040 USB bootloader |
| [gpio_write](#gpio_write) | `gpio_write port state` | Drive a GPIO high/low or make it an input |
| [gpio_read](#gpio_read) | `gpio_read [gpionum]` | Read all GPIOs or one GPIO |
| [i3c_clk](#i3c_clk) | `i3c_clk freq_khz` | Set the I3C SDR clock |
| [i3c_drivestrength](#i3c_drivestrength) | `i3c_drivestrength strength` | Set SDA/SCL pad drive strength |
| [i3c_recover](#i3c_recover) | `i3c_recover` | Re-initialise the I3C driver |
| [i3c_targetreset](#i3c_targetreset) | `i3c_targetreset` | Send the I3C Target Reset pattern |
| [i3c_scan](#i3c_scan) | `i3c_scan` | List acknowledging I3C addresses |
| [i3c_rstdaa](#i3c_rstdaa) | `i3c_rstdaa` | Broadcast RSTDAA (reset all dynamic addresses) |
| [i3c_entdaa](#i3c_entdaa) | `i3c_entdaa addr` | Assign one dynamic address with ENTDAA |
| [i3c_sdr_write](#i3c_sdr_write) | `i3c_sdr_write addr [payload]` | Private SDR write |
| [i3c_sdr_read](#i3c_sdr_read) | `i3c_sdr_read addr len` | Private SDR read |
| [i3c_sdr_writeread](#i3c_sdr_writeread) | `i3c_sdr_writeread addr payload len` | Private write + repeated START + read |
| [i3c_sdr_ccc_bc_write](#i3c_sdr_ccc_bc_write) | `i3c_sdr_ccc_bc_write payload` | Broadcast CCC write |
| [i3c_sdr_ccc_direct_write](#i3c_sdr_ccc_direct_write) | `i3c_sdr_ccc_direct_write addr bc_payload dir_payload` | Direct CCC write |
| [i3c_sdr_ccc_direct_read](#i3c_sdr_ccc_direct_read) | `i3c_sdr_ccc_direct_read addr payload len` | Direct CCC read |
| [i3c_poll](#i3c_poll) | `i3c_poll` | Read a pending IBI / Hot-Join |
| [i3c_ddr_config](#i3c_ddr_config) | `i3c_ddr_config crc_word_indicator enable_early_write_term write_ack_enable` | HDR-DDR target capability settings |
| [i3c_ddr_write](#i3c_ddr_write) | `i3c_ddr_write addr cmd payload` | HDR-DDR write |
| [i3c_ddr_read](#i3c_ddr_read) | `i3c_ddr_read addr cmd wordcount` | HDR-DDR read |
| [i3c_ddr_writeread](#i3c_ddr_writeread) | `i3c_ddr_writeread addr wrcmd rdcmd payload wordcount` | HDR-DDR write + HDR restart + read |
| [i2c_clk](#i2c_clk) | `i2c_clk freq_khz` | Set the I2C clock |
| [i2c_timeout](#i2c_timeout) | `i2c_timeout timeout_ms` | Set the I2C transfer timeout |
| [i2c_scan](#i2c_scan) | `i2c_scan` | List acknowledging I2C addresses |
| [i2c_write](#i2c_write) | `i2c_write addr [payload]` | I2C write |
| [i2c_read](#i2c_read) | `i2c_read addr len` | I2C read |
| [i2c_writeread](#i2c_writeread) | `i2c_writeread addr payload len` | I2C write + repeated START + read |

That is 30 commands. Not registered and therefore not available: `clkinfo`, `i3c_gpiobase` and `i3c_signaltest`. They exist in the source but their `ucli_cmd_register` lines are absent or commented out.

**Pins:** I3C SDA/SCL are GPIO16/GPIO17 on a Raspberry Pi Pico and GPIO6/GPIO7 on a Seeed Xiao RP2040 (detected at start-up). I2C commands temporarily switch the **same two pins** to the RP2040 I2C peripheral (`i2c0` on Pico, `i2c1` on Xiao) and switch them back to I3C afterwards.

---

## General commands

> Data values in the examples below are illustrative; real values depend on the connected target.

### help

List all commands, or show the description and parameters of one command.

**Syntax:** `help [command]`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `command` | string | any registered command name | (list all) | optional | Command to show details for |

**Responses**

| Response | Meaning |
|----------|---------|
| `Available commands:` followed by one line per command: `  <name> - <description>` (wrapped at 80 columns) | `help` without argument. |
| Description line, `Usage: <command> <arg> [<optional arg>]`, then one line per argument `  <arg> - <description>` | `help <command>` for a known command. |
| `ERROR: Unknown command (<command>)` (red) | `help <command>` with an unknown name. |

Output contains ANSI escape codes (bold/underline/colour). There is no `OK(0)` line.

**Example**
```
> help i3c_clk
Set I3C clock frequency
Usage: i3c_clk freq_khz
  freq_khz - The Clock frequency as integer number in units of kHz. Valid range: 49..12500
```

### info

Shows the firmware version and some debug information.

**Syntax:** `info` (no parameters)

**Responses** (multi-line, no status line):
```
Version: <git describe string, e.g. initial-41-gc02bc4d>
Supported protocols: I3C SDR, I3C OD
Automated command mode:
-----------------------
By sending @ as first character for each command, there is
no character echoed back for easier automation fromout PC
[0000] = xxxxxxxx
[0004] = xxxxxxxx
...
[0128] = xxxxxxxx
```
The `[offset] = value` lines are a hex dump of the RP2040 **PIO0 register block** (offsets 0x000..0x128), meant for debugging. **⚠ Note:** these dump lines end with `\n` only, not `\r\n`. The "Supported protocols" text doesn't mention HDR-DDR or I2C, although both are supported.

### reset

Software reset of the I3CBlaster itself (RP2040 reboot through the watchdog). This does **not** reset I3C targets; for that use [`i3c_targetreset`](#i3c_targetreset).

**Syntax:** `reset [bootloader]`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `bootloader` | integer | 0 or 1 | 0 | optional | 0 / omitted = normal reboot; 1 = same as [`bootloader`](#bootloader) |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Accepted. About 100 ms later the device reboots: the serial port disconnects and re-enumerates, followed by a fresh welcome banner. |
| `ERROR: bootloader has to be 0 or 1` (red) | Argument other than 0 or 1. Nothing happens. |
| `ERROR: Invalid value for 'bootloader' (...)` | Argument isn't a number. |

**Example:** `@reset` gives `OK(0)`, then the USB device disconnects. Python: `i3c.reset()`.

### bootloader

Reboots into the RP2040 ROM USB bootloader (BOOTSEL mode) for a firmware update, without pressing the BOOTSEL button.

**Syntax:** `bootloader` (no parameters)

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Accepted. About 100 ms later the device calls `reset_usb_boot(0,0)`: the serial port disappears and the board appears as the **RPI-RP2** USB mass storage drive. Copy an `i3cblaster.uf2` onto that drive to flash it. |

**Example:** `@bootloader` gives `OK(0)`. Python: `i3c.bootloader()` (alias `enter_bootloader()`).

### gpio_write

Sets a GPIO pin to output-high, output-low or input (tri-state).

**Syntax:** `gpio_write port state`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `port` | integer | 0..31 accepted (help text says 0..29) | – | required | GPIO number |
| `state` | string, 1 character | `0`, `1`, `Z` / `z` | – | required | `0` = output low, `1` = output high, `Z` = input (high impedance) |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Pin set. |
| `ERR_INVALID_PARAMETER(4)` | `port` outside 0..31, `state` longer than one character, or a character other than 0/1/Z. |

**⚠ Note:** only GPIO0..15 are initialised as plain GPIOs at start-up. Higher pins (e.g. the I3C pins, or GPIO25 which is the activity LED) keep their current function. Writing them may have no visible effect, or be overridden by the LED logic. Python: `gpio_write(gpionum, state)`.

**Example**
```
> gpio_write 3 1
OK(0)
```

### gpio_read

Reads the input state of all GPIOs, or of one GPIO.

**Syntax:** `gpio_read [gpionum]`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `gpionum` | integer | 0..31 accepted (help text says 0..29) | all | optional | GPIO to read |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0),<n>` | Without argument: `<n>` is a **decimal** 32-bit number. Bit *i* is the pad input level of GPIO *i* (0..29). |
| `OK(0),0` / `OK(0),1` | With `gpionum`: level of that pin. |
| `ERR_INVALID_PARAMETER(4),<n>` | `gpionum` < 0 or > 31. The value after the comma is still printed but is meaningless. |

**Example**
```
> gpio_read 3
OK(0),1
```

---

## I3C bus setup

### i3c_clk

Sets the I3C SDR push-pull clock frequency. At start-up the clock is 12.5 MHz (PIO clock divider 1.0).

**Syntax:** `i3c_clk freq_khz`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `freq_khz` | integer | 49..12500 | 12500 at boot | required | SCL frequency in kHz |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Frequency set; the divider is `12500*65536/freq_khz`, so the real value is quantised. |
| `ERR_INVALID_PARAMETER(4)` | Below 49 or above 12500. |

**Example:** `i3c_clk 1000` gives `OK(0)`. **⚠ Note:** the Python method `i3c_clk()` sends `i3c_clock`, which doesn't exist (it gets `ERROR: Command not found`).

### i3c_drivestrength

Sets the RP2040 pad drive strength of SDA and SCL. Lower values can reduce ringing and crosstalk.

**Syntax:** `i3c_drivestrength strength`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `strength` | integer | 2, 4, 8, 12 | 12 (set by `i3c_init`) | required | Drive strength in mA |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Set. |
| `ERR_INVALID_PARAMETER(4)` | Value other than 2, 4, 8 or 12. |

**Example:** `i3c_drivestrength 4` gives `OK(0)`.

### i3c_recover

Re-initialises the I3C driver (PIO state machines and pin setup) on the board's I3C pins. Use this if the bus or PIO got stuck.

**Syntax:** `i3c_recover` (no parameters)

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Always returned; `i3c_init()` has no failure path. |

**⚠ Note:** `i3c_init()` also restores the drive strength to 12 mA and the PIO clock divider to 1.0 (12.5 MHz). Settings made with `i3c_clk` / `i3c_drivestrength` are therefore lost; this follows from the code and hasn't been tested on hardware.

### i3c_targetreset

Generates the I3C **Target Reset pattern** (14 SDA transitions while SCL is low, followed by a Repeated START and STOP) on the bus. This resets the I3C targets according to their RSTACT configuration, not the I3CBlaster.

**Syntax:** `i3c_targetreset` (no parameters)

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Pattern sent. Always returned; targets don't acknowledge the pattern. |

---

## I3C addressing

### i3c_scan

Checks every 7-bit address 0x00..0x7F for an acknowledge: START, `0x7E`/W, Repeated START, `addr`/W, STOP. Reserved I3C addresses `0x3E, 0x5E, 0x6E, 0x76, 0x7A, 0x7C, 0x7F` are skipped.

**Syntax:** `i3c_scan` (no parameters)

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0),0x30,0x31` | Addresses that acknowledged, as a comma separated list. |
| `OK(0),` | Nothing acknowledged. Note the trailing comma. |

The status is always `OK(0)`. Addresses where the arbitration header was NAKed or an IBI happened are simply not listed.

**⚠ Note:**
- If an IBI is pending, the firmware prints `IBI CHECK` plus a newline (`\n` only) in the middle of the scan output. This breaks the one-line format.
- `0x7E` itself is not in the skip list, so when any I3C target is present `0x7e` may show up in the result.

**Example**
```
> i3c_scan
OK(0),0x30
```

### i3c_rstdaa

Sends the broadcast CCC **RSTDAA** (0x06): all targets lose their dynamic address.

**Syntax:** `i3c_rstdaa` (no parameters)

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | **Always.** The command ignores the transfer result, so an IBI or a NAKed arbitration header isn't reported. |

### i3c_entdaa

Runs **one** ENTDAA round. It sends the broadcast CCC ENTDAA (0x07), reads the 8 bytes from the winning target (48-bit Provisioned ID, BCR, DCR), then assigns `addr` (with the parity bit added by the firmware).

**Syntax:** `i3c_entdaa addr`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | Dynamic address to assign |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0),b0,b1,b2,b3,b4,b5,b6,b7` | A target took part and accepted `addr`. b0..b5 = Provisioned ID (MSB first), b6 = BCR, b7 = DCR. |
| `ERR_NAKED(3)` | Either no target answered the ENTDAA read (`0x7E`/R NAKed; all targets already have an address, or none is present), **or** the target NAKed the assigned address. The Python module treats this as "no device" and returns `None`. |
| `ERR_NAKED_DURING_ARBHDR(2)` | No target acknowledged `0x7E`. |
| `ERR_IBI_ARBITRATION(1)` | IBI or Hot-Join pending or arbitrated; nothing was assigned. |
| `ERROR: address has to be in range  0..0x7f` (red) | `addr` < 0 or ≥ 0x80. Nothing is sent. |

To assign several targets, call `i3c_entdaa` repeatedly with different addresses until it returns `ERR_NAKED(3)`.

**Example**
```
> i3c_entdaa 0x30
OK(0),0x04,0x6a,0x00,0x00,0x00,0x00,0x27,0xa0
```

---

## I3C SDR transfers

Common responses: see [Errors common to all I3C SDR transfers](#errors-common-to-all-i3c-sdr-transfers).

### i3c_sdr_write

Private write: START, `0x7E`/W, Repeated START, `addr`/W, data bytes, STOP.

**Syntax:** `i3c_sdr_write addr [payload]`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | 7-bit dynamic (or static) target address |
| `payload` | byte list | 0..255 each, ≤ 1024 values (line limit 256 chars) | none | optional | Bytes to write. Without payload, only the address is sent. |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Address acknowledged and all bytes sent. |
| `ERR_NAKED(3)` | Target didn't acknowledge `addr`. No data was sent. |
| `ERR_NAKED_DURING_ARBHDR(2)` / `ERR_IBI_ARBITRATION(1)` | See the common errors. |
| `ERROR: payload ...` + status line | Payload parse problem (see [Payload parser errors](#payload-parser-errors)). |

**Example:** `i3c_sdr_write 0x30 0x36,0xC0` gives `OK(0)`.

### i3c_sdr_read

Private read: START, `0x7E`/W, Repeated START, `addr`/R, up to `len` bytes, STOP.

**Syntax:** `i3c_sdr_read addr len`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | Target address |
| `len` | integer | help text says 0..255; **not checked**, buffer is 1024 | – | required | Maximum number of bytes to read |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0),0x12,0x34,...` | Bytes read. There can be **fewer** than `len` if the target ended the read (T-bit). |
| `OK(0)` | `len` was 0. |
| `ERR_NAKED(3)` | Target didn't acknowledge `addr`/R. No data. |
| `ERR_NAKED_DURING_ARBHDR(2)` / `ERR_IBI_ARBITRATION(1)` | See the common errors. |

**⚠ Note:** `len` > 1024 or a negative `len` overflow the 1024-byte receive buffer. There is no check.

**Example:** `i3c_sdr_read 0x30 2` gives `OK(0),0x43,0x10`.

### i3c_sdr_writeread

Private write followed by a Repeated START and a private read, typically "write register index, then read". START, `0x7E`/W, Sr, `addr`/W, payload, Sr, `addr`/R, read up to `len` bytes, STOP.

**Syntax:** `i3c_sdr_writeread addr payload len`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | Target address |
| `payload` | byte list | 0..255 each | – | required | Bytes written before the read (e.g. register index) |
| `len` | integer | help: 0..255; not checked, buffer 1024 | – | required | Maximum number of bytes to read |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0),0x..,...` | Read data; can be shorter than `len` (T-bit). |
| `ERR_NAKED(3)` | Target NAKed `addr`/W or `addr`/R; no data printed. |
| `ERR_NAKED_DURING_ARBHDR(2)` / `ERR_IBI_ARBITRATION(1)` | See the common errors. |

**Example**
```
> i3c_sdr_writeread 0x30 0x03 8
OK(0),0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08
```

---

## I3C CCCs

### i3c_sdr_ccc_bc_write

Broadcast CCC: START, `0x7E`/W, then the payload bytes (first byte = CCC code, optional defining byte and data), STOP.

**Syntax:** `i3c_sdr_ccc_bc_write payload`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `payload` | byte list | 0..255 each | – | required | CCC code (0x00..0x7F for broadcast CCCs) followed by optional data |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Sent. There is no per-target acknowledge for broadcast CCC data. |
| `ERR_NAKED_DURING_ARBHDR(2)` / `ERR_IBI_ARBITRATION(1)` | See the common errors. |

**Example:** ENEC broadcast enabling interrupts, `i3c_sdr_ccc_bc_write 0x00,0x01`, gives `OK(0)`.

### i3c_sdr_ccc_direct_write

Direct CCC write: START, `0x7E`/W, `bc_payload` (direct CCC code 0x80..0xFE plus optional defining byte), Sr, `addr`/W, `dir_payload`, STOP.

**Syntax:** `i3c_sdr_ccc_direct_write addr bc_payload dir_payload`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | Target address |
| `bc_payload` | byte list | 0..255 each | – | required | Bytes in the broadcast phase (the CCC code, optional defining byte) |
| `dir_payload` | byte list | 0..255 each | – | required | Bytes written to the target after its address |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Done. |
| `ERR_NAKED(3)` | Target NAKed its address; no direct data was sent. |
| `ERR_NAKED_DURING_ARBHDR(2)` / `ERR_IBI_ARBITRATION(1)` | See the common errors. |

**Example:** direct ENEC to 0x30, `i3c_sdr_ccc_direct_write 0x30 0x80 0x01`, gives `OK(0)`.

**⚠ Note:** the Python method `i3c_sdr_ccc_direct_write()` sends the command name `i3c_sdr_ccc_bc_write` with three arguments and so gets `ERROR: Too many arguments`.

### i3c_sdr_ccc_direct_read

Direct CCC read: START, `0x7E`/W, `payload` (direct CCC code plus optional defining byte), Sr, `addr`/R, read up to `len` bytes, STOP.

**Syntax:** `i3c_sdr_ccc_direct_read addr payload len`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | Target address |
| `payload` | byte list | 0..255 each | – | required | CCC code (e.g. 0x8D GETPID, 0x8E GETBCR, 0x8F GETDCR) plus optional defining byte |
| `len` | integer | not checked, buffer 1024 | – | required | Maximum bytes to read |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0),0x..,...` | Data returned by the target; may be shorter than `len` (T-bit). |
| `ERR_NAKED(3)` | Target NAKed `addr`/R (e.g. it doesn't support that CCC). |
| `ERR_NAKED_DURING_ARBHDR(2)` / `ERR_IBI_ARBITRATION(1)` | See the common errors. |

**Example**
```
> i3c_sdr_ccc_direct_read 0x30 0x8d 6
OK(0),0x04,0x6a,0x00,0x00,0x00,0x00
```

---

## I3C IBI / Hot-Join

### i3c_poll

Reads a pending In-Band Interrupt or Hot-Join request. There are two cases:
1. A previous command returned `ERR_IBI_ARBITRATION(1)` because a target won the arbitration header. The address the target sent is reported and its IBI payload bytes are read.
2. No previous arbitration, but a target currently holds SDA low (IBI request). The firmware reads the target's address byte in open-drain mode and acknowledges it. Unless that byte is `0x04` (Hot-Join), it then reads the payload bytes.

**Syntax:** `i3c_poll` (no parameters)

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0),<hdr>[,<data>...]` | IBI received. `<hdr>` is the byte the target sent in the address phase (7-bit address << 1 \| RnW). The following bytes are the IBI payload (mandatory data byte etc.), read until the target ends with the T-bit, up to the internal buffer size of 16 bytes. |
| `OK(0),0x04` | Hot-Join request (address 0x02, RnW = 0). No payload. The Hot-Joining target then needs `i3c_entdaa`. |
| `WARN_NO_IBI(5)` | Nothing pending. |

**⚠ Note:** the receive buffer is 16 bytes, but the loop can store one header byte plus up to 16 payload bytes. A very long IBI payload could therefore overrun the buffer by one byte. Check `i3c_hl_poll()` if you rely on long IBI payloads.

**Example**
```
> i3c_poll
OK(0),0x61,0x02
```

---

## I3C HDR-DDR

HDR-DDR commands enter HDR mode with ENTHDR0 (broadcast CCC 0x20), run the DDR transfer and leave with an HDR Exit pattern. Command codes are 7 bits; for reads the firmware sets bit 7 itself.

### i3c_ddr_config

Tells the firmware which optional HDR-DDR flow-control features the target supports. These are the ENDXFER CCC settings; they must match what the target is configured for. The settings are kept in RAM until the next reset.

**Syntax:** `i3c_ddr_config crc_word_indicator enable_early_write_term write_ack_enable`

| Parameter | Type | Range | Default (boot) | Required | Meaning |
|-----------|------|-------|----------------|----------|---------|
| `crc_word_indicator` | integer | 0 / non-zero (= 1) | 1 | required | Help text: 1 = "No CRC Word follows Early termination request", 0 = "CRC Word follows early Termination request". It is passed to the DDR write as `send_crc_on_early_termination`. **⚠ See note.** |
| `enable_early_write_term` | integer | 0 / non-zero | 0 | required | Target can request early termination of a DDR write (V1.1 feature) |
| `write_ack_enable` | integer | 0 / non-zero | 0 | required | Target ACKs/NACKs DDR write commands (V1.1 feature; V1.0 targets don't) |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0)` | Always; any non-zero value counts as 1. Nothing is sent on the bus. |

**⚠ Note:** the help text says `crc_word_indicator = 1` means "no CRC word follows", but the code passes the value directly as `send_crc_on_early_termination`, so 1 means a CRC **is** sent after an early termination. In addition, `i3c_ddr_read` uses `enable_early_write_term` (not `crc_word_indicator`) to decide whether to read a CRC after a controller early termination. The intended mapping is unclear from the source.

**Example:** `i3c_ddr_config 1 0 0` gives `OK(0)`. Python: `i3c_ddr_config(crc_word_indicator, enable_early_write_term, write_ack_enable)`.

### i3c_ddr_write

HDR-DDR write of 16-bit words to a target with a 7-bit command code. A CRC5 word is appended.

**Syntax:** `i3c_ddr_write addr cmd payload`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | Target address |
| `cmd` | integer | 0x00..0x7F (bit 7 is masked off) | – | required | DDR write command code |
| `payload` | word list | 0..65535 each, ≤ 1024 | – | required | Data words |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0),<n>` | Transfer done. `<n>` (decimal) is the number of words actually written. It is smaller than the payload length if the target NAKed the first word (`n = 0`, only with `write_ack_enable=1`) or requested early termination (only with `enable_early_write_term=1`). |
| `ERR_NAKED_DURING_ARBHDR(2),<n>` | No target acknowledged `0x7E` before ENTHDR0. **⚠ Note:** `<n>` is then the payload length, **not** the number of words written (nothing was written). |
| `ERR_IBI_ARBITRATION(1),<n>` | IBI pending or arbitrated; nothing was sent. `<n>` again is the payload length. |

**⚠ Note:** the source tries to return `ERR_NAKED_DDR(6)` (first word NAKed) and `WARN_EARLY_TERMINATED(7)`. Because of a typo (`retcode == ...` instead of `retcode = ...`) those codes are never set, so the result is `OK(0)` with a reduced count. Compare `<n>` with the number of words you sent.

**Example**
```
> i3c_ddr_write 0x30 0x00 0x1234,0x5678
OK(0),2
```

### i3c_ddr_read

HDR-DDR read of up to `wordcount` 16-bit words with a 7-bit command code. The firmware sets bit 7 of `cmd` for the read. The read ends when the target sends its CRC word or `wordcount` words were read; in the latter case the controller terminates early.

**Syntax:** `i3c_ddr_read addr cmd wordcount`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | Target address |
| `cmd` | integer | 0x00..0x7F | – | required | DDR read command code |
| `wordcount` | integer | 1..1024 (not checked above 1024) | – | required | Maximum number of 16-bit words to read (the help text says "bytes", but they are words) |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0),0x1234,0x5678,...` | Words read (4 hex digits each). Fewer than `wordcount` if the target ended with a CRC word. |
| `ERR_NAKED_DDR(6)` | Target NAKed the read command. No data printed. |
| `ERR_DDR_READ_PARITY_WRONG(9)` | Parity error in a received word. No data printed. If it happens on the **first** word, a debug line `dat: <d> pioretval: <d> calculated_parity: <d>` is printed **before** the status line. |
| `ERR_DDR_INVALID_PREAMBLE(8)` | Target sent an invalid preamble (neither data nor CRC). No data printed. |
| `ERR_INVALID_PARAMETER(4)` | `wordcount` was 0. **⚠ See note.** |
| `ERR_NAKED_DURING_ARBHDR(2)` / `ERR_IBI_ARBITRATION(1)` | See the common errors. |

**⚠ Note:**
- `wordcount 0` returns before interrupts are re-enabled (`save_and_disable_interrupts()` without `restore_interrupts()`). USB communication may stop working afterwards. **Don't send `wordcount 0`.**
- The CRC check sets `ERR_DDR_READ_CRC_WRONG(10)` with `==` instead of `=`, so a CRC mismatch is currently **not** reported.
- A `wordcount` above 1024 overflows the receive buffer.

**Example**
```
> i3c_ddr_read 0x30 0x00 2
OK(0),0x1234,0x5678
```

### i3c_ddr_writeread

HDR-DDR write (finished with an HDR Restart instead of HDR Exit), followed directly by an HDR-DDR read from the same target.

**Syntax:** `i3c_ddr_writeread addr wrcmd rdcmd payload wordcount`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | Target address |
| `wrcmd` | integer | 0x00..0x7F | – | required | DDR write command code |
| `rdcmd` | integer | 0x00..0x7F | – | required | DDR read command code |
| `payload` | word list | 0..65535 each | – | required | Words to write |
| `wordcount` | integer | 1..1024 | – | required | Maximum words to read (help text says "bytes") |

**Responses**

| Response | Meaning |
|----------|---------|
| `OK(0),<nw>,<w0>,<w1>,...` | `<nw>` (decimal) = number of words written; then words in `0x%04x` format. **⚠ See note on which words are printed.** |
| `<ERROR>(<code>),<nw>` | Write or read failed. `<ERROR>` is any of the `i3c_ddr_write` / `i3c_ddr_read` errors above; no data words are printed. |

**⚠ Note:** the firmware reads into the same buffer it wrote from, and then prints **`<nw>` words** (the write count) instead of the read count. So:
- if the target returns as many words as were written, the printed words are the read data;
- if it returns fewer, the remaining printed words are leftover **write** data;
- if it returns more, the extra read words are not printed.

Treat this output with care; it looks like a bug in `i3c_ddr_writeread` in `src/main.c`.

**Example**
```
> i3c_ddr_writeread 0x30 0x00 0x00 0x1234,0x5678 2
OK(0),2,0x1234,0x5678
```

---

## I2C

The I2C commands use the RP2040 hardware I2C on the **same SDA/SCL pins** as I3C. The pins are switched to I2C for the duration of the command and back to I3C afterwards.

### i2c_clk

**Syntax:** `i2c_clk freq_khz`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `freq_khz` | integer | 1..2000 | 100 | required | I2C SCL frequency in kHz. The actual frequency can be lower depending on bus capacitance (clock stretching / rise time). |

**Responses:** `OK(0)` when set; `ERR_INVALID_PARAMETER(4)` when outside 1..2000.

**Example:** `i2c_clk 400` gives `OK(0)`. **⚠ Note:** the Python method `i2c_clk()` sends `i2c_clock`, which doesn't exist.

### i2c_timeout

Timeout for a complete I2C read or write transfer.

**Syntax:** `i2c_timeout timeout_ms`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `timeout_ms` | integer | 0..10000 | 100 | required | Timeout in ms |

**Responses:** `OK(0)` when set; `ERR_INVALID_PARAMETER(4)` when > 10000.

**⚠ Note:**
- A negative value is not rejected (only `> 10000` is checked); it becomes a very large unsigned timeout.
- `0` is accepted; its effect depends on the pico-sdk timeout functions.

### i2c_scan

Tries a 1-byte read from every address 0x08..0x77 (addresses with `addr & 0x78` equal to 0x00 or 0x78 are skipped).

**Syntax:** `i2c_scan` (no parameters)

| Response | Meaning |
|----------|---------|
| `OK(0),0x18,0x50` | Addresses that acknowledged the read. |
| `OK(0),` | Nothing found (trailing comma). |

The status is always `OK(0)`. **Note:** a scan with read transfers can affect devices with read side effects.

### i2c_write

**Syntax:** `i2c_write addr [payload]`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | 7-bit I2C address |
| `payload` | byte list | 0..255 each | none | optional | Bytes to write |

| Response | Meaning |
|----------|---------|
| `OK(0)` | Written, STOP sent. |
| `ERR_I2C_FAILED(11)` | Address or data NAK, or timeout. |

**⚠ Note:** with no payload, a zero-length write is passed to the pico-sdk. Whether that produces an address-only transfer isn't defined in this firmware's source.

**Example:** `i2c_write 0x18 0x04,0x00` gives `OK(0)`.

### i2c_read

**Syntax:** `i2c_read addr len`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | 7-bit I2C address |
| `len` | integer | help: 0..255; not checked, buffer 1024 | – | required | Bytes to read |

| Response | Meaning |
|----------|---------|
| `OK(0),0x..,...` | Exactly `len` bytes (I2C reads have no early end). |
| `ERR_I2C_FAILED(11)` | Address NAK or timeout. No data. |

**Example:** `i2c_read 0x18 2` gives `OK(0),0x00,0x00`.

### i2c_writeread

Write followed by a **Repeated START** (no STOP in between) and a read.

**Syntax:** `i2c_writeread addr payload len`

| Parameter | Type | Range | Default | Required | Meaning |
|-----------|------|-------|---------|----------|---------|
| `addr` | integer | 0x00..0x7F | – | required | 7-bit I2C address |
| `payload` | byte list | 0..255 each | – | required | Bytes written first (e.g. register index) |
| `len` | integer | not checked, buffer 1024 | – | required | Bytes to read |

| Response | Meaning |
|----------|---------|
| `OK(0),0x..,...` | Read data. |
| `ERR_I2C_FAILED(11)` | NAK or timeout in the write or the read phase. No data. |

**Example:** `i2c_writeread 0x18 0x00 1` gives `OK(0),0x21`.

---

## Known quirks and unclear points found in the source

These are observations from reading the code, **not** changes. They are listed so users know what to expect from the responses.

1. **HDR-DDR status typos:** in `src/i3c_hl.c`, `retcode == i3c_hl_status_nak_ddr`, `retcode == i3c_hl_status_ddr_early_termination` (DDR write) and `retcode == i3c_hl_status_ddr_crc_wrong` (DDR read, two places) are comparisons, not assignments. As a result `ERR_NAKED_DDR(6)` (on write), `WARN_EARLY_TERMINATED(7)` and `ERR_DDR_READ_CRC_WRONG(10)` are never returned.
2. **`i3c_ddr_read` with `wordcount 0`** returns `ERR_INVALID_PARAMETER(4)` but leaves interrupts disabled.
3. **`i3c_ddr_writeread` output** prints the write count of words from a buffer that the read overwrote (see the command).
4. **`i3c_ddr_write` count on error:** after `ERR_IBI_ARBITRATION(1)` / `ERR_NAKED_DURING_ARBHDR(2)`, the count printed is the payload length, not the words written.
5. **`i3c_ddr_config` `crc_word_indicator` meaning** contradicts its help text, and `i3c_ddr_read` uses `enable_early_write_term` for its CRC-after-early-termination decision.
6. **No length checks:** `len` / `wordcount` arguments of the read commands aren't range-checked against the 1024-entry buffers. The help says 0..255 for byte reads.
7. **Payload errors don't abort the command:** the transfer still runs with a partial or zero-padded payload, and two lines are returned.
8. **Debug output in responses:** `IBI CHECK` (from `i3c_scan` when an IBI is pending) and the DDR parity debug line can appear in the response stream.
9. **`i3c_rstdaa` always answers `OK(0)`**, even when the transfer didn't happen.
10. **`i3c_scan` doesn't skip `0x7E`.**
11. **`gpio_write` / `gpio_read`** accept 0..31 while the help says 0..29. `gpio_read` with an invalid pin still prints a value.
12. **`info`** dumps the PIO registers with `\n` line endings and lists only "I3C SDR, I3C OD" as supported protocols.
13. **Python module mismatches** (`python/i3cblaster.py`):
    - `i3c_clk()` sends `i3c_clock` and `i2c_clk()` sends `i2c_clock`; both commands don't exist.
    - `i3c_sdr_ccc_direct_write()` sends `i3c_sdr_ccc_bc_write`.
    - Responses are decoded with the Windows-only `ansi` codec, so the module fails on Linux/macOS as is.
    - The module reads only **one** line per command, so multi-line responses (payload errors, debug lines) leave extra text in the buffer. It is flushed before the next command.
14. **`i3c_poll` buffer:** up to 17 bytes can be stored in a 16-byte buffer for long IBI payloads.
