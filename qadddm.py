#!/usr/bin/env python

__version__  = '2.3'
__author__   = 'David Ford <david@blue-labs.org>'
__date__     = '2017-Jul-30 21:44E'
__title__    = 'BlueLabs ButterflyDNS tools'
__license__  = 'Apache 2.0'

'''
Quick and dirty DNS distribution manager
----------------------------------------

quick, no time to explain, use this script!  ...This short ditty replicates all the ButterflyDNS activity with the primary PG database onto secondary PG databases.
(replicate ins/up/del on sql A to B,C,...)

<strike>
version 1.0:
monitor our main ButterflyDNS database, if the highest found serial number
changes, we get all records newer than our current serial number and dist
them to the secondary databases.

if we don't find any newer records, something got deleted so figure out what
got deleted and go rm it from the secondaries.
</strike>


example /etc/qadddm.conf
   [main]
   db uri        = postgres://bind:xxxxxxxxx@{host}:5432/dns_data?sslmode=require
   main db       = primary.blue-labs.org
   secondary dbs = secondary1.blue-labs.org secondary2.blue-labs.org

   [smtp]
   host          = mail.blue-labs.org
   ehlo          = primary.blue-labs.org
   username      = johndoe
   password      = superawesomepassword
   sender        = chicken.little@blue-labs.org
   recipients    = chicken.biggee@blue-labs.org



version 2.0:
use a pg_notify for all insert/update/deletes and replicate them to secondaries.

'''

import configparser
import datetime
import json
import logging
import psycopg2
import psycopg2.extensions
import psycopg2.extras
import select
import sys
import threading
import time
import traceback

import smtplib
from email.utils                import formatdate, getaddresses
from email.parser               import BytesParser, Parser
from email.encoders             import encode_7or8bit
from email.mime.text            import MIMEText
from email.mime.base            import MIMEBase
from email.mime.multipart       import MIMEMultipart
from email.message              import Message

def _cfg_List(config, section, key):
   v = _cfg_None(config, section, key)
   if not v:
      return
   return [x for x in v.replace(',', ' ').split(' ') if x]


_proc = '''
                CREATE OR REPLACE FUNCTION notify_proc() RETURNS trigger AS $$
                DECLARE
                    _json    json;
                    _record  record;
                BEGIN
                    IF TG_OP = 'INSERT' or TG_OP = 'UPDATE' THEN
                        SELECT TG_TABLE_NAME AS table, TG_OP AS action, NEW.*
                        INTO    _record;
                    ELSE
                        SELECT TG_TABLE_NAME AS table, TG_OP AS action, OLD.*
                        INTO    _record;
                    END IF;

                    _json = row_to_json(_record);
                    PERFORM pg_notify(CAST('butterflydns' AS text), CAST(_json AS text));

                    IF TG_OP = 'INSERT' or TG_OP = 'UPDATE' THEN
                        RETURN NEW;
                    ELSE
                        RETURN OLD;
                    END IF;

                END;
                $$ LANGUAGE plpgsql;
                '''

_trig = '''
                DO
                $$
                BEGIN
                    IF NOT EXISTS (SELECT *
                        FROM  information_schema.triggers
                        WHERE event_object_table = '{table}'
                        AND   trigger_name = 'butterflydns_notify_{table}_{op}'
                    )
                    THEN
                        CREATE TRIGGER butterflydns_notify_{table}_{op} {when} {op}
                                    ON {table}
                          FOR EACH ROW
                               EXECUTE
                             PROCEDURE notify_proc();
                    END IF;
                END;
                $$
                '''


class FlitterButter():
    def __init__(self, cfg, logger=None):
        self.cfg  = cfg
        self.live = False
        self.conn = None

        if not logger:
            logging.basicConfig(level=logging.DEBUG)
            logger = logging.getLogger()
            
        
        self.logger = logger


    def _check_online(self):
        reconnect = False

        if not self.conn or self.conn.closed:
            reconnect = True

        if not reconnect:
            try:
                with self.conn.cursor() as c:
                    c.execute('SELECT 1')
            except psycopg2.OperationalError:
                reconnect = True

        if not reconnect:
            return
        
        self._sql_connect()


    def _sql_connect(self):
        while True:
            try:
                _uri  = self.cfg.get('main', 'db uri')
                _main = self.cfg.get('main', 'main db')
                self.conn = psycopg2.connect(_uri.format(host=_main))
            except Exception as e:
                self.logger.critical('Failed to connect to main ButterflyDNS DB: {}'.format(e))
                time.sleep(10)
                continue
            
            if not self.conn:
                self.logger.critical('cannot mate with DB')
                time.sleep(10)
            else:
                break
        
        self.conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        self.logger.info('mated with ButterflyDNS DB')
        self._create_triggers()
        self.live = True


    def _create_triggers(self):
        tables    = ('canonical','owners','record','tld','xfr','zone','zone_templates')
        sequences = ('canonical_cid_seq','record_rid_seq','tld_tid_seq','xfr_xid_seq','zone_template_rid_seq','zone_zid_seq')
        
        with self.conn.cursor() as c:
          c.execute(_proc)

          for table in tables:
            for op,when in {'insert':'BEFORE','update':'AFTER','delete':'BEFORE'}.items():
              c.execute(_trig.format(op=op, when=when, table=table))


    def run(self):
        __running = True
        poll_timeout = None
        
        self._check_online()
        conn = self.conn
        self.logger.info('conn:{}, self.conn:{}'.format(conn, self.conn))

        with conn.cursor() as c:
            c.execute('LISTEN butterflydns')

        p = select.poll()
        p.register(conn, select.EPOLLIN|select.EPOLLERR|select.EPOLLHUP|select.EPOLLPRI)
        
        while True:
            x = p.poll(poll_timeout)
            
            if not x:
                # timeout expired
                self._check_online()

            try:
                conn.poll()
            except psycopg2.OperationalError:
                self.logger.error('OpErr')
                break
            except Exception as e:
                self.logger.error('error polling DB: {}'.format(e))
                break

            while conn.notifies:
                notify = conn.notifies.pop(0)
                data  = json.loads(notify.payload)
                self._update_secondary(data)

    
    def _update_secondary(self, data):
        op      = data['action']
        table   = data['table']
        varstr  = ''
        seqdict = {'canonical':      'canonical_cid_seq',
                   'owners':         'owners_rid_seq',
                   'record':         'record_rid_seq',
                   'tld':            'tld_tid_seq',
                   'xfr':            'xfr_xid_seq',
                   'zone':           'zone_zid_seq',
                   'zone_templates': 'zone_template_rid_seq'}
        
        # get table description
        with self.conn.cursor() as c:
            c.execute('SELECT * FROM {table} LIMIT 1'.format(table=table))
            colnames = ','.join([x.name for x in c.description])

        if op in ('INSERT',):
            q = "INSERT INTO {table} ({colnames}) VALUES ({varstr}) RETURNING rid"
            varstr = ','.join(['%('+x.name+')s' for x in c.description])

        elif op in ('UPDATE',):
            q = "UPDATE {table} SET {varstr} WHERE rid=%(rid)s RETURNING rid"
            varstr = ', '.join([x.name+'=%('+x.name+')s' for x in c.description])

        elif op in ('DELETE',):
            q = "DELETE FROM {table} WHERE rid=%(rid)s RETURNING rid"

        q = q.format(colnames=colnames, table=table, varstr=varstr)
        
        for secondary in _cfg_List(self.cfg, 'main', 'secondary dbs'):
            self.logger.info('>> replaying statement onto: {}'.format(secondary))
            sconn = psycopg2.connect(uri.format(host=secondary))
            sconn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            with sconn.cursor() as c, self.conn.cursor() as c_s:
                q = q.format(**data)
                try:
                    c.execute(q, data)
                    print('{}\n'.format(c.query))
                    rid = c.fetchall()
                    if not rid:
                        raise KeyError("row id #{} should have existed".format(data['rid']))
                    elif len(rid) > 1:
                        raise KeyError("too many rows, only expected one: {}".format(rid))
                    else:
                        rid = rid[0][0]
                        if not rid == data['rid']:
                            print('rid should be {}; {}'.format(data['rid'],rid))
                except Exception as e:
                    e = str(e).strip("'\n").replace('\n','; ')
                    es = 'Type: {}\nSecondary: {}\nQuery: {}\nMessage: {}'.format(e.__class__, secondary, c.query.decode(), e)
                    msg = '\x1b[1;31m\u26a0\x1b[0m {}'.format(es)
                    self.logger.error(msg)
                    self._send_alert(es)
        
                if op == 'INSERT':
                    if data['table'] in seqdict:
                        seqname = seqdict[data['table']]
                        self.logger.info('  yoyo is yaaaah man')

                        c_s.execute('SELECT last_value FROM {}'.format(seqname))
                        sval = c_s.fetchone()[0]
                        if not sval == data['rid']:
                            self.logger.warning('  sval should be {} instead of {}'.format(data['rid'],sval))
                    
                        # now set this value at the secondary
                        try:
                            self.logger.info('  updating sequence number')
                            q = "SELECT setval('{seqname}', %(sval)s) FROM {seq};".format(seqname=seqname, seq=seqname)
                            c.execute(q, {'sval':sval})
                        except Exception as e:
                            msg = '\x1b[1;37;41m{}\x1b[40m {}\x1b[0m'.format(e.__class__,e)
                            msg += '\n' + traceback.format_exc()
                            self.logger.error(msg)
                            self._send_alert(msg)


    def _send_alert(self, data):
        reporting_username = self.cfg.get('smtp', sender)
        headers = {'From':         '<{}>'.format(reporting_username),
                   'Subject':      'ButterflyDNS Sync Error',
                   'Date':         '{}Z'.format(formatdate()),
                   'MIME-Version': '1.0',
                   }
        outer = MIMEMultipart()
        for k,v in headers.items():
            outer[k] = v
        
        _part = MIMEText(data)
        outer.attach(_part)
        
        recipients = _cfg_List(self.cfg, 'smtp', recipients)
        
        try:
            s = smtplib.SMTP(host=self.cfg.get('smtp', 'host'), timeout=60)
            s.starttls()
            s.ehlo(self.cfg.get('smtp', 'ehlo'))
            s.login(self.cfg.get('smtp', 'username'), self.cfg.get('smtp', 'password'))

            s.send_message(outer, reporting_username, recipients, mail_options=['SMTPUTF8','BODY=8BITMIME'])
            self.logger.info('email sent')
        except Exception as e:
            self.logger.warning('failed to send report: {}'.format(e))
        
    
if __name__ == '__main__':
    cfg = configparser.ConfigParser()
    cfg.read('/etc/qadddm.conf')

    FitButt = FlitterButter(cfg)
    while True:
        try:
            FitButt.run()
        except KeyboardInterrupt:
            sys.exit()
