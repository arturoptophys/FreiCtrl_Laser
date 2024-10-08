from PyQt6 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
# a QWidget with a matplotlib plot embedded in it
import numpy as np
from host_utils import RunningAverage

from matplotlib.patches import Polygon
from matplotlib.transforms import Affine2D

# Function to create a lightning bolt Polygon at a given position and size
def create_lightning_bolt(ax, position, scale):
    # adopted from chatgpt
    x = np.array([0.7, 0, 1, 0.3])
    y = np.array([1, 0, 0, -1])
    lightning_bolt = Polygon(np.column_stack((x, y)), closed=None, edgecolor='magenta', linewidth=5, facecolor='none')
    # Apply a translation and scaling to move and resize the lightning bolt
    trans = Affine2D().translate(position[0], position[1]).scale(scale[0], scale[1])
    lightning_bolt.set_transform(trans + ax.transData)
    return lightning_bolt

class MplCanvas(FigureCanvasQTAgg):
    """
    Canvas to plot matplotlib figures in a QWidget
    """

    def __init__(self, parent=None, width=9, height=6, dpi=90):
        fig, ax1 = plt.subplots(1, 1, figsize=(width, height), dpi=dpi)
        ax2 = ax1.twinx()
        #plt.tight_layout()
        self.ax1 = ax1
        self.ax2 = ax2
        self.fig = fig
        super(MplCanvas, self).__init__(fig)

class SessionPlotWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sess_type = "two_ports"
        self.canvas = MplCanvas()
        self.vbox = QtWidgets.QVBoxLayout()
        self.vbox.addWidget(self.canvas)
        self.setLayout(self.vbox)
        self.colors_angle = plt.cm.ScalarMappable(mcolors.Normalize(0, 60), cmap='Purples')
        self.colors_probability = plt.cm.ScalarMappable(mcolors.Normalize(0, 1), cmap='gist_heat')
        self.curr_trial = 0
        self.artists = []
        self.choise_ticks = []
        self.prev_val = np.nan
        self.color_bars = []
        self.lr_balance = RunningAverage(7)
        self.np_duration = RunningAverage(7)

    def initialize_plot(self, sess_type='two_ports'):
        """ Initialize the plot with the correct labels and colorbars """
        self.vbox.removeWidget(self.canvas)
        self.canvas = None
        self.canvas = MplCanvas()
        self.vbox.addWidget(self.canvas)
        # remove all artists
        self.sess_type = sess_type
        self.curr_trial = 1
        #for artist in self.artists:
        #    artist.remove()
        self.artists = []
        # remove all patches
        # for tick in self.choise_ticks:
        #     try:
        #         tick.remove()
        #     except TypeError:
        #         pass # no idea y this happends
        self.choise_ticks = []

        if self.sess_type == 'two_ports':
            self.canvas.ax1.set_xlim(0, 50)
            self.canvas.ax1.set_ylim(0, 2)
            self.canvas.ax1.set_yticks([0, 2])
            self.canvas.ax1.set_yticklabels(['Right', 'Left'])
            self.canvas.ax2.set_yticks([])  # no ticks at 2. for now
            self.canvas.ax1.set_xlabel('Trial Nr.')
            # add colorbars above the plot
            # for colorbar in self.color_bars:
            #     colorbar.remove()
            self.color_bars = []
            c1 = self.canvas.fig.colorbar(self.colors_angle, ax=self.canvas.ax1, location='right', pad=0.01,
                                     label='Angle (°)', shrink=0.75)
            c2 = self.canvas.fig.colorbar(self.colors_probability, ax=self.canvas.ax1, location='top', pad=0.01,
                                     label='Probability')
            self.color_bars.extend([c1, c2])

        elif self.sess_type == 'single_port':
            self.canvas.ax1.set_xlim(0, 50)
            self.canvas.ax1.set_ylim(0, 1500)
            self.canvas.ax1.set_xlabel('Trial Nr.')
            self.canvas.ax1.set_ylabel('NP duration (ms)')
            #self.canvas.ax2.set_ylabel('Time to NP (s)')

        elif self.sess_type == 'reward_assos':
            self.canvas.ax1.set_xlim(0, 50)
            self.canvas.ax1.set_ylim(0, 10000)
            self.canvas.ax1.set_xlabel('Trial Nr.')
            self.canvas.ax1.set_ylabel('Time to Lick')

        elif self.sess_type == 'durations':
            self.canvas.ax1.set_xlim(0, 50)
            self.canvas.ax1.set_ylim(0, 1500)
            self.canvas.ax1.set_xlabel('Trial Nr.')
            #self.canvas.ax1.set_ylabel('NP duration (ms)')
            self.canvas.ax1.set_ylabel('Time to NP (s)')

        self.canvas.draw()
    def start_faking(self):
        self.fake_timer = QtCore.QTimer()
        self.fake_timer.timeout.connect(self.fake_trial)
        self.fake_timer.start(1000)

    def fake_trial(self):
        import random
        val = random.random()
        if val <= 0.4:
            choise = 0
        elif 0.4 < val <= 0.8:
            choise = 2
        else:
            choise = 1
        angle_l = random.random() * 60
        angle_r = random.random() * 60
        probability_l = random.random()
        probability_r = random.random()
        error = random.random() < 0.2
        if not error:
            rewarded = random.random() < 0.8
        else:
            rewarded = False

        np_dur = random.random() * 1000
        time_to_np = random.random() * 15
        np_dur_thresh = 800 if random.random() < 0.8 else 1000
        omission_time = 10

        if choise == 0:
            trial = {"nose_poke_durationR": np_dur, "nose_poke_durationL": 0, "omission": False, "hit": rewarded,
                     "error": error, 'nosepoke_SETdur_R': np_dur_thresh, 'nosepoke_SETdur_L': np_dur_thresh,
                     'omission_time': omission_time, "nose_poke_timingR": time_to_np}
        elif choise == 2:
            trial = {"nose_poke_durationR": 0, "nose_poke_durationL": np_dur, "omission": False, "hit": rewarded,
                     "error": error, 'nosepoke_SETdur_R': np_dur_thresh, 'nosepoke_SETdur_L': np_dur_thresh,
                     'omission_time': omission_time, "nose_poke_timingL": time_to_np}
        else:
            trial = {"nose_poke_durationR": 0, "nose_poke_durationL": 0, "omission": True, "hit": False, "error": False,
                     'nosepoke_SETdur_R': np_dur_thresh, 'nosepoke_SETdur_L': np_dur_thresh,
                     'omission_time': omission_time}

        trial.update(**{'angle_L': angle_l, 'angle_R': angle_r, 'reward_prob_L': probability_l,
                        'reward_prob_R': probability_r, 'omission_time': omission_time, "gate_openedL": 0,
                        "gate_openedR": 0, 'omission_time_D': omission_time})

        self.add_trial(trial=trial)

    def add_trial(self, trial: dict):
        # parse trial data from
        # plot data from trial
        if self.sess_type == 'two_ports':
            if trial["nose_poke_durationR"]:
                choise = 0
                self.lr_balance.add_value(0)
            elif trial["nose_poke_durationL"]:
                choise = 2
                self.lr_balance.add_value(2)
            elif trial["omission"]:
                choise = 1
                #self.lr_balance.add_value(np.nan)
            else:
                choise = 1
                self.lr_balance.add_value(np.nan)
            angle_r = trial["angle_R"]/10
            angle_l = trial["angle_L"]/10
            probability_r = trial["reward_prob_R"]
            probability_l = trial["reward_prob_L"]
            rewarded = True if trial["outcome"] == 'hit' else False
            error = True if trial["error"] else False
            prev_values = self.rolling_counter.experienced_probs
            previous_val_prob = prev_values[1] - prev_values[0] + 1
            self.rolling_counter.add_trial(trial)
            now_values = self.rolling_counter.experienced_probs
            now_val_prob = now_values[1] - now_values[0] + 1
            # add special marker for error at side !
            tick_col = 'g' if rewarded else 'y'

            if error:
                t_mark = '*'
                t_size = 7
                tick_col = "r"
            elif choise == 1:  # omission
                tick_col = 'm'
                t_mark = '^'
                t_size = 7
            else:
                t_mark = '|'
                t_size = 50

            tick = self.canvas.ax1.plot(self.curr_trial, choise, t_mark, markersize=t_size, color=tick_col)
            tick2 = self.canvas.ax1.plot([self.curr_trial - 1, self.curr_trial], [self.lr_balance.previous_value,
                                                                                  self.lr_balance.moving_average],
                                         ':', color='c', linewidth=1)
            tick3 = self.canvas.ax1.plot([self.curr_trial - 1, self.curr_trial], [previous_val_prob,
                                                                                  now_val_prob],
                                         '--', color='m', linewidth=2)
            try:
                if trial['laser_trigger_time'] is not None:  #and not
                    if trial['laser_params']['trigger1']['mock']:  #mask only
                        tick4 = self.canvas.ax1.plot(self.curr_trial, 1, 'o', color='b', markersize=10,
                                                     fillstyle='none')
                    else:
                        tick4 = self.canvas.ax1.plot(self.curr_trial, 1, 'o', color='c', markersize=10,
                                                     fillstyle='none')
                    self.choise_ticks.extend([tick, tick2, tick3, tick4])
                else:
                    self.choise_ticks.extend([tick, tick2, tick3])
            except KeyError:
                pass

            artists = []
            artists.append(Rectangle((self.curr_trial - 0.5, 1.5), 1, 0.5, color=self.colors_angle.to_rgba(angle_l)))
            artists.append(Rectangle((self.curr_trial - 0.5, 0), 1, 0.5, color=self.colors_angle.to_rgba(angle_r)))
            artists.append(
                Rectangle((self.curr_trial - 0.5, 1), 1, 0.5, color=self.colors_probability.to_rgba(probability_l)))
            artists.append(
                Rectangle((self.curr_trial - 0.5, 0.5), 1, 0.5, color=self.colors_probability.to_rgba(probability_r)))

            #if trial['laser_trigger_time'] is not None:
            #    #there was a laser stim
            #    lightning_patch = create_lightning_bolt(self.canvas.ax1, ((self.curr_trial - 0.5)*10, 0.5), (0.1, 0.1))
            #    artists.append(lightning_patch)
            #    #self.canvas.ax.add_patch(lightning_patch)

            for artist in artists:
                self.canvas.ax1.add_artist(artist)
            self.artists.extend(artists)

        elif self.sess_type == 'single_port':
            if trial["nose_poke_durationR"]:
                np_dur = trial["nose_poke_durationR"]
                #time_to_np = trial["nose_poke_timingR"] - trial["gate_openedR"]
                np_dur_thresh = trial['nosepoke_SETdur_R']
            elif trial["nose_poke_durationL"]:
                np_dur = trial["nose_poke_durationL"]
                #time_to_np = trial["nose_poke_timingL"] - trial["gate_openedL"]
                np_dur_thresh = trial['nosepoke_SETdur_L']
            elif trial["omission"]:
                np_dur = None
                #time_to_np = trial["omission"]
                np_dur_thresh = trial['nosepoke_SETdur_R']
            else:
                if trial["nose_poke_durationC"]:
                    np_dur = trial["nose_poke_durationC"]
                    np_dur_thresh = trial['nosepoke_SETdur_C']
                else:
                    self.curr_trial += 1
                    return

            self.np_duration.add_value(np_dur) if np_dur is not None else self.np_duration.add_value(np.nan)


            marker_col = 'g' if np_dur > np_dur_thresh else 'r'
            tick1 = self.canvas.ax1.plot(self.curr_trial, np_dur, 'd', markersize=5, color=marker_col)
            tick2 = self.canvas.ax1.plot([self.curr_trial - 1, self.curr_trial], [np_dur_thresh, np_dur_thresh], ':',
                                         color='g')

            tick3 = self.canvas.ax1.plot([self.curr_trial - 1, self.curr_trial], [self.np_duration.previous_value,
                                                                                  self.np_duration.moving_average], '--'
                                         , color='m')

            # line_col = 'g' if time_to_np > omission_time else 'b'
            # tick3 = self.canvas.ax2.plot([self.curr_trial - 1, self.curr_trial], [self.prev_val, time_to_np], '-',
            #                              color=line_col)
            # self.prev_val = time_to_np
            # tick4 = self.canvas.ax2.plot([self.curr_trial - 1, self.curr_trial], [omission_time, omission_time], ':',
            #                              color='b')
            self.choise_ticks.extend([tick1, tick2, tick3])

        elif self.sess_type == 'durations':
            if trial["nose_poke_durationR"]:
                time_to_np = trial["nose_poke_timingR"] - trial["gate_openedR"]
            elif trial["nose_poke_durationL"]:
                time_to_np = trial["nose_poke_timingL"] - trial["gate_openedL"]
            elif trial["omission"]:
                time_to_np = trial["omission"]
            else:
                self.curr_trial += 1
                return

            omission_time = trial['omission_time_D']
            try:
                line_col = 'g' if time_to_np < omission_time else 'b'
            except TypeError: # some comparison with nan
                line_col = 'b'
            tick3 = self.canvas.ax1.plot([self.curr_trial - 1, self.curr_trial], [self.prev_val, time_to_np], '-',
                                         color=line_col)
            self.prev_val = time_to_np
            tick4 = self.canvas.ax1.plot([self.curr_trial - 1, self.curr_trial], [omission_time, omission_time], ':',
                                         color='b')
            self.choise_ticks.extend([tick3, tick4])

        elif self.sess_type == 'reward_assos':
            if trial['reward_pump_on'] and trial['tone_on']:
                time_to_reward = trial['reward_pump_on'] - trial['tone_on']
                color = 'g'
            else:
                try:
                    time_to_reward = trial['reward_lag']
                except KeyError:
                    time_to_reward = 0
                color = 'r'
            tick1 = self.canvas.ax1.plot(self.curr_trial, time_to_reward, 'd', markersize=5, color=color)
            self.choise_ticks.extend([tick1])
            if time_to_reward >= 10000:  # readjust the y axis if needed
                self.canvas.ax1.set_ylim(0, time_to_reward+500)

        if self.curr_trial > 50:
            self.canvas.ax1.set_xlim(0, self.curr_trial+1)
        if self.sess_type == "single_port" or self.sess_type == 'reward_assos':
            plt.tight_layout()
        self.canvas.draw()
        self.curr_trial += 1


