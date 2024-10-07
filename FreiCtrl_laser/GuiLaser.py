import json
import logging
import queue
import math
import sys
import time
from threading import Thread

import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog
from PyQt6.QtCore import Qt, QTimer

from PyQt6 import uic, QtSerialPort, QtGui

from pathlib import Path
from datetime import datetime
from host_utils import PythonBoardCommander
from GUI_utils import QtPicoSerial
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from luxx_communication import LaserColor, TriggerEnum
from OmicronCommander import GUI_Omicron
from FreiCtrl_laser.config import *

log = logging.getLogger('main')
log.setLevel(logging.DEBUG)

logging.basicConfig(filename='GUI_laser.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')
VERSION = "1.2.0"


class MplCanvas(FigureCanvasQTAgg):
    """
    Canvas to plot matplotlib figures in a QWidget
    """
    def __init__(self, parent=None, width=9, height=6, dpi=90):
        fig, ax1 = plt.subplots(1, 1, figsize=(width, height), dpi=dpi)
        ax2 = ax1.twinx()
        # plt.tight_layout()
        self.ax1 = ax1
        self.ax2 = ax2
        self.fig = fig
        super(MplCanvas, self).__init__(fig)


class GuiLaser(QMainWindow):
    def __init__(self, main=None):
        super(GuiLaser, self).__init__()
        self.laser_module = None
        self.calib_data = []
        self.omicron_commander = None
        self.main = main
        self.calib_tread = None
        self.lasercalib_path = Path("laser_cal")
        self.trigger_log = {'name': datetime.now().strftime('%Y%m%d%H%M%S'),
                            'manual_triggers': []}  # save data about trigger events
        self.current_params = {}
        self.laser1_attenuation = 1
        self.laser2_attenuation = 1
        self.laser3_attenuation = 1
        self.laser4_attenuation = 1
        self.laser_attenuationValues_list = [self.laser1_attenuation, self.laser2_attenuation,
                                             self.laser3_attenuation, self.laser4_attenuation]

        self.last_send_params = None

        self.path2file = Path(__file__)
        uic.loadUi(self.path2file.parent / 'GUI' / 'laserGUI.ui', self)
        self.setWindowTitle('LaserController v.%s' % VERSION)

        self.portname = ''
        if self.main is None:
            self.pico = QtPicoSerial(self)
            self.pico.set_port(self.portname)
            self.communicator = PythonBoardCommander(self.pico)
            self.pico.comm = self.communicator  # looping interaction.. not great!

        self.log = logging.getLogger('Laser-GUI')
        self._handler = None
        self.consoleOutput.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.console_queue = queue.Queue()
        # manage the console output across threads
        self.console_timer = QTimer()
        self.console_timer.timeout.connect(self._poll_console_queue)
        self.console_timer.start(50)  # units are milliseconds

        self.task_is_running = False
        self.enable_console_logging()
        self.parameters_send = False  # Bool if parameters were send for this session
        self.set_Icons()
        if self.main is None:
            self.scan_ports()
        self.fs_show = 1

        self.wave_length_list = [self.WaveLength_combo, self.WaveLength_combo_2, self.WaveLength_combo_3,
                                 self.WaveLength_combo_4]

        for w_id, wave in enumerate(self.wave_length_list):
            wave.addItems([f"{v.value} {v.name}" for v in LaserColor])
            wave.setCurrentIndex(w_id)

        self.laser_pulsew_list = [self.Laser_burst_pulsewidth, self.Laser_burst_pulsewidth_2,
                                  self.Laser_burst_pulsewidth_3, self.Laser_burst_pulsewidth_4]
        self.laser_freq_list = [self.Laser_burst_freq, self.Laser_burst_freq_2, self.Laser_burst_freq_3,
                                self.Laser_burst_freq_4]
        self.laser_duration_list = [self.Laser_burst_duration, self.Laser_burst_duration_2, self.Laser_burst_duration_3,
                                    self.Laser_burst_duration_4]
        self.laser_duty_list = [self.Laser_burst_duty, self.Laser_burst_duty_2, self.Laser_burst_duty_3,
                                self.Laser_burst_duty_4]
        self.laser_attenuation_list = [self.Laser_burst_attenuation, self.Laser_burst_attenuation_2,
                                       self.Laser_burst_attenuation_3, self.Laser_burst_attenuation_4]

        self.laser_delay_list = [self.Laser_burst_delay, self.Laser_burst_delay_2, self.Laser_burst_delay_3,
                                 self.Laser_burst_delay_4]
        self.laser_power_list = [self.Laser_burst_power, self.Laser_burst_power_2, self.Laser_burst_power_3,
                                 self.Laser_burst_power_4]

        self.laser_calibB_list = [self.calB_1, self.calB_2, self.calB_3, self.calB_4]

        self.wave_square_list = [self.radioSquare, self.radioSquare_2, self.radioSquare_4, self.radioSquare_5]
        self.wave_sine_list = [self.radioSine, self.radioSine_2, self.radioSine_4, self.radioSine_5]
        self.wave_hsine_list = [self.radioHSine, self.radioHSine_2, self.radioHSine_4, self.radioHSine_5]

        self.laser_check_list = [self.lasercheck1, self.lasercheck2, self.lasercheck3, self.lasercheck4]
        self.mask_check_list = [self.maskcheck1, self.maskcheck2, self.maskcheck3, self.maskcheck4]
        self.Version_combo.addItems([f"{v.name}" for v in TriggerEnum])
        self.Version_combo.setCurrentIndex(0)

        if not USE_OMICRON:
            self.OmicronB.setEnabled(False)
            #deleter BUTTON
            self.OmicronB.deleteLater()

        self.ConnectSignals()
        self.show_example()
        self.read_calibrations()

        if self.main is not None:
            # turn off send and etc commands if not main window
            # self.StartTaskB.setEnabled(False)
            self.ScanB.setEnabled(False)
            self.PortsCombo.setEnabled(False)
            self.PingB.setEnabled(False)
            self.OmicronB.setEnabled(False)
            # for b in self.laser_calibB_list:
            #    b.setEnabled(False)
            # self.ScanB.setEnabled(False)
            # SendParamsB

    def power_calc(self):
        sender = self.sender()  # which power was changed
        idx = [idx for idx, b in enumerate(self.laser_power_list) if b == sender][0]
        self.laser_attenuationValues_list[idx] = ((self.laser_power_list[idx].value() - self.calib_data[idx]['b'])
                                                  / self.calib_data[idx]['m'])

        if self.laser_attenuationValues_list[idx] > 1:
            self.log.info(f"Current power settings for laser {idx} exceeds calibration value, setting to max")
            self.laser_attenuationValues_list[idx] = 1
            self.laser_power_list[idx].setValue(int(self.calib_data[idx]['m'] + self.calib_data[idx]['b']))

        self.log.info(f"Laser{idx+1} was set to {self.laser_attenuationValues_list[idx]} for "
                      f"{self.laser_power_list[idx].value()}mW")
        self.show_example()

    def start_task(self):
        message = ('TRIGGER' + '\n').encode('utf-8')

        if self.main is None:  # stand alone
            self.pico.write(message)
            now = time.ctime(time.time())
            self.trigger_log['manual_triggers'].append((now, self.current_params))
            # write to disk
            with open(f"laserLog_{self.trigger_log['name']}.json", 'w') as fi:
                json.dump(self.trigger_log, fi, indent=4)
        else:
            self.main.pico.write(message)

    def get_params(self) -> dict:
        """
        gets the current parameters as a dict
        """
        params = {}
        params["laser_list"] = []
        for idx in range(4):
            stype = "square" if self.wave_square_list[idx].isChecked() else ""
            if stype == "":
                stype = "full_sine" if self.wave_sine_list[idx].isChecked() else "half_sine"

            if self.laser_check_list[idx].isChecked() or self.mask_check_list[idx].isChecked():
                if self.laser_check_list[idx].isChecked():
                    params["laser_list"].append(f'laser{idx + 1}')
                params[f'laser{idx + 1}'] = {'pulsetrain_duration': self.laser_duration_list[idx].value(),
                                             'frequency': self.laser_freq_list[idx].value(),
                                             'pulse_dur': self.laser_pulsew_list[idx].value(),
                                             'pulse_type': stype,
                                             'attenuation_factor': self.laser_attenuationValues_list[idx],
                                             'attenuated_wave': self.laser_attenuation_list[idx].value(),
                                             'delay_time': self.laser_delay_list[idx].value(),
                                             'wavelength': self.wave_length_list[idx].currentIndex(),
                                             'power': self.laser_power_list[idx].value()}
            if self.mask_check_list[idx].isChecked():
                params["laser_list"].append(f'laser{idx+1}_mask')
            # trigger params
        trigger = self.Version_combo.currentText()
        # check what is our trigger ! if not internal set is primed to false!
        is_primed = True if trigger == 'IntTrigger' else False
        mock = self.MockRadio.isChecked()
        params['trigger1'] = {'mock': mock, 'is_primed': is_primed,
                              'use_trigger_pin': True, "trigger_pin": trigger, "use_priming_pin": not is_primed}
        params['message_type'] = 'LaserParams'

        self.current_params = params
        return params

    def get_params_old(self) -> dict:
        # to be deleted
        # get params in a dict
        if self.radioSquare.isChecked():
            stype = "square"
        elif self.radioSine.isChecked():
            stype = "full_sine"
        elif self.radioHSine.isChecked():
            stype = "half_sine"
        if self.radioSquare_2.isChecked():
            stype2 = "square"
        elif self.radioSine_2.isChecked():
            stype2 = "full_sine"
        elif self.radioHSine_2.isChecked():
            stype2 = "half_sine"

        if self.radioSquare_4.isChecked():
            stype3 = "square"
        elif self.radioSine_4.isChecked():
            stype3 = "full_sine"
        elif self.radioHSine_4.isChecked():
            stype3 = "half_sine"
        if self.radioSquare_5.isChecked():
            stype4 = "square"
        elif self.radioSine_5.isChecked():
            stype4 = "full_sine"
        elif self.radioHSine_5.isChecked():
            stype4 = "half_sine"

        params = {}
        params["laser_list"] = []

        if self.lasercheck1.isChecked() or self.maskcheck1.isChecked():
            if self.lasercheck1.isChecked():
                params["laser_list"].append('laser1')
            params['laser1'] = {
                'pulsetrain_duration': self.Laser_burst_duration.value(),
                'frequency': self.Laser_burst_freq.value(),
                'pulse_dur': self.Laser_burst_pulsewidth.value(),
                'pulse_type': stype,
                'attenuation_factor': self.laser_attenuationValues_list[0],
                'attenuated_wave': self.Laser_burst_attenuation.value(),
                'delay_time': self.Laser_burst_delay.value(),
                'power': self.Laser_burst_power.value()}

        if self.lasercheck2.isChecked() or self.maskcheck2.isChecked():
            if self.lasercheck2.isChecked():
                params["laser_list"].append('laser2')
            params['laser2'] = {
                'pulsetrain_duration': self.Laser_burst_duration_2.value(),
                'frequency': self.Laser_burst_freq_2.value(),
                'pulse_dur': self.Laser_burst_pulsewidth_2.value(),
                'pulse_type': stype2,
                'attenuation_factor': self.laser_attenuationValues_list[1],
                'attenuated_wave': self.Laser_burst_attenuation_2.value(),
                'delay_time': self.Laser_burst_delay_2.value(),
                'power': self.Laser_burst_power_2.value()}

        if self.lasercheck3.isChecked() or self.maskcheck3.isChecked():
            if self.lasercheck3.isChecked():
                params["laser_list"].append('laser3')
            params['laser3'] = {
                'pulsetrain_duration': self.Laser_burst_duration_3.value(),
                'frequency': self.Laser_burst_freq_3.value(),
                'pulse_dur': self.Laser_burst_pulsewidth_3.value(),
                'pulse_type': stype3,
                'attenuation_factor': self.laser_attenuationValues_list[2],
                'attenuated_wave': self.Laser_burst_attenuation_3.value(),
                'delay_time': self.Laser_burst_delay_3.value(),
                'power': self.Laser_burst_power_3.value()}

        if self.lasercheck4.isChecked() or self.maskcheck4.isChecked():
            if self.lasercheck4.isChecked():
                params["laser_list"].append('laser4')
            params['laser4'] = {
                'pulsetrain_duration': self.Laser_burst_duration_4.value(),
                'frequency': self.Laser_burst_freq_4.value(),
                'pulse_dur': self.Laser_burst_pulsewidth_4.value(),
                'pulse_type': stype4,
                'attenuation_factor': self.laser_attenuationValues_list[3],
                'attenuated_wave': self.Laser_burst_attenuation_4.value(),
                'delay_time': self.Laser_burst_delay_4.value(),
                'power': self.Laser_burst_power_4.value()}

        if self.maskcheck1.isChecked():
            params["laser_list"].append('laser1_mask')
        if self.maskcheck2.isChecked():
            params["laser_list"].append('laser2_mask')
        if self.maskcheck3.isChecked():
            params["laser_list"].append('laser3_mask')
        if self.maskcheck4.isChecked():
            params["laser_list"].append('laser4_mask')

        # trigger params
        trigger = self.Version_combo.currentText()
        # check what is our trigger ! if not internal set is primed to false!
        is_primed = True if trigger == 'IntTrigger' else False
        mock = self.MockRadio.isChecked()
        params['trigger1'] = {'mock': mock, 'is_primed': is_primed,
                              'use_trigger_pin': True, "trigger_pin": trigger, "use_priming_pin": not is_primed}
        params['message_type'] = 'LaserParams'

        self.current_params = params
        return params

    def send_params(self):
        params = self.get_params()
        message = (json.dumps(params) + '\n').encode('utf-8')
        # self.pico.thread_safe_write(message)
        if self.main is None:  # stand alone
            self.pico.write(message)
        else:
            self.main.set_laser_settings(params, send2pico=True)

    def read_calibrations(self):
        """get calib parameters from file"""
        for l_idx in range(4):
            try:
                c_file = list(self.lasercalib_path.rglob(f'calib_laser{l_idx+1}_*'))[-1]
                with open(c_file, 'r') as fi:
                    calib = json.load(fi)
                self.calib_data.append(calib['params'])
            except IndexError:
                print(f"no calibration file available for laser{l_idx+1}, assuming linear scale to 50mW")
                self.calib_data.append({"m": 50, "b": 0})

    def run_calibration(self):
        sender = self.sender()  # to know which button was pressed
        idx = [idx for idx, slider in enumerate(self.laser_calibB_list) if slider == sender][0]
        l_idx = f"laser{idx + 1}"
        dict2send = {"calibrate": True, 'laser2calib': l_idx, "calibsteps": CALIB_STEPS, 'calibdur': 10}
        if self.main is None:  # stand alone
            self.pico.write((json.dumps(dict2send) + '\n').encode('utf-8'))
        else:
            self.main.pico.write((json.dumps(dict2send) + '\n').encode('utf-8'))

        self.calib_tread = Thread(target=self.calibrate_laser_alt, args=(l_idx,))
        self.calib_tread.start()
        self.log.info(f"Calibrating {l_idx}")

    def calibrate_laser_alt(self, laser):
        try:
            wavelength = self.wave_length_list[int(laser.strip('laser'))-1].currentText()
            wavelength = int(wavelength.split(' ')[0])
        except IndexError:
            wavelength = 0

        if self.laser_module is None:
            self.log.info('Lasers are not connected to controller, manually turn them on')
        else:
            self.laser_module.prepare_lasers([wavelength])
            time.sleep(3)

        self.log.info('Set the powermeter to the correct wavelength!')
        calib_values = {'laser': laser, 'calib': []}
        for step in CALIB_STEPS:
            val = input(f'Enter current power reading in mW for setting {step*100}%')
            try:
                val = float(val.replace(',', '.'))
            except ValueError:
                val = 0
            calib_values['calib'].append((step, val))
            if val == 0:
                self.log.error('Received invalid value during calib, stopping. Wait for circuitpython to finish.')
                return  # break execution
            time.sleep(5)

        self.log.info('Calibration finished')
        xs = [value[0] for value in calib_values['calib']]
        ys = [value[1] for value in calib_values['calib']]
        m, b = np.polyfit(xs, ys, deg=1)
        r2 = calculate_r_squared(np.array(ys), np.array([(m * x + b) for x in xs]))
        calib_values['params'] = {'m': m, "b": b, "r2": r2}
        self.lasercalib_path.mkdir(exist_ok=True)
        with open(
                self.lasercalib_path / f"calib_{calib_values['laser']}_{datetime.now().strftime('%Y%m%d')}.json",
                'w') as fi:
            json.dump(calib_values, fi, indent=4)
        # put laser in standby ?
        if self.laser_module is None:
            self.log.info('Lasers are not connected to controller, manually turn them off')
        else:
            self.laser_module.put_lasers_standby()

        self.read_calibrations()  # update to newest values


    #### SERIAL PORTS ######
    def pico_data_received(self, payload):
        payload = payload.decode()
        self.log.debug("Received: %s", payload)

    def pingPython(self):
        self.communicator.PingCircuitPython()
        self.log.debug('Pinging Circuitpython')

    def scan_ports(self):
        self.log.debug(f'Scanning serial ports')
        self.PortsCombo.clear()
        self.PortsCombo.addItem("<no port selected>")
        for port in QtSerialPort.QSerialPortInfo.availablePorts():
            if 'ACM' in port.portName():
                self.PortsCombo.insertItem(0, port.portName())
        self.ConnectB.setEnabled(True)
        potential_port = [p_id for p_id, port in enumerate(QtSerialPort.QSerialPortInfo.availablePorts())
                          if port.portName() == 'ttyACM1']
        for port_id in potential_port:
            self.PortsCombo.setCurrentIndex(port_id + 1)

    def connect_to_pico(self):
        portname = self.PortsCombo.currentText()
        self.pico.set_port(portname)
        success = self.pico.open()
        if success:
            self.log.debug(f'Connected to port {portname}')
            self.ConnectB.setText("Connected")
            self.ConnectB.setEnabled(False)
            self.PortsCombo.setEnabled(False)
            self.ScanB.setEnabled(False)
            self.DisConnectB.setEnabled(True)

    def disconnect_from_pico(self):
        self.pico.close()
        self.log.debug('Disconnected')
        self.ConnectB.setText("Connect")
        self.ConnectB.setEnabled(True)
        self.PortsCombo.setEnabled(True)
        self.ScanB.setEnabled(True)
        self.DisConnectB.setEnabled(False)

    ### MAINTENANCE
    def save_params(self):
        params = {}
        params["laser_list"] = []
        for idx in range(4):
            stype = "square" if self.wave_square_list[idx].isChecked() else ""
            if stype == "":
                stype = "full_sine" if self.wave_sine_list[idx].isChecked() else "half_sine"

            params[f'laser{idx + 1}'] = {'pulsetrain_duration': self.laser_duration_list[idx].value(),
                                         'frequency': self.laser_freq_list[idx].value(),
                                         'pulse_dur': self.laser_pulsew_list[idx].value(),
                                         'pulse_type': stype,
                                         'attenuation_factor': self.laser_power_list[idx].value(),
                                         'attenuated_wave': self.laser_attenuation_list[idx].value(),
                                         'delay_time': self.laser_delay_list[idx].value(),
                                         'wavelength': self.wave_length_list[idx].currentIndex()
                                         }

        params["laser_checks"] = {'laser1': self.lasercheck1.isChecked(), "mask1": self.maskcheck1.isChecked(),
                                  'laser2': self.lasercheck2.isChecked(), "mask2": self.maskcheck2.isChecked(),
                                  'laser3': self.lasercheck3.isChecked(), "mask3": self.maskcheck3.isChecked(),
                                  'laser4': self.lasercheck4.isChecked(), "mask4": self.maskcheck4.isChecked()}
        # trigger params
        trigger = self.Version_combo.currentText()
        params['trigger1'] = {'mock': False, 'is_primed': True,
                              'use_trigger_pin': True, "trigger_pin": trigger}

        fileName = QFileDialog.getSaveFileName(self, "Save settings file", "./laserparams",
                                               "Settings Files (*.cfg.json)")
        with open(fileName[0], 'w') as fi:
            json.dump(params, fi, indent=4)

    def set_params_frommain(self, params):
        # todo clean up and maybe combine with next function ?
        self.Version_combo.setCurrentText(params['trigger1']['trigger_pin'])
        # modifyy in a way to set parameters also from main

        laserZ = ['laser1', 'laser2', 'laser3', 'laser4']
        for ele, name in zip(self.laser_check_list, laserZ):
            ele.setChecked(True if name in params['laser_list'] else False)
        for ele, name in zip([self.maskcheck1, self.maskcheck2, self.maskcheck3,
                              self.maskcheck4], laserZ):
            ele.setChecked(True if name+"_mask" in params['laser_list'] else False)

        for square, sine, hsine, name in zip(self.wave_square_list, self.wave_sine_list, self.wave_hsine_list, laserZ):
            try:
                if params[name]['pulse_type'] == 'square':
                    square.setChecked(True)
                elif params[name]['pulse_type'] == 'full_sine':
                    sine.setChecked(True)
                elif params[name]['pulse_type'] == 'half_sine':
                    hsine.setChecked(True)
            except KeyError:
                pass # no setting for this laser

        for ele, name in zip(self.laser_duration_list, laserZ):
            try:
                ele.setValue(params[name]['pulsetrain_duration'])
            except KeyError:
                pass # no setting for this laser
        for ele, name in zip(self.laser_freq_list, laserZ):
            try:
                ele.setValue(params[name]['frequency'])
            except KeyError:
                pass  # no setting for this laser
        for ele, name in zip(self.laser_pulsew_list, laserZ):
            try:
                ele.setValue(params[name]['pulse_dur'])
            except KeyError:
                pass  # no setting for this laser

        for ele, name in zip(self.laser_attenuation_list, laserZ):
            try:
                ele.setValue(params[name]['attenuated_wave'])
            except KeyError:
                pass # no setting for this laser
        for ele, name in zip(self.laser_delay_list, laserZ):
            try:
                ele.setValue(params[name]['delay_time'])
            except KeyError:
                pass # no setting for this laser

        for ele, name in zip(self.laser_power_list, laserZ):
            # problem here..
            try:
                ele.setValue(params[name]['power'])
            except KeyError:
                pass # no setting for this laser

        for ele, name in zip(self.wave_length_list, laserZ):
            try:
                ele.setCurrentIndex(params[name]['wavelength'])
            except KeyError:
                pass # no setting for this laser


    def load_params(self, file_name=None):
        if not isinstance(file_name, str):
            fileName = QFileDialog.getOpenFileName(self, "Load settings file", "./laserparams",
                                                   "Settings Files (*.cfg.json)")
            if fileName[0]:
                with open(fileName[0], 'r') as fi:
                    params = json.load(fi)
                # self.set_params(params)
            else:
                return
        else:
            try:
                with open(file_name, 'r') as fi:
                    params = json.load(fi)
            except FileNotFoundError:
                print('Check path')
                return

        laserZ = ['laser1', 'laser2', 'laser3', 'laser4']
        for ele, name in zip(self.laser_check_list, laserZ):
            ele.setChecked(params['laser_checks'][name])
        for ele, name in zip(self.mask_check_list, ['mask1', 'mask2', 'mask3', 'mask4']):
            ele.setChecked(params['laser_checks'][name])

        for ele, name in zip(self.laser_duration_list, laserZ):
            ele.setValue(params[name]['pulsetrain_duration'])
        for ele, name in zip(self.laser_freq_list, laserZ):
            ele.setValue(params[name]['frequency'])

        for ele, name in zip(self.laser_pulsew_list, laserZ):
            ele.setValue(params[name]['pulse_dur'])

        for ele, name in zip(self.laser_attenuation_list, laserZ):
            ele.setValue(params[name]['attenuated_wave'])

        for ele, name in zip(self.laser_delay_list, laserZ):
            ele.setValue(params[name]['delay_time'])

        for ele, name in zip(self.laser_power_list, laserZ):
            ele.setValue(params[name]['attenuation_factor'])

        for ele, name in zip(self.wave_length_list, laserZ):
            ele.setCurrentIndex(params[name]['wavelength'])

        for square, sine, hsine, name in zip(self.wave_square_list, self.wave_sine_list, self.wave_hsine_list, laserZ):
            if params[name]['pulse_type'] == 'square':
                square.setChecked(True)
            elif params[name]['pulse_type'] == 'full_sine':
                sine.setChecked(True)
            elif params[name]['pulse_type'] == 'half_sine':
                hsine.setChecked(True)
        self.Version_combo.setCurrentText(params['trigger1']['trigger_pin'])

    def omicron_commander_open(self, laser_module=None):
        #print(laser_module)
        if self.omicron_commander is None:
            self.omicron_commander = GUI_Omicron(self, laser_module=laser_module)
        self.omicron_commander.show()

    def ConnectSignals(self):
        """
        instanciates the callbacks of the GUI elements
        """
        self.StartTaskB.clicked.connect(self.start_task)
        # self.StopTaskB.clicked.connect(self.send_stop_task)
        # self.EmergencyStopTaskB.clicked.connect(self.emergency_stop_task)

        ##### SETTINGS Buttons ###
        self.SendParamsB.clicked.connect(self.send_params)
        self.SaveSettingsB.clicked.connect(self.save_params)
        self.LoadSettingsB.clicked.connect(self.load_params)
        ### SERIAL Buttons ####
        self.ScanB.clicked.connect(self.scan_ports)
        self.ConnectB.clicked.connect(self.connect_to_pico)
        self.DisConnectB.clicked.connect(self.disconnect_from_pico)
        self.PingB.clicked.connect(self.pingPython)

        ##### HELP-Buttons ##########
        self.ParametersHelpB.clicked.connect(self.showParametersHelp)

        self.OmicronB.clicked.connect(self.omicron_commander_open)

        #### Callbacks ####

        for ele in self.laser_freq_list + self.laser_pulsew_list:
            ele.valueChanged.connect(self.set_pulsedur)

        for ele in self.laser_duty_list:
            ele.valueChanged.connect(self.set_pulseduty)

        for ele in [self.radioSine, self.radioHSine, self.radioSine_2, self.radioHSine_2,
                    self.radioSine_4, self.radioHSine_4, self.radioSine_5, self.radioHSine_5]:
            ele.toggled.connect(self.set_sine)

        for ele in [self.radioSquare, self.radioSquare_2, self.radioSquare_4, self.radioSquare_5]:
            ele.toggled.connect(self.set_square)

        for ele in self.laser_duration_list + self.laser_delay_list + self.laser_attenuation_list:
            ele.valueChanged.connect(self.show_example)

        for check in [self.lasercheck1, self.lasercheck2, self.lasercheck3, self.lasercheck4,
                      self.maskcheck1, self.maskcheck2, self.maskcheck3, self.maskcheck4]:
            check.stateChanged.connect(self.show_example)

        for combo in self.wave_length_list:
            combo.currentIndexChanged.connect(self.show_example)

        for power in self.laser_power_list:
            power.valueChanged.connect(self.power_calc)

        # attenuation

        for button in self.laser_calibB_list:
            button.clicked.connect(self.run_calibration)

    def set_square(self):
        # check if i can just find out which button caused it
        sender = self.sender()  # Get the sender of the signal
        if sender == self.radioSquare:
            self.Laser_burst_attenuation.blockSignals(True)
            self.Laser_burst_attenuation.setValue(0)
            self.Laser_burst_attenuation.blockSignals(False)
        elif sender == self.radioSquare_2:
            self.Laser_burst_attenuation_2.blockSignals(True)
            self.Laser_burst_attenuation_2.setValue(0)
            self.Laser_burst_attenuation_2.blockSignals(False)
        elif sender == self.radioSquare_4:
            self.Laser_burst_attenuation_3.blockSignals(True)
            self.Laser_burst_attenuation_3.setValue(0)
            self.Laser_burst_attenuation_3.blockSignals(False)
        elif sender == self.radioSquare_5:
            self.Laser_burst_attenuation_4.blockSignals(True)
            self.Laser_burst_attenuation_4.setValue(0)
            self.Laser_burst_attenuation_4.blockSignals(False)
        self.show_example()

    def set_sine(self):
        sender = self.sender()  # Get the sender of the signal
        if sender == self.radioSine or sender == self.radioHSine:
            self.Laser_burst_pulsewidth.setValue(int(1000 / self.Laser_burst_freq.value() * 0.5))
        elif sender == self.radioSine_2 or sender == self.radioHSine_2:
            self.Laser_burst_pulsewidth_2.setValue(int(1000 / self.Laser_burst_freq_2.value() * 0.5))
        elif sender == self.radioSine_4 or sender == self.radioHSine_4:
            self.Laser_burst_pulsewidth_3.setValue(int(1000 / self.Laser_burst_freq_3.value() * 0.5))
        elif sender == self.radioSine_5 or sender == self.radioHSine_5:
            self.Laser_burst_pulsewidth_4.setValue(int(1000 / self.Laser_burst_freq_4.value() * 0.5))
        self.show_example()

    def set_pulsedur(self):
        """
        sets the pulse duration and duty cycle according to pulse_freq
        """
        sender = self.sender()  # Get the sender of the signal
        try:
            idx = [idx for idx, slider in enumerate(self.laser_pulsew_list) if slider == sender][0]
        except IndexError:
            idx = [idx for idx, slider in enumerate(self.laser_freq_list) if slider == sender][0]

        pulse = self.laser_pulsew_list[idx].value()
        if pulse > self.laser_duration_list[idx].value():
            self.laser_duration_list[idx].setValue(pulse)
        freq = self.laser_freq_list[idx].value()
        if pulse > 1000 / freq:
            pulse = 1000 / freq
            self.laser_pulsew_list[idx].blockSignals(True)
            self.laser_pulsew_list[idx].setValue(int(pulse))
            self.laser_pulsew_list[idx].blockSignals(False)
        duty = pulse / (1000 / freq) * 100
        self.laser_duty_list[idx].blockSignals(True)
        self.laser_duty_list[idx].setValue(duty)
        self.laser_duty_list[idx].blockSignals(False)
        self.show_example()

    def set_pulseduty(self):
        sender = self.sender()  # Get the sender of the signal
        idx = [idx for idx, slider in enumerate(self.laser_duty_list) if slider == sender][0]
        freq = self.laser_freq_list[idx].value()
        duty = self.laser_duty_list[idx].value()
        pulse = int(1000 / freq * duty / 100)
        self.laser_pulsew_list[idx].blockSignals(True)
        self.laser_pulsew_list[idx].setValue(pulse)
        self.laser_pulsew_list[idx].blockSignals(False)
        if pulse > self.laser_duration_list[idx].value():  # modify total duration accordingly
            self.laser_duration_list[idx].setValue(pulse)
        self.show_example()

    def get_values2plot(self, pulse_train_dur, total_duration, freq, duty, stype, delay, atten) -> tuple:
        tx = [v for v in range(0, total_duration, self.fs_show)]
        values2plot = np.zeros_like(tx)

        cycle = 1000 / freq

        if stype == 1:
            values2plot = [1 if (t % cycle) / cycle < duty else 0 for t in tx]
            values2plot = []
            for t in tx:
                t -= delay
                if t < 0:
                    new_val = 0
                else:
                    new_val = 1 if (t % cycle) / cycle < duty else 0
                values2plot.append(new_val)
        elif stype == 2:
            values2plot = []
            for t in tx:
                t -= delay
                if t < 0:
                    new_val = 0
                else:
                    new_val = (math.cos((t % cycle) / cycle * 2 * math.pi + math.pi) + 1) / 2
                    if (t - pulse_train_dur > 0) and (atten != 0):
                        new_val *= (1 - (t - pulse_train_dur) / atten)
                        try:
                            val2attenuate = 1 - (t - pulse_train_dur)//cycle / (atten//cycle)
                        except ZeroDivisionError:  # attenuation duration smaller than a cycle
                            val2attenuate = 1
                        #new_val *= val2attenuate
                values2plot.append(new_val)

        elif stype == 3:
            values2plot = []
            for t in tx:
                t -= delay
                if t < 0:
                    new_val = 0
                else:
                    new_val = math.sin((t % cycle) / cycle * 2 * math.pi)
                    if (t - pulse_train_dur > 0) and (atten != 0):
                        new_val *= (1 - (t - pulse_train_dur) / atten)
                if new_val < 0:
                    new_val = 0
                values2plot.append(new_val)

        tx = np.insert(tx, 0, tx[1])
        tx = np.insert(tx, -1, tx[1] + tx[-1])
        values2plot = np.insert(values2plot, 0, 0)
        values2plot = np.insert(values2plot, -1, 0)
        return tx, values2plot

    def show_example(self):
        # TODO rewrite with lists
        self.sessionPlotWidget.canvas.ax1.clear()
        self.sessionPlotWidget.canvas.ax2.clear()

        if self.lasercheck1.isChecked():
            freq = self.Laser_burst_freq.value()
            duty = self.Laser_burst_duty.value() / 100
            pulse = int(1000 / freq * duty / 100)
            atten = self.Laser_burst_attenuation.value()
            pulse_train_dur = self.Laser_burst_duration.value()
            total_duration = pulse_train_dur + atten
            delay = self.Laser_burst_delay.value()
            total_duration += delay
            if self.radioSquare.isChecked():
                stype = 1
            elif self.radioSine.isChecked():
                stype = 2
            elif self.radioHSine.isChecked():
                stype = 3
            tx, values2plot = self.get_values2plot(pulse_train_dur, total_duration, freq, duty, stype, delay, atten)
            c = self.WaveLength_combo.currentText().split(" ")[-1]

            self.sessionPlotWidget.canvas.ax1.plot(tx, values2plot * self.laser_attenuationValues_list[0], color=c)

        if self.maskcheck1.isChecked():
            freq = self.Laser_burst_freq.value()
            duty = self.Laser_burst_duty.value() / 100
            atten = self.Laser_burst_attenuation.value()
            pulse_train_dur = self.Laser_burst_duration.value()
            total_duration = pulse_train_dur + atten
            delay = self.Laser_burst_delay.value()

            if self.radioSquare.isChecked():
                stype = 1
            elif self.radioSine.isChecked():
                delay += int((1000 / freq) // 4)
                duty = 0.5
            elif self.radioHSine.isChecked():
                duty = 0.5
            stype = 1
            total_duration += delay
            tx, values2plot = self.get_values2plot(pulse_train_dur, total_duration, freq, duty, stype, delay, atten)
            c = self.WaveLength_combo.currentText().split(" ")[-1]
            self.sessionPlotWidget.canvas.ax1.plot(tx, values2plot, f':{c}')

        if self.lasercheck2.isChecked():
            freq = self.Laser_burst_freq_2.value()
            duty = self.Laser_burst_duty_2.value() / 100
            atten = self.Laser_burst_attenuation_2.value()
            pulse_train_dur = self.Laser_burst_duration_2.value()
            total_duration = pulse_train_dur + atten
            delay = self.Laser_burst_delay_2.value()
            total_duration += delay
            if self.radioSquare_2.isChecked():
                stype = 1
            elif self.radioSine_2.isChecked():
                stype = 2
            elif self.radioHSine_2.isChecked():
                stype = 3
            tx, values2plot = self.get_values2plot(pulse_train_dur, total_duration, freq, duty, stype, delay, atten)
            c = self.WaveLength_combo_2.currentText().split(" ")[-1]
            self.sessionPlotWidget.canvas.ax2.plot(tx, values2plot * self.laser_attenuationValues_list[1], color=c)

        if self.maskcheck2.isChecked():
            freq = self.Laser_burst_freq_2.value()
            duty = self.Laser_burst_duty_2.value() / 100
            atten = self.Laser_burst_attenuation_2.value()
            pulse_train_dur = self.Laser_burst_duration_2.value()
            total_duration = pulse_train_dur + atten
            delay = self.Laser_burst_delay_2.value()

            if self.radioSquare_2.isChecked():
                stype = 1
            elif self.radioSine_2.isChecked():
                delay += int((1000 / freq) // 4)
                duty = 0.5
            elif self.radioHSine_2.isChecked():
                duty = 0.5
            stype = 1
            total_duration += delay
            tx, values2plot = self.get_values2plot(pulse_train_dur, total_duration, freq, duty, stype, delay, atten)
            c = self.WaveLength_combo_2.currentText().split(" ")[-1]
            self.sessionPlotWidget.canvas.ax2.plot(tx, values2plot, f':{c}')

        if self.lasercheck3.isChecked():
            freq = self.Laser_burst_freq_3.value()
            duty = self.Laser_burst_duty_3.value() / 100
            pulse = int(1000 / freq * duty / 100)
            atten = self.Laser_burst_attenuation_3.value()
            pulse_train_dur = self.Laser_burst_duration_3.value()
            total_duration = pulse_train_dur + atten
            delay = self.Laser_burst_delay_3.value()
            total_duration += delay
            if self.radioSquare_4.isChecked():
                stype = 1
            elif self.radioSine_4.isChecked():
                stype = 2
            elif self.radioHSine_4.isChecked():
                stype = 3
            tx, values2plot = self.get_values2plot(pulse_train_dur, total_duration, freq, duty, stype, delay, atten)
            c = self.WaveLength_combo_3.currentText().split(" ")[-1]
            self.sessionPlotWidget.canvas.ax1.plot(tx, values2plot * self.laser_attenuationValues_list[2], color=c)

        if self.maskcheck3.isChecked():
            freq = self.Laser_burst_freq_3.value()
            duty = self.Laser_burst_duty_3.value() / 100
            atten = self.Laser_burst_attenuation_3.value()
            pulse_train_dur = self.Laser_burst_duration_3.value()
            total_duration = pulse_train_dur + atten
            delay = self.Laser_burst_delay_3.value()

            if self.radioSquare_4.isChecked():
                stype = 1
            elif self.radioSine_4.isChecked():
                delay += int((1000 / freq) // 4)
                duty = 0.5
            elif self.radioHSine_4.isChecked():
                duty = 0.5
            stype = 1
            total_duration += delay
            tx, values2plot = self.get_values2plot(pulse_train_dur, total_duration, freq, duty, stype, delay, atten)
            c = self.WaveLength_combo_3.currentText().split(" ")[-1]
            self.sessionPlotWidget.canvas.ax1.plot(tx, values2plot, f':{c}')

        if self.lasercheck4.isChecked():
            freq = self.Laser_burst_freq_4.value()
            duty = self.Laser_burst_duty_4.value() / 100
            atten = self.Laser_burst_attenuation_4.value()
            pulse_train_dur = self.Laser_burst_duration_4.value()
            total_duration = pulse_train_dur + atten
            delay = self.Laser_burst_delay_4.value()
            total_duration += delay
            if self.radioSquare_5.isChecked():
                stype = 1
            elif self.radioSine_5.isChecked():
                stype = 2
            elif self.radioHSine_5.isChecked():
                stype = 3
            tx, values2plot = self.get_values2plot(pulse_train_dur, total_duration, freq, duty, stype, delay, atten)
            c = self.WaveLength_combo_4.currentText().split(" ")[-1]
            self.sessionPlotWidget.canvas.ax2.plot(tx, values2plot * self.laser_attenuationValues_list[3], color=c)

        if self.maskcheck4.isChecked():
            freq = self.Laser_burst_freq_4.value()
            duty = self.Laser_burst_duty_4.value() / 100
            atten = self.Laser_burst_attenuation_4.value()
            pulse_train_dur = self.Laser_burst_duration_4.value()
            total_duration = pulse_train_dur + atten
            delay = self.Laser_burst_delay_4.value()

            if self.radioSquare_5.isChecked():
                stype = 1
            elif self.radioSine_5.isChecked():
                delay += int((1000 / freq) // 4)
                duty = 0.5
            elif self.radioHSine_5.isChecked():
                duty = 0.5
            stype = 1
            total_duration += delay
            tx, values2plot = self.get_values2plot(pulse_train_dur, total_duration, freq, duty, stype, delay, atten)
            c = self.WaveLength_combo_4.currentText().split(" ")[-1]
            self.sessionPlotWidget.canvas.ax2.plot(tx, values2plot, f':{c}')

        self.sessionPlotWidget.canvas.ax1.set_xlabel('Time in ms')
        self.sessionPlotWidget.canvas.draw()

    def showParametersHelp(self):
        self.log.warning('Not implemented')

    def set_Icons(self):
        self.ConnectB.setIcon(QtGui.QIcon("GUI/icons/connect.svg"))
        self.DisConnectB.setIcon(QtGui.QIcon("GUI/icons/disconnect.svg"))
        self.SendParamsB.setIcon(QtGui.QIcon("GUI/icons/WrenchScrewdriver.svg"))
        self.StartTaskB.setIcon(QtGui.QIcon("GUI/icons/power-icon.svg"))
        self.PingB.setIcon(QtGui.QIcon("GUI/icons/bell.svg"))
        self.LoadSettingsB.setIcon(QtGui.QIcon("GUI/icons/DocumentArrowDown.svg"))
        self.SaveSettingsB.setIcon(QtGui.QIcon("GUI/icons/DocumentArrowUp.svg"))
        self.OmicronB.setIcon(QtGui.QIcon("GUI/icons/laser.svg"))

        for sine in [self.radioSine, self.radioSine_2, self.radioSine_4, self.radioSine_5]:
            sine.setIcon(QtGui.QIcon("GUI/icons/sine.svg"))
        for sine in [self.radioSquare, self.radioSquare_2, self.radioSquare_4, self.radioSquare_5]:
            sine.setIcon(QtGui.QIcon("GUI/icons/square_wave.svg"))
        for sine in [self.radioHSine, self.radioHSine_2, self.radioHSine_4, self.radioHSine_5]:
            sine.setIcon(QtGui.QIcon("GUI/icons/half_sine.svg"))

        # self.tabWidget.setIcon(QtGui.QIcon("GUI/icons/lambda.svg"))

    def _poll_console_queue(self):
        """Write any queued console text to the console text area from the main thread."""
        while not self.console_queue.empty():
            string = str(self.console_queue.get())
            stripped = string.rstrip()
            errorFormat = '<span style="color:red;">{}</span>'
            warningFormat = '<span style="color:orange;">{}</span>'
            validFormat = '<span style="color:green;">{}</span>'
            normalFormat = '<span style="color:black;">{}</span>'

            if stripped != "":
                mess_type = stripped.split(":")[0]
                if mess_type == 'INFO':
                    self.consoleOutput.append(normalFormat.format(stripped))
                elif mess_type == 'ERROR':
                    self.consoleOutput.append(errorFormat.format(stripped))
                elif mess_type == 'WARNING':
                    self.consoleOutput.append(warningFormat.format(stripped))
                self.consoleOutput.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def write(self, string):
        """Write output to the console text area in a thread-safe way.  Qt only allows
        calls from the main thread, but the service routines run on separate threads."""
        self.console_queue.put(string)

    def enable_console_logging(self):
        # get the root logger to receive all logging traffic
        logger = logging.getLogger()
        # create a logging handler which writes to the console window via self.write
        handler = logging.StreamHandler(self)
        handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s: %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        handler.setLevel(logging.INFO)
        self._handler = handler
        log.info("Enabled logging in console window.")

    def disable_console_logging(self):
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None

    def app_is_exiting(self):
        if self.main is None:
            self.pico.close()  # close serial port
        self.disable_console_logging()

    def closeEvent(self, event):
        self.log.info("Received window close event.")
        self.app_is_exiting()
        super(GuiLaser, self).closeEvent(event)


def calculate_r_squared(y_true, y_pred):
    """
    Calculate R-squared value.
    Parameters:
    - y_true: array-like, the true values
    - y_pred: array-like, the predicted values
    Returns:
    - r_squared: float, R-squared value
    """
    # Calculate mean of true values
    mean_y_true = np.mean(y_true)
    # Calculate total sum of squares
    ss_total = np.sum((y_true - mean_y_true) ** 2)
    # Calculate residual sum of squares
    ss_residual = np.sum((y_true - y_pred) ** 2)
    # Calculate R-squared value
    r_squared = 1 - (ss_residual / ss_total)
    return r_squared


def start_gui():
    app = QApplication([])
    win = GuiLaser()
    win.show()
    app.exec()


if __name__ == '__main__':
    logging.info('Starting via __main__')
    sys.exit(start_gui())
