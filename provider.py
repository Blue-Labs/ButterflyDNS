
"""
This is the standalone provider for crossbar that provides all the RPCs and pub/sub for
operation of ButterflyDNS
"""

__version__  = '1.5'
__author__   = 'David Ford <david@blue-labs.org>'
__email__    = 'david@blue-labs.org'
__date__     = '2017-Jul-31 02:02Z'
__license__  = 'Apache 2.0'

import aiopg
import asyncio
import base64
import configparser
import datetime
import logging
import pythonwhois
import re
import ssl
import time
import traceback
import txaio
import warnings

warnings.resetwarnings()
logging.basicConfig(level=logging.DEBUG)
logging.captureWarnings(True)

import dns.exception
import dns.query
import dns.message
from dns.rdatatype import A, AAAA, NS, MX, to_text
from dns.resolver import Resolver
from dns.rcode import NOERROR
from dns.rcode import NXDOMAIN

from ldap3 import Server
from ldap3 import Connection
from ldap3 import Tls
from ldap3 import ALL_ATTRIBUTES
from ldap3 import ALL
from ldap3 import SUBTREE
from ldap3 import LEVEL
from ldap3 import MODIFY_ADD
from ldap3 import MODIFY_REPLACE
from ldap3 import MODIFY_DELETE
from ldap3 import SIMPLE
from ldap3 import HASHED_SALTED_SHA
from ldap3.core.exceptions import LDAPInvalidCredentialsResult
from ldap3.core.exceptions import LDAPSizeLimitExceededResult
from ldap3.core.exceptions import LDAPException
from ldap3.core.exceptions import LDAPSessionTerminatedByServerError
from ldap3.core.exceptions import LDAPSocketReceiveError
from ldap3.core.exceptions import LDAPAttributeOrValueExistsResult
from ldap3.core.exceptions import LDAPNoSuchAttributeResult
from ldap3.utils.hashed import hashed

from autobahn                import wamp
from autobahn.asyncio.wamp   import ApplicationSession, ApplicationRunner
from autobahn.wamp.types     import PublishOptions, SubscribeOptions, RegisterOptions

txaio.start_logging(level='info')

# DNS foo
gtld_ns = ['192.43.172.30', '192.41.162.30', '192.54.112.30', '192.35.51.30', '192.12.94.30',
           '192.26.92.30',  '192.42.93.30',  '192.55.83.30',  '192.5.6.30',   '192.48.79.30',
           '192.52.178.30', '192.33.14.30',  '192.31.80.30']

def get_name_rdtype_from_rrsets(rrsets, rdtypes=[A]):
    if not rrsets:
        raise ValueError
    results = []
    for rrset in rrsets:
      for a in rrset:
        if a.rdtype in rdtypes:
          if a.rdtype in (A,AAAA):
            _str = a.address
          elif a.rdtype == MX:
            _str = a.exchange.to_text()
          elif a.rdtype == NS:
            _str = a.to_text()
          else:
            print('  cannot determine which attribute to use for rdtype: {}'.format(a.rdtype))
            print(dir(a))
            results.append( 'cannot determine which attribute to use for rdtype: {}'.format(a.rdtype) )

          _t = (rrset.name.to_text(), a.rdtype, _str)
          results.append( _t )

    return results

@asyncio.coroutine
def _recurse_for_type(zone, _types, nsgroup=gtld_ns):
    answers = []
    for _otype in _types:
        _type = _otype
        while True:
            #print('resolving {} for {} at {}'.format(_type, zone, nsgroup))
            response = yield from _get_answers(zone, _type, nsgroup)

            # warning, response can be None, handle this
            if response.answer:
                answers += [x[2] for x in get_name_rdtype_from_rrsets(response.answer, _types)]
                break

            if not response.additional:
                # meh, got a referral to another set of root servers
                if not response.authority:
                    # error matey, this resource record does not exist [any more]
                    break

                __ = [x[2] for x in get_name_rdtype_from_rrsets(response.authority, [NS])]
                if not __: # again, no RR available
                    break

                nsgroup = __

                # just look up the first entry, we'll get all of them
                response = yield from _get_answers(nsgroup[0], A, gtld_ns)

            nsgroup = [x[2] for x in get_name_rdtype_from_rrsets(response.additional, [A,AAAA])]

    return answers

@asyncio.coroutine
def _get_answers(zone, _type, nsgroup):
        if not zone[-1] == '.':
            zone += '.'

        yield from asyncio.sleep(0.1)
        q = dns.message.make_query(zone, _type)

        if not isinstance(nsgroup, list):
            nsgroup = [nsgroup]

        response = None
        for ns in nsgroup:
            try:
                yield from asyncio.sleep(0.1)
                response = dns.query.tcp(q, ns, timeout=1)
                yield from asyncio.sleep(0.1)
            except dns.exception.Timeout:
                print('  [31mDNS timeout[0m for {}'.format(ns))
                continue
            except OSError:
                # ipv6 not supported?
                print('oserror')
                continue

            except Exception as e:
                print('{}'.format(e.__class__))
                print('wtf: dom:{} ns:{} q:{}'.format(zone, ns, q))
                raise

            if response.rcode() == NOERROR:
                break


            if not response.rcode() == NXDOMAIN:
                print('unexpected rcode: {}'.format(response.rcode()))

        return response

@asyncio.coroutine
def Bget_zone_ns_glue(zone):
        print('get zone glue for: {!r}'.format(zone))

        zone         = zone.strip('.')

        # get NS for TLD
        tld     = zone.split('.')[-1]
        nsgroup = gtld_ns

        while True:
            response = yield from _get_answers(tld, NS, nsgroup)
            if len(response.additional):
                try:
                    nsgroup = [x[2] for x in get_name_rdtype_from_rrsets(response.additional, [A,AAAA])]
                except:
                    print('breakfuck1')
                    raise
                break

            # meh, got a referral to another set of root servers
            try:
                nsgroup = [x[2] for x in get_name_rdtype_from_rrsets(response.authority, [NS])]
            except:
                print('breakfuck2')
                raise

            # just look up the first entry, we'll get all of them
            response = yield from _get_answers(nsgroup[0], A, gtld_ns)
            try:
                nsgroup = [x[2] for x in get_name_rdtype_from_rrsets(response.additional, [A,AAAA])]
            except:
                print('breakfuck3')
                raise

        # ask TLD ns for zone's glue records
        is_done = False
        while not is_done:
            response = yield from _get_answers(zone, NS, nsgroup)

            # set nsgroup to null to force an error
            nsgroup = []

            if response.rcode() != NOERROR:
                return [to_text(response.rcode())]

            section = response.answer or response.authority or None

            if section:
                for rrset in section:
                    if rrset.name.to_text().strip('.') == zone:
                        is_done = True
                        break

                # section didn't have our zone as the target, does it have nameservers?
                nsgroup  = [x[2] for x in get_name_rdtype_from_rrsets(section, [NS])]

            elif response.additional:
                nsgroup = [x[2] for x in get_name_rdtype_from_rrsets(response.additional)]

            # split this into two, detect RFC1918 vs otherwise blackholed answers
            if sorted(nsgroup) == ['blackhole-1.iana.org.','blackhole-2.iana.org.']:
                print(response)
                print('warning, blackholed nameservers found')
                return []
                #raise ApplicationError('org.head.butterflydns.get_zone_glue', 'Blackholed nameservers found')

            if not nsgroup:
                print(response)
                print('empty list')
                #raise ApplicationError('org.head.butterflydns.get_zone_glue', 'empty nameserver list')
                return {'error':'Error, empty list'}

        final = {}

        if len(response.additional):
            for k,_dummy,v in get_name_rdtype_from_rrsets(response.additional, [A,AAAA]):
                if not k in final:
                    final[k] = []
                final[k].append(v)

        else:
            # oh shit holio.
            resolver = Resolver()
            resolver.search = []
            resolver.timeout = 8.0
            resolver.lifetime = 16.0
            resolver.nameservers = gtld_ns

            nsgroup = [x[2] for x in get_name_rdtype_from_rrsets(response.authority, [NS])]

            for k in nsgroup:
                _ = yield from _recurse_for_type(k, [A,AAAA])
                if not k in final:
                    final[k] = []
                final[k] += _

        rv = []

        for k in sorted(final):
          rv.append( {k:sorted(final[k])} )

        print('finished',rv)
        return rv


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
                tlso    = Tls(ca_certs_file=ca_file, validate=ssl.CERT_REQUIRED,
                              valid_names=self.valid_names)
                server  = Server(self.host, port=self.port, use_ssl=False, tls=tlso)
                ctx     = Connection(server, user=self.userdn, password=self.passwd,
                                  raise_exceptions=True, authentication=SIMPLE)
                ctx.open()
                ctx.start_tls()
                if not ctx.bind():
                    print('oh shit, authenticator failed to bind')
                    raise Exception('Failed to bind')
                break

            except (LDAPSessionTerminatedByServerError, LDAPSocketReceiveError):
                time.sleep(1)

            except Exception as e:
                print(e)
                raise

        self.ctx = ctx


    def rsearch(self, base=None, filter=None, attributes=ALL_ATTRIBUTES):
        # allow secondary exceptions to raise
        if not base:
            base = self.base
        try:
            self.ctx.search(base, filter, attributes=attributes)
            print('search finished')
        except LDAPSessionTerminatedByServer:
            self.retry_connect()
            self.ctx.search(base, filter, attributes=attributes)


class ButterflyDNS(ApplicationSession):

    log   = logging.getLogger()
    pool  = None
    _ldap = None
    cache = {}
    topic_subscribers = {}

    @asyncio.coroutine
    def meta_on_join(self, details, b):
        print('meta_on_join:')
        print('details: {}'.format(details))
        print('b: {}'.format(b))
        #topic = yield self.call("wamp.subscription.get", b)
        #print('create topic:',topic)
        #yield self.publish('org.head.butterflydns.zones.get_all', self.get_zones.get_all())

    @asyncio.coroutine
    def meta_on_create(self, details, b):
        print('meta_on_create:')
        print('someone created, push them zones list')
        print('details: {}'.format(details))
        print('b: {}'.format(b))
        topic = yield from self.call("wamp.subscription.get", b)
        print('create topic:',topic)
        #yield self.publish('org.head.butterflydns.zones.get_all', self.get_zones.get_all())

    # since session.call('wamp.subscription*') breaks no matter what method is tried, we have
    # to resort to this
    @asyncio.coroutine
    def meta_on_subscribe(self, subscriberid, sub_details, details):
        print('meta_on_subscribe: sid:{}, sub_d:{}, d:{}'.format(subscriberid, sub_details, details))
        topic = yield from self.call("wamp.subscription.get", sub_details)
        print('\x1b[1;32m{} subscribed to {}\x1b[0m'.format(subscriberid, topic['uri']))
        if not topic['uri'] in self.topic_subscribers:
            self.topic_subscribers[topic['uri']] = []
        if not subscriberid in self.topic_subscribers[topic['uri']]:
            self.topic_subscribers[topic['uri']].append(subscriberid)

        #print('sub is: {}'.format(sub))
        #print('sub details and details object: {} {}'.format(sub_details, details))
        #print('details: {}'.format(details))
        #print('subscribe topic:',topic)
        #yield from self.publish('org.head.butterflydns.zones.get_all', self.get_zones.get_all())


    @asyncio.coroutine
    def meta_on_unsubscribe(self, subscriberid, sub_details, details):
        print('meta_on_unsubscribe: sid:{}, sub_d:{}, d:{}'.format(subscriberid, sub_details, details))
        try:
            topic = yield from self.call("wamp.subscription.get", sub_details)
            print('\x1b[1;32m{} unsubscribed from {}\x1b[0m'.format(subscriberid, topic['uri']))

            if topic['uri'] in self.topic_subscribers and subscriberid in self.topic_subscribers[topic['uri']]:
              self.topic_subscribers[topic['uri']].remove(subscriberid)
        #except wamp.error.no_such_subscription:
        #    print('nss')
        except Exception as e:
            print('fnucky: {}'.format(e))
            print('fnarcky: {}'.format(e.__class__))

        #print('sub is: {}'.format(sub))
        #print('sub details and details object: {} {}'.format(sub_details, details))
        #print('details: {}'.format(details))
        #print('subscribe topic:',topic)
        #yield from self.publish('org.head.butterflydns.zones.get_all', self.get_zones.get_all())

    # DNS db methods
    @asyncio.coroutine
    def _make_dict_list(self, curs, rows=None):
        if not rows:
            rows = yield from curs.fetchall()

        columns = [d.name for d in curs.description]
        rt = []

        try:
            for r in rows:
                _ = dict(zip(columns, r))

                # make strings out of timestamps and trim to 1sec precision, also convert from TZ to UTC
                for key in ('created','updated'):
                    if key in _:
                        ts = _[key]
                        #print('set ts to: [{}] {} on row: {}'.format(key,ts,_))
                        try:
                            ts = _[key].astimezone(tz=datetime.timezone.utc)
                        except Exception as e:
                            print('Missing create/update data on row')
                            print(curs.query.decode())
                            print(_)
                            print('---')
                            ts = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

                        ts = ts.replace(microsecond=0).strftime('%F %T')
                        _[key] = ts

                # make priority an integer
                for key in ('priority','ttl'):
                    try:    _[key] = int(_[key],10)
                    except: pass

                if 'soa' in _ or ('type' in _ and _['type'] == 'SOA'):
                    if 'soa' in _:
                        soa = _['soa']
                    else:
                        soa = _['data']

                    primary_ns,contact,serial,refresh,retry,expire,minimumttl = soa.strip().split(' ')

                    if not '@' in contact:
                        a,b = contact.split('.',1)
                        contact = a+'@'+b.strip('.')

                    serial     = int(serial,10)
                    refresh    = int(refresh,10)
                    retry      = int(retry,10)
                    expire     = int(expire,10)
                    minimumttl = int(minimumttl,10)


                    _t = {'primary_ns':primary_ns, 'contact':contact,
                          'serial':serial,
                          'refresh':refresh, 'retry':retry, 'expire':expire, 'minimumttl':minimumttl}

                    if 'soa' in _:
                        _['soa']  = _t
                    else:
                        _['data'] = _t

                rt.append(_)

        except Exception as e:
            print(e)
            traceback.print_exc()

        return rt


    def onConnect(self):
        realm = self.config.realm
        authid = self.config.extra['cfg'].get('provider', 'roleUsername', fallback=None)
        print("ClientSession connected:          Joining realm <{}> under authid <{}>".format(realm if realm else 'not provided', authid))
        self.join(realm, ['ticket'], authid)
        self._ldap = LDAP(self.config.extra['cfg'])


    def onChallenge(self, challenge):
        print("ClientSession challenge received: {}".format(challenge))
        if challenge.method == 'ticket':
            return self.config.extra['cfg'].get('provider', 'rolePassword', fallback=None)
        else:
            raise Exception("Invalid authmethod {}".format(challenge.method))


    @asyncio.coroutine
    def onJoin(self, details):
        print('ClientSession onJoin:             {}',details)
        if not self.pool:
            host     = self.config.extra['cfg'].get('postgresql', 'host')
            port     = int(self.config.extra['cfg'].get('postgresql', 'port', fallback=5432))
            database = self.config.extra['cfg'].get('postgresql', 'database')
            user     = self.config.extra['cfg'].get('postgresql', 'user')
            password = self.config.extra['cfg'].get('postgresql', 'password')

            self.pool = yield from aiopg.create_pool(host=host, port=port,
                                    database=database, user=user, password=password)
        if not self._ldap:
            self._ldap = LDAP(self.config.extra['cfg'])

        sublist = yield from self.call('wamp.subscription.list')
        print('onjoin sublist:',sublist)

        yield from self.register(self, options=RegisterOptions(details_arg='detail'))
        yield from self.subscribe(self.meta_on_join, 'wamp.subscription.on_join')
        yield from self.subscribe(self.meta_on_subscribe, 'wamp.subscription.on_subscribe', options=SubscribeOptions(details_arg="details"))
        yield from self.subscribe(self.meta_on_unsubscribe, 'wamp.subscription.on_unsubscribe', options=SubscribeOptions(details_arg="details"))
        #yield from self.subscribe(self.send_records, 'org.head.butterflydns.zone.send_records', options=SubscribeOptions(details_arg="details", match='prefix'))

        while True:
            #print('.')
            yield from asyncio.sleep(1)


    #@asyncio.coroutine
    #def onOpen(self, details):
    #    print('ClientSession open and running:   {}'.format(details))
    #    while True:
    #        yield from asyncio.sleep(1)


    def onLeave(self, details):
        print("ClientSession left:               {}".format(details))
        self.disconnect()


    def onDisconnect(self):
        print('clientSession disconnected')
        asyncio.get_event_loop().stop()


    def onSubscribe(self, details):
        print('==========',details)


    def get_cache(self, _type, zone):
        '''Current cache types are:
             zone.registrar, zone.ns_glue

           cache expiration is 24 hours, or 5 minutes if within 30 days of registrar expiration
        '''
        data = None

        # delete all expired cache entries for this type
        now = datetime.datetime.utcnow()
        dels = [z for t in self.cache for z in t if _type in self.cache and z in self.cache[_type] and self.cache[_type][z]['expires'] > now ]
        if dels: print('expiring zone.registrar cache for: ',dels)
        for z in dels:
            del self.cache[_type][z]

        if _type in self.cache and zone in self.cache[_type]:
            data = self.cache[_type][zone]['data']

        if data: print('returning cache for {}.{}={}'.format(_type,zone,self.cache[_type][zone]))

        return data


    def set_cache(self, _type, zone, data, expires):
            if not _type in self.cache:
                self.cache[_type] = {}

            if not zone in self.cache[_type]:
                self.cache[_type][zone] = {}

            self.cache[_type][zone]['expires'] = expires
            self.cache[_type][zone]['data']    = data


    def segment_txt_rr(self, text):
        def _sgen(txt):
            seg_size = 255
            txt = txt.replace('"', '\\"').replace("'", "\\'")
            while txt:
                if txt[:seg_size].endswith('\\'):
                    r = txt[:seg_size-1]
                    txt = txt[seg_size-1:]
                else:
                    r = txt[:seg_size]
                    txt = txt[seg_size:]
                yield '"' + r + '"'

        return ' '.join([x for x in _sgen(text)])


    def unsegment_text_rr(self, rr):
        # reassemble TXT record segments in order found
        # "abc" "def" becomes "abcdef"
        def _genc(s):
            _l = len(s)
            for _c in s:
                yield _c

        if rr[0] == '"':
            rr = rr[1:-1]
            out = []
            _s = ''
            _gs = iter(_genc(rr))

            for c in _gs:
                if c == '\\':
                    c = next(_gs)

                elif c == '"':
                    out.append(_s)
                    _s = ''

                    while True:
                        try:
                            c = next(_gs)
                        except StopIteration:
                            break

                        if c == '"':
                            break

                    continue

                _s += c

            out.append(_s)
            rr = ''.join(out)

        print('reassembled TXT: {}'.format(rr))
        return rr


    @wamp.register('org.head.butterflydns.role.lookup')
    def role_lookup(self, *args, **details):
        print('role lookup args: {}'.format(args))
        print('role lookup details: {}'.format(details['detail']))
        #for k in ('caller','caller_authid', 'caller_authrole', 'enc_algo', 'procedure', 'progress'):
        #  print('  {:<30}={}'.format(k,getattr(details['detail'], k)))

        attributes=['rolePassword','notBefore','notAfter','realm','role','roleAdmin',
                     'cbtid','cbtidExpires','department','displayName','jpegPhoto']
        authid=details['detail'].caller_authid

        try:
            self._ldap.rsearch(filter='(roleUsername={authid})'.format(authid=authid),
               attributes=attributes)
        except Exception as e:
            print('exc: {}'.format(e))
            raise ApplicationError('org.head.butterflydns.search_error', e)

        try:
            # WAMP cannot handle a dict like object from ldap, it has to be a real dict
            principal={}
            principal.update(self._ldap.ctx.response[0]['attributes'])

            if 'jpegPhoto' in principal
                if principal['jpegPhoto']:
                    if isinstance(principal['jpegPhoto'], list):
                        principal['jpegPhoto'] = [base64.b64encode(p) for p in principal['jpegPhoto']]
                    else:
                        principal['jpegPhoto'] = [base64.b64encode(principal['jpegPhoto'])]
                else:
                    principal['jpegPhoto'] = ['']
            else:
                principal['jpegPhoto'] = ['']

            if args and 'all-attributes' in args[0]:
                del principal['userPassword']
                return principal

            if not 'roleAdmin' in principal:
               principal['roleAdmin'] = [False]
            if not 'displayName' in principal:
               principal['displayName'] = [authid]
            if not 'department' in principal:
               principal['department'] = ['bit mover']

            res = {
                'extra': {
                    'roleAdmin': principal['roleAdmin'],
                    'jpegPhoto': principal['jpegPhoto'],
                    'department': principal['department'],
                    'displayName': principal['displayName']
                }
            }

        except Exception as e:
            print('buttpuff {}'.format(e))
            traceback.print_exc()
            raise ApplicationError('org.head.butterflydns.search_error', e)

        return res


    @wamp.register('org.head.butterflydns.zones.summary.trigger')
    def _zones_summary(self, **args):
        detail = args['detail']
        print('zones.summary(caller={})'.format(detail.caller))

        #@asyncio.coroutine
        def __yield(uri, data):
            yield from self.publish(uri, data)

        @asyncio.coroutine
        def f__g(pool):
            with (yield from pool.cursor()) as cur:
              yield from cur.execute('''SELECT  zone.name||'.'||tld.extension as zone,
                               record.data as soa,
                               owners.manager,
                               record.created,
                               record.updated
                         FROM  zone
                          JOIN tld
                            ON tld.rid = zone.tld
                          JOIN record
                            ON record.zone = zone.rid AND type='SOA'
                          JOIN owners ON owners.manager = zone.manager
                         ORDER BY name,extension''')

              _ = yield from cur.fetchall()
              _ = yield from self._make_dict_list(cur, _)
              print('publishing {} zones'.format(len(_)))

              try:
                print('topic subscribers: {}'.format(self.topic_subscribers['org.head.butterflydns.zones.summary']))
                exc = [s for s in self.topic_subscribers['org.head.butterflydns.zones.summary'] if not s == detail.caller]
              except:       # sometimes this trigger comes in BEFORE the client subscription event fires which means
                exc = None  # for the first subscriber, we don't know anything about this topic yet

              self.push_pub('org.head.butterflydns.zones.summary', _, options={'exclude':exc, 'eligible':[detail.caller]})

        yield from f__g(self.pool)


    @asyncio.coroutine
    def _get_zone_soa(self, zone):
        with (yield from self.pool.cursor()) as cur:
            yield from cur.execute('''SELECT  c.content as zone,
                                 r.created,r.updated,r.data,r.type,r.host,r.priority,r.ttl
                           FROM  record r,
                                 canonical c
                          WHERE  c.content = %(zone)s
                            AND  r.zone=c.domain
                            AND  r.type='SOA'
                           ''', {'zone':zone})

            _ = yield from cur.fetchone()
            _ = (yield from self._make_dict_list(cur, [_]))[0]

            # note, SOA updates go to everyone
            return ('org.head.butterflydns.zone.records.get.soa', _)


    @asyncio.coroutine
    def _update_zone_soa(self, zone, ts):
        with (yield from self.pool.cursor()) as cur:
            # update SOA, fetch existing record
            yield from cur.execute('''SELECT  r.data
                                        FROM  record r, canonical c
                                       WHERE  c.content  = %(zone)s
                                         AND  r.zone     = c.domain
                                         AND  r.type     = 'SOA'
                                   ''', {'zone':zone})

            soa = (yield from cur.fetchone())[0]

            # soa timestamp is 3rd element
            soa = soa.split(' ')
            soa = soa[:2]+[ts.strftime('%s')]+soa[3:]
            soa = ' '.join(soa)

            yield from cur.execute('''UPDATE  record r
                                         SET  (data,updated) = (%(soa)s, %(now)s)
                                        FROM  canonical c
                                       WHERE  c.content  = %(zone)s
                                         AND  r.zone     = c.domain
                                         AND  r.type     = 'SOA'
                                   ''', {'zone':zone, 'soa':soa, 'now':ts})

            return (yield from self._get_zone_soa(zone))


    @asyncio.coroutine
    def _get_zone_local(self, zone):
        with (yield from self.pool.cursor()) as cur:
            yield from cur.execute('''SELECT  c.content as zone,
                               c.admin as manager, c.owner,
                               r.created,r.updated
                         FROM  record r,
                               canonical c
                        WHERE  c.content = %(zone)s
                          AND  r.zone=c.domain
                          AND  r.type='SOA'
                         ''', {'zone':zone})

            _ = yield from cur.fetchone()
            _ = (yield from self._make_dict_list(cur, [_]))[0]
            return ('org.head.butterflydns.zone.records.get.local.'+zone, _)

    @asyncio.coroutine
    def _get_zone_transfer_acl(self, zone):
        with (yield from self.pool.cursor()) as cur:
          yield from cur.execute('''SELECT  r.rid as rid, r.client, r.created, r.updated
                         FROM  xfr r,
                               canonical c
                        WHERE  c.content = %(zone)s
                          AND  r.zone=c.domain
                         ''', {'zone':zone})

          _ = yield from cur.fetchall()
          # convert cidr hosts into just host
          _ = [(x,re.sub('(/(?:32|128))$','',y),a,b) for x,y,a,b in _ ]
          _ = yield from self._make_dict_list(cur, _)
          data = {'zone':zone, 'data':_}
          return ('org.head.butterflydns.zone.records.get.zone_transfer_acl.'+zone, data)

    @asyncio.coroutine
    def _get_zone_resourcerecords(self, zone):
        with (yield from self.pool.cursor()) as cur:
            yield from cur.execute('''SELECT  c.content as zone,c.admin as manager,c.owner,
                                 r.created,r.updated,r.data,r.type,r.host,r.priority,r.ttl,r.rid
                           FROM  record r,
                                 canonical c
                          WHERE  c.content = %(zone)s
                            AND  r.zone=c.domain
                           ORDER BY r.type,r.host,r.priority,r.data''', {'zone':zone})

            _ = yield from cur.fetchall()
            if not _:
                return {}

            r = []

            # then default NS and MX records
            r += sorted([x for x in _ if x[6] == 'NS' and x[7] == '@'])
            r += sorted([x for x in _ if x[6] == 'MX' and x[7] == '@'])

            for i,x in enumerate(_):
                if x[6] in ('SOA','NS','MX'):
                    if x[6] == 'SOA': continue
                    if x[6] == 'NS' and x[7] == '@': continue
                    if x[6] == 'MX' and x[7] == '@': continue

                if x[6] == 'TXT':
                    _[i] = (x[0],x[1],x[2],x[3],x[4],self.unsegment_text_rr(x[5]),x[6],x[7],x[8],x[9],x[10])

                r.append(x)

            r2 = []
            for _ in r:
                if '"' in _[5]:
                    _new = ''
                    _in = False
                    for e,_c in enumerate(_[5]):
                        if _c == ' ':
                            if not _in:
                                continue
                        if _c == '"':
                            _in = not _in
                            continue

                        _new += _c
                    _ = _[:5]+(_new,)+_[6:]
                r2.append(_)

            data = yield from self._make_dict_list(cur, r2)
            data={'zone':zone, 'data':data}

            return ('org.head.butterflydns.zone.records.get.resourcerecords.'+zone, data)


    @asyncio.coroutine
    def _get_zone_registrar(self, zone):
        '''This is a SLOW callback and can take several seconds
        '''
        data = self.get_cache('zone.registrar', zone)
        if not data:
            try:
                w = pythonwhois.get_whois(zone)
            except Exception as e:
                print('kapew on pythonwhois: {}: {}'.format(zone,e))
                w = {'registrar':[''], 'status':str(e)}

            expires = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            if 'expiration_date' in w:
                daysleft = str((w['expiration_date'][0] - datetime.datetime.utcnow()).days)+' days left'
                if (w['expiration_date'][0] - datetime.datetime.utcnow()).days <= 30:
                    expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)

            if 'registrar' in w:
                data = { 'registrar': w['registrar'][0],
                         'status':    'creation_date' in w and w['status'][0].split(' ',1)[0] or w['status'],
                         'created':   'creation_date' in w and w['creation_date'][0].strftime('%F %T') or '',
                         'updated':   'updated_date' in w and w['updated_date'][0].strftime('%F %T') or '',
                         'expires':   'expiration_date' in w and w['expiration_date'][0].strftime('%F %T') + ' ('+ daysleft +')' or '',
                        }
            else:
                data = { 'registrar': '',
                         'status':    len(zone.split('.'))<3 and 'Not registered' or 'Tertiary hostname?',
                         'created':   '',
                         'updated':   '',
                         'expires':   '',
                       }
            data['zone'] = zone
            self.set_cache('zone.registrar', zone, data, expires)

        return ('org.head.butterflydns.zone.records.get.registrar.'+zone, data)


    @asyncio.coroutine
    def _get_zone_ns_glue(self, zone):
        '''This is a SLOW callback and can take several seconds
        '''
        try:
            data = self.get_cache('zone.ns_glue', zone)
            if not data:
                data = yield from Bget_zone_ns_glue(zone)

                # use same expiration delta as registrar, if we happen to be faster than the
                # registrar lookup, then simply don't cache this data set -- we'll cache it next
                # time
                if 'zone.registrar' in self.cache and zone in self.cache['zone.registrar']:
                    data = {'zone':zone, 'data':data}
                    self.set_cache('zone.ns_glue', zone, data, self.cache['zone.registrar'][zone]['expires'])
        except:
            traceback.print_exc()

        return ('org.head.butterflydns.zone.records.get.ns_glue.'+zone, data)


    #@inlineCallbacks
    def push_pub(self, uri, data, options=None):
        print('\x1b[1;33mpublishing to {}, options={}\x1b[0m'.format(uri,options))
        if options:
            self.publish(uri, data, options=PublishOptions(**options))
        else:
            self.publish(uri, data)


    @wamp.register('org.head.butterflydns.zone.records.send')
    def send_records(self, *args, **detail):
        for e in args:
            print('send_records received args: {}'.format(args))
        for k,v in detail.items():
            print('send_records: k={} v={}'.format(k,v))

        zone = args[0]

        if not zone:
            return

        def process_runner(zone):
            # run all of these concurrently
            tasks = [
                self._get_zone_soa(zone),
                self._get_zone_local(zone),
                self._get_zone_registrar(zone),
                self._get_zone_transfer_acl(zone),
                self._get_zone_resourcerecords(zone),
                self._get_zone_ns_glue(zone),
                ]

            for f in asyncio.as_completed(tasks):
                topic, result = yield from f

                self.push_pub(topic, result)

        yield from process_runner(zone)

        """
        @asyncio.coroutine
        def _get_zone_registrar(pool, zone):
            try:
                w = pythonwhois.get_whois(zone)
            except Exception as e:
                print('kapew on pythonwhois: {}: {}'.format(zone,e))
                w = {'registrar':[''], 'status':str(e)}

            if 'expiration_date' in w:
                daysleft = str((w['expiration_date'][0] - datetime.datetime.utcnow()).days)+' days left'

            if 'registrar' in w:
              _ = { 'registrar': w['registrar'][0],
                     'status':    'creation_date' in w and w['status'][0].split(' ',1)[0] or w['status'],
                     'created':   'creation_date' in w and w['creation_date'][0].strftime('%F %T') or '',
                     'updated':   'updated_date' in w and w['updated_date'][0].strftime('%F %T') or '',
                     'expires':   'expiration_date' in w and w['expiration_date'][0].strftime('%F %T') + ' ('+ daysleft +')' or '',
              }
            else:
              _ = { 'registrar': '',
                     'status':    len(zone.split('.'))<3 and 'Not registered' or 'Tertiary hostname?',
                     'created':   '',
                     'updated':   '',
                     'expires':   '',
              }

            self.push_pub('org.head.butterflydns.zone.records.get.registrar.'+zone, _)

        @asyncio.coroutine
        def _get_zone_ns_glue(pool, zone):
            _ = yield from Bget_zone_ns_glue(zone)
            self.push_pub('org.head.butterflydns.zone.records.get.ns_glue.'+zone, _)



        loop = asyncio.get_event_loop()
        loop.slow_callback_duration = 2.0

        # run all of these concurrently
        tasks = [
            asyncio.Task(self._get_zone_soa(zone)),
            asyncio.Task(self._get_zone_local(zone)),
            asyncio.Task(_get_zone_registrar(self.pool, zone)),
            asyncio.Task(self._get_zone_transfer_acl(zone)),
            asyncio.Task(self._get_zone_resourcerecords(zone)),
            asyncio.Task(_get_zone_ns_glue(self.pool, zone))
            ]

        try:
            loop.run_until_complete(asyncio.wait(tasks))
        except Exception as e:
            print('fuck me with a 3in footer: {}'.format(e))
    """

    @wamp.register('org.head.butterflydns.zone.record.add')
    def zone_record_add(self, *data, **detail):
        self.log.info('zone_record_add({!r}) {}'.format(data, detail))
        if not data:
            return {'success':False}

        @asyncio.coroutine
        def _zone_record_add(pool, data):
            with (yield from pool.cursor()) as cur:
                now         = datetime.datetime.utcnow();
                data        = data[0]
                data['now'] = now

                # if TTL is blank, make it None
                if data['ttl'] == '': data['ttl'] = None

                if data['type'] == 'TXT':
                    data['data'] = self.segment_txt_rr(data['data'])

                q = '''INSERT
                         INTO  record
                               (host,zone,ttl,type,priority,data,created,updated)
                       VALUES  (
                                %(host)s,
                                (SELECT c.domain as zone FROM canonical c WHERE c.content = %(zone)s),
                                %(ttl)s,
                                %(type)s,
                                %(priority)s,
                                %(data)s,
                                %(now)s,
                                %(now)s
                               )
                    RETURNING  rid
                               '''
                yield from cur.execute(q, data)
                rid = (yield from cur.fetchone())[0]
                (topic,_data) = yield from self._update_zone_soa(data['zone'], now)
                self.push_pub(topic,_data)

                if data['type'] == 'TXT':
                    data['data'] = self.unsegment_text_rr(data['data'])

                data['rid'] = rid

                # one of these days we ought to put created & updated somewhere in here
                data['created'] = data['now'].strftime('%F %T')
                data['updated']  = data['created']
                del data['now']

                self.push_pub('org.head.butterflydns.zone.records.get.single_rr.'+data['zone'], data)

            return {'success':True, 'rid':rid}

        return (yield from _zone_record_add(self.pool, data))


    @wamp.register('org.head.butterflydns.zone.record.update')
    def zone_record_update(self, *data, **detail):
        self.log.info('zone_record_update({!r}) {}'.format(data, detail))
        if not data:
            return {'success':False}

        @asyncio.coroutine
        def _zone_record_update(pool, data):
            with (yield from pool.cursor()) as cur:
                now  = datetime.datetime.utcnow();
                data = data[0]
                data['now'] = now

                if not data['ttl']: data['ttl'] = None

                if data['type'] == 'TXT':
                    data['data'] = self.segment_txt_rr(data['data'])

                # we don't need the old data any more, we have the row id
                yield from cur.execute('''UPDATE  record r
                                             SET  (host,ttl,type,priority,data,updated)
                                                  =
                                                  (%(host)s,%(ttl)s,%(type)s,%(priority)s,%(data)s,%(now)s)
                                            FROM  canonical c
                                           WHERE  c.content  = %(zone)s
                                             AND  r.zone     = c.domain
                                             AND  r.rid      = %(rid)s
                                       ''', data)

                # one of these days we ought to put created & updated somewhere in here
                data['updated'] = data['now'].strftime('%s')
                del data['now']

                if data['type'] == 'TXT':
                    data['data'] = self.unsegment_text_rr(data['data'])

                (topic,_data) = yield from self._update_zone_soa(data['zone'], now)
                self.push_pub(topic,_data)

                self.push_pub('org.head.butterflydns.zone.records.get.single_rr.'+data['zone'], data)

            return {'success':True}

        #loop = asyncio.get_event_loop()
        #z = loop.run_until_complete(_zone_record_update(self.pool, data))
        #return z
        return (yield from _zone_record_update(self.pool, data))


    @wamp.register('org.head.butterflydns.zone.record.delete')
    def zone_record_delete(self, *data, **detail):
        self.log.info('zone_record_delete({!r}) {}'.format(data, detail))
        if not data:
            return {'success':False}

        @asyncio.coroutine
        def _zone_record_delete(pool, data):
            with (yield from pool.cursor()) as cur:
                now  = datetime.datetime.utcnow();
                data = data[0]
                print('data is:',data)

                # now delete the record
                yield from cur.execute('''DELETE
                                          FROM  record r
                                         WHERE  r.rid=%(rid)s''', data)

                (topic,_data) = yield from self._update_zone_soa(data['zone'], now)
                self.push_pub(topic,_data)
                self.push_pub('org.head.butterflydns.zone.records.get.single_rr.'+data['zone'], {'zone':data['zone'], 'rid':data['rid']})

            return {'success':True, 'rid':data['rid']}

        return (yield from _zone_record_delete(self.pool, data))


    @wamp.register('org.head.butterflydns.zone.xfr-acl.add')
    def zone_xfr_acl_add(self,*data,**detail):
        self.log.info('zone_record_add({}) {}'.format(data, detail))
        if not data:
            return {'success':False}

        @asyncio.coroutine
        def _zone_xfr_acl_add(pool, data):
            with (yield from pool.cursor()) as cur:
                now         = datetime.datetime.utcnow();
                data        = data[0]
                data['now'] = now

                q = '''INSERT
                         INTO  xfr
                               (zone,client,created,updated)
                       VALUES  (
                                (SELECT c.domain as zone FROM canonical c WHERE c.content = %(zone)s),
                                %(host)s,
                                %(now)s,
                                %(now)s
                               )
                    RETURNING  rid
                               '''
                yield from cur.execute(q, data)
                rid = (yield from cur.fetchone())[0]
                data['rid'] = rid

                # one of these days we ought to put created & updated somewhere in here
                data['created'] = data['now'].strftime('%F %T')
                data['updated']  = data['created']
                del data['now']

                self.push_pub('org.head.butterflydns.zone.xfr-acls.get.single.'+data['zone'], data)

            return {'success':True, 'rid':rid}

        return (yield from _zone_xfr_acl_add(self.pool, data))


    @wamp.register('org.head.butterflydns.zone.xfr-acl.update')
    def zone_xfr_acl_update(self,*data,**detail):
        self.log.info('zone_record_update({}) {}'.format(data, detail))
        if not data:
            return {'success':False}

        @asyncio.coroutine
        def _zone_xfr_acl_update(pool, data):
            with (yield from pool.cursor()) as cur:
                data = data[0]
                now  = datetime.datetime.utcnow();
                data['now'] = now

                # we don't need the old data any more, we have the row id
                yield from cur.execute('''UPDATE  xfr r
                                             SET  (client,updated)
                                                  =
                                                  (%(host)s,%(now)s)
                                            FROM  canonical c
                                           WHERE  c.content  = %(zone)s
                                             AND  r.zone     = c.domain
                                             AND  r.rid      = %(rid)s
                                       ''', data)

                # one of these days we ought to put created & updated somewhere in here
                data['updated'] = data['now'].strftime('%s')
                del data['now']

                self.push_pub('org.head.butterflydns.zone.xfr-acls.get.single.'+data['zone'], data)

            return {'success':True}

        return (yield from _zone_xfr_acl_update(self.pool, data))


    @wamp.register('org.head.butterflydns.zone.xfr-acl.delete')
    def zone_xfr_acl_delete(self,*data,**detail):
        self.log.info('zone_record_delete({})'.format(data))
        if not data:
            return {'success':False}

        @asyncio.coroutine
        def _zone_xfr_acl_delete(pool, data):
            with (yield from pool.cursor()) as cur:
                data = data[0]

                # now delete the record
                yield from cur.execute('''DELETE
                                          FROM  xfr r
                                         WHERE  r.rid=%(rid)s''', data)

                self.push_pub('org.head.butterflydns.zone.xfr-acls.get.single.'+data['zone'], {'rid':data['rid']})

            return {'success':True, 'rid':data['rid']}

        return (yield from _zone_xfr_acl_delete(self.pool, data))


    @wamp.register('org.head.butterflydns.zone.meta.update')
    def zone_meta_update(self, *data, **detail):
        self.log.info('zone_meta_update({!r}) {}'.format(data, detail))
        if not data:
            return {'success':False}
        data = data[0]

        @asyncio.coroutine
        def _zone_meta_update(pool, data):
            with (yield from pool.cursor()) as cur:
                now  = datetime.datetime.utcnow();
                # find the zone id
                print('zone meta update data is:',data);
                zone = data['zone']
                yield from cur.execute('''SELECT  c.domain
                                            FROM  canonical c
                                           WHERE  c.content = %(zone)s ''', {'zone':zone})

                zid = (yield from cur.fetchone())[0]
                print('ZID is:',zid)
                data['zid'] = zid
                data['rid'] = -1
                data['now'] = now

                changed     = data['changed']
                success     = True
                errors      = []

                # rewrite SOA?
                new_soa = {k:data[k][0] for k in data if k in ('Primary NS','Contact','Serial','Refresh','Retry','Expire','Minimum TTL')}
                for k in new_soa:
                    del data[k]

                # now, if no soa key are in the changed keys, we'll ignore all SOA records
                if not [k for k in new_soa if k in changed]:
                    new_soa = {}

                # fun with all sorts of shit, yay.
                for K in data:
                    if not K in changed:
                        continue

                    if K in ('Manager','Owner'):
                        if not len(data[K]) == 1:
                            raise ValueError('must be exactly one entry long')
                        data[K] = data[K][0]

                        print('updating {}:{} to {!r}'.format(zone,K,data[K]))

                        k = K.lower()
                        if k == 'manager': k='admin'

                        q = 'UPDATE canonical SET '+k+' = %('+K+')s WHERE domain = %(zid)s RETURNING rid'
                        yield from cur.execute(q, data)
                        rows = yield from cur.fetchall()
                        if not len(rows) == 1:
                            success = False
                            errors.append( 'Update did not modify exactly 1 row; {} rows modified for key {!r}'.format(len(rows),K) )
                        data['rid'] = rows[0][0]

                        q = 'UPDATE canonical SET updated = %(now)s WHERE rid = %(rid)s'
                        yield from cur.execute(q, data)

                        yield from self._get_zone_local(zone)

                    if K in ('Default TTL'):
                        try:
                            _ = int(data[K][0], 10)
                            if not 0 <= _ <= 2147483647:
                                raise ValueError
                        except:
                            success = False
                            errors.append('Unable to parse value for Default TTL, must be an integer in {0..2147483647}')
                            continue

                        data[K] = data[K][0]
                        print('updating {}:{} to {!r}'.format(zone,K,data[K]))
                        q = "UPDATE record SET ttl = %(Default TTL)s WHERE zone = %(zid)s AND type = 'SOA' RETURNING rid"
                        yield from cur.execute(q, data)
                        rows = yield from cur.fetchall()
                        if not len(rows) == 1:
                            success = False
                            errors.append( 'Update did not modify exactly 1 row; {} rows modified for key {!r}'.format(len(rows),K) )
                        data['rid'] = rows[0][0]
                        q = 'UPDATE canonical SET updated = %(now)s WHERE rid = %(rid)s'
                        yield from cur.execute(q, data)

                # now do the SOA record if requested
                while new_soa: # use 'while' so we can break out early

                    # fetch the current SOA record
                    yield from cur.execute("SELECT rid,data FROM record WHERE zone = %(zid)s AND type = 'SOA'", data)
                    old_soa = (yield from cur.fetchone())

                    # first, check the new serial # is >= the old serial number. we allow changing the SOA serial manually
                    # this too will break when we support BIND time formats: s/m/h/d/w
                    old_soa_sn = int(old_soa[1].split(' ')[2], 10)
                    # really dumb breakable test
                    new_soa_sn = int(new_soa['Serial'], 10)

                    if not (new_soa_sn >= old_soa_sn):
                        success = False
                        errors.append('New serial number is less than existing ({}); serial number must increment'.format(old_soa_sn))
                        break
                    if (new_soa_sn - old_soa_sn) > 2147483647:
                        success = False
                        errors.append('New serial number delta is > 2147483647; ({})'.format(new_soa_sn - old_soa_sn))
                        break

                    # some validation
                    for k in ('Serial','Refresh','Retry','Expire','Minimum TTL'):
                        try:
                            _ = int(new_soa[k], 10) # this will break when we start supporting BIND time formats
                            if K == 'Serial':
                                maxn=4294967295  # 68 yrs
                            elif K == 'Minimum TTL':
                                maxn=10800       # 3 hrs
                            else:
                                maxn=2147483647  # 34 yrs

                            if not 0 <= _ <= maxn:
                                raise ValueError
                        except:
                            success = False
                            errors.append('Unable to parse value for {}, must be an integer in range \{0..{}\}'.format(k,maxn))
                            break

                    for k in ('Primary NS','Contact'):
                        if k == 'Contact' and '@' in new_soa[k]:
                            new_soa[k] = new_soa[k].replace('@','.')
                        if not new_soa[k].endswith('.'):
                            new_soa[k] += '.'
                        if k == 'Primary NS':
                            mk='[\w._-]+$'
                        else:
                            mk='[\w._+-]+$'
                        if not re.match(mk, new_soa[k]):
                            success = False
                            errors.append('Invalid characters for {}'.format(k))
                            break

                    soa_s = ''
                    for k in ('Primary NS','Contact','Serial','Refresh','Retry','Expire','Minimum TTL'):
                        soa_s += new_soa[k]+' '

                    soa_s = soa_s.rstrip(' ')

                    print('oldsoa:',old_soa)
                    print('newsoa:',soa_s)

                    q = "UPDATE record SET data = %(soa)s WHERE rid = %(rid)s"
                    yield from cur.execute(q, {'soa':soa_s, 'rid':old_soa[0]})

                    break

                # and we're done
                if errors:
                    for e in errors:
                        print(e)

                return {'success':success, 'errors':errors}

        return (yield from _zone_meta_update(self.pool, data))


    @wamp.register('org.head.butterflydns.zone.template.names.get')
    def zone_template_names_get(self, **detail):
        self.log.info('zone.template.names.get({})'.format(detail))

        @asyncio.coroutine
        def __f(pool):
            with (yield from self.pool.cursor()) as cur:
                # update SOA, fetch existing record
                yield from cur.execute('''SELECT
                                    DISTINCT  r.name
                                        FROM  zone_templates r
                                    ORDER BY  r.name
                                   ''')

                _ = yield from cur.fetchall()
                _ = yield from self._make_dict_list(cur, _)
                data = {'success':True, 'names':_}
                print(data)
                return data

        return (yield from __f(self.pool))


    #try:
    #    res = yield self.call('org.head.butterflydns.get_zones.get_all')
    #    yield self.publish('org.head.butterflydns.get_zones.get_all', res)
    #except ApplicationError as e:
    #    # ignore errors due to the frontend not yet having
    #    # registered the procedure we would like to call
    #    if e.error != 'wamp.error.no_such_procedure':
    #        raise e


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


def make(config):
    ##
    # This component factory creates instances of the
    # application component to run.
    ##
    # The function will get called either during development
    # using the ApplicationRunner below, or as  a plugin running
    # hosted in a WAMPlet container such as a Crossbar.io worker.
    ##
    if config:
        return ButterflyDNS(config)
    else:
        # if no config given, return a description of this WAMPlet ..
        return {'label': 'Butterfly Service WAMPlet',
            'description': 'This is the backend WAMP application component of Butterfly.'}

if __name__ == '__main__':
    # this provider is expecting to be started from the same CWD as crossbar was
    cfg = configparser.ConfigParser()
    cfg.read('butterflydns.conf')

    irl = cfg.get('main', 'site_irl')
    if not irl:
        s = "section [main]; required config option '{}' not found".format('site_irl')

    host,*port = (cfg['ldap']['host']).rsplit(':',1)
    port       = port and port[0] or '389'
    cfg['ldap']['host'] = host
    cfg['ldap']['port'] = cfg.get('ldap', 'port', fallback=port)

    for key in ('valid_names','host','userdn','userpassword','base'):
        if not cfg.get('ldap', key):
            s = "section [ldap]; required config option '{}' not found".format(key)
            raise KeyError(s)

    for key in ('roleUsername','rolePassword'):
        if not cfg.get('provider', key):
            s = "section [provider]; required config option '{}' not found".format(key)
            raise KeyError(s)

    host,*port = (cfg['postgresql']['host']).rsplit(':',1)
    port       = port and port[0] or '5432'
    cfg['postgresql']['host'] = host
    cfg['postgresql']['port'] = cfg.get('postgresql', 'port', fallback=port)

    for key in ('host','database','user','password'):
        if not cfg.get('postgresql', key):
            s = "section [postgresql]; required config option '{}' not found".format(key)
            raise KeyError(s)


    runner = ApplicationRunner(
        url=irl,
        realm="butterflydns",
        extra={'authid':'provider', 'cfg':cfg})

    runner.run(make)
