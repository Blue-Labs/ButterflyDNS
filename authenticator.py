
"""
This is the integrated component for crossbar that does dynamic authentication. Crossbar
will instantiate the below AuthenticatorSession() class, you do not need to run this
yourself.
"""

__version__  = '1.0'
__author__   = 'David Ford <david@blue-labs.org>'
__email__    = 'david@blue-labs.org'
__date__     = '2016-Apr-14 00:31Z'
__license__  = 'Apache 2.0'


import os
import ssl
import base64
import hashlib
import datetime
import configparser
from dateutil import parser as dateparser
from ldap3 import Server, Connection, Tls, ALL, ALL_ATTRIBUTES, AUTH_SIMPLE
from ldap3 import LDAPInvalidCredentialsResult, LDAPSizeLimitExceededResult, LDAPException
from ldap3.core.exceptions import LDAPSessionTerminatedByServer
from ldap3.utils.log import set_library_log_detail_level, set_library_log_activation_level
from ldap3.utils.log import OFF, BASIC, NETWORK, EXTENDED

from pprint import pprint
from base64 import urlsafe_b64decode as dcode

from twisted.internet.defer import inlineCallbacks

from autobahn.twisted.wamp import ApplicationSession
from autobahn.wamp.exception import ApplicationError


# configparser helpers
def _cfg_None(config, section, key):
   return  config.get(section, key, fallback=None) or \
      config.get('default', key, fallback=None) or \
      None

def _cfg_List(config, section, key):
   v = _cfg_None(config, section, key)
   if not v:
      return
   return [x for x in v.replace(',', ' ').split(' ') if x]


class LDAP():
   def __init__(self):
      valid_names = _cfg_List(cfg, 'ldap', 'valid_names')
      host        = cfg.get('ldap', 'host', fallback='127.0.0.1')
      port        = int(cfg.get('ldap', 'port', fallback='389'))
      userdn      = cfg.get('ldap', 'userdn')
      passwd      = cfg.get('ldap', 'userpassword')

      try:
         ca_file = '/etc/ssl/certs/ca-certificates.crt'
         tlso    = Tls(ca_certs_file=ca_file, validate=ssl.CERT_REQUIRED,
                       valid_names=valid_names)
         server  = Server(host, port=port, use_ssl=False, tls=tlso)
         ctx     = Connection(server, userdn, passwd, raise_exceptions=True,
                       authentication=AUTH_SIMPLE)

         ctx.open()
         ctx.start_tls()
         if not ctx.bind():
            print('oh shit, authenticator failed to bind')
            raise Exception('Failed to bind')
      except Exception as e:
         raise
      self.ctx = ctx



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

      for key in ('valid_names','host','userdn','userpassword'):
         if not cfg.get('ldap', key):
            s = "LDAP; required config option '{}' not found".format(key)
            raise KeyError(s)
      
      self.cfg = cfg

      _ldap = LDAP(cfg)
      self.ctx = _ldap.ctx

      def checkPassword(challenge_password, password):
         challenge_bytes = dcode(challenge_password[6:])
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
         
         try:
            self.ctx.search('ou=ButterflyDNS,dc=head,dc=org',
               '(roleUsername={authid})'.format(authid=authid),
               attributes=attributes)
         except LDAPSessionTerminatedByServer:
            _ldap = LDAP(self.cfg)
            self.ctx = _ldap.ctx
            self.ctx.search('ou=ButterflyDNS,dc=head,dc=org',
               '(roleUsername={authid})'.format(authid=authid),
               attributes=attributes)

         if not len(self.ctx.response) == 1:
            raise ApplicationError(u'org.head.butterflydns.invalid_credentials',
              "could not authenticate session - invalid credentials '{}' for principal {}"\
              .format(ticket, authid))

         principal = self.ctx.response[0]['attributes']
         if not 'roleAdmin' in principal:
            principal['roleAdmin'] = [False]
         if not 'jpegPhoto' in principal:
            principal['jpegPhoto'] = ['']
         if not 'displayName' in principal:
            principal['displayName'] = [authid]
         if not 'department' in principal:
            principal['department'] = ['bit mover']

         if principal['jpegPhoto'][0]:
            principal['jpegPhoto'] = [base64.b64encode(principal['jpegPhoto'][0])]
            
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
               'roleAdmin': principal['roleAdmin'][0],
               'jpegPhoto': principal['jpegPhoto'][0],
               'department': principal['department'][0],
               'displayName': principal['displayName'][0]
            }
         }

         resp = {
            'realm': principal['realm'][0],
            'role':  principal['role'][0],
            'extra': {
               'roleAdmin': principal['roleAdmin'][0],
               'jpegPhoto': '<suppressed>',
               'department': principal['department'][0],
               'displayName': principal['displayName'][0]
            }
         }
         
         print("WAMP-Ticket authentication success: {}".format(resp))
         return res

      try:
         yield self.register(authenticate, 'org.head.butterflydns.authenticate')
         print("WAMP-Ticket dynamic authenticator registered!")
      except Exception as e:
         print("Failed to register dynamic authenticator: {0}".format(e))
