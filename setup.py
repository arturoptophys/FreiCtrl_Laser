from setuptools import setup, find_packages

setup(
    name="FreiCtrl_Laser",
    version='0.0.1',
    description='Laser controller for optogenetic experiments',
    author='Artur',
    python_requires=">=3.8",
    install_requires=[
            'pyqt6~=6.4',
            'pyqtgraph~=0.13.3',
            'pyserial'
        ],
    packages=find_packages(include=["FreiCtrl_laser"], exclude=['docs', 'circuitpython_code, arduino_barcodes'])
)
