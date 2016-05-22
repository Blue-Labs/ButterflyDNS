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
\.


--
-- Name: canonical_cid_seq; Type: SEQUENCE SET; Schema: public; Owner: bind
--

SELECT pg_catalog.setval('canonical_cid_seq', 1, true);


--
-- Data for Name: owners; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY owners (manager, contact, actual_owner, rid) FROM stdin;
\.


--
-- Name: owners_rid_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('owners_rid_seq', 1, true);


--
-- Data for Name: record; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY record (rid, host, zone, ttl, type, priority, data, created, updated) FROM stdin;
\.


--
-- Name: record_rid_seq; Type: SEQUENCE SET; Schema: public; Owner: bind
--

SELECT pg_catalog.setval('record_rid_seq', 1, true);


--
-- Data for Name: std_ns_by_admin; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY std_ns_by_admin (admin, ns) FROM stdin;
\.


--
-- Data for Name: tld; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY tld (rid, extension) FROM stdin;
\.


--
-- Name: tld_tid_seq; Type: SEQUENCE SET; Schema: public; Owner: bind
--

SELECT pg_catalog.setval('tld_tid_seq', 1, true);


--
-- Data for Name: xfr; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY xfr (rid, zone, client, created, updated) FROM stdin;
\.


--
-- Name: xfr_xid_seq; Type: SEQUENCE SET; Schema: public; Owner: bind
--

SELECT pg_catalog.setval('xfr_xid_seq', 1, true);


--
-- Data for Name: zone; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY zone (rid, name, tld, comment, manager) FROM stdin;
\.


--
-- Name: zone_template_rid_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('zone_template_rid_seq', 1, true);


--
-- Data for Name: zone_templates; Type: TABLE DATA; Schema: public; Owner: bind
--

COPY zone_templates (rid, name, host, ttl, type, priority, data, created, updated) FROM stdin;
\.


--
-- Name: zone_zid_seq; Type: SEQUENCE SET; Schema: public; Owner: bind
--

SELECT pg_catalog.setval('zone_zid_seq', 1, true);


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

