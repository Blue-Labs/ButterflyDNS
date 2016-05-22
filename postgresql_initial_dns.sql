--
-- PostgreSQL database dump
--

-- Dumped from database version 9.5.1
-- Dumped by pg_dump version 9.5.2

SET statement_timeout = 0;
SET lock_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET client_min_messages = warning;
SET row_security = off;

SET search_path = public, pg_catalog;

DROP DATABASE dns_data;

-- These are the two usernames ButterflyDNS uses.
--   The provider uses this:
--     butterflydns
--   BIND uses this:
--     bind
--
-- PostgreSQL password hashes are: 'md5' + md5sum( password + username )
-- so, for u:bind, p:Littlefrog820BERRY--Tizzlepart5, the result would be:
--   echo -n 'md5'; (echo -n 'Littlefrog820BERRY--Tizzlepart5bind')|md5sum
--   md5c8fa4725e3cec243c1ae44a2ca349d03

DROP ROLE bind;
CREATE ROLE bind;
ALTER ROLE bind WITH NOSUPERUSER NOINHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS PASSWORD 'md5xxxxxxxx';

DROP ROLE butterfly;
CREATE ROLE butterfly;
ALTER ROLE butterfly WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS PASSWORD 'md5xxxxxxxx';


--
-- Name: dns_data; Type: DATABASE; Schema: -; Owner: bind
--
CREATE DATABASE dns_data WITH TEMPLATE = template0 ENCODING = 'UTF8' LC_COLLATE = 'en_US.utf8' LC_CTYPE = 'en_US.utf8';


ALTER DATABASE dns_data OWNER TO bind;

\connect dns_data

SET statement_timeout = 0;
SET lock_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: plpgsql; Type: EXTENSION; Schema: -; Owner: 
--

CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;


--
-- Name: EXTENSION plpgsql; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION plpgsql IS 'PL/pgSQL procedural language';

SET search_path = public, pg_catalog;

--
-- Name: notify_proc(); Type: FUNCTION; Schema: public; Owner: bind
--

CREATE FUNCTION notify_proc() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
                $$;


ALTER FUNCTION public.notify_proc() OWNER TO bind;

SET default_tablespace = '';

SET default_with_oids = false;

SET search_path = public, pg_catalog;

--
-- Name: authorized_networks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE authorized_networks (
    username text
);


ALTER TABLE authorized_networks OWNER TO postgres;

--
-- Name: authorized_users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE authorized_users (
    username text,
    password text,
    permission text DEFAULT 'read'::text,
    network cidr
);


ALTER TABLE authorized_users OWNER TO postgres;

--
-- Name: canonical; Type: TABLE; Schema: public; Owner: bind
--

CREATE TABLE canonical (
    rid integer NOT NULL,
    domain integer NOT NULL,
    content text NOT NULL,
    admin character varying DEFAULT 'David Ford'::character varying NOT NULL,
    owner character varying,
    created timestamp with time zone DEFAULT now(),
    updated timestamp with time zone DEFAULT now()
);


ALTER TABLE canonical OWNER TO bind;

--
-- Name: canonical_cid_seq; Type: SEQUENCE; Schema: public; Owner: bind
--

CREATE SEQUENCE canonical_cid_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE canonical_cid_seq OWNER TO bind;

--
-- Name: canonical_cid_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: bind
--

ALTER SEQUENCE canonical_cid_seq OWNED BY canonical.rid;


--
-- Name: owners_rid_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE owners_rid_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE owners_rid_seq OWNER TO postgres;

--
-- Name: owners; Type: TABLE; Schema: public; Owner: bind
--

CREATE TABLE owners (
    manager character varying DEFAULT 'David Ford'::character varying NOT NULL,
    contact character varying NOT NULL,
    actual_owner character varying,
    rid integer DEFAULT nextval('owners_rid_seq'::regclass) NOT NULL
);


ALTER TABLE owners OWNER TO bind;

--
-- Name: record; Type: TABLE; Schema: public; Owner: bind
--

CREATE TABLE record (
    rid integer NOT NULL,
    host character varying(255) DEFAULT '@'::character varying,
    zone integer NOT NULL,
    ttl integer DEFAULT 21600,
    type character varying(5) NOT NULL,
    priority character varying(5) DEFAULT ''::character varying NOT NULL,
    data text NOT NULL,
    created timestamp with time zone DEFAULT now(),
    updated timestamp with time zone DEFAULT now(),
    CONSTRAINT record_type CHECK ((((type)::text = 'A'::text) OR ((type)::text = 'AAAA'::text) OR ((type)::text = 'CNAME'::text) OR ((type)::text = 'HINFO'::text) OR ((type)::text = 'MBOXFW'::text) OR ((type)::text = 'MX'::text) OR ((type)::text = 'NAPTR'::text) OR ((type)::text = 'NS'::text) OR ((type)::text = 'PTR'::text) OR ((type)::text = 'SOA'::text) OR ((type)::text = 'SPF'::text) OR ((type)::text = 'TXT'::text) OR ((type)::text = 'URL'::text) OR ((type)::text = 'SRV'::text)))
);


ALTER TABLE record OWNER TO bind;

--
-- Name: record_rid_seq; Type: SEQUENCE; Schema: public; Owner: bind
--

CREATE SEQUENCE record_rid_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE record_rid_seq OWNER TO bind;

--
-- Name: record_rid_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: bind
--

ALTER SEQUENCE record_rid_seq OWNED BY record.rid;


--
-- Name: std_ns_by_admin; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE std_ns_by_admin (
    admin character varying NOT NULL,
    ns character varying NOT NULL
);


ALTER TABLE std_ns_by_admin OWNER TO postgres;

--
-- Name: tld; Type: TABLE; Schema: public; Owner: bind
--

CREATE TABLE tld (
    rid integer NOT NULL,
    extension character varying(20) NOT NULL
);


ALTER TABLE tld OWNER TO bind;

--
-- Name: tld_tid_seq; Type: SEQUENCE; Schema: public; Owner: bind
--

CREATE SEQUENCE tld_tid_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE tld_tid_seq OWNER TO bind;

--
-- Name: tld_tid_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: bind
--

ALTER SEQUENCE tld_tid_seq OWNED BY tld.rid;


--
-- Name: xfr; Type: TABLE; Schema: public; Owner: bind
--

CREATE TABLE xfr (
    rid integer NOT NULL,
    zone integer NOT NULL,
    client cidr NOT NULL,
    created timestamp with time zone DEFAULT now(),
    updated timestamp with time zone DEFAULT now()
);


ALTER TABLE xfr OWNER TO bind;

--
-- Name: xfr_xid_seq; Type: SEQUENCE; Schema: public; Owner: bind
--

CREATE SEQUENCE xfr_xid_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE xfr_xid_seq OWNER TO bind;

--
-- Name: xfr_xid_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: bind
--

ALTER SEQUENCE xfr_xid_seq OWNED BY xfr.rid;


--
-- Name: zone; Type: TABLE; Schema: public; Owner: bind
--

CREATE TABLE zone (
    rid integer NOT NULL,
    name character varying(255) NOT NULL,
    tld integer NOT NULL,
    comment text DEFAULT ''::text,
    manager text
);


ALTER TABLE zone OWNER TO bind;

--
-- Name: zone_template_rid_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE zone_template_rid_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE zone_template_rid_seq OWNER TO postgres;

--
-- Name: zone_templates; Type: TABLE; Schema: public; Owner: bind
--

CREATE TABLE zone_templates (
    rid integer DEFAULT nextval('zone_template_rid_seq'::regclass) NOT NULL,
    name text,
    host text,
    ttl integer,
    type text,
    priority integer,
    data text,
    created timestamp with time zone,
    updated timestamp with time zone
);


ALTER TABLE zone_templates OWNER TO bind;

--
-- Name: zone_zid_seq; Type: SEQUENCE; Schema: public; Owner: bind
--

CREATE SEQUENCE zone_zid_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE zone_zid_seq OWNER TO bind;

--
-- Name: zone_zid_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: bind
--

ALTER SEQUENCE zone_zid_seq OWNED BY zone.rid;

SET search_path = public, pg_catalog;

--
-- Name: rid; Type: DEFAULT; Schema: public; Owner: bind
--

ALTER TABLE ONLY canonical ALTER COLUMN rid SET DEFAULT nextval('canonical_cid_seq'::regclass);


--
-- Name: rid; Type: DEFAULT; Schema: public; Owner: bind
--

ALTER TABLE ONLY record ALTER COLUMN rid SET DEFAULT nextval('record_rid_seq'::regclass);


--
-- Name: rid; Type: DEFAULT; Schema: public; Owner: bind
--

ALTER TABLE ONLY tld ALTER COLUMN rid SET DEFAULT nextval('tld_tid_seq'::regclass);


--
-- Name: rid; Type: DEFAULT; Schema: public; Owner: bind
--

ALTER TABLE ONLY xfr ALTER COLUMN rid SET DEFAULT nextval('xfr_xid_seq'::regclass);


--
-- Name: rid; Type: DEFAULT; Schema: public; Owner: bind
--

ALTER TABLE ONLY zone ALTER COLUMN rid SET DEFAULT nextval('zone_zid_seq'::regclass);


SET search_path = public, pg_catalog;

--
-- Data for Name: authorized_networks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY authorized_networks (username) FROM stdin;
\.


--
-- Data for Name: authorized_users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY authorized_users (username, password, permission, network) FROM stdin;
\.


--
-- Data for Name: canonical; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY canonical (rid, domain, content, admin, owner, created, updated) FROM stdin;
90	99	0.255.10.in-addr.arpa	David Ford	\N	\N	\N
107	116	ovas-master.wh.verio.net	David Ford	\N	\N	\N
108	117	1.255.10.in-addr.arpa	David Ford	\N	\N	\N
120	129	20.10.in-addr.arpa	David Ford	\N	\N	\N
122	131	corp.verio.net	David Ford	\N	\N	\N
\.


--
-- Name: canonical_cid_seq; Type: SEQUENCE SET; Schema: public; Owner: bind
--

SELECT pg_catalog.setval('canonical_cid_seq', 132, true);


--
-- Data for Name: owners; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY owners (manager, contact, actual_owner, rid) FROM stdin;
david	David Ford <david@blue-labs.org>	\N	1
mjh	Matthew Harmon <mjh@itys.net>	\N	2
david-z2e	David Ford <david@blue-labs.org>	Erik (z2e)	3
\.


--
-- Name: owners_rid_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('owners_rid_seq', 7, true);


--
-- Data for Name: record; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY record (rid, host, zone, ttl, type, priority, data, created, updated) FROM stdin;
790	@	99	21600	SOA		ranger.blue-labs.org. david.blue-labs.org. 1440734032 21600 3600 604800 3600	2010-05-13 08:53:16.40112-04	2010-05-13 16:22:02.99333-04
792	@	99	21600	NS		ranger.blue-labs.org.	2010-05-13 08:53:16.456048-04	2010-05-13 08:54:15.740875-04
794	5	99	21600	PTR		ranger.vpn.blue-labs.org.	2010-05-13 08:55:54.974962-04	2010-05-13 09:03:42.715255-04
1849	2	99	21600	PTR		vss.vpn.blue-labs.org.	2011-12-23 23:20:25.544636-05	2011-12-23 23:20:25.52507-05
1855	91	99	21600	PTR		oscar.vpn.blue-labs.org.	2012-01-27 17:34:50.439656-05	2012-01-27 17:34:50.438711-05
1298	@	116	21600	SOA		ranger.blue-labs.org. david.blue-labs.org. 1458013513 21600 3600 604800 3600 	2010-11-22 23:55:28.277328-05	2016-03-15 03:45:13.215007-04
1300	@	116	21600	NS		ranger.blue-labs.org.	2010-11-22 23:55:28.320278-05	2010-11-22 23:55:28.320278-05
1305	@	116	21600	A		10.255.1.11	2010-11-22 23:55:28.356461-05	2010-11-23 00:01:03.57687-05
1307	@	116	21600	MX	10	mail.security-carpet.com.	2010-11-22 23:55:28.372448-05	2016-03-15 03:44:58.758614-04
1309	@	116	21600	TXT		v=spf1 ip6:2001:470:d:3de::/64 ip6:2001:470:4:1d8::/64 ip6:2001:470:1f07:916::/64 a mx include:security-carpet.com -all	2010-11-22 23:55:28.388452-05	2016-03-15 03:44:56.087897-04
1310	www	116	21600	CNAME		@	2010-11-22 23:55:28.397264-05	2010-11-22 23:55:28.397264-05
1311	@	117	21600	SOA		ranger.blue-labs.org. david.blue-labs.org. 1439503056 21600 3600 604800 3600	2010-11-23 00:03:07.234854-05	2010-11-23 00:06:34.304494-05
1312	@	117	21600	NS		ranger.blue-labs.org.	2010-11-23 00:03:07.245502-05	2010-11-23 00:03:59.344123-05
1314	11	117	21600	PTR		ovas-master.vpn.security-carpet.com.	2010-11-23 00:04:32.659377-05	2014-01-31 02:47:40.957215-05
1900	12	117	21600	PTR		lab.vpn.security-carpet.com.	2012-11-10 04:15:20.655433-05	2012-11-10 04:15:20.654263-05
1901	18	117	21600	PTR		jump2.vpn.security-carpet.com.	2012-11-10 04:15:40.794937-05	2014-01-31 02:48:13.723244-05
1905	16	117	21600	PTR		jump0.vpn.security-carpet.com.	2012-12-05 01:55:24.279357-05	2014-01-31 02:47:59.037515-05
1906	17	117	21600	PTR		jump1.vpn.security-carpet.com.	2012-12-05 01:55:54.033613-05	2014-01-31 02:48:06.525681-05
1907	30	117	21600	PTR		pandora.vpn.blue-labs.org.	2012-12-06 23:00:43.785571-05	2012-12-06 23:00:43.784523-05
1992	19	117	21600	PTR		arch-gluster.vpn.security-carpet.com.	2014-05-14 18:45:32.479036-04	2014-05-14 18:45:32.478193-04
1993	20	117	21600	PTR		yubi-validation-server.vpn.security-carpet.com.	2014-05-14 18:46:02.640243-04	2014-05-14 18:46:02.639341-04
1996	10	117	21600	PTR		vibbler.vpn.security-carpet.com.	2014-06-11 11:24:28.860515-04	2014-06-11 11:24:28.8597-04
1997	8	117	21600	PTR		db.vpn.security-carpet.com.	2014-06-11 11:24:40.088063-04	2014-06-11 11:24:40.087244-04
2064	9	117	21600	PTR		vibbler.vpn.security-carpet.com.	2015-06-30 14:36:39.284876-04	2015-06-30 14:41:20.11668-04
2065	7	117	21600	PTR		abt.vpn.security-carpet.com.	2015-06-30 14:42:08.688233-04	2015-06-30 14:42:08.687382-04
2068	27	117	21600	PTR		gitlab.vpn.security-carpet.com.	2015-08-13 17:50:06.528921-04	2015-08-13 17:57:36.350243-04
1930	@	129	21600	SOA		ranger.blue-labs.org. david@blue-labs.org. 1377765803 21600 3600 604800 86400	2013-08-29 04:26:24.036287-04	2013-08-29 04:26:24.036058-04
1931	0	129	21600	NS		verio.corp.nameserver.blue-labs.org.	2013-08-29 04:27:12.268825-04	2013-08-29 04:27:58.341237-04
1932	@	129	21600	NS		ranger.blue-labs.org.	2013-08-29 04:43:23.294162-04	2013-08-29 04:43:23.293286-04
1952	@	131	21600	SOA		security-carpet.com. dford@verio.net. 1390946807 21600 3600 604800 3600	2014-01-27 16:02:28.900411-05	2014-01-27 16:03:26.174011-05
1954	@	131	21600	NS		ns.corp.verio.net.	2014-01-27 16:02:28.916073-05	2014-01-27 17:09:47.511748-05
1959	@	131	21600	A		198.171.79.27	2014-01-27 16:02:28.924029-05	2014-01-27 17:10:17.504577-05
1965	_ldap._tcp	131	21600	SRV		0 100 389 stngva1-dc02	2014-01-27 16:17:31.160498-05	2014-01-27 16:48:29.385287-05
1966	_ldap._tcp	131	21600	SRV		0 100 389 stngva1-dc04	2014-01-27 16:23:18.870159-05	2014-01-27 16:48:34.236575-05
1967	stngva1-dc02	131	21600	A		198.171.79.27	2014-01-27 16:29:41.445094-05	2014-01-27 16:29:41.444222-05
1968	stngva1-dc04	131	21600	A		198.171.79.62	2014-01-27 16:30:04.524289-05	2014-01-27 16:30:04.52195-05
1969	_kerberos._tcp	131	21600	SRV		15 100 88 stngva1-dc02	2014-01-27 16:37:05.708823-05	2014-01-27 16:47:47.367635-05
1970	_kerberos._tcp	131	21600	SRV		15 100 88 stngva1-dc04	2014-01-27 16:37:20.054567-05	2014-01-27 16:47:52.626401-05
1971	_kpasswd._tcp	131	21600	SRV		15 100 464 stngva1-dc02	2014-01-27 16:39:21.969571-05	2014-01-27 16:48:06.982384-05
1972	_kpasswd._tcp	131	21600	SRV		15 100 464 stngva1-dc04	2014-01-27 16:39:41.022436-05	2014-01-27 16:48:12.724712-05
1973	_gc._tcp	131	21600	SRV		15 100 3268 stngva1-dc02	2014-01-27 16:40:53.504299-05	2014-01-27 16:47:30.736389-05
1974	_gc._tcp	131	21600	SRV		15 100 3268 stngva1-dc04	2014-01-27 16:41:02.66747-05	2014-01-27 16:47:40.467495-05
1975	_kpasswd._udp	131	21600	SRV		15 100 464 stngva1-dc02	2014-01-27 16:42:24.004538-05	2014-01-27 16:48:18.424639-05
1976	_kpasswd._udp	131	21600	SRV		15 100 464 stngva1-dc04	2014-01-27 16:42:36.758116-05	2014-01-27 16:48:23.891717-05
1977	_kerberos._udp	131	21600	SRV		15 100 88 stngva1-dc02	2014-01-27 16:43:17.869035-05	2014-01-27 16:47:57.201517-05
1978	_kerberos._udp	131	21600	SRV		15 100 88 stngva1-dc04	2014-01-27 16:43:29.208851-05	2014-01-27 16:48:02.027988-05
1979	ns	131	21600	A		128.242.79.5	2014-01-27 17:10:07.388599-05	2014-01-27 17:10:07.38761-05
1980	@	131	21600	A		198.171.79.62	2014-01-27 17:10:34.014753-05	2014-01-27 17:10:43.583171-05
1981	irc	131	21600	A		208.55.255.77	2014-01-28 17:06:47.960414-05	2014-01-28 17:06:47.959524-05
2004	sap	131	21600	A		198.106.137.20	2014-07-30 00:12:54.926067-04	2014-07-30 00:12:54.926067-04
\.


--
-- Name: record_rid_seq; Type: SEQUENCE SET; Schema: public; Owner: bind
--

SELECT pg_catalog.setval('record_rid_seq', 2240, true);


--
-- Data for Name: std_ns_by_admin; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY std_ns_by_admin (admin, ns) FROM stdin;
	colt.blue-labs.org
	colt6.blue-labs.org
	mustang.blue-labs.org
	mustang6.blue-labs.org
	ranger.blue-labs.org
	ranger6.blue-labs.org
\.


--
-- Data for Name: tld; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY tld (rid, extension) FROM stdin;
1	com
7	biz
3	org
4	info
5	net
6	us
2	arpa
8	ro
9	mn
10	me
11	cat
12	pe
\.


--
-- Name: tld_tid_seq; Type: SEQUENCE SET; Schema: public; Owner: bind
--

SELECT pg_catalog.setval('tld_tid_seq', 17, true);


--
-- Data for Name: xfr; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY xfr (rid, zone, client, created, updated) FROM stdin;
\.


--
-- Name: xfr_xid_seq; Type: SEQUENCE SET; Schema: public; Owner: bind
--

SELECT pg_catalog.setval('xfr_xid_seq', 58, true);


--
-- Data for Name: zone; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY zone (rid, name, tld, comment, manager) FROM stdin;
99	0.255.10.in-addr	2		david
116	ovas-master.wh.verio	5		david
117	1.255.10.in-addr	2		david
129	20.10.in-addr	2		david
131	corp.verio	5		david
\.


--
-- Name: zone_template_rid_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('zone_template_rid_seq', 3, true);


--
-- Data for Name: zone_templates; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY zone_templates (rid, name, host, ttl, type, priority, data, created, updated) FROM stdin;
3	david 1	@	21600	SOA	\N	ranger.blue-labs.org. david.blue-labs.org. 1449393832 21600 3600 604800 3600	2015-12-09 18:10:28.430917-05	\N
\.


--
-- Name: zone_zid_seq; Type: SEQUENCE SET; Schema: public; Owner: bind
--

SELECT pg_catalog.setval('zone_zid_seq', 179, true);


SET search_path = public, pg_catalog;

--
-- Name: canonical_pkey; Type: CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY canonical
    ADD CONSTRAINT canonical_pkey PRIMARY KEY (rid);


--
-- Name: record_pkey; Type: CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY record
    ADD CONSTRAINT record_pkey PRIMARY KEY (rid);


--
-- Name: record_rid_key; Type: CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY record
    ADD CONSTRAINT record_rid_key UNIQUE (rid);


--
-- Name: tld_pkey; Type: CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY tld
    ADD CONSTRAINT tld_pkey PRIMARY KEY (rid);


--
-- Name: xfr_pkey; Type: CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY xfr
    ADD CONSTRAINT xfr_pkey PRIMARY KEY (rid);


--
-- Name: zone_id_pkey; Type: CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY zone
    ADD CONSTRAINT zone_id_pkey PRIMARY KEY (rid);


--
-- Name: zone_zid_key; Type: CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY zone
    ADD CONSTRAINT zone_zid_key UNIQUE (rid);


SET search_path = public, pg_catalog;

--
-- Name: canonical_content_index; Type: INDEX; Schema: public; Owner: bind
--

CREATE UNIQUE INDEX canonical_content_index ON canonical USING btree (content);


--
-- Name: record_host_zone_index; Type: INDEX; Schema: public; Owner: bind
--

CREATE INDEX record_host_zone_index ON record USING btree (host, zone);


--
-- Name: record_type_index; Type: INDEX; Schema: public; Owner: bind
--

CREATE INDEX record_type_index ON record USING btree (type);


--
-- Name: tld_extension_index; Type: INDEX; Schema: public; Owner: bind
--

CREATE UNIQUE INDEX tld_extension_index ON tld USING btree (extension);


--
-- Name: xfr_zone_client_index; Type: INDEX; Schema: public; Owner: bind
--

CREATE UNIQUE INDEX xfr_zone_client_index ON xfr USING btree (zone, client);


--
-- Name: zone_name_tld_index; Type: INDEX; Schema: public; Owner: bind
--

CREATE UNIQUE INDEX zone_name_tld_index ON zone USING btree (name, tld);


--
-- Name: butterflydns_notify_canonical_delete; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_canonical_delete BEFORE DELETE ON canonical FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_canonical_insert; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_canonical_insert BEFORE INSERT ON canonical FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_canonical_update; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_canonical_update AFTER UPDATE ON canonical FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_owners_delete; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_owners_delete BEFORE DELETE ON owners FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_owners_insert; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_owners_insert BEFORE INSERT ON owners FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_owners_update; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_owners_update AFTER UPDATE ON owners FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_record_delete; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_record_delete BEFORE DELETE ON record FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_record_insert; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_record_insert BEFORE INSERT ON record FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_record_update; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_record_update AFTER UPDATE ON record FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_tld_delete; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_tld_delete BEFORE DELETE ON tld FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_tld_insert; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_tld_insert BEFORE INSERT ON tld FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_tld_update; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_tld_update AFTER UPDATE ON tld FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_xfr_delete; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_xfr_delete BEFORE DELETE ON xfr FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_xfr_insert; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_xfr_insert BEFORE INSERT ON xfr FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_xfr_update; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_xfr_update AFTER UPDATE ON xfr FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_zone_delete; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_zone_delete BEFORE DELETE ON zone FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_zone_insert; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_zone_insert BEFORE INSERT ON zone FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_zone_templates_delete; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_zone_templates_delete BEFORE DELETE ON zone_templates FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_zone_templates_insert; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_zone_templates_insert BEFORE INSERT ON zone_templates FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_zone_templates_update; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_zone_templates_update AFTER UPDATE ON zone_templates FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: butterflydns_notify_zone_update; Type: TRIGGER; Schema: public; Owner: bind
--

CREATE TRIGGER butterflydns_notify_zone_update AFTER UPDATE ON zone FOR EACH ROW EXECUTE PROCEDURE notify_proc();


--
-- Name: $1; Type: FK CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY zone
    ADD CONSTRAINT "$1" FOREIGN KEY (tld) REFERENCES tld(rid);


--
-- Name: $1; Type: FK CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY record
    ADD CONSTRAINT "$1" FOREIGN KEY (zone) REFERENCES zone(rid) ON DELETE CASCADE;


--
-- Name: canonical_domain_fkey; Type: FK CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY canonical
    ADD CONSTRAINT canonical_domain_fkey FOREIGN KEY (domain) REFERENCES zone(rid) ON DELETE CASCADE;


--
-- Name: xfr_zone_fkey; Type: FK CONSTRAINT; Schema: public; Owner: bind
--

ALTER TABLE ONLY xfr
    ADD CONSTRAINT xfr_zone_fkey FOREIGN KEY (zone) REFERENCES zone(rid) ON DELETE CASCADE;


--
-- Name: public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM postgres;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO PUBLIC;


SET search_path = public, pg_catalog;

--
-- Name: canonical; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON TABLE canonical FROM PUBLIC;
REVOKE ALL ON TABLE canonical FROM bind;
GRANT ALL ON TABLE canonical TO bind;
GRANT SELECT,DELETE,UPDATE ON TABLE canonical TO butterfly;


--
-- Name: owners_rid_seq; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON SEQUENCE owners_rid_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE owners_rid_seq FROM postgres;
GRANT ALL ON SEQUENCE owners_rid_seq TO postgres;
GRANT ALL ON SEQUENCE owners_rid_seq TO bind;


--
-- Name: owners; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON TABLE owners FROM PUBLIC;
REVOKE ALL ON TABLE owners FROM bind;
GRANT ALL ON TABLE owners TO bind;
GRANT SELECT,DELETE,UPDATE ON TABLE owners TO butterfly;
GRANT ALL ON TABLE owners TO postgres;


--
-- Name: record; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON TABLE record FROM PUBLIC;
REVOKE ALL ON TABLE record FROM bind;
GRANT ALL ON TABLE record TO bind;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE record TO butterfly;


--
-- Name: record_rid_seq; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON SEQUENCE record_rid_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE record_rid_seq FROM bind;
GRANT ALL ON SEQUENCE record_rid_seq TO bind;
GRANT SELECT,UPDATE ON SEQUENCE record_rid_seq TO butterfly;


--
-- Name: std_ns_by_admin; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON TABLE std_ns_by_admin FROM PUBLIC;
REVOKE ALL ON TABLE std_ns_by_admin FROM postgres;
GRANT ALL ON TABLE std_ns_by_admin TO postgres;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE std_ns_by_admin TO bind;


--
-- Name: tld; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON TABLE tld FROM PUBLIC;
REVOKE ALL ON TABLE tld FROM bind;
GRANT ALL ON TABLE tld TO bind;
GRANT SELECT,DELETE,UPDATE ON TABLE tld TO butterfly;


--
-- Name: tld_tid_seq; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON SEQUENCE tld_tid_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE tld_tid_seq FROM bind;
GRANT ALL ON SEQUENCE tld_tid_seq TO bind;


--
-- Name: xfr; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON TABLE xfr FROM PUBLIC;
REVOKE ALL ON TABLE xfr FROM bind;
GRANT ALL ON TABLE xfr TO bind;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE xfr TO butterfly;


--
-- Name: xfr_xid_seq; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON SEQUENCE xfr_xid_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE xfr_xid_seq FROM bind;
GRANT ALL ON SEQUENCE xfr_xid_seq TO bind;
GRANT SELECT,UPDATE ON SEQUENCE xfr_xid_seq TO butterfly;


--
-- Name: zone; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON TABLE zone FROM PUBLIC;
REVOKE ALL ON TABLE zone FROM bind;
GRANT ALL ON TABLE zone TO bind;
GRANT SELECT,DELETE,UPDATE ON TABLE zone TO butterfly;


--
-- Name: zone_template_rid_seq; Type: ACL; Schema: public; Owner: postgres
--

REVOKE ALL ON SEQUENCE zone_template_rid_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE zone_template_rid_seq FROM postgres;
GRANT ALL ON SEQUENCE zone_template_rid_seq TO postgres;
GRANT ALL ON SEQUENCE zone_template_rid_seq TO bind;


--
-- Name: zone_templates; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON TABLE zone_templates FROM PUBLIC;
REVOKE ALL ON TABLE zone_templates FROM bind;
GRANT ALL ON TABLE zone_templates TO bind;
GRANT SELECT,DELETE,UPDATE ON TABLE zone_templates TO butterfly;


--
-- Name: zone_zid_seq; Type: ACL; Schema: public; Owner: bind
--

REVOKE ALL ON SEQUENCE zone_zid_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE zone_zid_seq FROM bind;
GRANT ALL ON SEQUENCE zone_zid_seq TO bind;


--
-- PostgreSQL database dump complete
--

