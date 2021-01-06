# To Execute: python3 simulation.py
#
# Dependencies: python3, PyQt5 etc.
#
# Description: MainWindow is created by the app, which in turn starts a SimulationThread thread.

# USE ONLY SI UNITS
import sys
import logging
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from datastore import (DataStore, RacingSimulationResults)
from logging_config import configure_logging
from visualization_functions import MainWindow

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    MainApp = QApplication(sys.argv)
    if __name__ == "__main__":
        configure_logging()
    window = MainWindow()
    window.show()
    sys.exit(MainApp.exec_())
