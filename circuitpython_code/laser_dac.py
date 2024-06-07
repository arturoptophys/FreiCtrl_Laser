import gc
import board
import supervisor
import math
import digitalio
import random
import ulab
import sys
import json
import array
import rp2pio
import adafruit_pioasm

from timing_utils import ticks_diff, ticks_less, Debouncer

TRIGGER_DEBOUNCE = 5
MAX_FREQUENCY = 200
TRIGGER_PINS = [board.GP15, board.GP13, board.GP12, board.GP11, board.GP10, board.GP14]
TRIGGER_PINS = {"IntTrigger": board.GP15, "ExtTrigger0": board.GP13, "ExtTrigger1": board.GP12,
                "ExtTrigger2": board.GP11, "ExtTrigger3": board.GP10, "IntTrigger2": board.GP14}

BOARD_TRIGGER = board.GP15


class BaseMachine:
    """
    This is a base class which implements methods share between all Machine classes
    """

    def __init__(self, name: str, verbose: bool = False):
        self.name = name
        self.verbose = verbose
        self.is_active = True  # switch for the Machine to be ignored in update loop
        self.trial = None

    def update(self):
        pass

    def execute_str_command(self, command: str, params: (list, float, int, str, None) = None):
        """
        runs the corresponding command send as a string, to be used for serial communication
        """
        try:
            if params is None:
                getattr(self, command)()
            elif isinstance(params, list):
                getattr(self, command)(*params)
            else:
                getattr(self, command)(params)
        except TypeError:
            print(f'Parameter {params} was given for {command}, but doesnt exist, or is required but not given')
        except AttributeError:
            print(f'{self.name} doesnt understand command {command}')


class LaserTrigger(BaseMachine):
    def __init__(self, lasers: list, trigger_pin=None, priming_pin=None,
                 name: str = 'trigger1', verbose: bool = False):
        super().__init__(name, verbose)
        self.trigger_mirror = None
        self.mock = True  # whether only masks should run
        self.lasers = lasers
        self._pulse_ctrl = 1  # ctrl  # laser is on according to settings or while a pin is high
        self._priming_pin = None
        self.is_primed = False  # flag for priming double condition laser is only on if primed and
        self.trigger_flag = False
        self.laser_prob = True  # probability off actually setting of the laser
        self.trigger_debouncer_interval = TRIGGER_DEBOUNCE

        # not to be used.. control in main_board

        # self.trigger_pin = trigger_pin
        # print(trigger_pin is not None)
        self.use_trigger_pin = True  # whether we monitor a pin for Triggering an event
        if self.use_trigger_pin:
            assert trigger_pin is not None, "use trigger pin is set but no pin is provided"
            self.current_trig_pin = trigger_pin
            self.trigger_pin = digitalio.DigitalInOut(trigger_pin)
            self.trigger_pin.direction = digitalio.Direction.INPUT
            self.trigger_pin = Debouncer(self.trigger_pin, interval=self.trigger_debouncer_interval)

        self.use_priming_pin = False  # whether we monitor a pin for priming
        if priming_pin is not None:
            self.use_priming_pin = True
            self.priming_pin = priming_pin

    @property
    def priming_pin(self):
        return self._priming_pin

    @priming_pin.setter
    def priming_pin(self, value):
        self._priming_pin = digitalio.DigitalInOut(value)
        self._priming_pin.direction = digitalio.Direction.INPUT

    @property
    def pulse_ctrl(self):
        if self._pulse_ctrl == 1:
            return "timed"
        elif self._pulse_ctrl == 2:
            return "ctrl"

    @pulse_ctrl.setter
    def pulse_ctrl(self, new_val: str):
        if new_val == "timed":
            self._pulse_ctrl = 1
        elif new_val == 'ctrl':
            self._pulse_ctrl = 2
        else:
            print("Not clear mode for pulse_ctrl")
            self._pulse_ctrl = 0

    def set_settings(self, params: dict):
        try:
            params = params[self.name]
        except KeyError:
            print(f'no parameters provided for {self.name}')
            return
        if params is None:  # empty parameters means not in use
            self.stop_all_lasers()
            return

        params_keys = params.keys()

        if 'trigger_pin' in params_keys:  # change trigger pin
            if self.current_trig_pin != TRIGGER_PINS[params['trigger_pin']]:
                # trigger pin has not changed
                self.trigger_pin.pin.deinit()
                if TRIGGER_PINS[params['trigger_pin']] != BOARD_TRIGGER:  # if using external trigger use a mirror
                    if self.trigger_mirror is None:
                        self.trigger_mirror = digitalio.DigitalInOut(BOARD_TRIGGER)
                        self.trigger_mirror.direction = digitalio.Direction.OUTPUT
                else:
                    if self.trigger_mirror is not None:
                        self.trigger_mirror.deinit()
                    self.trigger_mirror = None
                self.trigger_pin = digitalio.DigitalInOut(TRIGGER_PINS[params['trigger_pin']])
                self.trigger_pin.direction = digitalio.Direction.INPUT
                self.trigger_pin = Debouncer(self.trigger_pin, interval=self.trigger_debouncer_interval)
                self.current_trig_pin = TRIGGER_PINS[params['trigger_pin']]

        if 'use_trigger_pin' in params_keys:
            self.use_trigger_pin = params['use_trigger_pin']

        if 'use_priming_pin' in params_keys:
            self.use_priming_pin = params['use_priming_pin']

        if 'pulse_ctrl' in params_keys:
            self.pulse_ctrl = params['pulse_ctrl']

        if 'is_primed' in params_keys:
            self.is_primed = params['is_primed']

        if 'mock' in params_keys:
            self.mock = params['mock']

        if 'laser_list' in params_keys:
            self.update_lasers_list(params_keys['laser_list'])

    def update_lasers_list(self, new_lasers: list):
        '''
        modify the lasers under control of this trigger
        :param new_lasers:
        :return:
        '''
        if len(new_lasers) == 0:
            self.stop_all_lasers()
        self.lasers = new_lasers

    @micropython.native
    def start_all_lasers(self):
        """
        starts all lasers
        :return:
        """
        for laser in self.lasers:
            if self.mock:
                if laser.is_mask:
                    laser.start_pulsing()
            else:
                laser.start_pulsing()

    @micropython.native
    def stop_all_lasers(self):
        """
        stops all laser immediatly
        :return:
        """
        for laser in self.lasers:
            laser.stop_pulsing_immediatly()

    @micropython.native
    def stop_all_lasers_graceful(self):
        """
        stops all laser at the end of cycle or attenuated time
        :return: None
        """
        for laser in self.lasers:
            laser.stop_pulsing_graceful()

    @micropython.native
    def update(self):
        for laser in self.lasers:  # stop execution of one of the lasers is still active
            if laser.pulse_active:
                return

        # check for triggers
        if self.use_priming_pin:
            self.is_primed = self.priming_pin.value  # check status of our priming Pin
            if not self.is_primed:
                if self.trigger_mirror is not None:
                    self.trigger_mirror.value = False  # turn off mirror
        # if self._pulse_ctrl ==1:

        if self.use_trigger_pin and not self.trigger_flag:
            self.trigger_pin.update()  # update trigger debouncer
            if self.trigger_pin.rose and self.is_primed:
                self.trigger_flag = True
                if self.trigger_mirror is not None:  # if ext_trigger mirror the signal on main trigger line
                    self.trigger_mirror.value = True  # need
                if self.verbose:
                    print('got triggered')
        if self.trigger_flag:
            self.start_all_lasers()
            self.trigger_flag = False

    @micropython.native
    def update_lasers(self):
        for laser in self.lasers:
            laser.update()


class LaserController(BaseMachine):
    def __init__(self, ttl_pin, dac_i2c=None, name: str = 'laser_ctrl_1', verbose: bool = False):
        super().__init__(name, verbose)

        self.pulse_ends = None
        self.pulse_starts = None
        self.last_t = None
        self.is_mask = False
        self.pulse_t0 = None
        self.attenuation_t0 = None
        self.delay_t0 = int(-2 ** 31)
        self.ttl_pin = digitalio.DigitalInOut(ttl_pin)  # connect this pin to Arduino
        self.ttl_pin.direction = digitalio.Direction.OUTPUT
        self.ttl_pin.value = False
        self.dac_i2c = dac_i2c
        if self.dac_i2c is not None:
            self.dac_i2c.raw_value = 0
        # ar = ulab.numpy.arange(0, 2 * math.pi, math.pi / 500)
        # self.sine_lookup = [(math.sin(val) + 1) / 2 for val in ar]

        self._pulse_type = 'square'  # half_sine, full_sine
        self.attenuated_wave = 0  # duration of attenuation
        self._pulse_dur = 100  # ms duration of single pulse
        self._duty_cycle = 0.1  # percent
        self._frequency = 1  # Hz
        self._cycle = 1 / self._frequency
        self._off_dur = None  # duration in ms of the off phase for ttl
        self.attenuation_factor = 0.5  # percent to modulate max laser power to desired output
        self.analog_mod = False
        self.pulsetrain_duration = 1000  # ms duration of whole train
        self.delay_time = 0  # time in ms to delay th start of pulse relative to the start

        self.pulse_active = False  # FLAG activating the pulsation
        self.pulse_activation_lag = 0  # ms to lag after being activated
        # not implemented, not sure if needed

        self.graceful_stop = False  # flag to stop the pulsation after full cycle
        self.reset_times()

    @property
    def pulse_type(self):
        if self._pulse_type == 1:
            return 'half_sine'
        elif self._pulse_type == 2:
            return 'full_sine'
        elif self._pulse_type == 0:
            return 'square'
        return self._pulse_type

    @pulse_type.setter
    def pulse_type(self, typ: str):
        if typ not in ['square', 'half_sine', 'full_sine']:
            print(f'Undefined pulse type {typ}')
            typ = 'square'

        if typ == 'half_sine':
            self._pulse_type = 1
        elif typ == 'full_sine':
            self._pulse_type = 2
        elif typ == 'square':
            self._pulse_type = 0

        if typ in ['half_sine', 'full_sine']:
            self.analog_mod = True
        else:
            self.analog_mod = False

    def reset_times(self):
        self.pulse_starts = []  # list of times of pulse starts
        self.pulse_ends = []

    def set_settings(self, params: dict):
        # sets parameters of the LaserController
        try:
            params = params[self.name]
        except KeyError:
            print(f'no parameters provided for {self.name}')
            return
        if params is None:  # empty parameters means not in use
            self.stop_pulsing_immediatly()
            return

        params_keys = params.keys()

        if 'frequency' in params_keys:
            self.frequency = params['frequency']
        if 'duty_cycle' in params_keys:
            self.duty_cycle = params['duty_cycle']
        if 'pulsetrain_duration' in params_keys:
            self.pulsetrain_duration = params['pulsetrain_duration']
        if 'pulse_dur' in params_keys:
            self.pulse_dur = params['pulse_dur']
        if 'pulse_type' in params_keys:
            self.pulse_type = params['pulse_type']
        if 'attenuation_factor' in params_keys:
            self.attenuation_factor = params['attenuation_factor']
        if 'pulse_activation_lag' in params_keys:
            self.pulse_activation_lag = params['pulse_activation_lag']
        if 'use_trigger_pin' in params_keys:
            self.use_trigger_pin = params['use_trigger_pin']
        if 'attenuated_wave' in params_keys:
            self.attenuated_wave = params['attenuated_wave']
        if 'delay_time' in params_keys:
            self.delay_time = params['delay_time']
        # etc.

    @property
    def frequency(self):
        return self._frequency

    @frequency.setter
    def frequency(self, new_value: float, set_duration: bool = True):
        if new_value > MAX_FREQUENCY:
            new_value = MAX_FREQUENCY
            if self.verbose:
                print(f'Input outside of range. Setting to {new_value}Hz')
        self._frequency = new_value
        if set_duration:
            self._pulse_dur = int(self._frequency * self._duty_cycle * 1000)
            if self.verbose:
                print(f'Changing pulse duration in accordance to duty cycle: {self._pulse_dur} ms')
        self._off_dur = int(1000 / self._frequency - self._pulse_dur)
        self._cycle = 1 / self._frequency

    @property
    def duty_cycle(self):
        return self._duty_cycle

    @duty_cycle.setter
    def duty_cycle(self, new_value: float):
        if new_value > 1:
            new_value = 1
            if self.verbose:
                print(f'Input outside of range. Setting to {100}%')
        elif new_value <= 0:
            print(f'Invalid value for duty cycle. must be >0 and <=1')
        self._duty_cycle = new_value
        self._pulse_dur = int(1000 / self._frequency * self._duty_cycle)
        self._off_dur = int(1000 / self._frequency - self._pulse_dur)

    @property
    def pulse_dur(self):
        return self._pulse_dur

    @pulse_dur.setter
    def pulse_dur(self, new_value: int):
        max_duration = 1000 / self._frequency
        if new_value > max_duration:
            new_value = max_duration
            if self.verbose:
                print(f'Input outside of range. Setting to {new_value}ms')
        self._pulse_dur = int(new_value)
        self._duty_cycle = self._pulse_dur / (1000 / self._frequency)
        self._off_dur = int(1000 / self._frequency - self._pulse_dur)

    @micropython.native
    def start_pulsing(self):
        self.delay_t0 = supervisor.ticks_ms()

    @micropython.native
    def start_pulsing_now(self):
        # will start pulsing on next update loop
        self.pulse_active = True
        self.graceful_stop = False  # reset
        self.pulse_t0 = supervisor.ticks_ms()
        if self.verbose:
            print(f'Started pulsing {self.pulse_t0}')
        self.last_t = self.pulse_t0
        if self.dac_i2c is not None and not self.analog_mod:  # set analog value for ttl pulsing
            self.dac_i2c.normalized_value = self.attenuation_factor
            # add a sleep ?
        self.ttl_pin.value = True

        self.pulse_starts.append(self.pulse_t0)

    @micropython.native
    def stop_pulsing_immediatly(self):
        '''
        stops the pulsation immediately
        '''
        self.pulse_active = False
        self.ttl_pin.value = False
        self.delay_t0 = int(-2 ** 31)  # reset delayed counter
        if self.dac_i2c is not None:
            self.dac_i2c.raw_value = 0
        self.pulse_ends.append(supervisor.ticks_ms())
        if self.verbose:
            print(f'Stopped pulsing {self.pulse_ends[-1]}')

    @micropython.native
    def stop_pulsing_graceful(self):
        # finish_current cycle and then stop
        self.graceful_stop = True
        self.attenuation_t0 = supervisor.ticks_ms()
        if self.verbose:
            print(f'start stopping {self.attenuation_t0}')

    # def check_stopping(self):
    # self.pu
    @micropython.native
    def update(self):
        # check if pulsation should be activated
        # check for new params every x secons ?
        now = supervisor.ticks_ms()

        if self.pulse_active:  # is actively pulsing
            t = ticks_diff(now, self.pulse_t0) / 1000
            # self.last_t
            cycle = self._cycle
            cycle_fraction = (t % cycle) / cycle
            if ticks_less(self.pulsetrain_duration, ticks_diff(now, self.pulse_t0)) and not self.graceful_stop:
                self.stop_pulsing_graceful()
            if self.analog_mod:
                # analog routine set TTL to on an modulate the DAC to achieve sinusiod wave
                # modulate analog value in dependence
                if self._pulse_type == 1:  # replace with int for speed
                    new_value = math.sin(cycle_fraction * 2 * math.pi)
                    # todo replace with raw_value ?
                elif self._pulse_type == 2:
                    new_value = (math.cos(cycle_fraction * 2 * math.pi + math.pi) + 1) / 2
                    # new_value = self.sine_lookup[int(cycle_fraction*1000)]
                if self.graceful_stop:
                    # how to deal with attenuation cycle
                    if self.attenuated_wave:
                        # TODO make a per cycle attenuation cause otherwise weird shit is happening
                        t_past = ticks_diff(now, self.attenuation_t0)
                        new_value *= (1 - t_past / self.attenuated_wave)  # attenuate the wave accordingly
                        if t_past >= self.attenuated_wave:
                            self.stop_pulsing_immediatly()
                            return
                    elif cycle_fraction < 0.1:
                        self.stop_pulsing_immediatly()
                        return
                        # problem can add one more cycle to pulse
                if new_value < 0:  # cant be negative
                    new_value = 0
                self.dac_i2c.normalized_value = new_value * self.attenuation_factor

            else:
                # digital routine set dac to 1 value and modulate TTL
                # option one.. via float compare
                # if cycle_fraction >= self.duty_cycle:  # is a float compare maybe slow
                #    self.ttl_pin.value = True
                # else:
                #    self.ttl_pin.value = False
                # option two timers
                if self.ttl_pin.value:  # pin is high
                    # if ticks_diff(now, self.last_t) > self.pulse_dur:  # was on long enough
                    if ticks_less(self.pulse_dur, ticks_diff(now, self.last_t)):
                        self.ttl_pin.value = False
                        # self.last_t = supervisor.ticks_ms()
                        self.last_t += self.pulse_dur
                        if self.graceful_stop:  # if stopping is set turn off pulsing
                            self.stop_pulsing_immediatly()
                else:  # pin is low
                    # if ticks_diff(now, self.last_t) >= self._off_dur:  # was off long enough
                    if self.graceful_stop:  # if stopping is set turn off pulsing
                        self.stop_pulsing_immediatly()
                        return
                    if ticks_less(self._off_dur, ticks_diff(now, self.last_t)):
                        self.ttl_pin.value = True
                        # self.last_t = supervisor.ticks_ms()
                        self.last_t += self._off_dur
                # option 3 PIO, define mashine after parameters here just start or stop it

            # self.check_stopping()  # check if should stop pulsing
            # if (ticks_diff(now, self.pulse_t0) >= self.pulsetrain_duration) and (not self.graceful_stop):

        else:
            if ticks_less(self.delay_time, ticks_diff(now, self.delay_t0)) and self.delay_t0 > 0:
                self.start_pulsing_now()


def make_mask(laserctl: LaserController, maskctl: LaserController):
    '''
    Takes to controllers and makes one as a mask ofthe other- makes squarewaves for mask, makes sure it runs on all triggers
    :param laserctl: controller of the actual laser
    :param maskctl: controller of the mask
    :return:
    '''

    maskctl.name = laserctl.name + '_mask'
    maskctl.is_mask = True
    maskctl.frequency = laserctl.frequency

    if laserctl.pulse_type == 'full_sine':
        # make correspoding adjustments
        maskctl.duty_cycle = 0.5
        maskctl.delay_time = int((1000 / laserctl.frequency) // 4)  # or 4 ?
        maskctl.pulse_type = 'square'
        maskctl.pulsetrain_duration = laserctl.pulsetrain_duration + laserctl.attenuated_wave
    elif laserctl.pulse_type == 'half_sine':
        maskctl.duty_cycle = 0.5
        maskctl.delay_time = 0
        maskctl.pulse_type = 'square'
        maskctl.pulsetrain_duration = laserctl.pulsetrain_duration + laserctl.attenuated_wave
    else:
        maskctl.pulse_dur = laserctl.pulse_dur
        maskctl.delay_time = laserctl.delay_time
        maskctl.pulsetrain_duration = laserctl.pulsetrain_duration


class SerialReaderComm:
    """ Read a line from USB Serial (up to end_char), non-blocking, with optional echo """

    def __init__(self, serial):
        self.s = ''
        self.serial = serial

    def read(self, end_char='\n', echo=True):
        # n = supervisor.runtime.serial_bytes_available
        n = self.serial.in_waiting
        if n > 0:  # we got bytes!
            # s = sys.stdin.read(n)  # actually read it in
            s = self.serial.read(n)  # actually read it in
            if echo:
                sys.stdout.write(s)  # echo back to human via serial console!
                self.serial.write(s)
            self.s = self.s + s.decode('utf-8')  # keep building the string up
            pieces = self.s.split(end_char)
            if len(pieces) > 1:
                rstr = pieces[0]
                self.s = self.s[len(rstr) + 1:]  # reset str to beginning
                return rstr  # .strip()
        return None  # no end_char yet

    def send_to_host(self, message: (dict, str), message_type: str = None):
        """Sends data back to host computer"""
        # if supervisor.runtime.serial_connected:
        if self.serial.connected:
            if isinstance(message, dict):
                message.update(**{'message_type': message_type})
                message = json.dumps(message) + '\n'
                self.serial.write(message.encode('utf-8'))
            elif isinstance(message, str):
                self.serial.write((message + "\n").encode("utf-8"))
        else:
            print('No serial connection established!!')


blink = adafruit_pioasm.assemble(
    """
.program blink
    pull block    ; These two instructions take the blink duration
    out y, 32     ; and store it in y
forever:
    mov x, y
    set pins, 1   ; Turn LED on
lp1:
    jmp x-- lp1   ; Delay for (x + 1) cycles, x is a 32 bit number
    mov x, y
    set pins, 0   ; Turn LED off
lp2:
    jmp x-- lp2   ; Delay for the same number of cycles again
    jmp forever   ; Blink forever!
"""
)


def start_LEDpulsing(freq=3):
    freq = freq
    sm = rp2pio.StateMachine(blink, frequency=125_000_000, first_set_pin=board.GP25, wait_for_txstall=False)
    data = array.array("I", [sm.frequency // freq])
    sm.write(data)
