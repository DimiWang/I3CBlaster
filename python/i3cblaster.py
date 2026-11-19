import serial 
import serial.tools.list_ports 
import time
import os
import shutil
import subprocess

class i3cblaster:
    
    OKTEXT = 'OK(0)'
    USB_VID = 0x2E8A # USB vendor ID of the i3cblaster devices
    USB_PID = 0x000A # USB product ID of the i3cblaster devices
    
    _ser = None
    _serialnumber = None
    _port = None # optional fixed serial port (e.g. 'COM5' or '/dev/ttyACM0'), see init()

    # text encoding used on the serial line (the firmware only sends ASCII). 'latin-1' works on all OSes.
    ENCODING = 'latin-1'
    
    def _findcomport(self, serialnumber=None): 
        if self._port is not None:
            return self._port
        foundport = None 
        matchstr = 'USB VID:PID=%04x:%04x' % (self.USB_VID, self.USB_PID) 
        ports = serial.tools.list_ports.comports() 
        for port in ports: 
            if port.usb_info().find(matchstr.upper()) >= 0: 
                if foundport is None: 
                    if serialnumber is None:
                        foundport = port.device # full device path, e.g. COM5 or /dev/ttyACM0
                    elif serialnumber == port.serial_number:
                        foundport = port.device
        return foundport 
        
    # optionally select a device by USB serial number and/or a fixed serial port name
    def init(self, serialnumber=None, port=None): 
        self._serialnumber = serialnumber
        self._port = port
    
    # Magic function to close all relevant serial port instances running open in current python instance right now
    def close_serialport(self, port): 
        import gc 
        a = gc.get_objects() 
        for o in a: 
            try: 
                if isinstance(o, serial.serialwin32.Serial):   # for windows 
                    if o.portstr == port: 
                        o.close() 
                elif isinstance(o, serial.serialposix.Serial): # for unix based systems 
                    if o.portstr == port: 
                        o.close() 
            except: # exceptions are expected cause we support 2 OS here and the classes are not known for both 
                pass; 
    
    # connect if not connected to the RP2040 serial port 
    def _connect(self, forcereconnect = False): 
        if forcereconnect: 
            if self._ser is not None: 
                self._ser.close() 
                del self._ser 
                self._ser = None 
        if self._ser is None: 
            comport = self._findcomport(self._serialnumber) 
            if comport is not None: 
                self.close_serialport(comport) # close port if it is open within this python instance... just to be sure 
                # now try to connect with a timeout
                openedit = False 
                timedout = False 
                starttime = time.time() 
                while not openedit and not timedout: 
                    try: 
                        self._ser = serial.Serial(comport, 115200, timeout=1) 
                        openedit = True; 
                    except: 
                        time.sleep(0.05); 
                    timedout = (time.time()-starttime) >= 2; 
                    
                    if timedout:
                        del self._ser
                        self._ser = None
                    else:
                        # suppress startup message
                        st = b''
                        done = False
                        starttime = time.time()
                        while not done:
                            st += self._ser.read_all()
                            if len(st) > 0:
                                time.sleep(0.5)
                                st += self._ser.read_all()
                                done = True
                            if time.time()-starttime > 2:
                                done = True
                
        return self._ser is not None

    def _exec(self, cmdstr): 
        respstr = ''
        if self._connect():
            self._ser.read_all() # flush
            self._ser.write(('@'+cmdstr+'\r').encode(self.ENCODING))
            respstr = self._ser.readline()
        return respstr
    
    def _parse_response(self, resp):
        errorcode = ''
        returnvalues = []
        resp = resp.decode(self.ENCODING).strip()
        errorend = resp.find(')')
        if errorend >= 0:            
            errorcode = resp[0:errorend+1]
            values = resp[errorend+1:]
            if len(values) > 0:
                if values[0] == ',':
                    values = values[1:]
                values = values.split(',')              
                for v in values:
                    try:
                        returnvalues.append(int(v, 0))                
                    except:
                        pass;
        else:
            errorcode = resp
        return (errorcode, returnvalues)
    
    # set a gpio pin.
    # gpionum is a integer number between 0 to 15 and selects the GPIO pin to set
    # set is a character. Provide either
    #   1 or True to set the pin to HIGH
    #   0 or False to set the pin to LOW
    #   'Z' or None to set the pin to tristate = input
    def gpio_write(self, gpionum, state):        
        if (state == 1) or (state == True) or (state == '1'):
            state = '1'
        elif (state == 0) or (state == False)  or (state == '0'):
            state = '0'
        else:
            state = 'Z'
        resp = self._parse_response(self._exec('gpio_write %d %c' % (gpionum, state)))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
    
    # read the state of the full GPIO port or single GPIO pins.
    # if gpionum is given as a parameter (valid range 0..15) the state of that 
    # single pin is returned. Otherwise the state of the full port is returned as decimal number
    def gpio_read(self, gpionum=None):
        if gpionum is None:
            resp = self._parse_response(self._exec('gpio_read'))
        else:
            resp = self._parse_response(self._exec('gpio_read %d' % gpionum))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]

    # check by scanning which I3C addresses are responding on the i3c bus
    # returns a python array with integer values which are the addresses which naked in 7-bit format.
    def i3c_scan(self):
        resp = self._parse_response(self._exec('i3c_scan'))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]

    # execute a broadcast RST DAA
    def i3c_rstdaa(self):
        resp = self._parse_response(self._exec('i3c_rstdaa'))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
    
    # execute an ENTDAA CCC. returns the information of the device which is read during entdaa cycle
    # In case no devices are available for ENTDAA execution (0x7E NAKed) the value None is returned
    def i3c_entdaa(self, targetaddr):
        resp = self._parse_response(self._exec('i3c_entdaa 0x%x' % targetaddr))
        if resp[0] != self.OKTEXT:
            if resp[0] == 'ERR_NAKED(3)':
                return None
            else:
                raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]
    
    # Create a target reset pattern condition on the I3C bus
    def i3c_targetreset(self):
        resp = self._parse_response(self._exec('i3c_targetreset'))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])

    # close the serial port after a command that makes the device drop off USB
    def _drop_connection(self):
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    # Software reset of the I3CBlaster device (RP2040 reboot).
    # The device acknowledges with OK(0) and reboots; its USB serial port disconnects
    # and re-enumerates, so the serial port is closed here and the next command reconnects.
    # bootloader=True is the same as calling bootloader().
    # wait_s: for a plain reset, wait up to this many seconds for the device to come back
    # (0 = do not wait). Returns True if the device is reachable again (or no wait was requested).
    def reset(self, bootloader=False, wait_s=5):
        if bootloader:
            self.bootloader()
            return True
        resp = self._parse_response(self._exec('reset'))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        self._drop_connection()
        if not wait_s:
            return True
        time.sleep(0.5) # give the device time to drop off USB before looking for it again
        starttime = time.time()
        while (time.time() - starttime) < wait_s:
            if self._findcomport(self._serialnumber) is not None and self._connect():
                return True
            time.sleep(0.2)
        return False

    # Jump to the RP2040 USB bootloader (BOOTSEL mode) for a firmware update.
    # no_drive=False: the device shows up as the RPI-RP2 USB drive (copy a .uf2 file onto it)
    #                 and also offers the PICOBOOT interface used by picotool.
    # no_drive=True:  only the PICOBOOT interface is offered (no USB drive pops up);
    #                 load the firmware with picotool, e.g. 'picotool load -x file.uf2' (see update_firmware()).
    # The serial port is closed here; this function does not wait for the device.
    def bootloader(self, no_drive=False):
        if not self._connect():
            raise Exception('I3C Blaster exception: no I3CBlaster serial port found')
        resp = self._parse_response(self._exec('bootloader 1' if no_drive else 'bootloader'))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        self._drop_connection()

    # alias for bootloader()
    def enter_bootloader(self, no_drive=False):
        self.bootloader(no_drive)

    # Update the I3CBlaster firmware with picotool, without the USB drive appearing.
    #   uf2_path : path of the firmware file, e.g. 'bin/i3cblaster.uf2'
    #   picotool : picotool executable name or full path
    #   timeout  : seconds to wait for the bootloader and for the device to come back
    #   verify   : pass -v to picotool load (read back and compare)
    # Steps: 'bootloader 1' -> wait for the PICOBOOT device -> 'picotool load [-v] -x <uf2>'
    #        -> wait for the I3CBlaster serial port to come back.
    # If no I3CBlaster serial port is found but a board is already in BOOTSEL mode, it is loaded directly.
    # Returns the picotool output. Raises an Exception with a clear message on failure.
    def update_firmware(self, uf2_path, picotool='picotool', timeout=20, verify=True):
        if not os.path.isfile(uf2_path):
            raise Exception('firmware file not found: %s' % uf2_path)
        picotool_exe = shutil.which(picotool) or (picotool if os.path.isfile(picotool) else None)
        if picotool_exe is None:
            raise Exception("picotool not found ('%s'). Install it (see docs/FIRMWARE_UPDATE.md) "
                            "or pass its full path with picotool=..." % picotool)

        def picoboot_present():
            r = subprocess.run([picotool_exe, 'info'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            return r.returncode == 0, r.stdout

        # 1) send the I3CBlaster into the bootloader (PICOBOOT only)
        if self._connect():
            self.bootloader(no_drive=True)
        else:
            present, _ = picoboot_present()
            if not present:
                raise Exception('no I3CBlaster serial port and no RP2040 in BOOTSEL mode found')

        # 2) wait for the PICOBOOT interface
        starttime = time.time()
        last_out = ''
        while True:
            present, last_out = picoboot_present()
            if present:
                break
            if time.time() - starttime > timeout:
                raise Exception('RP2040 bootloader (PICOBOOT, USB 2e8a:0003) not found within %ds. picotool says: %s\n'
                                'Linux: install the udev rule (or run with sudo). Windows: install the WinUSB driver '
                                'for "RP2 Boot" with Zadig. See docs/FIRMWARE_UPDATE.md' % (timeout, last_out.strip()))
            time.sleep(0.5)

        # 3) load the firmware and start it
        cmd = [picotool_exe, 'load'] + (['-v'] if verify else []) + ['-x', uf2_path]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if r.returncode != 0:
            raise Exception('picotool load failed (exit code %d):\n%s' % (r.returncode, r.stdout))

        # 4) wait for the I3CBlaster serial port to come back
        self._drop_connection()
        starttime = time.time()
        while time.time() - starttime < timeout:
            if self._findcomport(self._serialnumber) is not None and self._connect():
                return r.stdout
            time.sleep(0.5)
        raise Exception('firmware loaded, but the I3CBlaster serial port did not come back within %ds.\n%s'
                        % (timeout, r.stdout))

    # Set the I3C clock frequency in units of kHz.
    # provide e.g. 12500 for 12.5 MHz
    def i3c_clk(self, clockrate_khz):
        resp = self._parse_response(self._exec('i3c_clock %d' % clockrate_khz))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])

    # execute a private write transfer to a I3C target.
    # writedata is an array, targetaddr is the 7-bit targetaddress to write to
    def i3c_sdr_write(self, targetaddr, writedata):
        cmd = 'i3c_sdr_write %d ' % targetaddr
        for d in writedata:
            cmd += hex(d)+','
        if len(writedata) > 0:
            cmd = cmd[0:-1]
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])

    # execute a private read transfer from a I3C target.
    # readbyecount is the count of bytes requested to read, 
    # targetaddr is the 7-bit targetaddress to write to
    # The function returns the read data bytes.
    # Note: This can be less as the requested bytecount in case the I3C target
    #       terminated the read earlier.
    def i3c_sdr_read(self, targetaddr, readbytecount):
        cmd = 'i3c_sdr_read %d %d' % (targetaddr, readbytecount)
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]
    
    # execute a private write transfer from a I3C target followed by a restart and read transfer.
    # targetaddr is the 7-bit targetaddress to write to.
    # write data is an array with the bytes to write during write phase.
    # readbyecount is the count of bytes requested to read.
    # The function returns the read data bytes.
    # Note: This can be less as the requested bytecount in case the I3C target
    #       terminated the read earlier.
    def i3c_sdr_writeread(self, targetaddr, writedata, readbytecount):
        cmd = 'i3c_sdr_writeread %d ' % targetaddr
        for d in writedata:
            cmd += hex(d)+','
        if len(writedata) > 0:
            cmd = cmd[0:-1]
        cmd += ' %d' % readbytecount
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]
    
    # execute a broadcast ccc transfer to the I3C bus.
    # writedata is an array with payload data to write
    def i3c_sdr_ccc_bc_write(self, writedata):
        cmd = 'i3c_sdr_ccc_bc_write '
        for d in writedata:
            cmd += hex(d)+','
        if len(writedata) > 0:
            cmd = cmd[0:-1]
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        
    # execute a direct ccc transfer to an I3C target
    # targetaddr is the 7-bit target address    
    # bc_phase_writedata is an array with payload data to write during the broadcast phase of the transfer
    # direct_phase_writedata is an array with payload data to write during the direct addressed phase of the transfer
    def i3c_sdr_ccc_direct_write(self, targetaddr, bc_phase_writedata, direct_phase_writedata):
        cmd = 'i3c_sdr_ccc_bc_write %d ' % targetaddr
        for d in bc_phase_writedata:
            cmd += hex(d)+','
        if len(bc_phase_writedata) > 0:
            cmd = cmd[0:-1]
        cmd += ' '
        for d in direct_phase_writedata:
            cmd += hex(d)+','
        if len(direct_phase_writedata) > 0:
            cmd = cmd[0:-1]
        
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        
    # execute a direct ccc transfer to an I3C target
    # targetaddr is the 7-bit target address    
    # writedata is an array with payload data to write during the broadcast phase of the transfer
    # direct_phase_writedata is an array with payload data to write during the direct addressed phase of the transfer
    # The function returns the read data bytes.
    # Note: This can be less as the requested bytecount in case the I3C target
    #       terminated the read earlier.
    def i3c_sdr_ccc_direct_read(self, targetaddr, writedata, readbytecount):
        cmd = 'i3c_sdr_ccc_direct_read %d ' % targetaddr
        for d in writedata:
            cmd += hex(d)+','
        if len(writedata) > 0:
            cmd = cmd[0:-1]
        cmd += ' %d' % readbytecount
        
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]
    
    # check if an I3C IBI or HJ request occured.
    # All transfer functions will also return an error in case an IBI or HJ was detected.
    # directly after such an error occured i3c_poll has to be called to read the IBI data or HJ code.
    # The function returns None in case no IBI was detected
    # In case an IBI/HJ was dtected, it returns the target address and read IBI data payload as an array
    def i3c_poll(self):
        resp = self._parse_response(self._exec('i3c_poll'))
        if resp[0] != self.OKTEXT:
            if 'WARN_NO_IBI(5)' == resp[0]:
                return None
            else:
                raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]        
    
    # Configure drive strength of controllers SDA/SCL pads.
    # Valid values are 2, 4, 8, 12 for either 2mA, 4mA, 8mA or 12mA drive strength
    # Note that it might be necessary to set the drivestrength of the I3C target too by doing target specific writes
    def i3c_drivestrength(self, drivestrength_mA):
        cmd = 'i3c_drivestrength %d' % drivestrength_mA
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
    
    # Configure I3C DDR specific target capabilities. Look into ENDXFER CCC for complete explanation.
    # For the values of the 3 parameters use either True or False
    def i3c_ddr_config(self, crc_word_indicator, enable_early_write_term, write_ack_enable):
        cmd = 'i3c_ddr_config %d %d %d' % (int(crc_word_indicator), int(enable_early_write_term), int(write_ack_enable))
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
    

    # execute a write transfer to a I3C target in HDR-DDR mode
    # writedata is an array, targetaddr is the 7-bit targetaddress to write to
    # Note that writedata for HDR-DDR mode are 16-bit values!
    # writecommand is the 7-bit command value which is used for the command word in the HDR-DDR write
    def i3c_ddr_write(self, targetaddr, writecommand, writedata):
        cmd = 'i3c_ddr_write %d %d ' % (targetaddr, writecommand)
        for d in writedata:
            cmd += hex(d)+','
        if len(writedata) > 0:
            cmd = cmd[0:-1]
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])

    # execute a read transfer from a I3C target in HDR-DDR mode.
    # readbyecount is the count of bytes requested to read, 
    # targetaddr is the 7-bit targetaddress to write to
    # The function returns the read data bytes.
    # Note: This can be less as the requested bytecount in case the I3C target
    #       terminated the read earlier.
    # readcommand is the 7-bit command value which is used for the command word in the HDR-DDR read
    def i3c_ddr_read(self, targetaddr, readcommand, readbytecount):
        cmd = 'i3c_ddr_read %d %d %d' % (targetaddr, readcommand, readbytecount)
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]

    # execute a write transfer from a I3C target followed by a restart and read transfer in HDR-DDR mode.
    # targetaddr is the 7-bit targetaddress to write to.
    # write data is an array with the bytes to write during write phase.
    # readbyecount is the count of bytes requested to read.
    # The function returns the read data bytes.
    # Note: This can be less as the requested bytecount in case the I3C target
    #       terminated the read earlier.
    # The result is an array with 2 elements. 
    #   The first item contains the amount of words written successfully
    #   The second item is an array containing the read data values
    def i3c_ddr_writeread(self, targetaddr, writecommand, readcommand, writedata, readbytecount):
        cmd = 'i3c_ddr_writeread %d %d %d ' % (targetaddr, writecommand, readcommand)
        for d in writedata:
            cmd += hex(d)+','
        if len(writedata) > 0:
            cmd = cmd[0:-1]
        cmd += ' %d' % readbytecount
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        if len(resp[1]) > 0:
            count_written = resp[1][0]
            read_data = resp[1][1:]
            return [count_written, read_data]
        else:
            return [0, []]
    
    # check by scanning which I2C addresses are responding on the bus
    # returns a python array with integer values which are the addresses which naked in 7-bit format.
    def i2c_scan(self):
        resp = self._parse_response(self._exec('i2c_scan'))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]


    # Set the I2C clock frequency in units of kHz.
    # provide e.g. 1000 for 1 MHz. Note that the actual frequency will be lower as function of bus capacitance.
    def i2c_clk(self, clockrate_khz):
        resp = self._parse_response(self._exec('i2c_clock %d' % clockrate_khz))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])

    # Set the I2C timeout in units of milliseconds [ms].
    # provide e.g. 100 for a 100ms timeout. The timeout applies to the full i2c write or read transfer time.
    def i2c_timeout(self, timeout_ms):
        resp = self._parse_response(self._exec('i2c_timeout %d' % timeout_ms))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])

    # execute an i2c write transfer to a I2C target.
    # writedata is an array, targetaddr is the 7-bit targetaddress to write to
    def i2c_write(self, targetaddr, writedata):
        cmd = 'i2c_write %d ' % targetaddr
        for d in writedata:
            cmd += hex(d)+','
        if len(writedata) > 0:
            cmd = cmd[0:-1]
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])

    # execute an i2cread transfer from a I2C target.
    # readbyecount is the count of bytes requested to read, 
    # targetaddr is the 7-bit targetaddress to write to
    # The function returns the read data bytes.
    def i2c_read(self, targetaddr, readbytecount):
        cmd = 'i2c_read %d %d' % (targetaddr, readbytecount)
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]

    # execute an i2c write transfer from a I3C target followed by a restart and read transfer.
    # targetaddr is the 7-bit targetaddress to write to.
    # write data is an array with the bytes to write during write phase.
    # readbyecount is the count of bytes requested to read.
    # The function returns the read data bytes.
    def i2c_writeread(self, targetaddr, writedata, readbytecount):
        cmd = 'i2c_writeread %d ' % targetaddr
        for d in writedata:
            cmd += hex(d)+','
        if len(writedata) > 0:
            cmd = cmd[0:-1]
        cmd += ' %d' % readbytecount
        resp = self._parse_response(self._exec(cmd))
        if resp[0] != self.OKTEXT:
            raise Exception('I3C Blaster exception: ' + resp[0])
        return resp[1]


def listdevices():
    foundserials = []
    matchstr = 'USB VID:PID=%04x:%04x' % (i3cblaster.USB_VID, i3cblaster.USB_PID) 
    ports = serial.tools.list_ports.comports() 
    for port in ports: 
        if port.usb_info().find(matchstr.upper()) >= 0: 
            foundserials.append(port.serial_number)
    return foundserials
    
