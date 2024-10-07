import math
import shutil
import socket
import sys
import itertools
import time
from threading import Thread, Event
from queue import Queue, PriorityQueue
import logging

from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QRect

from PyQt6 import uic, QtGui

from pathlib import Path
from luxx_communication import LaserModule

log = logging.getLogger('main')
log.setLevel(logging.INFO)

logging.basicConfig(filename='GUI_Omicron.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')
VERSION = "0.1.2"

LASER_MODES = ['Standby', "CW-ACC", "CW-APC", "Analog"]


class MySwitch(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setMinimumWidth(66)
        self.setMinimumHeight(60)

    def paintEvent(self, event):
        label = "ON" if self.isChecked() else "OFF"
        bg_color = Qt.GlobalColor.green if self.isChecked() else Qt.GlobalColor.red

        radius = 10
        width = 42
        center = self.rect().center()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.translate(center)
        painter.setBrush(QtGui.QColor(0, 0, 0))

        pen = QtGui.QPen(Qt.GlobalColor.black)
        pen.setWidth(2)
        painter.setPen(pen)

        painter.drawRoundedRect(QRect(-width, -radius, 2 * width, 2 * radius), radius, radius)

        if self.isEnabled():
            painter.setBrush(QtGui.QBrush(bg_color))
        else:
            # Set gray color if the button is disabled
            painter.setBrush(QtGui.QBrush(Qt.GlobalColor.gray))

        sw_rect = QRect(-radius, -radius, width + radius, 2 * radius)
        if not self.isChecked():
            sw_rect.moveLeft(-width)
        painter.drawRoundedRect(sw_rect, radius, radius)
        painter.drawText(sw_rect, Qt.AlignmentFlag.AlignCenter, label)

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.repaint()


class SerialWorker(QThread):
    command_signal = pyqtSignal(tuple)  # Signal for sending commands
    response_signal = pyqtSignal(str)  # Signal for receiving responses

    def __init__(self, laser, laser_idx, queu: Queue, parent=None):
        super(SerialWorker, self).__init__(parent)
        self.is_busy = False  # Flag to track command execution status
        self.laser = laser  # the laser we are communicating with
        self.queu = queu
        self.idx = laser_idx

    def run(self):
        while True:
            if not self.queu.empty():
                command = self.queu.get_nowait()
                # print(command)
                # print(f"Received command {command[1]} with params {command[2]}")

                if command[1] == 'Mode':
                    response = self.laser.set_mode(command[2])
                elif command[1] == 'AMode':
                    response = self.laser.get_mode()
                elif command[1] == 'OnState':
                    if command[2]:
                        response = self.laser.start()
                    else:
                        response = self.laser.stop()

                elif command[1] == 'POnState':
                    if command[2]:
                        response = self.laser.turn_power_on()
                    else:
                        response = self.laser.turn_power_off()

                elif command[1] == 'CPower':
                    response = self.laser.get_emitted_power()

                elif command[1] == 'Power':
                    response = self.laser.set_power(command[2])

                elif command[1] == 'Status':
                    self.laser.get_status_mine()
                    response = (f"{self.laser.status['powered']}/{self.laser.status['on state']}/"
                                f"{self.laser.status['preheat']}/{self.laser.status['interlock']}")
                else:
                    continue
                response = f"{self.idx}_{command[1]}_{response}"
                # time.sleep(2)
                # print(response)
                # response = "Response from device"
                self.response_signal.emit(response)


class GUI_Omicron(QMainWindow):
    def __init__(self, main=None, laser_module=None):
        super(GUI_Omicron, self).__init__()
        self.value = False
        self.serial_workers = []
        self.main = main

        self.path2file = Path(__file__)
        uic.loadUi(self.path2file.parent / 'GUI' / 'laser_controllerGUI.ui', self)
        self.setWindowTitle('OmicronController v.%s' % VERSION)
        self.log = logging.getLogger('GUI')
        self.laser_module = laser_module


        self.message_queu_1 = PriorityQueue(0)
        self.message_queu_2 = PriorityQueue(0)
        self.message_queu_3 = PriorityQueue(0)
        self.message_queu_4 = PriorityQueue(0)

        self.on_switches = [self.OnSwitch_1, self.OnSwitch_2, self.OnSwitch_3, self.OnSwitch_4]
        self.poweron_switches = [self.PowerOnSwitch_1, self.PowerOnSwitch_2, self.PowerOnSwitch_3, self.PowerOnSwitch_4]
        self.message_queus = [self.message_queu_1, self.message_queu_2, self.message_queu_3, self.message_queu_4]
        self.mode_combos = [self.ModecomboBox_1, self.ModecomboBox_2, self.ModecomboBox_3, self.ModecomboBox_4]
        self.power_sliders = [self.power_dial_1, self.power_dial_2, self.power_dial_3, self.power_dial_4]
        self.power_spins = [self.PowerSpinBox_1, self.PowerSpinBox_2, self.PowerSpinBox_3, self.PowerSpinBox_4]
        self.laser_labels = [self.SpecLaserslabel_1, self.SpecLaserslabel_2, self.SpecLaserslabel_3,
                             self.SpecLaserslabel_4]
        self.status_labels = [self.interlock_label_1, self.interlock_label_2, self.interlock_label_3,
                              self.interlock_label_4]
        self.lcds = [self.CurrentPowerlcdNumber_1, self.CurrentPowerlcdNumber_2, self.CurrentPowerlcdNumber_3,
                     self.CurrentPowerlcdNumber_4]
        self.power_gauges =[self.power_gauge_1, self.power_gauge_2, self.power_gauge_3,self.power_gauge_4]

        self.laser_connection = [False, False, False, False]

        self.ConnectSignals()
        if self.laser_module is None:
            self.scan_ports()
        else:
            self.set_passed_lasers()

        self.cpower_timer = QTimer()
        self.cpower_timer.timeout.connect(self.ask_emmited_power)
        self.cpower_timer.start(1000)  # units are milliseconds

        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.ask_status)
        self.status_timer.start(4000)  # units are milliseconds

        self.mode_timer = QTimer()
        self.mode_timer.timeout.connect(self.ask_mode)
        self.mode_timer.start(5000)  # units are milliseconds

        self.power_gauge_1.setGaugeTheme(21)
        self.power_gauge_2.setGaugeTheme(19)
        self.power_gauge_3.setGaugeTheme(12)
        # self.power_gauge_3.setGaugeTheme(15)
        self.power_gauge_4.setGaugeTheme("red")

    def ask_mode(self):
        for q, conn in zip(self.message_queus, self.laser_connection):
            if conn:
                q.put((11, 'AMode', True))

    def ask_status(self):
        for switch, q, conn in zip(self.on_switches, self.message_queus, self.laser_connection):
            if conn:
                q.put((5, 'Status', True))

    def ask_emmited_power(self):
        for switch, q, conn in zip(self.on_switches, self.message_queus, self.laser_connection):
            if conn and switch.isChecked():
                q.put((10, 'CPower', True))

    def handle_response(self, response):
        sender = int(response.split("_")[0])
        if response.split("_").pop() == 'x':
            self.log.error('last command returned an error !')
        elif response.split("_").pop() == '>':
            print('worked')
        if response.split("_")[1] == 'CPower':
            # print(f'EmittedPower {response.split("_")[1]}')
            try:
                self.lcds[sender].display(response.split("_")[2])
                self.power_gauges[sender].updateValue(float(response.split("_")[2]))
            except TypeError:
                pass
            except IndexError:
                pass
        elif response.split("_")[1] == "Status":
            status = response.split("_").pop().split('/')
            if status[0] == 'False':
                self.set_off(sender)
            elif status[-2] == 'True':
                self.set_preheat(sender)
            elif status[-3] == 'True':
                self.set_on(sender)
            else:
                self.set_ready(sender)
            if status[-1] == 'True':
                self.set_interlock(sender)
            self.on_switches[sender].blockSignals(True)
            self.poweron_switches[sender].blockSignals(True)
            self.on_switches[sender].setChecked(status[-3] == "True")
            self.poweron_switches[sender].setChecked(status[-4] == "True")
            self.on_switches[sender].blockSignals(False)
            self.poweron_switches[sender].blockSignals(False)

        elif response.split("_")[1] == "AMode":
            mode = response.split('_')[-1]
            self.mode_combos[sender].setCurrentText(mode)

    def ConnectSignals(self):
        for combo in self.mode_combos:
            combo.addItems(LASER_MODES)
        self.ScanB.clicked.connect(self.scan_ports)

        for slider in self.on_switches:
            slider.toggled.connect(self.toggle_laser)

        for slider in self.poweron_switches:
            slider.toggled.connect(self.toggle_laserpower)

        for combo in self.mode_combos:
            combo.currentIndexChanged.connect(self.change_laser_mode)

        for slider in self.power_spins:
            slider.valueChanged.connect(self.change_power)



    def change_power(self):
        sender = self.sender()
        idx = [idx for idx, slider in enumerate(self.power_spins) if slider == sender][0]
        self.message_queus[idx].put((2, 'Power', self.power_spins[idx].value()))

    def toggle_laserpower(self):
        sender = self.sender()
        idx = [idx for idx, slider in enumerate(self.poweron_switches) if slider == sender][0]
        self.message_queus[idx].put((0, 'POnState', self.poweron_switches[idx].isChecked()))

    def toggle_laser(self):
        sender = self.sender()
        idx = [idx for idx, slider in enumerate(self.on_switches) if slider == sender][0]
        if self.on_switches[idx].isChecked():
            self.message_queus[idx].put((0, 'OnState', True))
        else:
            self.message_queus[idx].put((0, 'OnState', False))

    # TODO do i even need this ? just let it check the queu
    def change_laser_mode(self):
        sender = self.sender()
        idx = [idx for idx, slider in enumerate(self.mode_combos) if slider == sender][0]
        self.message_queus[idx].put((1, 'Mode', self.mode_combos[idx].currentText()))

    def scan_ports(self):
        if self.laser_module is not None:
            del self.laser_module
        self.laser_module = LaserModule()
        self.foundLaserslabel.setText(f'Found {len(self.laser_module.lasers)} Lasers')

        # iterate over lasers
        for idx, wave in enumerate([405, 473, 594, 647]):
            for laser in self.laser_module.lasers:
                if laser.wavelength == wave:
                    break
            else:
                laser = None
            self.set_laser(idx, laser)

    def set_passed_lasers(self):
        self.foundLaserslabel.setText(f'Found {len(self.laser_module.lasers)} Lasers')
        # iterate over lasers
        for idx, wave in enumerate([405, 473, 594, 647]):
            for laser in self.laser_module.lasers:
                if laser.wavelength == wave:
                    break
            else:
                laser = None
            self.set_laser(idx, laser)

    def set_laser(self, idx, laser=None):
        if laser is None:
            self.laser_labels[idx].setText(f"Not Connected")
            self.mode_combos[idx].setDisabled(True)
            self.power_sliders[idx].setDisabled(True)
            self.laser_connection[idx] = False
            self.on_switches[idx].setDisabled(True)
            self.status_labels[idx].setText('OFF')
            self.power_spins[idx].setDisabled(True)
            self.poweron_switches[idx].setDisabled(True)
            self.power_gauges[idx].setOff()
        else:
            self.laser_connection[idx] = True
            self.laser_labels[idx].setText(f"{laser}")

            self.mode_combos[idx].blockSignals(True)
            self.mode_combos[idx].setCurrentText(self.laser_module.lasers[0].get_mode())
            self.mode_combos[idx].blockSignals(False)

            self.poweron_switches[idx].blockSignals(True)
            if laser.status['powered']:
                self.poweron_switches[idx].setChecked(True)
            else:
                self.poweron_switches[idx].setChecked(False)
            self.poweron_switches[idx].blockSignals(False)

            self.on_switches[idx].blockSignals(True)
            if laser.status['on state']:
                self.on_switches[idx].setChecked(True)
            else:
                self.on_switches[idx].setChecked(False)
            self.on_switches[idx].blockSignals(False)

            if laser.status['interlock']:
                self.set_interlock(idx)
            elif laser.status['preheat']:
                self.set_preheat(idx)
            else:
                self.set_ready(idx)

            self.power_sliders[idx].blockSignals(True)
            self.power_spins[idx].blockSignals(True)
            current_power = laser.get_power()
            self.power_sliders[idx].setValue(int(current_power))
            self.power_spins[idx].setValue(int(current_power))
            self.power_sliders[idx].setRange(0, int(laser.pmax))
            self.power_spins[idx].setRange(0, int(laser.pmax))
            self.power_sliders[idx].blockSignals(False)
            self.power_spins[idx].blockSignals(False)

            serial_worker = SerialWorker(laser, idx, self.message_queus[idx])
            serial_worker.response_signal.connect(self.handle_response)
            # or could have handle function for each ?
            # Start the worker thread
            serial_worker.start()
            self.serial_workers.append(serial_worker)

    def set_interlock(self, idx):
        self.status_labels[idx].setText('INTERLOCK !!!')
        self.status_labels[idx].setStyleSheet("QLabel {background-color : red; }")

    def set_on(self, idx):
        self.status_labels[idx].setText('EMITTING')
        self.status_labels[idx].setStyleSheet("QLabel {color : green; }")

    def set_off(self, idx):
        self.status_labels[idx].setText('OFF')
        self.status_labels[idx].setStyleSheet("QLabel {color : black; }")

    def set_preheat(self, idx):
        self.status_labels[idx].setText('Preheating')
        self.status_labels[idx].setStyleSheet("QLabel {color : yellow; }")

    def set_ready(self, idx):
        self.status_labels[idx].setText('Ready')
        self.status_labels[idx].setStyleSheet("QLabel {color : blue; }")

    def app_is_exiting(self):
        self.cpower_timer.stop()
        self.status_timer.stop()
        self.mode_timer.stop()
        #empty Qs
        self.message_queu_1.empty()
        self.message_queu_2.empty()
        self.message_queu_3.empty()
        self.message_queu_4.empty()
        self.laser_module.turn_off_lasers() # make sure laser is Off!
        del self.laser_module

    def closeEvent(self, event):
        self.log.info("Received window close event.")
        if sum([slider.isChecked() for slider in self.on_switches]) > 0:
            self.log.info("Turn off lasers first !")
            event.ignore()
            return
        self.app_is_exiting()
        super(GUI_Omicron, self).closeEvent(event)


def start_gui():
    app = QApplication([])
    win = GUI_Omicron()
    win.show()
    app.exec()


if __name__ == '__main__':
    logging.info('Starting via __main__')
    sys.exit(start_gui())
