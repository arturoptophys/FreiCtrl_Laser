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

