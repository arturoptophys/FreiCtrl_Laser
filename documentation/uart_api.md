## Using UART to send parameters and trigger FreiLaser-board

The parameters can be sent to FreiLaser via serial/UART. The parameters are transmitted as a JavaScript Object Notation 
(JSON) dictionary followed by a line-break character. This enables FreiLaser to operate in fully autonomous mode, where 
another system sets the stimulation parameters and controls the mask and trigger signals. Ideally, this system also 
controls the behavioral task, allowing synchronization of events.

Example how to send parameters in Python:

    import serial 
    port = serial.Serial(port='/dev/ttyACM1', baudrate=115200)
    port.open()
    
    params = {}
    params["laser_list"] = []
    #set parameters for laser 1
    params['laser1'] = {
                    'pulsetrain_duration': 1000, # in ms
                    'frequency': 20, # in Hz
                    'pulse_dur': 0, # not needed for sinusiodal
                    'pulse_type': "full_sine", # or square or half_sine
                    'attenuation_factor': 0.5, # using half the available amplitude
                    'attenuated_wave': 200, # ms
                    'delay_time': 0, #ms                    
                    'power': 50  # in %
                    } 
                    
    #indicate that laser1 and its mask should be used
    params["laser_list"].append('laser1')
    params["laser_list"].append('laser1_mask')   
    is_primed = True  # preprime as we use internal trigger
    trigger = 0 # internal trigger connected to GP15 pin of pico 
    
    #set parameters for a trigger
    params['trigger1'] = {'mock': False, 'is_primed': is_primed,
                          'use_trigger_pin': True, "trigger_pin": trigger,
                          "use_priming_pin": not is_primed}
    # indicate its parameters message
    params['message_type'] = 'LaserParams' 
    
    # encode message as JSON
    message = (json.dumps(params) + '\n').encode('utf-8') 
    port.write(message)    


Example how to send software trigger in Python:

    message = ('TRIGGER' + '\n').encode('utf-8')
    port.write(message) 


