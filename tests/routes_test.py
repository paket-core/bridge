"""Tests for routes module"""
import json
import time
import unittest

import paket_stellar
import util.logger
import webserver.validation

import routes

LOGGER = util.logger.logging.getLogger('pkt.bridge.test')
APP = webserver.setup(routes.BLUEPRINT)
APP.testing = True


class BridgeBaseTest(unittest.TestCase):
    """Base class for routes tests."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = APP.test_client()
        self.host = 'http://localhost'
        self.funder_seed = paket_stellar.ISSUER_SEED
        self.funder_pubkey = paket_stellar.ISSUER
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

    def create_and_setup_new_account(self, starting_balance=50000000, buls_amount=None, trust_limit=None):
        """Create account. Add trust and send initial ammount of BULs (if specified)"""
        keypair = paket_stellar.get_keypair()
        pubkey = keypair.address().decode()
        seed = keypair.seed().decode()
        self.create_account(from_pubkey=self.funder_pubkey, new_pubkey=pubkey,
                            seed=self.funder_seed, starting_balance=starting_balance)
        self.trust(pubkey, seed, trust_limit)
        if buls_amount is not None:
            self.send(from_seed=self.funder_seed, to_pubkey=pubkey, amount_buls=buls_amount)
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

    def prepare_relay(self, payment, collateral, deadline, location=None):
        """Create launcher, courier, recipient, escrow accounts and call prepare_escrow"""
        escrow_details = self.prepare_escrow(payment, collateral, deadline, location)
        relayer = escrow_details['courier']
        relayee = self.create_and_setup_new_account(collateral)
        relay = self.create_and_setup_new_account()
        total_stroops = payment + collateral
        relayer_stroops = int(total_stroops / 2)
        relayee_stroops = total_stroops - relayer_stroops
        LOGGER.info(
            "preparing relay: %s, relayer: %s, relayee: %s",
            relay[0], relayer[0], relayee[0])
        relay_transactions = self.call(
            'prepare_relay', 201, 'can not prepare relay transactions', relay[1],
            relayer_pubkey=relayer[0], relayee_pubkey=relayee[0],
            relayer_stroops=relayer_stroops, relayee_stroops=relayee_stroops,
            deadline_timestamp=deadline, location=location)

        return {
            'escrow': escrow_details,
            'relayee': relayee,
            'relay': relay,
            'transactions': relay_transactions
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
            from_pubkey=self.funder_pubkey, new_pubkey=new_pubkey)['transaction']
        signed_account = self.sign_transaction(unsigned_account, self.funder_seed)
        LOGGER.info('Submitting signed create_account transaction')
        self.call(
            path='submit_transaction', expected_code=200,
            fail_message='unexpected server response for submitting signed create_account transaction',
            seed=self.funder_seed, transaction=signed_account)

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
            'prepare_send_buls', 200, "can not prepare send from {} to {}".format(self.funder_pubkey, new_pubkey),
            from_pubkey=self.funder_pubkey, to_pubkey=new_pubkey, amount_buls=5)['transaction']
        signed_send_buls = self.sign_transaction(unsigned_send_buls, self.funder_seed)
        LOGGER.info('Submitting signed send_buls transaction')
        self.call(
            path='submit_transaction', expected_code=200,
            fail_message='unexpected server response for submitting signed send_buls transaction',
            seed=self.funder_seed, transaction=signed_send_buls)


class BulAccountTest(BridgeBaseTest):
    """Test for bul_account endpoint."""

    def test_bul_account(self):
        """Test getting existing account."""
        accounts = [self.funder_pubkey]
        # additionally create 3 new accounts
        for _ in range(3):
            keypair = paket_stellar.get_keypair()
            pubkey = keypair.address().decode()
            seed = keypair.seed().decode()
            self.create_account(from_pubkey=self.funder_pubkey, new_pubkey=pubkey, seed=self.funder_seed)
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
            from_pubkey=self.funder_pubkey, new_pubkey=pubkey)


class PrepareTrustTest(BridgeBaseTest):
    """Test for prepare_trust endpoint."""

    def test_prepare_trust(self):
        """Test preparing transaction for trusting BULs."""
        keypair = paket_stellar.get_keypair()
        pubkey = keypair.address().decode()
        self.create_account(from_pubkey=self.funder_pubkey, new_pubkey=pubkey, seed=self.funder_seed)
        LOGGER.info('querying prepare trust for user: %s', pubkey)
        self.call('prepare_trust', 200, 'could not get trust transaction', from_pubkey=pubkey)


class PrepareSendBulsTest(BridgeBaseTest):
    """Test for prepare_send_buls endpoint."""

    def test_prepare_send_buls(self):
        """Test preparing transaction for sending BULs."""
        pubkey, _ = self.create_and_setup_new_account()
        LOGGER.info('preparing send buls transaction for user: %s', pubkey)
        self.call(
            'prepare_send_buls', 200, 'can not prepare send from {} to {}'.format(self.funder_pubkey, pubkey),
            from_pubkey=self.funder_pubkey, to_pubkey=pubkey, amount_buls=50000000)


class PrepareEscrowTest(BridgeBaseTest):
    """Test for prepare_escrow endpoint."""

    def test_prepare_escrow_and_relay(self):
        """Test preparing escrow transaction."""
        payment, collateral = 50000000, 100000000
        deadline = int(time.time())
        LOGGER.info('preparing new escrow and relay')
        LOGGER.debug(self.prepare_relay(payment, collateral, deadline))

    def test_ent_to_end(self):
        "End-to-end test."
        # prepare escrow properties
        payment = 10000000
        collateral = 20000000
        relay_payment = 5000000
        relay_collateral = 10000000
        deadline = int(time.time()) + 60 * 60 * 24 * 10

        # prepare accounts
        # launcher_account, first_courier_account, second_courier_account, recipient_account = (
        #     self.create_and_setup_new_account() for _ in range(4))
        # escrow_account = self.create_and_setup_new_account(buls_amount=payment)
        launcher_account = ('GBI27N2K5CA46RVPPO2UFQABNQIOFVJGJPXJWNROS2KR6J5BP2H7TX4M',
                            'SAAR6N7SLB3OECH7OBEGNPXADX35GV7R7EVC6P67EEXXWKIZYC346BWV')
        first_courier_account = ('GDCFBUSFW5GDHO6TQW65ACW3JRDFTBK2I5YTWJRRJHIFIPO5FIQWLOLA',
                                 'SDBE3HXYKW2WMQWKZOCNRD4EICC4VMBOTM7BCSROQAA7TGVWZZGCO7LV')
        second_courier_account = ('GB7VMXUABOSAG7TXDPVR2MMHEBKEXBNWA2EHP5SUHG5HU66PDW2F77W6',
                                  'SAEYMJX77WYIHT2TSONGMTUTTSR7CR2GOMPZQKNRJA5Z6JZ63REZ5KU2')
        recipient_account = ('GBR4SCRHZUPYYFIC7HBJKMEIESSZRGSTYMZSLNSG2IH2B6Z766QDTXJC',
                             'SB7R6P6NMJS3S6PA6WKFWQMD3BU4H2N7ZT4OORVQC5PSHLBBEG2OU7TZ')
        # prepare escrow account
        # escrow_account = self.create_and_setup_new_account(buls_amount=payment+collateral)
        escrow_keypair = paket_stellar.stellar_base.Keypair.random()
        escrow_account = escrow_keypair.address().decode(), escrow_keypair.seed().decode()
        prepare_escrow_account = paket_stellar.prepare_create_account(launcher_account[0], escrow_account[0])
        paket_stellar.submit_transaction_envelope(prepare_escrow_account, launcher_account[1])
        prepare_trust = paket_stellar.prepare_trust(escrow_account[0])
        paket_stellar.submit_transaction_envelope(prepare_trust, escrow_account[1])

        # prepare escrow transactions
        escrow_transactions = paket_stellar.prepare_escrow(
            escrow_account[0], launcher_account[0], first_courier_account[0],
            recipient_account[0], payment, collateral, deadline)
        paket_stellar.submit_transaction_envelope(escrow_transactions['set_options_transaction'], escrow_account[1])

        # send payment and collateral to escrow
        prepare_send_buls = paket_stellar.prepare_send_buls(launcher_account[0], escrow_account[0], payment)
        paket_stellar.submit_transaction_envelope(prepare_send_buls, launcher_account[1])
        prepare_send_buls = paket_stellar.prepare_send_buls(first_courier_account[0], escrow_account[0], collateral)
        paket_stellar.submit_transaction_envelope(prepare_send_buls, first_courier_account[1])

        # prepare relay
        relay_keypair = paket_stellar.stellar_base.Keypair.random()
        relay_account = relay_keypair.address().decode(), relay_keypair.seed().decode()
        prepare_relay_account = paket_stellar.prepare_create_account(first_courier_account[0], relay_account[0])
        paket_stellar.submit_transaction_envelope(prepare_relay_account, first_courier_account[1])
        prepare_trust = paket_stellar.prepare_trust(relay_account[0])
        paket_stellar.submit_transaction_envelope(prepare_trust, relay_account[1])

        # prepare relay transactions
        relay_transactions = paket_stellar.prepare_relay(
            relay_account[0], first_courier_account[0], second_courier_account[0],
            relay_payment, relay_collateral, deadline)
        paket_stellar.submit_transaction_envelope(relay_transactions['set_options_transaction'], relay_account[1])

        # send payment and collateral to relay account
        prepare_send_buls = paket_stellar.prepare_send_buls(first_courier_account[0], relay_account[0], relay_payment)
        paket_stellar.submit_transaction_envelope(prepare_send_buls, first_courier_account[1])
        prepare_send_buls = paket_stellar.prepare_send_buls(
            second_courier_account[0], relay_account[0], relay_collateral)
        paket_stellar.submit_transaction_envelope(prepare_send_buls, second_courier_account[1])

        # accept package by recipient
        paket_stellar.submit_transaction_envelope(escrow_transactions['payment_transaction'], recipient_account[1])
