"""Bridge server for the PAKET project."""
import sys
import os.path

import util.logger
import webserver

import routes
import swagger_specs

util.logger.setup()
APP = webserver.setup(routes.BLUEPRINT, swagger_specs.CONFIG)
