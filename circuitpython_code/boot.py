import usb_cdc
import board
import digitalio
import storage

usb_cdc.enable(console=True, data=True)

switch = digitalio.DigitalInOut(board.GP16)
switch.direction = digitalio.Direction.INPUT
switch.pull = digitalio.Pull.UP
#True if it has not been grounded, but if connected to ground it reads False

# If the GP16 is connected to ground with a wire
# computer can write to the drive
storage.remount("/", not switch.value)  #When the value=False, the CIRCUITPY drive is writable by CircuitPython