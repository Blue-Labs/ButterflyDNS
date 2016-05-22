# ButterflyDNS

A WAMP driven DNS management tool aimed at making DNS records management
easier for BIND with DLZ using a postgresql backend. DNS record changes are
immediately live with no _rndc_ scripting needed.

## WAMP references:
* [Crossbar router](crossbar.io)  ![Crossbar Logo](http://crossbar.io/static/img/gen/crossbar_icon_and_text_vectorized_yellow_icon.svg)
* [Autobahn js and Python](autobahn.ws)  ![Autobahn Logo](http://autobahn.ws/static/img/gen/autobahnws_large.svg)

DLZ in BIND is to be understood as _dynamically loaded zone_ and gives BIND
the ability to fetch resource records from a multitude of backend database
types. In our case, we chose to use [PostgreSQL](postgresql.org) as our
backend for this project as we'd had a non/limited GUI interface for our
implementation for several years now.

## This implementation of WAMP utilizes the following concepts:

* Dynamic authentication using a simple LDAP database with our own schema as a child component of crossbar
* Recurring/reload authentication using WAMP cookies
* URI registration and static authorization for RPCs and PUB/SUB
* SSL certs by [Let's Encrypt](letsencrypt.com) providing TLS v1.2 sessions with strong ciphers
* IO handled with Python 3.5's built in _asyncio_ module

As a bonus, you get a short little replication tool _qadddm.py_ just for
ButterflyDNS and PostgreSQL. Replicate your changes from the primary to all
your secondaries immediately.

All changes are reflected realtime for all persons logged into ButterflyDNS.
When viewing the same zone another person is editing, each submitted record
update will immediately pop into existence, as will the automatically updated
SOA data.

Directory structure is intended to be the following:

```dir
/etc/nginx/sites/foo.com/
  htdocs/
    js/
      butterfly.js
    css/
      butterfly.css
    images/
      ...
    index.html

  butterflydns/
    .crossbar/
      config.json
      cookies.dat (generated)
      node.key (generated)
      node.pid (generated)

  authenticator.py
  butterflydns.conf
  provider.py
```

If your htdocs location is different, change the reference in _config.json._


We will have a demo site soon :)
