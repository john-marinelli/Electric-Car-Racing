# USE ONLY SI UNITS
import sys
import time
import logging
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import pyqtgraph as pg
import cProfile
from datastore import (DataStore, RacingSimulationResults)
from physics_equations import (max_negative_power_physics_simulation,
                               max_positive_power_physics_simulation,
                               constrained_velocity_physics_simulation,
                               )
from electric_car_properties import ElectricCarProperties
from track_properties import TrackProperties

logger = logging.getLogger(__name__)


class SimulationThread(QThread):
    # Define the Signals we'll be emitting to the MainWindow
    simulationThreadSignal = pyqtSignal(str)
    simulationThreadPlotSignal = pyqtSignal(int)

    def __init__(self, passed_data_store, parent=None):
        QThread.__init__(self, parent)
        self.exiting = False
        self.setObjectName("SimulationThread")

        """ SimulationComputing is used for staring/stopping loop control logic which is
        controlled ( signalled) from the MainWindow.
        Start without compution in the simulationThread running
        """
        self.simulationComputing = False
        self.iterations = 0

        # Initialize the simulation universe
        self._data_store = passed_data_store
        self.initialize_race()

        #print('SimulationThread: __init()__')
        #print("SimulationThread: Simulation Index = {}".format(self._data_store.get_simulation_index()))

        #connect some signals from the main window to us
        #self.connect(self, QtCore.SIGNAL('To_End',self.processToEnd)


    def __del__(self):    
        # Before a SimulationThread object is destroyed, we need to ensure that it stops processing. 
        # For this reason, we implement the following method in a way that indicates to 
        # the part of the object that performs the processing that it must stop, and waits 
        # until it does so.
        self.exiting = True
        self.wait()

        # rotational inertia estimation: http://www.hpwizard.com/rotational-inertia.html
    def initialize_race(self):

        segment_distance = 0.005  # meters, this must be very very small
        battery_power = 40000  # 40kW
        motor_efficiency = 0.8
        wheel_radius = 0.25  # m, ~20 in OD on tires
        rotational_inertia = 10  # kg*m^2
        mass = 1000  # kg
        drag_coefficient = 0.4
        frontal_area = 7  # m^2
        air_density = 1  # kg/m^3
        wheel_pressure_bar = 3 # bar

        track = TrackProperties()
        track.set_air_density(air_density)

        track.add_critical_point(0.0, 10.0, track.FREE_ACCELERATION)
        track.add_critical_point(5.0, 5.0, track.FREE_ACCELERATION)
        track.add_critical_point(10.0, 10.0, track.FREE_ACCELERATION)
        track.add_critical_point(12.0, 12.0, track.FREE_ACCELERATION)
        track.add_critical_point(16.0, 15.0, track.FREE_ACCELERATION)
        track.add_critical_point(50.0, 40.0, track.FREE_ACCELERATION)
        track.generate_track_list(segment_distance)

        car = ElectricCarProperties()
        car.set_car_parameters(mass=mass, rotational_inertia=rotational_inertia,
                               motor_power=battery_power, motor_efficiency=motor_efficiency,
                               battery_capacity=10, drag_coefficient=drag_coefficient,
                               frontal_area=frontal_area, wheel_radius=wheel_radius,
                               wheel_pressure_bar=wheel_pressure_bar)

        self._data_store.initialize_lap_lists(len(track.distance_list))
        self._data_store.set_car_properties(car)
        self._data_store.set_track_properties(track)

    """ SimulationThread signal handling routines. This is the collection of SLOTS
        that get signaled from the MainWindow tell the SimulationThread what to do,
        like change states and start calculating, pause, etc.
    """
    @pyqtSlot()
    def thread_start_calculating(self):
        logger.info('Slot:thread_start_calculating :', 
                extra={'sim_index': self._data_store.get_simulation_index()})
        # Now send a signal back to the main window
        self.simulationThreadSignal.emit("Calculating...")
        # "state" variable indicating thread should be calculating
        self.simulationComputing = True

    @pyqtSlot()
    def thread_stop_calculating(self):
        logger.info('Slot:thread_stop_calculating :', 
                extra={'sim_index': self._data_store.get_simulation_index()})
        # Now send a signal back to the main window
        self.simulationThreadSignal.emit("Paused")

        # "state" variable indicating thread should stop calculating
        self.simulationComputing = False

    def racing_simulation(self):
        """Function accepts a car and a track and executes
        a simulation to ouput critical metrics related
        to battery life and track speed.

        Args:
            Nothing, all required vars are defined in class

        Returns:
            Nothing, all required vars are defined in class

        """
        results = RacingSimulationResults()

        self.lap_velocity_simulation()
        # only calculate results if the simulation ran through without an interruption
        if not self._data_store.exit_event.is_set():
            lap_results = self._data_store.get_lap_results()

            # TODO fix this
            #results.laps_per_pit_stop = car["battery_capacity"] / lap_results.motor_energy_list[-1]
            results.lap_time = lap_results.end_velocity
            results.lap_results = lap_results
            self._data_store.set_race_results(results)

    def lap_velocity_simulation(self):
        """Function calculates the velocity profile of a car with
        car_properties on a track with track_properties. The car
        starts with an ititial velocity of initial_velocity.

        Args:
            data_store (DataStore): Thread safe storage for all simulation data

        Returns:
            Nothing (all data saved in the datastore)
        """
        # performance increases by assigning local functions
        # https://towardsdatascience.com/10-techniques-to-speed-up-python-runtime-95e213e925dc
        add_physics_result_to_datastore = self._data_store.add_physics_results_to_lap_results
        get_velocity = self._data_store.get_velocity_at_index

        track = self._data_store.get_track_properties()
        air_density = track.get_air_density()
        car = self._data_store.get_car_properties()

        sim_index = self._data_store.get_simulation_index()
        # need to populate the time profile be the same length as the distance list
        # to complete a lap of simulation
        list_len = len(track.distance_list)
        logger.debug('list_len={}'.format(list_len), extra={'sim_index': sim_index})

        # TODO - Add self.simulationComputing to loop control to while
        while self._data_store.get_simulation_index() < list_len:
            sim_index = self._data_store.get_simulation_index()
            #print('lap_velocity_simulation: simulation_index={}'.format(sim_index))

            # only continue simulation if the GUI says to do so.
            if (self.simulationComputing == True):
                if self._data_store.exit_event.is_set():
                    break
                distance_of_travel = (track.distance_list[sim_index] -
                                      track.distance_list[sim_index - 1])

                velocity = get_velocity(sim_index - 1)
                physics_results = max_positive_power_physics_simulation(velocity,
                                                                        distance_of_travel,
                                                                        car,
                                                                        air_density)
                add_physics_result_to_datastore(physics_results, sim_index)
                # check if velocity constraints are violated
                if get_velocity(sim_index) > track.max_velocity_list[sim_index]:
                    # velocity constraint violated!!
                    # start walking back until velocity constraint at sim_index is met
                    logger.info("velocity constraint violated starting walk back, current v: {}, max: {}"
                                .format(physics_results.final_velocity, track.max_velocity_list[sim_index]),
                                extra={'sim_index': self._data_store.get_simulation_index()})
                    max_velocity_constraint = track.max_velocity_list[sim_index]
                    while get_velocity(sim_index) > max_velocity_constraint:
                        """This while loop's pupose is to recalculate a portion of the
                        car's car profile because the car ended up going to fast at a point on the
                        track. To recalculate the following happens:

                        1. a "walk back" index is used to track how far back the recalculation occurs
                        2. from the index (sim_index - walk_back_index) to (sim_index - 1) the results
                           are calculated as a maximum regeneration effort by the motor
                        3. at the sim_index the results are calculated as a constrained velocity
                            - if the results of the calculation are realistic then the walk back is done
                            - if the results are not realistic then increment the
                              walk back counter and recalculate
                        """
                        walk_back_counter = self._data_store.get_walk_back_counter()
                        recalculation_start_index = sim_index - walk_back_counter
                        logger.debug("starting and ending walkback index: {}, {}"
                                     .format(recalculation_start_index, sim_index),
                                     extra={'sim_index': self._data_store.get_simulation_index()})
                        for i in range(recalculation_start_index, sim_index):

                            velocity = get_velocity(i - 1)
                            logger.debug("velocity: {}"
                                         .format(velocity),
                                         extra={'sim_index': i})
                            # recalculate with negative motor power
                            physics_results = max_negative_power_physics_simulation(velocity,
                                                                                    distance_of_travel,
                                                                                    car,
                                                                                    air_density)
                            logger.debug("next velocity: {}"
                                         .format(physics_results.final_velocity),
                                         extra={'sim_index': i})
                            add_physics_result_to_datastore(physics_results, i)

                        velocity = get_velocity(sim_index - 1)
                        # last deceleration will be a constrained velocity because
                        # it will be neither max positive or negative motor power
                        physics_results = \
                            constrained_velocity_physics_simulation(velocity,
                                                                    max_velocity_constraint,
                                                                    distance_of_travel,
                                                                    car,
                                                                    air_density)
                        logger.debug("velocity start, end, max: {} {} {}"
                                     .format(velocity,
                                             physics_results.final_velocity,
                                             max_velocity_constraint),
                                     extra={'sim_index': sim_index})
                        # check if constrained velocity calculation is realistic
                        # TODO other checks here can be on acceleration or wheel force
                        if physics_results.motor_power < -car["motor_power"]:
                            logger.debug(
                                "velocity constraint still violated, calculated power: {}, max power: {}"
                                .format(physics_results.motor_power, car["motor_power"]),
                                extra={'sim_index': sim_index})
                            logger.debug("sim_index, walkback: {} {}, incrementing walk back"
                                         .format(sim_index, walk_back_counter),
                                         extra={'sim_index': sim_index})
                            self._data_store.increment_walk_back_counter()
                        else:
                            logger.info(
                                "velocity constraint accepted, calculated power: {}, max power: {}"
                                .format(physics_results.motor_power, car["motor_power"]),
                                extra={'sim_index': sim_index})
                            logger.info("constrained velocity equation accepted",
                                        extra={'sim_index': sim_index})
                            add_physics_result_to_datastore(physics_results, sim_index)

                    # reset walk back index
                    self._data_store.reset_walk_back_counter()

                self._data_store.increment_simulation_index()
            else:
                # self.simulationComputing is False, so wait for GUI user to indicate proceed
                time.sleep(1)
                logger.debug("waiting for simulationComputing==True",
                        extra={'sim_index': sim_index})
        # end of while data_store.get_simulation_index() < list_len:

        logger.info("SIMULATION COMPLETE!", extra={'sim_index': 'N/A'})
        self.simulationThreadSignal.emit("Finished!")
        self._data_store.exit_event.set()

    def run(self):
        # Note: This is never called directly. It is called by Qt once the
        # thread environment with the thread's start() method has been setup,
        # and then runs "continuously"
        logger.info("SimulationThread: entering cProfile.runctx() ",
                extra={'sim_index': 'N/A'})

        # profiling tool, look at results with runsnake:
        # https://kupczynski.info/2015/01/16/profiling-python-scripts.html
        # this has relatively little overhead for the overall runtime of the program
        # I have only been able to get the runsnake files to work on linux
        # alternative profile results viewer for windows (untried): https://sourceforge.net/projects/qcachegrindwin/
        #cProfile.runctx("racing_simulation(self._data_store)", globals(), locals(), 'profile.out')
        cProfile.runctx("self.racing_simulation()", globals(), locals(), 'profile.out')
