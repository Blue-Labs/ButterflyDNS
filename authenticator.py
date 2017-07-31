
"""
This is the integrated component for crossbar that does dynamic authentication. Crossbar
will instantiate the below AuthenticatorSession() class, you do not need to run this
yourself.
"""

__version__  = '1.2.2'
__author__   = 'David Ford <david@blue-labs.org>'
__email__    = 'david@blue-labs.org'
__date__     = '2017-Jul-31 02:48Z'
__license__  = 'Apache 2.0'


import ssl
import time
import base64
import hashlib
import datetime
import configparser

from ldap3 import Server
from ldap3 import Connection
from ldap3 import Tls
from ldap3 import ALL_ATTRIBUTES
from ldap3 import ALL
from ldap3 import SUBTREE
from ldap3 import LEVEL
from ldap3 import MODIFY_REPLACE
from ldap3 import AUTH_SIMPLE
from ldap3 import LDAPInvalidCredentialsResult
from ldap3 import LDAPSizeLimitExceededResult
from ldap3 import LDAPException

from ldap3.core.exceptions import LDAPInvalidCredentialsResult
from ldap3.core.exceptions import LDAPSizeLimitExceededResult
from ldap3.core.exceptions import LDAPException
from ldap3.core.exceptions import LDAPSessionTerminatedByServerError
from ldap3.core.exceptions import LDAPSocketReceiveError

from pprint                  import pprint
from base64                  import urlsafe_b64decode as dcode
from dateutil                import parser as dateparser
from twisted.internet.defer  import inlineCallbacks
from autobahn.twisted.wamp   import ApplicationSession
from autobahn.wamp.exception import ApplicationError


# configparser helpers
def _cfg_None(config, section, key):
    return config.get(section, key, fallback=None) or \
        config.get('default', key, fallback=None) or \
        None

def _cfg_List(config, section, key):
    v = _cfg_None(config, section, key)
    if not v:
        return
    return [x for x in v.replace(',', ' ').split(' ') if x]


class LDAP():
    def __init__(self, cfg):
        self.cfg         = cfg
        self.valid_names = _cfg_List(cfg, 'ldap', 'valid_names')
        self.host        = cfg.get('ldap', 'host', fallback='127.0.0.1')
        self.port        = int(cfg.get('ldap', 'port', fallback='389'))
        self.base        = cfg.get('ldap', 'base')
        self.userdn      = cfg.get('ldap', 'userdn')
        self.passwd      = cfg.get('ldap', 'userpassword')
        self.retry_connect()

    def retry_connect(self):
        deadtime = datetime.datetime.utcnow() + datetime.timedelta(seconds=60)
        self.ctx = None

        while deadtime > datetime.datetime.utcnow():
            try:
                ca_file = '/etc/ssl/certs/ca-certificates.crt'
                tlso    = Tls(ca_certs_file=ca_file,
                              validate=ssl.CERT_REQUIRED,
                              valid_names=self.valid_names)
                server  = Server(host=self.host,
                                 port=self.port,
                                 use_ssl=False,
                                 get_info=ALL,
                                 tls=tlso)
                ctx     = Connection(server,
                                  user=self.userdn,
                                  password=self.passwd,
                                  raise_exceptions=True,
                                  authentication=SIMPLE)
                ctx.open()
                ctx.start_tls()
                if not ctx.bind():
                    print('oh shit, authenticator failed to bind')
                    raise Exception('Failed to bind')
                break

            except (LDAPSessionTerminatedByServerError, LDAPSocketReceiveError) as e:
                print('LDAP server connect error: {}'.format(e))
                time.sleep(1)

            except Exception as e:
                print('LDAP error: {}'.format(e))
                raise

        self.ctx = ctx


    def rsearch(self, base=None, filter=None, attributes=ALL_ATTRIBUTES):
        # allow secondary exceptions to raise
        if not base:
            base = self.base
        try:
            self.ctx.search(base, filter, attributes=attributes)
            print('search finished')
        except (LDAPSessionTerminatedByServer, LDAPSocketReceiveError):
            self.retry_connect()
            self.ctx.search(base, filter, attributes=attributes)



class AuthenticatorSession(ApplicationSession):
    @inlineCallbacks
    def onJoin(self, details):
        print("WAMP-Ticket dynamic authenticator joined: {}".format(details))

        # we expect to be started by crossbar and crossbar's CWD will be $path/.crossbar/
        # allow exceptions to propogate up to the router
        cfg = configparser.ConfigParser()
        cfg.read('../butterflydns.conf')
        host,*port = (cfg['ldap']['host']).rsplit(':',1)
        port       = port and port[0] or '389'
        cfg['ldap']['host'] = host
        cfg['ldap']['port'] = cfg.get('ldap', 'port', fallback=port)

        for key in ('valid_names','host','userdn','userpassword','base'):
            if not cfg.get('ldap', key):
                s = "section [ldap]; required config option '{}' not found".format(key)
                raise KeyError(s)

        self.cfg = cfg
        self._ldap = LDAP(cfg)

        def checkPassword(challenge_password, password):
            challenge_bytes = dcode(challenge_password)[6:]
            digest,salt     = challenge_bytes[:20],challenge_bytes[20:]
            hr = hashlib.sha1(password.encode())
            hr.update(salt)
            return digest == hr.digest()

        def authenticate(realm, authid, details):
            print("WAMP-Ticket dynamic authenticator invoked: realm='{}', authid='{}', details=".format(realm, authid))
            pprint(details)
            gnow = datetime.datetime.now(datetime.timezone.utc)
            ticket = details['ticket']

            attributes=['rolePassword','notBefore','notAfter','realm','role','roleAdmin',
                       'cbtid','cbtidExpires','department','displayName','jpegPhoto']

            self._ldap.rsearch(filter='(roleUsername={authid})'.format(authid=authid),
                 attributes=attributes)

            if not len(self._ldap.ctx.response) == 1:
                raise ApplicationError(u'org.head.butterflydns.invalid_credentials',
                  "could not authenticate session - invalid credentials '{}' for principal {}"\
                  .format(ticket, authid))

            principal = self._ldap.ctx.response[0]['attributes']

            if not isinstance(principal['realm'], list):
                principal['realm'] = [principal['realm']]

            if not 'roleAdmin' in principal:
                principal['roleAdmin'] = [False]
            if not 'jpegPhoto' in principal:
                principal['jpegPhoto'] = ['']
            if not 'displayName' in principal:
                principal['displayName'] = [authid]
            if not 'department' in principal:
                principal['department'] = ['bit mover']
            if not isinstance(principal['department'], list):
                principal['department'] = [principal['department']]
            if not len(principal['department']):
                principal['department'] = ['bit mover']

            if 'jpegPhoto' in principal and principal['jpegPhoto']:
                if isinstance(principal['jpegPhoto'], list):
                    principal['jpegPhoto'] = [base64.b64encode(p) for p in principal['jpegPhoto']]
                else:
                    principal['jpegPhoto'] = base64.b64encode(principal['jpegPhoto'])

            if not 'notBefore' in principal and 'notAfter' in principal:
                raise ApplicationError(u'org.head.butterflydns.invalid_role_configured',
                  "couldn't authenticate session - invalid role configuration '{}' for principal {}"\
                  .format(ticket, authid))

            # .strftime('%Y%m%d%H%M%SZ')
            nB = dateparser.parse(principal['notBefore'][0])
            nA = dateparser.parse(principal['notAfter'][0])
            if not ( nB < gnow < nA ):
                raise ApplicationError(u'org.head.butterflydns.expired_ticket', "could not authenticate session - expired ticket '{}' for principal {}".format(ticket, authid))

            if not checkPassword(principal['rolePassword'][0], ticket):
                raise ApplicationError(u'org.head.butterflydns.invalid_credentials', "could not authenticate session - invalid credentials '{}' for principal {}".format(ticket, authid))

            res = {
                'realm': principal['realm'][0],
                'role':  principal['role'][0],
                'extra': {
                     'roleAdmin': principal['roleAdmin'],
                     'jpegPhoto': principal['jpegPhoto'],
                     'department': principal['department'],
                     'displayName': principal['displayName']
                }
            }

            resp = {
                'realm': principal['realm'],
                'role':  principal['role'],
                'extra': {
                     'roleAdmin': principal['roleAdmin'],
                     'jpegPhoto': '<suppressed>',
                     'department': principal['department'],
                     'displayName': principal['displayName']
                }
            }

            print("WAMP-Ticket authentication success: {}".format(resp))
            return res

    try:
        yield self.register(authenticate, 'org.head.butterflydns.authenticate')
        print("WAMP-Ticket dynamic authenticator registered!")
    except Exception as e:
        print("Failed to register dynamic authenticator: {0}".format(e))
