"""Run the PaKeT funding server."""
import sys
import os.path

import util.logger
import webserver

import routes

# Python imports are silly.
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
# pylint: disable=wrong-import-position
import swagger_specs
# pylint: enable=wrong-import-position

util.logger.setup()

webserver.run(routes.BLUEPRINT, swagger_specs.CONFIG, routes.PORT)
