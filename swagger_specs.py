"""Swagger specifications of Identity Server."""
VERSION = 3
CONFIG = {
    'title': 'PaKeT API',
    'uiversion': 2,
    'specs_route': '/',
    'specs': [{
        'endpoint': '/',
        'route': '/apispec.json',
    }],
    'info': {
        'title': 'The PaKeT Server API',
        'version': VERSION,
        'contact': {
            'name': 'The PaKeT Project',
            'email': 'israel@paket.global',
            'url': 'https://api.paket.global',
        },
        'license': {
            'name': 'GNU GPL 3.0',
            'url': 'http://www.gnu.org/licenses/'
        },
        'description': '''
Web API Server for The PaKeT Project

What is this?
=============
This page is used as both documentation of our server API and as a sandbox to
test interaction with it. You can use this page to call the RESTful API while
specifying any required or optional parameter. The page also presents curl
commands that can be used to call the server.

Our Server
==========
We run a centralized server that can be used to interact with PaKeT's bottom
layers. Since Layer one is completely implemented on top of the Stellar
network, it can be interacted with directly in a fully decentralized fashion.
We created this server only as a gateway to the bottom layers to simplify the
interaction with them.

Security
========
Our calls are split into the following security levels:
 - Debug functions: require no authentication, available only in debug mode.
 - Anonymous functions: require no authentication.
 - Authenticated functions: require asymmetric key authentication. Not tested
   in debug mode.
    - The 'Pubkey' header will contain the user's pubkey.
    - The 'Fingerprint' header is constructed from the comma separated
      concatenation of the called URI, all the arguments (as key=value), and an
      ever increasing nonce (recommended to use Unix time in milliseconds).
    - The 'Signature' header will contain the signature of the key specified in
      the 'Pubkey' header on the fingerprint specified in the 'Fingerprint'
      header, encoded to Base64 ASCII.

Walkthrough
===========
The following steps demonstrate the main functionality of the API.

### Setup

To play around with the system you will need at least three accounts: a
launcher account, a courier account, and a recipient account.

- To create an account you need a Stellar compatible ed25519 keypair with a
  matching funded Stellar account. While on testnet, the Stellar account
  creator is your friend: https://www.stellar.org/laboratory/#account-creator
- Once your account is created, check it by calling /bul_account - you should
  get a 409 error saying that the account does not trust BULs.
- To change this and extend trust in BULs, from each account you should call
  /prepare_trust, sign the returned XDR with the matching private key, and
  submit it to /submit_transaction.
- Check your account by calling /bul_account again - you should now get a BUL
  balance of 0.
- Transfer some BULs into each of the accounts. In debug mode, you can call
  /fund_from_issuer.
- Check your account by calling /bul_account again - make sure your BUL balance
  reflects the amount of BULs you transfered.

### Launch a Package

- As the launcher, create the escrow account. Unlike the accounts in the setup
  section, this account will receive its minimal funding in XLM from the
  launcher, and it will be the launhcer's responsability to merge this account
  back to reclaim any leftover XLMs.
    - Generate a keypair.
    - As the launcher, call /prepare_account with the new pubkey given
      as argument, sign the returned transaction (with the launcher private
      key), and submit it to /submit_transaction.
    - Optionally, check the new account by calling /bul_account - you should
      get a 409 error saying that the account does not trust BULs.
    - As the new escrow account, call /prepare_trust, sign the returned
      transaction (with the escrow private key), and submit it to
      /submit_transaction.
    - Optionally, call /bul_account and verify your BUL balance is now 0.
- As the escrow account, call /prepare_escrow. Make sure that the payment is
  not larger than the launcher's BUL balance, and that the collateral is not
  larger than the courier's. The call will return four unsigned transactions:
    - set_options_transaction: changes the signers and weights, thus
      pre-authorizing the other transactions and invalidating the escrow
      private key, thereby locking the account. This transaction must be signed
      by the escrow account before being submitted.
    - refund_transaction: sends payment + collateral BULs from the escrow
      account to the launcher. If there aren't enough BULs in the escrow
      account it will fail and invalidate itself. While it requires no
      signatures, it can only be submitted if the set_options_transaction has
      been submitted, the payment_transaction has not been submitted, and the
      deadline has passed.
    - payment_transaction: sends payment + collateral BULs from the escrow
      account to the courier. If there aren't enough BULs in the escrow account
      it will fail and invalidate itself. It requires the signature of the
      recipient, and it can only be submitted if the set_options_transaction
      has been submitted and the refund_transaction has not.
    - merge_transaction: closes the escrow account and sends any remaining XLM
      balance to the launcher. If the escrow account still trusts any other
      token it will fail and invalidate itself. It requires no signatures, but
      can only be submitted after either the payment or the collateral
      transaction.
- As the escrow account, sign and submit the set_options_transaction.
- Call /bul_account on the escrow account and verify that the signers are
properly set.
- Make note of the BUL balances of the launcher by calling /bul_account.
- Transfer the payment from the launcher to the escrow by calling
/prepare_send_buls, signing the transaction, and submitting it to
/submit_transaction from your launcher account.
- Make note of the BUL balances of the launcher by calling /bul_account. It
  should be the same as before minus the payment.

### Accept the Package by Courier

- Make note of the BUL balances of the courier by calling /bul_account.
- Transfer the collateral from the courier to the escrow by calling
/prepare_send_buls, signing the transaction, and submitting it to
/submit_transaction from the courier account.
- Make note of the BUL balances of the courier by calling /bul_account. It
  should be the same as before minus the collateral.
- As the courier, call /accept_package with the escrow_pubkey as argument.

### Settle the Delivery

- Either approve the delivery:
    - As the recipient, sign and submit the payment transaction.
    - Make note of the BUL balances of the courier by calling /bul_account. It
    should be the same as before, plus both payment and collateral.
- Or wait for deadline to pass and ask for a refund + insurance.
    - Submit the payment transaction.
    - Make note of the BUL balances of the launcher by calling /bul_account. It
    should be the same as before, plus both payment and collateral.

### Merge the Escrow Account

- Make note of the XLM balances of the launcher and the escrow by calling
/bul_account on both.
- Submit the merge account transaction to /submit_transaction for the launcher
  to reclaim any unspent XLM that were spent creating the escrow account.
- Make note of the XLM balances of the launcher. It should be the same as
  before plus the escrow's XLM balance.

The API
=======
        '''
    }
}

SUBMIT_TRANSACTION = {
    'tags': ['wallet'],
    'parameters': [
        {
            'name': 'transaction', 'description': 'transaction to submit',
            'in': 'formData', 'required': True, 'type': 'string'
        }
    ],
    'responses': {
        '200': {'description': 'horizon response'}
    }
}

BUL_ACCOUNT = {
    'tags': ['wallet'],
    'parameters': [
        {
            'name': 'queried_pubkey', 'description': 'pubkey of the account',
            'in': 'formData', 'required': True, 'type': 'string'
        }
    ],
    'responses': {
        '200': {'description': 'account details'}
    }
}

PREPARE_ACCOUNT = {
    'tags': ['wallet'],
    'parameters': [
        {
            'name': 'from_pubkey', 'description': 'creating pubkey (existing account)',
            'in': 'formData', 'required': True, 'type': 'string'
        },
        {
            'name': 'new_pubkey', 'description': 'pubkey of account to be created',
            'in': 'formData', 'required': True, 'type': 'string'
        },
        {
            'name': 'starting_balance', 'description': 'amount of XLM to transfer from creating account',
            'in': 'formData', 'required': False, 'type': 'integer'
        }
    ],
    'responses': {
        '201': {'description': 'unsigned account creation transaction'}
    }
}

PREPARE_TRUST = {
    'tags': ['wallet'],
    'parameters': [
        {
            'name': 'from_pubkey', 'description': 'pubkey that wants to add trust in our token',
            'in': 'formData', 'required': True, 'type': 'string'
        },
        {
            'name': 'limit', 'description': 'limit of trust (default is max, set 0 to remove trustline)',
            'in': 'formData', 'required': False, 'type': 'integer'
        }
    ],
    'responses': {
        '201': {'description': 'unsigned add trust transaction'}
    }
}

PREPARE_SEND_BULS = {
    'tags': ['wallet'],
    'parameters': [
        {
            'name': 'from_pubkey', 'description': 'target pubkey for transfer',
            'in': 'formData', 'required': True, 'type': 'string'
        },
        {
            'name': 'to_pubkey', 'description': 'target pubkey for transfer',
            'in': 'formData', 'required': True, 'type': 'string'
        },
        {
            'name': 'amount_buls', 'description': 'amount to transfer',
            'in': 'formData', 'required': True, 'type': 'integer'
        }
    ],
    'responses': {
        '200': {'description': 'unsigned BUL transfer transaction'}
    }
}

PREPARE_ESCROW = {
    'tags': [
        'wallet'
    ],
    'parameters': [
        {'name': 'Pubkey', 'in': 'header', 'required': True, 'type': 'string'},
        {'name': 'Fingerprint', 'in': 'header', 'required': True, 'type': 'string'},
        {'name': 'Signature', 'in': 'header', 'required': True, 'type': 'string'},
        {
            'name': 'launcher_pubkey', 'description': 'escrow pubkey',
            'in': 'formData', 'required': True, 'type': 'string'},
        {
            'name': 'courier_pubkey', 'description': 'courier pubkey',
            'in': 'formData', 'required': True, 'type': 'string'},
        {
            'name': 'recipient_pubkey', 'description': 'recipient pubkey',
            'in': 'formData', 'required': True, 'type': 'string'},
        {
            'name': 'payment_buls', 'description': 'BULs promised as payment',
            'in': 'formData', 'required': True, 'type': 'integer'},
        {
            'name': 'collateral_buls', 'description': 'BULs promised as collateral',
            'in': 'formData', 'required': True, 'type': 'integer'},
        {
            'name': 'deadline_timestamp', 'description': 'deadline timestamp',
            'in': 'formData', 'required': True, 'type': 'integer'}
    ],
    'responses': {
        '201': {
            'description': 'escrow transactions',
        }
    }
}


FUND_FROM_ISSUER = {
    'tags': ['debug'],
    'parameters': [
        {
            'name': 'funded_pubkey', 'description': 'pubkey of account to be funded',
            'in': 'formData', 'required': True, 'type': 'string'},
        {
            'name': 'funded_buls', 'description': 'amount of BULs to fund the account',
            'in': 'formData', 'required': False, 'type': 'integer'},
    ],
    'responses': {
        '200': {'description': 'funding successful'}
    }
}


LOG = {
    'tags': [
        'debug'
    ],
    'parameters': [
        {
            'name': 'lines_num',
            'required': False,
            'in': 'formData',
            'schema': {
                'type': 'integer',
                'format': 'integer'
            }
        },
    ],
    'responses': {
        '200': {
            'description': 'log lines',
        }
    }
}
