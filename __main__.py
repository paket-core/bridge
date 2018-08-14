"""Run the PaKeT funding server."""
import sys
import os.path

import util.logger
import webserver

import bridge.routes

# Python imports are silly.
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
# pylint: disable=wrong-import-position
import bridge.swagger_specs
# pylint: enable=wrong-import-position

util.logger.setup()

webserver.run(bridge.BLUEPRINT, bridge.swagger_specs.CONFIG, bridge.PORT)
