# The actual simulation goes here
# This is the main application framework for the Race Simulation which contains the MainWindow,
# based on PyQt, and spawns a Qthread SimulationThread thread.  Qt signals/slots are used to
# communicate in both directions between them to control (start/pause/stop) and report results
# between them.
#
#
# To Execute: python3 simulation.py
#
# Dependencies: python3, PyQt5 etc.
#
# Description: MainWindow is created by the app, which in turn starts a SimulationThread thread. o
# Note: the MainWindow is not a QMainWindow, rather a QWidget which allows for more flexibility
# in placing controls, plots, etc.
# The MainWindow contains user controls such push button (QPushButton) that when pressed,
# emits a signal that is captured  but the "slot" on the SimulationThread thread which acts on it
# (thread_start_calculating).
# Likewise, the SimulationThread thread emits various signals which are captured by associated slots
# in the MainWindow and acted upon.
# In either direction data (e.g. input parameters to the SimulationThread thread or results of
# calculation from the SimulationThread thread) passed with emitted signal is then displayed on the
# PushButton.
#
# This is based on :
# https://stackoverflow.com/questions/52993677/how-do-i-setup-signals-and-slots-in-pyqt-with-qthreads-in-both-directions
# Author: RMH 10/28/2020
#
# Status:
# 11/25/20 This version does NO simulating and provides only the very basic GUI framework
# with a simple placeholder graph/plot, threading, and signalling  between the thread and
# the main window.
# 12/1/20 Adding a data storage area to share between the SimulationThread and MainWindow thread
# which incorporates a mutex mechanism (QReadWriteLock) to allow coordinating sharing of the
# data which MainWindow will be consuming (reading).
# 12/52/20 Manual merge in branch 'one-lock-rules-them-all' simulation code with the QThread
# architecture framed in from the previous versions of this branch

# USE ONLY SI UNITS
import time
import logging
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import pyqtgraph as pg
import cProfile
from datastore import (DataStore, RacingSimulationResults)


from simulation_functions import SimulationThread

logger = logging.getLogger(__name__)


class MainWindow(QWidget):

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, parent=None)

        self.data_store = DataStore()
        logger.info("MainWindow: DataStore initialized",
                extra={'sim_index': self.data_store.get_simulation_index()})

        # Create GUI related resources
        self.setWindowTitle('Race Simulation')
        
        # create the user play controls and data results graphs to run the simulation
        self.createUserDisplayControls()

        # create placeholders for the plots MainWindow will delivering (updating)
        # data into.
        self.graphs = pg.GraphicsLayoutWidget(show=True, title="Race Sim plots")
        self.graphs.resize(1000,540)
        self.p1 = self.graphs.addPlot(name="Plot1", title="Time (s)")        
        self.p2 = self.graphs.addPlot(name="Plot2", title="Distance (m)")        
        self.p2.hide()
        self.p3 = self.graphs.addPlot(name="Plot3", title="Velocity (m/s)")        
        self.p3.hide()
        self.p4 = self.graphs.addPlot(name="Plot4", title="Acceleration (m/s^2)")        
        self.p4.hide()
        self.p5 = self.graphs.addPlot(name="Plot5", title="Motor Power")        
        self.p5.hide()
        self.p6 = self.graphs.addPlot(name="Plot6", title="Battery Power")        
        self.p6.hide()
        self.p7 = self.graphs.addPlot(name="Plot7", title="Battery Energy (joules)")        
        self.p7.hide()
        
        # Links user X-coordinate movements of all plots together. Practically, there has
        # to be one plot they all link to, and in this case it's self.p1 (Time) b
        self.p2.setXLink(self.p1)
        self.p3.setXLink(self.p1)
        self.p4.setXLink(self.p1)
        self.p5.setXLink(self.p1)
        self.p6.setXLink(self.p1)
        self.p7.setXLink(self.p1)
        
        # Layout the major GUI components 
        #self.layout = QtGui.QVBoxLayout()
        self.layout = QHBoxLayout()
        self.layout.addWidget(self.userDisplayControlsGroup)
        self.layout.addWidget(self.graphs)
        self.setLayout(self.layout)

        # Create the instances of our worker threads
        self.simulationThread = SimulationThread(self.data_store)
        self.plotRefreshTimingThread = PlotRefreshTimingThread()

        # Setup the SIGNALs to be received from the worker threads
        self.simulationThread.simulationThreadSignal.connect(self.signalRcvFromSimulationThread)
        self.plotRefreshTimingThread.plotRefreshTimingSignal.connect(self.signalPlotRefresh)

        # TODO - what mechanism and what to do when SimulationThread or dies like
        #       refresh GUI and save/close results file??
        #self.simulationThread.finished.connect(self.simulationThreadFinished)
        #self.simulationThread.terminated.connect(self.simulationThreadTerminated)

        # Now that the SimulationThread has been created (but not yet running), connect the
        # Button clicked in MainWindow - call a SimulationThread method to do something
        self.buttonRun.clicked.connect(self.simulationThread.thread_start_calculating)
        self.buttonStop.clicked.connect(self.simulationThread.thread_stop_calculating)

        self.simulationThread.start()
        self.plotRefreshTimingThread.start()
        
    def createUserDisplayControls(self):
        self.labelDisplayControl = QLabel("Display Control")

        self.labelStatus = QLabel("Status")
        self.textboxStatus = QLineEdit("Initialized", self)
        self.textboxStatus.setReadOnly(True)
        self.buttonRun = QPushButton('Run/Continue', self)
        self.buttonRun.setEnabled(True)
        self.buttonStop = QPushButton('Pause', self)
        self.buttonStop.setEnabled(True) 
        
        self.labelSimulationIndex = QLabel("Sim. Index")
        self.textboxSimulationIndex = QLineEdit("0",self)
        self.textboxSimulationIndex.setReadOnly(False)

        self.checkboxTime = QCheckBox('Time (s)', self)
        self.checkboxTime.setChecked(False)
        self.spinboxTime = QDoubleSpinBox()
        self.spinboxTime.setReadOnly(True)

        self.checkboxDistance = QCheckBox('Distance (m)', self)
        self.checkboxDistance.setChecked(False) 
        self.spinboxDistance = QDoubleSpinBox()
        self.spinboxDistance.setReadOnly(True)

        self.checkboxVelocity = QCheckBox('Velocity (m/s)', self)
        self.checkboxVelocity.setChecked(False) 
        self.spinboxVelocity = QDoubleSpinBox()
        self.spinboxVelocity.setReadOnly(True)

        self.checkboxAcceleration = QCheckBox('Acceleration (m/s^2)', self)
        self.checkboxAcceleration.setChecked(False) 
        self.spinboxAcceleration = QDoubleSpinBox()
        self.spinboxAcceleration.setReadOnly(True)

        self.checkboxMotorPower = QCheckBox('Motor Power', self)
        self.checkboxMotorPower.setChecked(False) 
        self.spinboxMotorPower = QDoubleSpinBox()
        self.spinboxMotorPower.setReadOnly(True)

        self.checkboxBatteryPower = QCheckBox('Battery Power', self)
        self.checkboxBatteryPower.setChecked(False) 
        self.spinboxBatteryPower = QDoubleSpinBox()
        self.spinboxBatteryPower.setReadOnly(True)
        
        self.checkboxBatteryEnergy = QCheckBox('Battery Energy (j)', self)
        self.checkboxBatteryEnergy.setChecked(False) 
        self.spinboxBatteryEnergy = QDoubleSpinBox()
        self.spinboxBatteryEnergy.setReadOnly(True)

        #self.userDisplayControlsGroup = QtGui.QGroupBox('User Display Controls')
        self.userDisplayControlsGroup = QGroupBox('User Display Controls')
        #self.userDisplayControlsLayout= QtGui.QGridLayout()
        self.userDisplayControlsLayout= QGridLayout()
        self.userDisplayControlsLayout.addWidget(self.labelStatus,              0, 0)
        self.userDisplayControlsLayout.addWidget(self.textboxStatus,            0, 1)
        self.userDisplayControlsLayout.addWidget(self.buttonRun,                1, 0)
        self.userDisplayControlsLayout.addWidget(self.buttonStop,               1, 1)
        self.userDisplayControlsLayout.addWidget(self.labelSimulationIndex,     2, 0)
        self.userDisplayControlsLayout.addWidget(self.textboxSimulationIndex,   2, 1)
        self.userDisplayControlsLayout.addWidget(self.checkboxTime,             3, 0)
        self.userDisplayControlsLayout.addWidget(self.spinboxTime,              3, 1)
        self.userDisplayControlsLayout.addWidget(self.checkboxDistance,         4, 0)
        self.userDisplayControlsLayout.addWidget(self.spinboxDistance,          4, 1)
        self.userDisplayControlsLayout.addWidget(self.checkboxVelocity,         5, 0)
        self.userDisplayControlsLayout.addWidget(self.spinboxVelocity,          5, 1)
        self.userDisplayControlsLayout.addWidget(self.checkboxAcceleration,     6, 0)
        self.userDisplayControlsLayout.addWidget(self.spinboxAcceleration,      6, 1)
        self.userDisplayControlsLayout.addWidget(self.checkboxMotorPower,       7, 0)
        self.userDisplayControlsLayout.addWidget(self.spinboxMotorPower,        7, 1)
        self.userDisplayControlsLayout.addWidget(self.checkboxBatteryPower,     8, 0)
        self.userDisplayControlsLayout.addWidget(self.spinboxBatteryPower,      8, 1)
        self.userDisplayControlsLayout.addWidget(self.checkboxBatteryEnergy,    9, 0)
        self.userDisplayControlsLayout.addWidget(self.spinboxBatteryEnergy,     9, 1)
        self.userDisplayControlsGroup.setLayout(self.userDisplayControlsLayout)

    def simulationThreadResultsDataDisplay(self):
        # TODO placeholder for real work to be done when the SimulationThread (a simulationThread thread)
        # SIGNALs MainWindow new data is available in shared memory
        print('Window SIGNAL from SimulationThread: Results_data_ready')

    def simulationThreadFinished(self):
        # TODO placeholder for SimulationThread SIGNALs ??exiting
        # data is available in shared memory
        print('Window: SIGNAL From SimulationThread: Finished')

    def simulationThreadTerminated(self):
        # TODO placeholder for SimulationThread SIGNALs terminated
        print('Window: SIGNAL From SimulationThread: Terminated')

    ###################################
    # TODO REMOVE/REPLACE FOR THE SIM APP
    @pyqtSlot(str)
    def signalRcvFromSimulationThread(self, text):
        #self.buttonRun.setText(text)
        self.textboxStatus.setText(text)

    @pyqtSlot()
    def signalPlotRefresh(self):
        #Display/update the window to display computation status, data, and plots selected by the user
        # This is called periodically because of the signal emitted from PlotRefreshTimingThread
        
        # TODO current_sim_index is "-1" for the following call 
        # because the lap_velocity_simulation calculations may be incomplete for the index
        # when this signal was received and interrupted it. That is, that thread is still 
        # updating a DataStore data (lists) records  @ simulation_index and not all lists 
        # have been calculated, so we should just plot upto the last complete record.
        current_sim_index = (self.data_store.get_simulation_index())-1
        #logger.info("MainWindow:", extra={'sim_index': current_sim_index})
        self.textboxSimulationIndex.setText("{}".format(current_sim_index))
        
        # Get the current data values and update the corresponding display field textbox
        time = self.data_store.get_time_at_index(current_sim_index)
        self.spinboxTime.setValue(time)
        
        distance = self.data_store.get_distance_at_index(current_sim_index)
        self.spinboxDistance.setValue(distance)
        
        velocity = self.data_store.get_velocity_at_index(current_sim_index)
        self.spinboxVelocity.setValue(velocity)
        
        acceleration = self.data_store.get_acceleration_at_index(current_sim_index)
        self.spinboxAcceleration.setValue(acceleration)
        
        motor_power = self.data_store.get_motor_power_at_index(current_sim_index)
        self.spinboxMotorPower.setValue(motor_power)
        
        battery_power = self.data_store.get_battery_power_at_index(current_sim_index)
        self.spinboxBatteryPower.setValue(battery_power)
        # TBD not yet implemented in physics_equations
        #battery_energy = self.data_store.get_battery_energy_at_index(current_sim_index)
        #self.spinboxBatteryEnergy.setValue(battery_energy)
        
        # Display the data values
        
        # create a new plot for every point simulated so far
        x = [z+1 for z in range(current_sim_index)]
        #x = [z for z in range(current_sim_index)]
        _time = []
        _distance = []
        _velocity = []
        _max_velocity = []
        _acceleration = []
        _motor_power = []
        _battery_power = []
        _battery_energy = []
        # TODO: build the lists in a function call to the datastore
        # to reduce locking/unlocking overhead
        for z in x:
            _time.append(self.data_store.get_time_at_index(z))
            _distance.append(self.data_store.get_distance_at_index(z))
            _velocity.append(self.data_store.get_velocity_at_index(z))
            _max_velocity.append(self.data_store.get_track_max_velocity_at_index(z))
            _acceleration.append(self.data_store.get_acceleration_at_index(z))
            _motor_power.append(self.data_store.get_motor_power_at_index(z))
        #    _battery_power.append(self.data_store.get_battery_power_at_index(z))
            # TODO not yet implemented in physics_equations
            #_battery_energy.append(self.data_store.get_battery_energy_at_index(z))
        #print('x={} current_sim_index = {}'.format(x, current_sim_index))
        #_time = self.data_store.get_time_list(current_sim_index+1)
        #_distance = self.data_store.get_distance_list(current_sim_index+1)
        #_velocity = self.data_store.get_velocity_list(current_sim_index+1)
        #_max_velocity = self.data_store.get_track_max_velocity_list(current_sim_index+1)
        #_acceleration = self.data_store.get_acceleration_list(current_sim_index+1)
        #_motor_power = self.data_store.get_motor_power_list(current_sim_index+1)
        #_battery_power = self.data_store.get_battery_power_list(current_sim_index+1)
        #TODO not yet implemented
        #_battery_energy = self.data_store.get_battery_energy_list(current_sim_index)
        
        self.p1.plot(x=x, y=_time, name="Plot1", title="Time")        
        
        # selectively display the plots based on the checkboxes 
        if self.checkboxDistance.isChecked() == True :
            self.p2.show()
            self.p2.plot(x=x, y=_distance, name="Plot2", title="Distance (m)")        
        else:
            self.p2.hide()
            
        if self.checkboxVelocity.isChecked() == True :
            self.p3.show()
            self.p3.plot(x=x, y=_max_velocity, name="Plot3", title="Max Velocity (m/sec)", pen='r')
            self.p3.plot(x=x, y=_velocity, name="Plot3", title="Velocity (m/sec)")        
            
        else:
            self.p3.hide()
            
        if self.checkboxAcceleration.isChecked() == True :
            self.p4.show()
            self.p4.plot(x=x, y=_acceleration, name="Plot4", title="Acceleration (m/sec^2)")        
        else:
            self.p4.hide()
            
        if self.checkboxMotorPower.isChecked() == True :
            self.p5.show()
            self.p5.plot(x=x, y=_motor_power, name="Plot5", title="Motor Power")        
        else:
            self.p5.hide()
            
        if self.checkboxBatteryPower.isChecked() == True :
            self.p6.show()
            self.p6.plot(x=x, y=_battery_power, name="Plot6", title="Battery Power")        
        else:
            self.p6.hide()
            
        """TBD - to be added once Battery Energy is working in physics_equations
        if self.checkboxBatteryEnergy.isChecked() == True :
            self.p7.show()
            self.p7.plot(x=x, y=_battery_energy, name="Plot7", title="Battery Energy (joules)")        
        else:
            self.p7.hide()
        """

        
class PlotRefreshTimingThread(QThread): 
    # Thread responsible for a periodic signal to the MainWindow which when received causes 
    # MainWindow to refresh it's plots.

    # Define the Signals we'll be emitting to the MainWindow
    plotRefreshTimingSignal = pyqtSignal()

    # start without compution in the simulationThread running

    def __init__(self, parent=None):
        QThread.__init__(self, parent)
        self.exiting = False

        logger.info("PlotRefreshTimingThread: __init()__",
                extra={'sim_index': 'N/A'})

        # TODO connect some signals from the main window to us
        #self.connect(self, QtCore.SIGNAL('To_End',self.processToEnd)


    def __del__(self):    
        # Before a PlotRefreshTimingThread object is destroyed, we need to ensure that it stops 
        # processing.  For this reason, we implement the following method in a way that 
        # indicates to  the part of the object that performs the processing that it must stop,
        # and waits until it does so.
        self.exiting = True
        self.wait()

    def run(self):
        # Note: This is never called directly. It is called by Qt once the
        # thread environment with the thread's start() method has been setup,
        # and then runs "continuously" to do the work of the thread as it's main
        # processing loop

        logger.info("PlotRefreshTimingThread: entering while() ",
                extra={'sim_index': 'N/A'})
        while True:
            time.sleep(0.25)
            self.plotRefreshTimingSignal.emit()
