"""Tests for routes module"""
import json
import time
import unittest

import paket_stellar
import util.logger
import webserver.validation

import routes

LOGGER = util.logger.logging.getLogger('pkt.api.test')
APP = webserver.setup(routes.BLUEPRINT)
APP.testing = True


class BridgeBaseTest(unittest.TestCase):
    """Base class for routes tests."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = APP.test_client()
        self.host = 'http://localhost'
        self.funded_seed = 'SDJGBJZMQ7Z4W3KMSMO2HYEV56DJPOZ7XRR7LJ5X2KW6VKBSLELR7MRQ'
        self.funded_account = paket_stellar.get_keypair(seed=self.funded_seed)
        self.funded_pubkey = self.funded_account.address().decode()
        LOGGER.info('init done')

    @staticmethod
    def sign_transaction(transaction, seed):
        """Sign transaction with provided seed"""
        builder = paket_stellar.stellar_base.builder.Builder(horizon=paket_stellar.HORIZON_SERVER, secret=seed)
        builder.import_from_xdr(transaction)
        builder.sign()
        signed_transaction = builder.gen_te().xdr().decode()
        return signed_transaction

    def call(self, path, expected_code=None, fail_message=None, seed=None, **kwargs):
        """Post data to API server."""
        LOGGER.info("calling %s", path)
        if seed:
            fingerprint = webserver.validation.generate_fingerprint(
                "{}/v{}/{}".format(self.host, routes.VERSION, path), kwargs)
            signature = webserver.validation.sign_fingerprint(fingerprint, seed)
            headers = {
                'Pubkey': paket_stellar.get_keypair(seed=seed).address().decode(),
                'Fingerprint': fingerprint, 'Signature': signature}
        else:
            headers = None
        response = self.app.post("/v{}/{}".format(routes.VERSION, path), headers=headers, data=kwargs)
        response = dict(real_status_code=response.status_code, **json.loads(response.data.decode()))
        if expected_code:
            self.assertEqual(response['real_status_code'], expected_code, "{} ({})".format(
                fail_message, response.get('error')))
        return response

    def submit(self, transaction, seed=None, description='unknown'):
        """Submit a transaction, optionally adding seed's signature."""
        LOGGER.info("trying to submit %s transaction", description)
        if seed:
            transaction = self.sign_transaction(transaction, seed)
        return self.call(
            'submit_transaction', 200, "failed submitting {} transaction".format(description), transaction=transaction)

    def create_account(self, from_pubkey, new_pubkey, seed, starting_balance=50000000):
        """Create account with starting balance"""
        LOGGER.info('creating %s from %s', new_pubkey, from_pubkey)
        unsigned = self.call(
            'prepare_account', 200, 'could not get create account transaction',
            from_pubkey=from_pubkey, new_pubkey=new_pubkey, starting_balance=starting_balance)['transaction']
        response = self.submit(unsigned, seed, 'create account')
        return response

    def create_and_setup_new_account(self, amount_buls=None, trust_limit=None):
        """Create account. Add trust and send initial ammount of BULs (if specified)"""
        keypair = paket_stellar.get_keypair()
        pubkey = keypair.address().decode()
        seed = keypair.seed().decode()
        self.create_account(from_pubkey=self.funded_pubkey, new_pubkey=pubkey, seed=self.funded_seed)
        self.trust(pubkey, seed, trust_limit)
        if amount_buls is not None:
            self.send(from_seed=self.funded_seed, to_pubkey=pubkey, amount_buls=amount_buls)
        return pubkey, seed

    def trust(self, pubkey, seed, limit=None):
        """Submit trust transaction for specified account"""
        LOGGER.info('adding trust for %s (%s)', pubkey, limit)
        unsigned = self.call(
            'prepare_trust', 200, 'could not get trust transaction', from_pubkey=pubkey, limit=limit)['transaction']
        return self.submit(unsigned, seed, 'add trust')

    def send(self, from_seed, to_pubkey, amount_buls):
        """Send BULs between accounts."""
        from_pubkey = paket_stellar.get_keypair(seed=from_seed).address().decode()
        description = "sending {} from {} to {}".format(amount_buls, from_pubkey, to_pubkey)
        LOGGER.info(description)
        unsigned = self.call(
            'prepare_send_buls', 200, "can not prepare send from {} to {}".format(from_pubkey, to_pubkey),
            from_pubkey=from_pubkey, to_pubkey=to_pubkey, amount_buls=amount_buls)['transaction']
        return self.submit(unsigned, from_seed, description)

    def prepare_escrow(self, payment, collateral, deadline, location=None):
        """Create launcher, courier, recipient, escrow accounts and call prepare_escrow"""
        LOGGER.info('preparing package accounts')
        launcher = self.create_and_setup_new_account(payment)
        courier = self.create_and_setup_new_account(collateral)
        recipient = self.create_and_setup_new_account()
        escrow = self.create_and_setup_new_account()

        LOGGER.info(
            "launching escrow: %s, launcher: %s, courier: %s, recipient: %s",
            escrow[0], launcher[0], courier[0], recipient[0])
        escrow_transactions = self.call(
            'prepare_escrow', 201, 'can not prepare escrow transactions', escrow[1],
            launcher_pubkey=launcher[0], courier_pubkey=courier[0], recipient_pubkey=recipient[0],
            payment_buls=payment, collateral_buls=collateral, deadline_timestamp=deadline, location=location)

        return {
            'launcher': launcher,
            'courier': courier,
            'recipient': recipient,
            'escrow': escrow,
            'transactions': escrow_transactions
        }


class SubmitTransactionTest(BridgeBaseTest):
    """Test for submit_transaction route."""

    def test_submit_signed(self):
        """Test submitting signed transactions."""
        keypair = paket_stellar.get_keypair()
        new_pubkey = keypair.address().decode()
        new_seed = keypair.seed().decode()

        # checking create_account transaction
        unsigned_account = self.call(
            'prepare_account', 200, 'could not get create account transaction',
            from_pubkey=self.funded_pubkey, new_pubkey=new_pubkey)['transaction']
        signed_account = self.sign_transaction(unsigned_account, self.funded_seed)
        LOGGER.info('Submitting signed create_account transaction')
        self.call(
            path='submit_transaction', expected_code=200,
            fail_message='unexpected server response for submitting signed create_account transaction',
            seed=self.funded_seed, transaction=signed_account)

        # checking trust transaction
        unsigned_trust = self.call(
            'prepare_trust', 200, 'could not get trust transaction', from_pubkey=new_pubkey)['transaction']
        signed_trust = self.sign_transaction(unsigned_trust, new_seed)
        LOGGER.info('Submitting signed trust transaction')
        self.call(
            path='submit_transaction', expected_code=200,
            fail_message='unexpected server response for submitting signed trust transaction',
            seed=new_seed, transaction=signed_trust)

        # checking send_buls transaction
        unsigned_send_buls = self.call(
            'prepare_send_buls', 200, "can not prepare send from {} to {}".format(self.funded_pubkey, new_pubkey),
            from_pubkey=self.funded_pubkey, to_pubkey=new_pubkey, amount_buls=5)['transaction']
        signed_send_buls = self.sign_transaction(unsigned_send_buls, self.funded_seed)
        LOGGER.info('Submitting signed send_buls transaction')
        self.call(
            path='submit_transaction', expected_code=200,
            fail_message='unexpected server response for submitting signed send_buls transaction',
            seed=self.funded_seed, transaction=signed_send_buls)


class BulAccountTest(BridgeBaseTest):
    """Test for bul_account endpoint."""

    def test_bul_account(self):
        """Test getting existing account."""
        accounts = [self.funded_pubkey]
        # additionally create 3 new accounts
        for _ in range(3):
            keypair = paket_stellar.get_keypair()
            pubkey = keypair.address().decode()
            seed = keypair.seed().decode()
            self.create_account(from_pubkey=self.funded_pubkey, new_pubkey=pubkey, seed=self.funded_seed)
            self.trust(pubkey, seed)
            accounts.append(pubkey)

        for account in accounts:
            with self.subTest(account=account):
                LOGGER.info('getting information about account: %s', account)
                self.call('bul_account', 200, 'could not verify account exist', queried_pubkey=account)


class PrepareAccountTest(BridgeBaseTest):
    """Test for prepare_account endpoint."""

    def test_prepare_account(self):
        """Test preparing transaction for creating account."""
        keypair = paket_stellar.get_keypair()
        pubkey = keypair.address().decode()
        LOGGER.info('preparing create account transaction for public key: %s', pubkey)
        self.call(
            'prepare_account', 200, 'could not get create account transaction',
            from_pubkey=self.funded_pubkey, new_pubkey=pubkey)


class PrepareTrustTest(BridgeBaseTest):
    """Test for prepare_trust endpoint."""

    def test_prepare_trust(self):
        """Test preparing transaction for trusting BULs."""
        keypair = paket_stellar.get_keypair()
        pubkey = keypair.address().decode()
        self.create_account(from_pubkey=self.funded_pubkey, new_pubkey=pubkey, seed=self.funded_seed)
        LOGGER.info('querying prepare trust for user: %s', pubkey)
        self.call('prepare_trust', 200, 'could not get trust transaction', from_pubkey=pubkey)


class PrepareSendBulsTest(BridgeBaseTest):
    """Test for prepare_send_buls endpoint."""

    def test_prepare_send_buls(self):
        """Test preparing transaction for sending BULs."""
        pubkey, _ = self.create_and_setup_new_account()
        LOGGER.info('preparing send buls transaction for user: %s', pubkey)
        self.call(
            'prepare_send_buls', 200, 'can not prepare send from {} to {}'.format(self.funded_pubkey, pubkey),
            from_pubkey=self.funded_pubkey, to_pubkey=pubkey, amount_buls=50000000)


class PrepareEscrowTest(BridgeBaseTest):
    """Test for prepare_escrow endpoint."""

    def test_prepare_escrow(self):
        """Test preparing escrow transaction."""
        payment, collateral = 50000000, 100000000
        deadline = int(time.time())
        LOGGER.info('preparing new escrow')
        self.prepare_escrow(payment, collateral, deadline)
