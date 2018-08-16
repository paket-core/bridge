"""JSON swagger API to PaKeT."""
import os

import flasgger
import flask

import paket_stellar
import util.logger
import util.conversion
import webserver.validation

import swagger_specs

LOGGER = util.logger.logging.getLogger('pkt.api')
VERSION = swagger_specs.VERSION
PORT = os.environ.get('PAKET_API_PORT', 8000)
BLUEPRINT = flask.Blueprint('api', __name__)


# Input validators and fixers.
webserver.validation.KWARGS_CHECKERS_AND_FIXERS['_timestamp'] = webserver.validation.check_and_fix_natural
webserver.validation.KWARGS_CHECKERS_AND_FIXERS['_buls'] = webserver.validation.check_and_fix_natural
webserver.validation.KWARGS_CHECKERS_AND_FIXERS['_num'] = webserver.validation.check_and_fix_natural


# Wallet routes.


@BLUEPRINT.route("/v{}/submit_transaction".format(VERSION), methods=['POST'])
@flasgger.swag_from(swagger_specs.SUBMIT_TRANSACTION)
@webserver.validation.call(['transaction'])
def submit_transaction_handler(transaction):
    """
    Submit a signed transaction. This call is used to submit signed
    transactions. Signed transactions can be obtained by signing unsigned
    transactions returned by other calls. You can use the
    [laboratory](https://www.stellar.org/laboratory/#txsigner?network=test) to
    sign the transaction with your private key.
    ---
    :param transaction:
    :return:
    """
    return {'status': 200, 'response': paket_stellar.submit_transaction_envelope(transaction)}


@BLUEPRINT.route("/v{}/bul_account".format(VERSION), methods=['POST'])
@flasgger.swag_from(swagger_specs.BUL_ACCOUNT)
@webserver.validation.call(['queried_pubkey'])
def bul_account_handler(queried_pubkey):
    """
    Get the details of a Stellar BUL account.
    ---
    :param queried_pubkey:
    :return:
    """
    account = paket_stellar.get_bul_account(queried_pubkey)
    return dict(status=200, **account)


@BLUEPRINT.route("/v{}/prepare_account".format(VERSION), methods=['POST'])
@flasgger.swag_from(swagger_specs.PREPARE_ACCOUNT)
@webserver.validation.call(['from_pubkey', 'new_pubkey'])
def prepare_account_handler(from_pubkey, new_pubkey, starting_balance=50000000):
    """
    Prepare a create account transaction.
    ---
    :param from_pubkey:
    :param new_pubkey:
    :param starting_balance:
    :return:
    """
    try:
        return {'status': 200, 'transaction': paket_stellar.prepare_create_account(
            from_pubkey, new_pubkey, starting_balance)}
    # pylint: disable=broad-except
    # stellar_base throws this as a broad exception.
    except Exception as exception:
        LOGGER.info(str(exception))
        if str(exception) == 'No sequence is present, maybe not funded?':
            return {'status': 400, 'error': "{} is not a funded account".format(from_pubkey)}
        raise
    # pylint: enable=broad-except


@BLUEPRINT.route("/v{}/prepare_trust".format(VERSION), methods=['POST'])
@flasgger.swag_from(swagger_specs.PREPARE_TRUST)
@webserver.validation.call(['from_pubkey'])
def prepare_trust_handler(from_pubkey, limit=None):
    """
    Prepare an add trust transaction.
    ---
    :param from_pubkey:
    :param limit:
    :return:
    """
    return {'status': 200, 'transaction': paket_stellar.prepare_trust(from_pubkey, limit)}


@BLUEPRINT.route("/v{}/prepare_send_buls".format(VERSION), methods=['POST'])
@flasgger.swag_from(swagger_specs.PREPARE_SEND_BULS)
@webserver.validation.call(['from_pubkey', 'to_pubkey', 'amount_buls'])
def prepare_send_buls_handler(from_pubkey, to_pubkey, amount_buls):
    """
    Prepare a BUL transfer transaction.
    ---
    :param from_pubkey:
    :param to_pubkey:
    :param amount_buls:
    :return:
    """
    return {'status': 200, 'transaction': paket_stellar.prepare_send_buls(from_pubkey, to_pubkey, amount_buls)}


# Package routes.


@BLUEPRINT.route("/v{}/prepare_escrow".format(VERSION), methods=['POST'])
@flasgger.swag_from(swagger_specs.PREPARE_ESCROW)
@webserver.validation.call(
    ['launcher_pubkey', 'recipient_pubkey', 'courier_pubkey', 'payment_buls', 'collateral_buls', 'deadline_timestamp'],
    require_auth=True)
def prepare_escrow_handler(
        user_pubkey, launcher_pubkey, courier_pubkey, recipient_pubkey,
        payment_buls, collateral_buls, deadline_timestamp):
    """
    Launch a package.
    Use this call to create a new package for delivery.
    ---
    :param user_pubkey: the escrow pubkey
    :param launcher_pubkey:
    :param courier_pubkey:
    :param recipient_pubkey:
    :param payment_buls:
    :param collateral_buls:
    :param deadline_timestamp:
    :param location:
    :return:
    """
    package_details = paket_stellar.prepare_escrow(
        user_pubkey, launcher_pubkey, courier_pubkey, recipient_pubkey,
        payment_buls, collateral_buls, deadline_timestamp)
    return dict(status=201, package_details=package_details)
