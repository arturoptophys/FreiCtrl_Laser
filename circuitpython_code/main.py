import time

import supervisor
import board
import busio
import adafruit_mcp4728
import digitalio
import json
import gc
from micropython import const
import usb_cdc
import microcontroller

microcontroller.cpu.frequency = 200000000

from timing_utils import ticks_diff, ticks_less
from laser_dac import LaserController, LaserTrigger, SerialReaderComm, make_mask, BOARD_TRIGGER, start_LEDpulsing

# I2C-GP27,GP26
# UART - [GP0.GP1]
mask_ttlpins = [board.GP6, board.GP7, board.GP8, board.GP9]
laser_ttlpins = [board.GP21, board.GP20, board.GP19, board.GP18]
# trigger_inpins = [board]

# Initialize I2C bus.
i2c = busio.I2C(board.GP27, board.GP26, frequency=100000 * 4)  # modify the frequency of the i2c
uart = busio.UART(board.GP0, board.GP1, baudrate=115200, receiver_buffer_size=1024)  # communication with main circuit

stand_alone_switch = digitalio.DigitalInOut(board.GP17)
stand_alone_switch.direction = digitalio.Direction.INPUT
stand_alone_switch.pull = digitalio.Pull.UP
if stand_alone_switch.value:  # switch between using usb or uart as serial communication
    data_serial = uart
    REFRESH = 1000  # ms
    PULSE_FREQ = 3  # Hz
    STANDALONE = False
else:
    data_serial = usb_cdc.data
    REFRESH = 500  # ms
    PULSE_FREQ = 6  # Hz
    STANDALONE = True

# dac_single = adafruit_mcp4725.MCP4725(i2c)
dac_multi = adafruit_mcp4728.MCP4728(i2c)

enable_pin = digitalio.DigitalInOut(board.GP22)  # connect this pin to TrialComm
enable_pin.direction = digitalio.Direction.INPUT

PRIMING_PIN = board.GP28  # TODO connect this pin to priming_pin

laser1 = LaserController(board.GP21, dac_i2c=dac_multi.channel_a, verbose=False, name='laser1')
laser1_mask = LaserController(board.GP6, verbose=False, name='laser1_mask')

laser2 = LaserController(board.GP20, dac_i2c=dac_multi.channel_b, verbose=False, name='laser2')
laser2_mask = LaserController(board.GP7, verbose=False, name='laser2_mask')

laser3 = LaserController(board.GP19, dac_i2c=dac_multi.channel_c, verbose=False, name='laser3')
laser3_mask = LaserController(board.GP8, verbose=False, name='laser3_mask')

laser4 = LaserController(board.GP18, dac_i2c=dac_multi.channel_d, verbose=False, name='laser4')
laser4_mask = LaserController(board.GP9, verbose=False, name='laser4_mask')

# laser3 = LaserController(board.GP12, dac_i2c=dac_multi.channel_b, verbose=False, name='laser3')
all_lasers = [laser1, laser1_mask, laser2, laser2_mask, laser3, laser3_mask, laser4, laser4_mask]

trigger = LaserTrigger([laser1, laser1_mask, laser2, laser2_mask], trigger_pin=BOARD_TRIGGER, verbose=False,
                       priming_pin=PRIMING_PIN, name='trigger1')
# todo think if it makes sense to extend this to have a second trigger ?
# potential application 2 diff lasers in individual arms ?

serial_comm = SerialReaderComm(data_serial)
serial_comm.serial.reset_input_buffer()


@micropython.native
def set_setting_laser(params):
    laser1.set_settings(params)
    make_mask(laser1, laser1_mask)
    laser2.set_settings(params)
    make_mask(laser2, laser2_mask)
    laser3.set_settings(params)
    make_mask(laser3, laser3_mask)
    laser4.set_settings(params)
    make_mask(laser4, laser4_mask)


def ask_lasers_active() -> bool:
    return (laser1.pulse_active or laser1_mask.pulse_active or laser2.pulse_active or laser2_mask.pulse_active or
            laser3.pulse_active or laser3_mask.pulse_active or laser4.pulse_active or laser4_mask.pulse_active)


def run_laser_calib(laser: LaserController, steps: list, dur: int):
    """
    :param laser:  LaserController to be calibrated
    :param steps: list of attenuations steps to be tested
    :param dur: duration of each step in seconds
    """
    laser.ttl_pin.value = True
    for step in steps:
        if step > 1:
            step = 1
        elif step < 0:
            step = 0
        laser.dac_i2c.normalized_value = step
        time.sleep(dur)
    laser.ttl_pin.value = False
    laser.dac_i2c.normalized_value = 0
    print(f"Done calibrating {laser.name}")


t0 = 0  # last time checked the serial
start_LEDpulsing(PULSE_FREQ)  # pulse the board led via PIO to make sure the board is running normally

while True:
    try:
        trigger.update_lasers()  # to only update current laser
        trigger.update()
        now = supervisor.ticks_ms()
        if ticks_less(REFRESH, ticks_diff(now, t0)):
            t0 = now
            if not enable_pin.value or STANDALONE:  # switch to not try read serial during the trial (Signal is high if trial is on)
                if not ask_lasers_active():  # only if lasers are not active
                    gc.collect()  # force garbage collection
                    data = serial_comm.read(echo=False)
                    if data is not None:  # is none if serial is empty
                        if data == "TRIGGER":  # signal to manually trigger laser pulse
                            trigger.start_all_lasers()
                            continue
                        try:
                            data = json.loads(data)  # expecting a dict via json
                        except ValueError:  # json is broken
                            continue
                        if data is None:  # empty json
                            trigger.update_lasers_list([])  # maybe add turning off of lasers ?
                            continue  # got None as json
                        if data.get('calibrate', False):
                            try:
                                laser = [las for las in all_lasers if las.name == data["laser2calib"]][0]
                            except IndexError:
                                continue
                            values2test = data["calibsteps"]
                            calib_duration = data["calibdur"]
                            print(f"Calibrating {laser.name}")
                            run_laser_calib(laser, values2test, calib_duration)
                        else:
                            set_setting_laser(data)
                            trigger.set_settings(data)
                            if 'laser_list' in data.keys():
                                lasers2add = []
                                for laser in all_lasers:
                                    if laser.name in data['laser_list']:
                                        lasers2add.append(laser)
                                    elif laser.name in [f'{l.name}_mask' for l in lasers2add]:
                                        lasers2add.append(laser)
                                # lasers2add = [laser for laser in all_lasers if laser.name in data['laser_list']]
                                trigger.update_lasers_list(lasers2add)
    except Exception as e:
        with open("/log.txt", "a") as fp:
            fp.write(f'{type(e).__name__}: {e}\n')
            fp.flush()
