from setuptools import setup, find_packages

setup(
    name="FreiCtrl_Laser",
    version='1.0.0',
    description='Laser controller for optogenetic experiments',
    author='Artur',
    python_requires=">=3.8",
    packages=find_packages(include=["FreiCtrl_laser"], exclude=['docs', 'circuitpython_code, arduino_barcodes'])
)
