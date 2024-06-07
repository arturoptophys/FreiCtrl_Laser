# this code is a starting point for the host-application communicating with the CircuitPython
import time
from uuid import UUID

import numpy as np
from pathlib import Path
import json
import serial

import logging

logging.basicConfig(level=logging.INFO)

# from Task_classes import Trial
# get inspiration https://courses.ideate.cmu.edu/16-223/f2021/text/code/pico-remote.html

# json_stream = json.dumps(vars(trial))
# new_dict = json.loads(json_stream)

# ser = serial.Serial('/dev/ttyACM2')  # open serial port

"""
params = TaskParameters().dictionize()
params.update(**{"message_type":"TaskParameters"})

params = json.dumps(params) + "\n"
ser.write(params.encode())
"""


class PythonBoardCommander:
    def __init__(self, ser: serial.Serial):

        self.log = logging.getLogger('PythonBoardComm')
        self.serial = ser
        self.message_type = None
        self.command = None
        self.params = None
        self.gate = None
        self.received = ""
        self.waiting_forecho = False
        self.waiting_forpong = False
        self.params_names = None
        self.mess_in = []
        # self.serial.reset_output_buffer()  # make sure buffers are empty
        # self.serial.reset_input_buffer()

    def clear_message_queu(self):
        self.mess_in = []

    def send_laser_params(self, dictionary: dict):
        dictionary['message_type'] = "LaserParams"
        self.serial.write(f'{json.dumps(dictionary)}\n'.encode('utf-8'))

    def send_task_params(self, dictionary: dict):
        self.message_type = "TaskParameters"
        self.params_names = dictionary.keys()
        self.__dict__.update(**dictionary)
        self.log.info('Sending Task parameters')
        self.send_command()

    def send_StartTask(self):
        self.message_type = "StartTask"
        self.log.info('Sending Task Start Command')
        self.send_command()
        # if not self.send_command():
        #    logging.warning('Start Command was not echoed! Check if Task started')

    def send_EndTask(self):
        self.message_type = "EndTask"
        self.log.info('Sending End Task Command')
        self.send_command()

    def ask_dummy_trial(self):
        self.message_type = "AskTrial"
        self.send_command()
        self.log.info("Asking for dummy trial data")

    def ask_params(self):
        self.message_type = "AskTask"
        self.send_command()
        self.log.info("Asking for task params data")

    def reset_board(self):
        self.message_type = "ResetBoard"
        self.send_command()
        self.log.info("resetting board")

    def initialize_box(self):
        self.message_type = "ResetBox"
        self.send_command()
        self.log.info("Initializing Box")

    def exit_debug(self):
        self.message_type = "ExitDebug"
        self.send_command()
        self.log.info("Exiting Debug")

    def test_startSignal(self):
        self.message_type = "SendStartPul"
        self.send_command()
        self.log.info("Asked to send trial start pulses")

    def PingCircuitPython(self):  # not really needed if i echo commands...
        self.message_type = "Ping"
        self.send_command()
        self.log.debug("send ping")
        self.waiting_forpong = True

    def ToggleLED(self, gate: str, value: bool):
        self.message_type = "SwitchLED"
        if value:
            self.command = 'turn_on'
        else:
            self.command = 'turn_off'
        self.gate = gate
        self.send_command()

    def STOPMove(self):
        self.message_type = "MoveArm"
        self.command = 'stopMotors'
        self.send_command()

    def MoveArmR(self, value: float):
        self.message_type = "MoveArm"
        self.command = 'moveArmR'
        self.params = value
        self.send_command()

    def MoveArmL(self, value: float):
        self.message_type = "MoveArm"
        self.command = 'moveArmL'
        self.params = value
        self.send_command()

    def AskAngles(self):
        self.message_type = "MoveArm"
        self.command = 'askAngles'
        self.send_command()

    def MoveGate(self, gate: str, state: bool):
        self.message_type = "MoveGate"
        if state:
            self.command = 'open_gate'
        else:
            self.command = 'close_gate'
        self.gate = gate
        self.send_command()

    def MoveServo(self, gate: str, value: int):
        self.message_type = "MoveGate"
        self.command = 'move_gate_fast'
        self.gate = gate
        self.params = value
        self.send_command()

    def PlayRewardSound(self):
        self.log.info("playing reward sound")
        self.message_type = "PlaySound"
        self.command = 'play'
        self.gate = 'reward'
        self.send_command()

    def PlayErrorSound(self):
        self.log.info("playing error sound")
        self.message_type = "PlaySound"
        self.command = 'play'
        self.gate = 'noise'
        self.send_command()

    def GiveReward(self, value: int = None):
        self.log.info("Giving reward")
        self.message_type = "GiveReward"
        self.command = 'give_reward'
        self.params = value
        self.send_command()

    def RewardPumpToggle(self, state: bool):
        self.log.info("Toggling Reward Pump")
        self.message_type = "GiveReward"
        if state:
            self.command = 'open_valve'
        else:
            self.command = 'close_valve'
        self.send_command()

    def ToggleCameraTriggers(self, fps: int, state: bool):
        self.log.info("Toggling camera Triggers")
        self.message_type = "CameraTrigger"
        if state:
            self.command = 'startPulsing'
            self.params = fps
        else:
            self.command = 'stopPulsing'
        self.send_command()

    def PingArduino(self):
        self.log.info("Pinging Arduino")
        self.message_type = "PingArduino"
        self.command = 'pingSlave'
        self.send_command()

    def PollBeamBlockes(self):
        self.log.info("PollingBeamBlocks")
        self.message_type = "PollBeamBlockers"
        self.command = 'pollBeamblockers'
        self.send_command()

    def RoomLights(self, value: int):
        self.log.info(f"Turning roomlights {'On' if value == 100 else str(value) if value != 0 else 'Off'}")
        self.message_type = "RoomLights"
        self.command = 'dimm_roomlight'
        self.params = value * 255 // 100
        self.send_command()

    def send_ctrlc(self):
        """ writes ctrl c character to serial """
        self.serial.write(b"\x03")
        # tODO write this to the other serial not data

    def send_ctrld(self):
        self.serial.write(b"\x04")

    def get_bytes(self) -> bytes:
        dict2send = vars(self).copy()
        dict2send.pop('serial', None)
        dict2send.pop('log', None)
        dict2send.pop('received', None)
        dict2send.pop('waiting_forecho', None)
        dict2send.pop('waiting_forpong', None)
        dict2send.pop('mess_in', None)
        dict2send.pop('params_names', None)
        return f'{json.dumps(dict2send)}\n'.encode('utf-8')

    def send_command(self):
        message2send = self.get_bytes()
        self.mess_in.append(message2send)
        # self.serial.write(mess_in)
        self.serial.write(message2send)
        # replace with send
        self.waiting_forecho = True
        # mess_out = self.serial.readline()
        # self.serial.read_input()
        # replace with self.serial.read_input()

    def pico_data_received(self, payload):
        """Process a message from the Pico."""
        self.log.debug("Received: %s", payload.decode())
        self.received = payload.decode()
        # TODO Problem if we send more then one message before aknowledging it, it contains previos params.
        # strip params direktly after sending and not after aknowledgement ?
        if self.waiting_forecho:
            for m_id, message in enumerate(self.mess_in):  # look through messages we await echo from.
                if message.rstrip() == payload:
                    self.log.debug(f"Successfull transmission {m_id + 1} out of {len(self.mess_in)}")
                    self.message_type = None
                    self.command = None
                    self.params = None
                    self.gate = None
                    if self.params_names is not None:
                        for name in self.params_names:
                            delattr(self, name)  # purge params from self to not be resend
                        print(self.__dict__)
                        self.params_names = None
                    self.mess_in.pop(m_id)  # remove message from list
                    if len(self.mess_in) == 0:  # waiting list is empty
                        self.waiting_forecho = False
                    break
            else:  # went throu all but not found
                self.log.info("Echo not equal input !")
        elif self.waiting_forpong:
            self.waiting_forpong = False
            if self.received == 'Pong':
                self.log.info(f'Board on {self.serial._port.portName()} responded to ping')


import csv
import json
import logging
from pathlib import Path
from datetime import datetime


class DataWriter:
    """Class for writing data received from serial to csv and JSON file
    data arrives per trial and is written as individual row"""

    def __init__(self, session_id: str, path2save: (str, Path) = None, write_csv: bool = False):
        self.log = logging.getLogger('DataWriter')
        self.log.setLevel('DEBUG')
        self.session_id = session_id
        if path2save is None:
            prepath = Path('data')
        else:
            prepath = Path(path2save)
        prepath.mkdir(parents=True, exist_ok=True)
        self.file_name = prepath / f'{self.session_id}_behav.csv'
        self.json_file = self.file_name.parent / f"{self.file_name.name.split('.')[0]}.json"

        self.header_written = False  # flag to check if header was written
        # here one can define the sorting in the csv!
        self.fieldnames = ['trial_nr', "trial_start_absolute", "trial_end_absolute", "duration", "outcome", "choice",
                           "hit", "omission", "error",
                           "nose_poke_timingC", "NP_exitC", 'nose_poke_durationC', "nosepoke_SETdur_C",
                           "nose_poke_timingR", "NP_exitR", 'nose_poke_durationR', "nosepoke_SETdur_R",
                           "nose_poke_timingL", "NP_exitL", 'nose_poke_durationL', "nosepoke_SETdur_L",
                           "time_to_NPd", "time_to_NPc",
                           "gate_openedC", "gate_closedC", "gate_openedR", "gate_closedR", "gate_openedL",
                           "gate_closedL", "angle_R", "angle_L", "reward_prob_C", "reward_prob_R", "reward_prob_L",
                           "reward_pump_on", "reward_pump_off", "lick_start", "time_to_lick", "tone_on", "tone_off",
                           "tone_dur",
                           "tone_type", "LED_C_on", "LED_C_off", "LED_R_on", "LED_R_off", "LED_L_on", "LED_L_off",
                           "trial_sync_pulse"]

        self.task = None
        self.trial_counter = 0
        self.error_counter = 0
        self.hit_counter = 0
        self.omission_counter = 0
        self.miss_counter = 0
        self.right_counter = 0
        self.left_counter = 0
        self.lr_balance = RunningAverage(5)
        self.np_duration = RunningAverage(5)
        self.motivation_counter = RunningAverage(10)
        self.laser_counter = 0
        self.write_csv = write_csv  # whether or not to have a csv copy of the trial data

    def injest_task(self, task: dict):
        """get a dictionary from GUI writes the params to Json"""
        self.task = task
        # self.task.update(**{'session_id': self.session_id})
        self.task['session_id'] = self.session_id
        self.task['trials'] = list()
        self.task['motortimes'] = list()
        self.writeJSON()

    def injest_trial(self, trial: dict, do_additional_math: bool = True):
        """
        gets a trial dictionary, writes to csv and to json
        """
        if self.task is None:
            self.log.error('No task was passed!, saving only trial info')
            self.task = {'session_id': self.session_id, 'trials': list()}
        self.trial_counter += 1
        if trial['trial_nr'] != self.trial_counter:
            self.log.warning('Trial counter host/remote do not correspond !')
        try:
            trial = self.make_trial_math(trial)  # add some additional info to the trial
        except TypeError as e:
            self.log.error(e)
        if self.write_csv:
            self.writeTrial(trial)  # append trial to csv
        self.task['trials'].append(trial)
        self.writeJSON()
        if trial['outcome'] == 'omission':
            self.omission_counter += 1
        elif trial['outcome'] == 'error':
            self.error_counter += 1
        elif trial['outcome'] == 'hit' or trial['reward_pump_on']:
            self.hit_counter += 1
        elif trial['outcome'] == 'miss':
            self.miss_counter += 1

        if trial['outcome'] == 'omission':
            self.motivation_counter.add_value(1)
        else:
            self.motivation_counter.add_value(0)
        # self.log.info(f'Current mot counter{ self.motivation_counter.moving_sum}')
        if trial['nose_poke_timingR'] is not None:
            self.right_counter += 1
            self.np_duration.add_value(trial['nose_poke_durationR'])
            self.lr_balance.add_value(1)
            side = "right"
        elif trial['nose_poke_timingL'] is not None:
            self.left_counter += 1
            self.np_duration.add_value(trial['nose_poke_durationL'])
            self.lr_balance.add_value(-1)
            side = "left"
        else:
            side = "None"
            self.np_duration.add_value(np.nan)
            self.lr_balance.add_value(np.nan)
        if trial.get("laser_trigger_time") is not None:
            if not trial.get("laser_params", True).get("trigger1", True).get('mock', True):
                self.laser_counter += 1

        self.log.info(f"Received trial {trial['trial_nr']} with {trial['outcome']} at {side}")

    def injest_motortimes(self, motor_time: list):
        self.task['motortimes'] = motor_time
        self.writeJSON()

    def make_trial_math(self, dict_trial: dict) -> dict:
        """modify the trial dictionary with some more calculated values"""
        mod_dict_trial = dict_trial.copy()

        # calculate the duration of the trial
        mod_dict_trial["duration"] = mod_dict_trial["trial_end_absolute"] - mod_dict_trial["trial_start_absolute"]

        # NP timing from the gate being open
        if mod_dict_trial['nose_poke_timingR'] is not None:
            mod_dict_trial['time_to_NPd'] = mod_dict_trial['nose_poke_timingR'] - mod_dict_trial[
                'gate_openedR']
        elif mod_dict_trial['nose_poke_timingL'] is not None:
            mod_dict_trial['time_to_NPd'] = mod_dict_trial['nose_poke_timingL'] - mod_dict_trial[
                'gate_openedL']
        else:
            mod_dict_trial['time_to_NPd'] = None

        # NP timing for central_port
        if mod_dict_trial['nose_poke_timingC'] is not None:
            mod_dict_trial['time_to_NPc'] = mod_dict_trial['nose_poke_timingC'] - mod_dict_trial[
                'gate_openedC']
        else:
            mod_dict_trial['time_to_NPc'] = None

        # timing to reward
        # use hit time instead ?
        if mod_dict_trial['lick_start'] is not None and mod_dict_trial['hit'] is not None:
            mod_dict_trial['time_to_lick'] = mod_dict_trial['lick_start'] - mod_dict_trial['hit']
        else:
            mod_dict_trial['time_to_lick'] = None

        # Choise
        if mod_dict_trial['nose_poke_timingR'] is not None:
            mod_dict_trial['choice'] = "right"
        elif mod_dict_trial['nose_poke_timingL'] is not None:
            mod_dict_trial['choice'] = "left"
        else:
            mod_dict_trial['choice'] = "None"

        # tone duration
        if mod_dict_trial['tone_on'] is not None and mod_dict_trial['tone_off'] is not None:
            mod_dict_trial['tone_dur'] = mod_dict_trial['tone_off'] - mod_dict_trial['tone_on']
        else:
            mod_dict_trial['tone_dur'] = None

        # Nosepoke exit
        if mod_dict_trial['nose_poke_timingR'] is not None:
            mod_dict_trial['NP_exitR'] = mod_dict_trial['nose_poke_timingR'] + mod_dict_trial['nose_poke_durationR']
        else:
            mod_dict_trial['NP_exitR'] = None

        if mod_dict_trial['nose_poke_timingL'] is not None:
            mod_dict_trial['NP_exitL'] = mod_dict_trial['nose_poke_timingL'] + mod_dict_trial['nose_poke_durationL']
        else:
            mod_dict_trial['NP_exitL'] = None

        # NosepokeC exit
        if mod_dict_trial['nose_poke_timingC'] is not None:
            mod_dict_trial['NP_exitC'] = mod_dict_trial['nose_poke_timingC'] + mod_dict_trial['nose_poke_durationC']
        else:
            mod_dict_trial['NP_exitC'] = None

        return mod_dict_trial

    def writeJSON(self):
        """Write global parameters as json
        input is Task.strip_parameters(return_global = True) """
        # header.update(**{'datetime': datetime.now().strftime('%Y%m%d_%H%M')})
        with open(self.json_file, 'w') as fi:
            json.dump(self.task, fi, indent=4, sort_keys=True)

    def writeTrial(self, trial: dict):
        """write a  dict representing Information about a single Trial to file"""
        with open(self.file_name, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.fieldnames, extrasaction='ignore')
            self.log.debug(f"Opened {self.file_name} for writing")
            if not self.header_written:
                writer.writeheader()
                self.header_written = True
            writer.writerow(trial)
        self.log.debug(f"Written trial {trial['trial_nr']} to file")

    def copyCSV(self, target_path: Path):
        """
        copy files to specified path, To be called from GUI with DB knowledge
        """
        # TODO trow an error if files not exist !
        import shutil
        try:
            shutil.copy2(self.file_name, target_path)
        except FileNotFoundError:
            pass
        shutil.copy2(self.json_file, target_path)
        self.log.info(f"Copied {self.file_name.name} to {target_path.as_posix()}")

    def purgeFiles(self):
        """delete created files, in case of early abort"""
        self.json_file.unlink()
        self.file_name.unlink()
        self.log.info(f"Deleted {self.file_name.name}.")


import hashlib
import uuid


def dict_to_uuid(key: dict):
    """Given a dictionary `key`, returns a hash string as UUID
    Args:
        key (dict): Any python dictionary"""
    hashed = hashlib.md5()
    for k, v in sorted(key.items()):
        hashed.update(str(k).encode())
        hashed.update(str(v).encode())
    return uuid.UUID(hex=hashed.hexdigest())


from collections import namedtuple

Stage_params = namedtuple('stage_tuple', "stage_name,params,stage_description")
Version_params = namedtuple('version_tuple', "version,stages_list")
"""
from Task_parameters import TaskParameters
params = TaskParameters().dictionize()
NP_init = Stage_params("NP_init",params,'Initial stage, whereby the animal learns to interact with the nose poke.')
ver0 = Version_params(0,[NP_init])
"""


class HostsideParamsOld:
    def __init__(self, path2json: (str, Path) = "params.json"):
        self.all_params = None
        self.path2json = path2json
        self.log = logging.getLogger('ParameterCommander')
        self.log.setLevel(logging.DEBUG)
        self.import_taskParams()
        # self.all_versions()

    def init_from_list(self, all_params: list):
        for v in range(len(all_params)):
            all_params[v] = Version_params._make(all_params[v])
            for st in range(len(all_params[v].stages_list)):
                all_params[v].stages_list[st] = Stage_params._make(all_params[v].stages_list[st])
                all_params[v].stages_list[st].params.update(
                    **{"version": all_params[v].version, "training_stage": all_params[v].stages_list[st].stage_name})
        self.all_params = all_params

    def write_json(self, path2json: (str, Path) = "params.json"):
        with open(path2json, 'w') as fi:
            json.dump(self.all_params, fi, indent=4)

    def modify_params(self, version: int, stage: str, params: dict):
        self.log.debug(f"modifying parameters vor v{version} and stage: {stage}")
        try:
            for v_id in range(len(self.all_params)):
                if self.all_params[v_id].version != version:
                    continue
                for st in range(len(self.all_params[v_id].stages_list)):
                    if self.all_params[v_id].stages_list[st].stage_name != stage:
                        continue
                    self.all_params[v_id].stages_list[st].params.update(**params)
            self.write_json()
        except Exception as e:
            self.log.warning(e)

    def import_taskParams(self):
        """reads the parameters json"""
        from collections import namedtuple
        Stage_params = namedtuple('stage_tuple', "stage_name,params")
        Version_params = namedtuple('version_tuple', "version,stages_list")
        try:
            with open(self.path2json, "r") as fi:
                all_params = json.load(fi)
            self.init_from_list(all_params)
        except FileNotFoundError:
            print('No parameter File exists!')
        # for v in range(len(all_params)):
        #     all_params[v] = Version_params._make(all_params[v])
        #     for st in range(len(all_params[v].stages_list)):
        #         all_params[v].stages_list[v] = Stage_params._make(all_params[v].stages_list[v])
        #         all_params[v].stages_list[v].params.update(
        #             **{"version": all_params[v].version, "training_stage": all_params[v].stages_list[v].stage_name})
        # self.all_params = all_params

    def hash_params(self):
        """create a hash of the parameters to check if those already exist"""
        # maybe remove the version number from the hash
        pass

    def all_versions(self) -> list:
        self.versions = [ver.version for ver in self.all_params]
        return self.versions

    def all_stages(self, version: int) -> list:
        """returns all stages in a certain version of parameters_set"""
        stages = list()
        for ver in self.all_params:
            if ver.version != version:
                continue
            for stage in ver.stages_list:
                stages.append(Stage_params._make(stage).stage_name)
        return stages

    def get_params(self, version: int, stage2find: str) -> (dict, None):
        if version not in self.all_versions():
            print(f'Ver.{version} doesnt exist')
            return None
        if stage2find not in self.all_stages(version):
            print(f'Stage {stage2find} doesnt exist in ver.{version}')
            return None
        for ver in self.all_params:
            if ver.version != version:
                continue
            for stage in ver.stages_list:
                stage = Stage_params._make(stage)
                if stage.stage_name != stage2find:
                    continue
                params = stage.params

        return params

    def add_new_stage(self):
        pass

    def add_new_version(self, version, stage, params):

        pass


class HostsideParams:
    def __init__(self, path2json: (str, Path) = "params.json"):
        self.stages = None
        self.versions = None
        self.all_params = {}
        self.path2json = path2json
        self.log = logging.getLogger('ParameterCommander')
        self.log.setLevel(logging.DEBUG)
        self.read_json()
        # self.all_versions()

    def reload_file(self):
        self.read_json()

    def write_json(self, path2json: (str, Path) = "params.json"):
        with open(path2json, 'w') as fi:
            json.dump(self.all_params, fi, indent=4)

    def read_json(self):
        """reads the parameters json"""
        try:
            with open(self.path2json, "r") as fi:
                self.all_params = json.load(fi)
        except FileNotFoundError:
            self.log.warning('No parameter File exists!')
            self.all_params = {}

    def add_new_stage(self, stage_name: str, params: dict, state_discription: str = ""):
        # json.load(state_discription)
        self.all_params[stage_name] = {"version_0": params}
        self.write_json()

    def add_new_version(self, stage: str, params: dict, note: str = "") -> int:
        """adds a new version to the parameters"""
        if stage not in self.all_params.keys():
            self.log.warning(f"stage {stage} doesnt exist")
            return None
        version = len(self.all_params[stage].keys())
        params["note"] = note
        self.all_params[stage][f"version_{version}"] = params
        self.write_json()
        return version

    def modify_params(self, version: int, stage: str, params: dict):
        self.log.debug(f"modifying parameters vor v{version} and stage: {stage}")
        if stage not in self.all_params.keys():
            self.log.warning(f"stage {stage} doesnt exist")
            return
        if f"version_{version}" not in self.all_params[stage].keys():
            self.log.warning(f"version {version} doesnt exist")
            return
        self.all_params[stage][f"version_{version}"].update(**params)
        self.write_json()

    def hash_params(self, params: dict = None, version: int = 0, stage2find: str = "") -> UUID:
        """create a hash of the parameters to check if those already exist"""
        # maybe remove the version number from the hash
        if params is None:
            params = self.get_params(version, stage2find)

        return dict_to_uuid(params)

    def all_versions(self, stage: str) -> list:
        try:
            self.versions = [int(ver.split("_")[-1]) for ver in self.all_params[stage].keys()]
            return self.versions
        except KeyError:
            return []

    def all_stages(self) -> list:
        """returns all stages of parameters_set"""
        stages = list()
        for stage in self.all_params.keys():
            stages.append(stage)
        self.stages = stages
        return stages

    def get_params(self, version: int, stage2find: str) -> (dict, None):
        if stage2find not in self.all_stages():
            self.log.warning(f'Stage {stage2find} doesnt exist in ver.{version}')
            return None
        if version not in self.all_versions(stage2find):
            self.log.warning(f'Ver.{version} doesnt exist')
            return None
        params = self.all_params[stage2find][f"version_{version}"]
        return params


class Session_backupCreator:

    def __init__(self):
        from datastructure_tools.DataBaseAccess import DataBaseAccess
        self.path2datafiles = Path("./data/")
        self.typical_exptype = 'HillYmaze_Training'
        self.DB = DataBaseAccess()
        self.sessions_indb = self.DB.Session.fetch('session_id')
        self.sessions2add = []
        self.go_through_files()

    def fill_session_notinDB(self):
        self.add_session_to_DB()

    def change_animal_nr(self, session_id: str, new_animal: str):
        from datastructure_tools.utils import SessionClass
        import shutil
        assert session_id in self.sessions_indb, f"Session {session_id} not in DB!"
        assert new_animal in self.DB.Animal.fetch('animal_id'), f"Animal {new_animal} not in DB!"
        print(f'Trying to patch {session_id} to be from animal {new_animal}')
        # assert session_id in self.sessions2add, f"Session {session_id} not in files!"
        session = (
                    self.DB.Session.Experiment * self.DB.Session.Root * self.DB.Session.Project * self.DB.Session.User * self.DB.Session & {
                "session_id": session_id}).fetch1()
        session_path = self.DB.server_path / session["session_dir"]
        # self.DB.Session.update1({"session_id": session_id, "animal_id": new_animal})

        new_sessname = "_".join([session_id.split("_")[0], new_animal, session_id.split("_")[-1]])
        # create new session
        session_class = SessionClass(self.DB, animal_id=new_animal, session_datetime=session["session_datetime"],
                                     project=session["project"],
                                     user=session['user'], expName=session["experiment_name"],
                                     experiment_template=session['experiment_template'],
                                     session_id=new_sessname,
                                     test=True if new_animal == 'MusterMaus' else False)
        pathcreationSuccess = session_class.createSession_path()  # create Paths on server
        assert pathcreationSuccess, "paths could not be created"
        new_path = self.DB.server_path / session_class.session_dir
        print(f'Created new fodler structure at {new_path}')

        # rename folder
        print(f'renaming{session_path} to {new_path}')
        shutil.move(session_path, new_path)

        # rename files
        for file in new_path.rglob("*"):
            if file.is_file():
                old_name = file.name
                new_name = [old_name.split("_")[0], new_animal]
                new_name.extend(old_name.split("_")[3:])
                new_name = '_'.join(new_name)
                print(f'renaming {old_name} to {new_name}')
                shutil.move(file, file.parent.parent / new_name)

        PushSuccess = session_class.checkInputs()  # checks inputs and pushes to DB

        print(f'Created new Session{new_sessname}')
        if PushSuccess:
            try:
                old_weight = (self.DB.Animal.Weight & {'weight_date': session_class.session_datetime}).fetch1()
                session_class.weight = old_weight['weight']
                session_class.weight_note = old_weight['weight_note']
                session_class.pushWeights()
                print(f'Pushed to DB')
            except Exception:
                print('Could not pull weight from DB! enter manually')
        # delete entry
        print('Deleting wrong entry')
        (self.DB.Session & session).delete()
        # TODO Delete preprocessed and processed files

        # rename session in in the behavior file.  in daq data is still wrongly named!
        try:
            for file in (new_path / 'behav').rglob('*.json'):
                try:
                    with open(file, 'r') as fi:
                        sess_data = json.load(fi)
                except json.decoder.JSONDecodeError:  # not a json
                    sess_data = None
                if sess_data is not None:
                    try:
                        assert sess_data['session_id'] == session_id
                        sess_data['session_id'] = new_sessname
                        with open(file, 'w') as fi:
                            json.dump(sess_data,fi)
                        break
                    except AssertionError:
                        print("Session id in beh is not as expected")
        except Exception as e:
            pass


    def go_through_files(self):
        for file in self.path2datafiles.rglob('*_behav.json'):
            sess_id = '_'.join(file.name.split('_')[:-1])
            if sess_id not in self.sessions_indb and 'MusterMaus' not in sess_id:
                self.sessions2add.append(sess_id)
        print(f"Found {len(self.sessions2add)} session not in DB")

    def add_session_to_DB(self):
        from datastructure_tools.utils import SessionClass
        from GUI_full import PROJECT_NAME, CURRENT_EXPERIMENT, BEHAVIOUR_FOLDER
        from datetime import datetime
        import shutil
        for sess_id in self.sessions2add:
            animal_id = "_".join(sess_id.split('_')[1:-1])
            session_datetime = datetime.strptime("_".join(sess_id.split('_')[0::3]), '%Y%m%d_%H%M')
            session_class = SessionClass(self.DB, animal_id=animal_id, session_datetime=session_datetime,
                                         project=PROJECT_NAME,
                                         user='as153', expName=CURRENT_EXPERIMENT,
                                         experiment_template=self.typical_exptype,
                                         session_id=sess_id,
                                         test=True if animal_id == 'MusterMaus' else False)
            pathcreationSuccess = session_class.createSession_path()  # create Paths on server
            if pathcreationSuccess:
                print(f'Created session{sess_id} on the server')
                #shutil.copyfile(self.path2datafiles / (sess_id + '_behav.csv'),
                #                self.DB.server_path / session_class.session_dir
                #                / BEHAVIOUR_FOLDER / (sess_id + '_behav.csv'))
                shutil.copyfile(self.path2datafiles / (sess_id + '_behav.json'),
                                self.DB.server_path / session_class.session_dir
                                / BEHAVIOUR_FOLDER / (sess_id + '_behav.json'))
                print(f'copied files')
                PushSuccess = session_class.checkInputs()  # checks inputs and pushes to DB
                if PushSuccess:
                    weight = None
                    while weight is None:
                        weight = input(f'Enter animal weight for {animal_id} on {session_datetime.date()}')
                        try:
                            weight.replace(',', '.')
                            weight = float(weight)
                        except ValueError:
                            print('Wrong weight format, try again')
                            weight = None

                    session_class.weight = weight
                    session_class.weight_note = 'Training'
                    session_class.pushWeights()
                    print(f'Pushed to DB')


class RunningAverage:

    def __init__(self, window=5):
        self.window = window
        self.data = np.zeros((self.window,)) * np.nan
        self.previous_value = np.nan

    @property
    def moving_average(self):
        return np.nanmean(self.data)

    @property
    def moving_sum(self):
        return np.nansum(self.data)

    def add_value(self, value):
        self.previous_value = self.moving_average
        self.data[:-1] = self.data[1:]
        self.data[-1] = value

    def reset(self):
        self.data = np.zeros((self.window,)) * np.nan
        self.previous_value = np.nan


if __name__ == "__main__":
    sess_cleanup = Session_backupCreator()
    sess_cleanup.sessions2add = [sess_cleanup.sessions2add[0]]
    sess_cleanup.fill_session_notinDB()
    #sess_cleanup.change_animal_nr("20231211_r0093_wt_1607", "r0092_wt")

    # DONT RUN while a session is running !
