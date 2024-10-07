## Installation

### GUI installation 
if you have git installed:
	
	git clone https://github.com/arturoptophys/FreiCtrl_Laser.git
	cd FreiCtrl_Laser

Install the module with required packages, ideally from a conda env. 
run inside FreiCtrl_Laser

    conda create -n FreiCtrl_Laser python=3.11
    conda activate FreiCtrl_Laser
    
    pip install -e .

To start the GUI, run the following command:

    python FreiCtrl_laser/GuiLaser.py

### CircuitPython installation
Please install CircuitPython firmware on your pico board according to instructions (https://circuitpython.org/board/raspberry_pi_pico/). 
Functionality was tested on 7.XX <= CircuitPython versions <=8.X.X.

_CircuitPython_ drive will appear on your computer. Now you can copy the code files (from circuit python code folder) on to the drive.
Then the LED on the pico should blink with 6 Hz indicating its functioning properly. 

