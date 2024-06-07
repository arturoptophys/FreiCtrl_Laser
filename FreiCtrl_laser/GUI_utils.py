import logging, queue
from enum import IntEnum
from pathlib import Path
from PyQt6 import QtSerialPort
from PyQt6.QtWidgets import QMessageBox, QDialog, QTreeWidgetItem
from PyQt6.QtCore import QObject, pyqtSignal, QIODevice, pyqtSlot
from PyQt6 import uic, QtGui

import datetime


class AbbrevSide(IntEnum):
    C = 0
    R = 1
    L = 2


class FullSide(IntEnum):
    Central = 0
    Right = 1
    Left = 2


def convert_tomillis(time: (int, float)) -> int:
    return int(time * 1000)


def convert_frommillis(time: (int), toint=False) -> (float, int):
    if toint:
        return time // 1000
    else:
        return time / 1000


class InfoDialog(QMessageBox):
    """
    Error Dialog
    """

    def __init__(self, message):
        super().__init__()
        replace_messagebox = QMessageBox.information(
            self,
            "Info",
            "%s" % message,
            buttons=QMessageBox.StandardButton.Ok)

class SessionDoneDialog(QDialog):
    def __init__(self, main, sess_id: str = 'testSess', trial_nr: int = 0, weight_note: str = 'TV'):
        super(SessionDoneDialog, self).__init__(main)
        self.sess_id = sess_id
        self.log = logging.getLogger(f'SessionDoneDialog')
        self.log.setLevel(logging.INFO)
        self.path2file = Path(__file__)
        uic.loadUi(self.path2file.parent / 'GUI' / 'SessionDone_dialog.ui', self)
        self.SessionId_label.setText(self.sess_id)
        self.WeightNote_plainTextEdit.setPlainText(weight_note)
        self.parent = main
        self.TrialNumber.display(trial_nr)

        self.SaveB.clicked.connect(self.saveSess)
        self.IgnoreB.clicked.connect(self.ignoreSess)
        self.DiscardB.clicked.connect(self.discardSess)

        self.DiscardB.setIcon(QtGui.QIcon("GUI/icons/discard.svg"))
        self.SaveB.setIcon(QtGui.QIcon("GUI/icons/pushDB.svg"))
        self.IgnoreB.setIcon(QtGui.QIcon("GUI/icons/bug.svg"))

        if datetime.date.today().weekday() == 4:  #ITS friday
            self.checkBox.setChecked(True)
        else:
            self.checkBox.setChecked(False)

        #self.WeightNote_plainTextEdit.clear()

        #self.WeightNote_plainTextEdit.setText("Training")

    def saveSess(self):
        weight = self.AnimalWeightSpin.value()
        weight_note = self.WeightNote_plainTextEdit.toPlainText()
        sess_note = self.SessNote_plainTextEdit.toPlainText()
        if self.checkBox.isChecked():
            try:
                qtime = self.ZWRtimeEdit.time()
                today = datetime.date.today()
                time = datetime.time(qtime.hour(), qtime.minute(), qtime.second())
                zwd = datetime.datetime.combine(today, time)
            except Exception as e:  # just in case there is a bug
                print(e)
                zwd = None
        else:
            zwd = None
        self.parent.pushSession2DB(self.sess_id, weight, weight_note, sess_note, zwd=zwd)
        self.close()

    def ignoreSess(self):
        self.close()

    def discardSess(self):
        self.parent.discardSess(self.sess_id)
        self.close()


class StageDialog(QDialog):
    def __init__(self, main, version: (str, int) = '0', stage: str = ""):
        super(StageDialog, self).__init__(main)
        self.log = logging.getLogger('StageWindow')
        self.log.setLevel(logging.INFO)
        self.path2file = Path(__file__)
        uic.loadUi(self.path2file.parent / 'GUI' / 'Stage_dialog.ui', self)
        if isinstance(version, int):
            version = str(version)
        self.VersionNr.setText(version)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.was_accepted = False
        self.main = main


        if stage:
            self.label.setText("Create a new version with current parameters?\nfor the stage")
            self.StageName_lineEdit.setText(stage)
            self.StageName_lineEdit.setReadOnly(True)
            self.label_2.setText("Description of changes to previous version:")
            self.StageStates_plainTextEdit.deleteLater()
            self.label_5.deleteLater()

    def get_data(self):
        self.stage_name = self.StageName_lineEdit.text()
        self.description = self.StageDesc_plainTextEdit.toPlainText()
        self.states = self.StageStates_plainTextEdit.toPlainText()

    def accept(self):
        self.get_data()
        self.was_accepted = True
        super().accept()

    def reject(self):
        self.was_accepted = False
        super().reject()


class QtPicoSerial(QObject):
    """Class to manage a serial connection to a CircuitPython sketch using Qt
    QSerialPort object for data transport.  The data protocol is based on lines
    of text."""

    # class variable with Qt signal used to communicate between background thread and serial port thread
    _threadedWrite = pyqtSignal(bytes, name='threadedWrite')

    def __init__(self, main, comm=None):
        super(QtPicoSerial, self).__init__()
        self._portname = None
        self._buffer = b''
        self._port = None
        self.log = logging.getLogger('pico')
        # self.log.setLevel(logging.INFO)
        self.log.setLevel(logging.DEBUG)
        self.main = main
        self.comm = comm

    def is_open(self):
        return self._port is not None

    @staticmethod
    def available_ports():
        """Return a list of names of available serial ports."""
        return [port.portName() for port in QtSerialPort.QSerialPortInfo.availablePorts()]

    def set_port(self, name):
        self._portname = name

    def open(self):
        """Open the serial port and initialize communications.  If the port is already
        open, this will close it first.  If the current name is None, this will not open
        anything.  Returns True if the port is open, else False."""
        if self._port is not None:
            self.close()

        if self._portname is None:
            self.log.debug("No port name provided so not opening port.")
            return False
        # todo add open and close of the port using pyserial.. soe weird is happening on windoof
        self._port = QtSerialPort.QSerialPort()
        self._port.setBaudRate(115200)
        self._port.setPortName(self._portname)

        # open the serial port
        if self._port.open(QIODevice.OpenModeFlag.ReadWrite):
            self.log.info("Opened serial port %s", self._port.portName())
            # always process data as it becomes available
            self._port.readyRead.connect(self.read_input)

            # initialize the slot used to receive data from background threads
            self._threadedWrite.connect(self._data_send)
            self._port.clear(QtSerialPort.QSerialPort.Direction.AllDirections)  # Clear queues on connection
            return True

        else:
            # Error codes: https://doc.qt.io/qt-5/qserialport.html#SerialPortError-enum
            errcode = self._port.error()
            if errcode == QtSerialPort.QSerialPort.SerialPortError.PermissionError:
                self.log.warning(
                    "Failed to open serial port %s with a QSerialPort PermissionError, which could involve an already running control process, a stale lock file, or dialout group permissions.",
                    self._port.portName())
            else:
                self.log.warning("Failed to open serial port %s with a QSerialPort error code %d.",
                                 self._port.portName(), errcode)
            self._port = None
            return False

    def set_and_open_port(self, name):
        # import serial
        # ser = serial.Serial(name)
        # ser.flush()
        # ser.close()
        # del ser
        self.set_port(name)
        self.open()

    def close(self):
        """Shut down the serial connection to the Pico."""
        if self._port is not None:
            self.log.info("Closing serial port %s", self._port.portName())
            self._port.close()
            self._port = None
        return

    def write(self, data):
        if self._port is not None:
            res = self._port.write(data)
            self._port.flush()
            # self.log.debug(f"writen{res} to serial")
        else:
            self.log.error("Serial port not open during write.")

    @pyqtSlot(bytes)
    def _data_send(self, data):
        """Slot to receive serial data on the main thread."""
        self.write(data)

    def thread_safe_write(self, data):
        """Function to receive data to transmit from a background thread, then send it as a signal to a slot on the main thread."""
        self._threadedWrite.emit(data)

    def read_input(self):
        # Read as much input as available; callback from Qt event loop.
        data = self._port.readAll()
        if len(data) > 0:
            self.data_received(data)
        else:
            logging.debug("no data received")
        return

    def _parse_serial_input(self, data):
        # parse a single line of status input provided as a bytestring
        tokens = data.split()
        self.log.debug("Received serial data: %s", tokens)
        self.main.pico_data_received(data)
        if self.comm is not None:
            self.comm.pico_data_received(data)

    def data_received(self, data):
        # Manage the possibility of partial reads by appending new data to any previously received partial line.
        # The data arrives as a PyQT5.QtCore.QByteArray.
        self._buffer += bytes(data)

        # Process all complete newline-terminated lines.
        while b'\n' in self._buffer:
            first, self._buffer = self._buffer.split(b'\n', 1)
            first = first.rstrip()
            self._parse_serial_input(first)

    def send(self, string):
        self.log.debug("Sending to serial port: %s", string)
        self.write(string.encode() + b'\n')


def populate_tree(tree_widget, data, parent_item=None):
    for key, value in data.items():
        if isinstance(value, dict):
            # If the value is a dictionary, create a new top-level item
            item = QTreeWidgetItem(tree_widget if parent_item is None else parent_item)
            item.setText(0, str(key))
            populate_tree(tree_widget, value, item)  # Recursively populate the sub-dictionary
        else:
            # If the value is not a dictionary, create a child item
            item = QTreeWidgetItem(parent_item if parent_item is not None else tree_widget)
            item.setText(0, str(key))
            item.setText(1, str(value))


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    myapp = StageDialog(None, stage="test")
    myapp.show()
    app.exec()
    print(myapp.buttonBox)
    # print which button was clicked
    # print(myapp.buttonClicked)
