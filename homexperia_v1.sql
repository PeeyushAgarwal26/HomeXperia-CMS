-- ============================================================
--  HomeXperia Admin CMS  |  Schema + Reference Data  v1
-- ============================================================
--  Generated via pg_dump from the Alembic-managed schema — this file is a
--  snapshot, not the source of truth. Alembic migrations (alembic/versions/)
--  are canonical; regenerate this file after adding a migration:
--
--    pg_dump --schema-only --no-owner --no-privileges -T alembic_version \
--        -h <host> -U <user> -d <db> > /tmp/schema.sql
--    pg_dump --data-only --no-owner --column-inserts -t states -t modules \
--        -h <host> -U <user> -d <db> > /tmp/seed.sql
--    cat /tmp/schema.sql /tmp/seed.sql > homexperia_v1.sql
--
--  Contains: full schema for all 7 tables (admin_users, states, modules,
--  admin_user_module_permissions, refresh_tokens, password_reset_tokens,
--  activity_logs) plus seed data for states (36) and modules (24) — the
--  read-only reference tables. Deliberately excludes admin_users data: the
--  super admin is created per-environment via `./setup.sh setup` /
--  `python -m scripts.create_superadmin`, never baked into a checked-in
--  file, since there is no create-account page in this admin panel and a
--  shared credential in git would defeat the point.
--
--  ./setup.sh runs Alembic migrations + scripts/seed_reference_data.py by
--  default (see docs/03-backend-architecture.md); this dump is a faster
--  fresh-environment path or a reference artifact for DBAs, not required
--  for normal setup.
-- ============================================================

--
-- PostgreSQL database dump
--

\restrict SNltkHEdWQPnScAxJSUX8tzb8T7XENJAbjqKmIfHTYQ3GLu2DKwa9ifaKwPP1uK

-- Dumped from database version 17.10 (Homebrew)
-- Dumped by pg_dump version 17.10 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activity_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.activity_logs (
    id uuid NOT NULL,
    admin_user_id uuid,
    actor_username character varying(100),
    action character varying(100) NOT NULL,
    method character varying(10) NOT NULL,
    path character varying(255) NOT NULL,
    status_code smallint NOT NULL,
    ip_address character varying(45),
    user_agent character varying(255),
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: admin_user_module_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_user_module_permissions (
    admin_user_id uuid NOT NULL,
    module_id uuid NOT NULL,
    granted_by uuid,
    granted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: admin_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_users (
    is_super_admin boolean NOT NULL,
    name character varying(150) NOT NULL,
    date_of_birth date,
    email character varying(255) NOT NULL,
    phone_number character varying(20) NOT NULL,
    address character varying(255),
    pin_code character varying(10) NOT NULL,
    state_code character varying(10) NOT NULL,
    city character varying(100) NOT NULL,
    profile_image_url character varying(500),
    username character varying(100) NOT NULL,
    password_hash character varying(255) NOT NULL,
    is_active boolean NOT NULL,
    created_by uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: modules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.modules (
    key character varying(100) NOT NULL,
    name character varying(100) NOT NULL,
    parent_id uuid,
    sort_order smallint NOT NULL,
    is_buildable boolean NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_tokens (
    id uuid NOT NULL,
    admin_user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    requested_ip character varying(45),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: refresh_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.refresh_tokens (
    id uuid NOT NULL,
    admin_user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    issued_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    ip_address character varying(45),
    user_agent character varying(255)
);


--
-- Name: states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.states (
    code character varying(10) NOT NULL,
    name character varying(100) NOT NULL,
    sort_order smallint NOT NULL
);


--
-- Name: activity_logs activity_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_pkey PRIMARY KEY (id);


--
-- Name: admin_user_module_permissions admin_user_module_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_user_module_permissions
    ADD CONSTRAINT admin_user_module_permissions_pkey PRIMARY KEY (admin_user_id, module_id);


--
-- Name: admin_users admin_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_users
    ADD CONSTRAINT admin_users_pkey PRIMARY KEY (id);


--
-- Name: modules modules_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_key_key UNIQUE (key);


--
-- Name: modules modules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: states states_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.states
    ADD CONSTRAINT states_name_key UNIQUE (name);


--
-- Name: states states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.states
    ADD CONSTRAINT states_pkey PRIMARY KEY (code);


--
-- Name: ix_activity_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_activity_logs_action ON public.activity_logs USING btree (action);


--
-- Name: ix_activity_logs_admin_user_id_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_activity_logs_admin_user_id_created_at ON public.activity_logs USING btree (admin_user_id, created_at);


--
-- Name: ix_admin_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_admin_users_email ON public.admin_users USING btree (email) WHERE (deleted_at IS NULL);


--
-- Name: ix_admin_users_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_admin_users_is_active ON public.admin_users USING btree (is_active);


--
-- Name: ix_admin_users_phone_number; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_admin_users_phone_number ON public.admin_users USING btree (phone_number) WHERE (deleted_at IS NULL);


--
-- Name: ix_admin_users_state_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_admin_users_state_code ON public.admin_users USING btree (state_code);


--
-- Name: ix_admin_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_admin_users_username ON public.admin_users USING btree (username) WHERE (deleted_at IS NULL);


--
-- Name: ix_modules_parent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_modules_parent_id ON public.modules USING btree (parent_id);


--
-- Name: ix_password_reset_tokens_admin_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_password_reset_tokens_admin_user_id ON public.password_reset_tokens USING btree (admin_user_id);


--
-- Name: ix_refresh_tokens_admin_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_refresh_tokens_admin_user_id ON public.refresh_tokens USING btree (admin_user_id);


--
-- Name: activity_logs activity_logs_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.admin_users(id);


--
-- Name: admin_user_module_permissions admin_user_module_permissions_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_user_module_permissions
    ADD CONSTRAINT admin_user_module_permissions_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.admin_users(id) ON DELETE CASCADE;


--
-- Name: admin_user_module_permissions admin_user_module_permissions_granted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_user_module_permissions
    ADD CONSTRAINT admin_user_module_permissions_granted_by_fkey FOREIGN KEY (granted_by) REFERENCES public.admin_users(id);


--
-- Name: admin_user_module_permissions admin_user_module_permissions_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_user_module_permissions
    ADD CONSTRAINT admin_user_module_permissions_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.modules(id) ON DELETE CASCADE;


--
-- Name: admin_users admin_users_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_users
    ADD CONSTRAINT admin_users_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.admin_users(id);


--
-- Name: admin_users admin_users_state_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_users
    ADD CONSTRAINT admin_users_state_code_fkey FOREIGN KEY (state_code) REFERENCES public.states(code);


--
-- Name: modules modules_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.modules(id);


--
-- Name: password_reset_tokens password_reset_tokens_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.admin_users(id) ON DELETE CASCADE;


--
-- Name: refresh_tokens refresh_tokens_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.admin_users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict SNltkHEdWQPnScAxJSUX8tzb8T7XENJAbjqKmIfHTYQ3GLu2DKwa9ifaKwPP1uK

--
-- PostgreSQL database dump
--

\restrict SvoUDrXSAIE8HdwWPZgggyQJ2R5nlhuyVHi8VFBch8FN5QcL4u6ozLXiO7YGs04

-- Dumped from database version 17.10 (Homebrew)
-- Dumped by pg_dump version 17.10 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: modules; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('dashboard', 'Dashboard', NULL, 0, true, true, 'b1bff791-500e-49d5-bd55-5ae1e68d33c9', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master', 'Master', NULL, 1, false, true, '8ba546d9-0f2d-4ac4-a64a-303e220e6d22', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master.parent_category', 'Parent Category', '8ba546d9-0f2d-4ac4-a64a-303e220e6d22', 2, false, true, 'b495b7ef-43ef-4dfa-8aed-110b2eef6a30', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master.child_category', 'Child Category', '8ba546d9-0f2d-4ac4-a64a-303e220e6d22', 3, false, true, 'c4c4c8c7-97a1-4586-85fe-09978afc4d8e', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master.filter_value', 'Filter Value', '8ba546d9-0f2d-4ac4-a64a-303e220e6d22', 4, false, true, 'ca8bcaa6-16cc-4a8f-9ca6-9a6173a92ad0', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('activity', 'Activity', NULL, 5, false, true, '99e63ee4-f7e5-4ed4-9377-9a23fc7c9b99', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('activity.orders', 'Orders', '99e63ee4-f7e5-4ed4-9377-9a23fc7c9b99', 6, false, true, 'e8021bc1-2264-43d8-b310-0ba8976069e5', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('activity.filter', 'Filter', '99e63ee4-f7e5-4ed4-9377-9a23fc7c9b99', 7, false, true, 'c2a930c1-421e-4881-9524-54dbef5967bf', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('activity.product', 'Product', '99e63ee4-f7e5-4ed4-9377-9a23fc7c9b99', 8, false, true, '4dc1394f-a747-4d2a-9100-718c03d3ce07', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('upload_product', 'Upload Product', NULL, 9, false, true, 'a151c33c-2057-4fcb-a42f-c1af2e84efd6', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('upload_product.upload_files', 'Upload Files', 'a151c33c-2057-4fcb-a42f-c1af2e84efd6', 10, false, true, 'b6ce2285-90a3-4c8a-bba5-321be120d360', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('upload_product.logs', 'Logs', 'a151c33c-2057-4fcb-a42f-c1af2e84efd6', 11, false, true, 'dc47920e-c1a9-4c1b-93b8-15d9682e81ee', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('user_management', 'User Management', NULL, 12, true, true, 'a3370636-b486-4b55-9fef-1291df04a6a3', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('user_management.customer', 'Customer', 'a3370636-b486-4b55-9fef-1291df04a6a3', 13, false, true, '72326fae-6b48-49f0-af3b-60b96351eb1c', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('user_management.sub_admin', 'Sub Admin', 'a3370636-b486-4b55-9fef-1291df04a6a3', 14, true, true, 'deb77d56-5a26-4d2b-ad91-7c08385edf72', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('user_management.suppliers', 'Suppliers', 'a3370636-b486-4b55-9fef-1291df04a6a3', 15, false, true, '0b5dde46-6172-4141-806b-ea36f5873c68', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('logs', 'Logs', NULL, 16, false, true, '159b12bb-b748-472e-8642-99c291f182e2', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('logs.customer_login_history', 'Customer Login History', '159b12bb-b748-472e-8642-99c291f182e2', 17, false, true, 'a8a676ca-fc8b-4776-819a-190a9467177f', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('notification', 'Notification', NULL, 18, false, true, '4b0a16e4-b53f-4f41-bdd3-9d3d4ed498be', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('setting', 'Setting', NULL, 19, false, true, '9f758e8f-03ad-45ec-a646-37827c318124', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('setting.change_password', 'Change Password', '9f758e8f-03ad-45ec-a646-37827c318124', 20, true, true, '9d1c4a42-8f59-423f-bcd8-00d98ab57a3d', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('setting.log_off', 'Log Off', '9f758e8f-03ad-45ec-a646-37827c318124', 21, false, true, '3bd30f83-fb16-4b9d-b91f-0452947ca08f', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('app_feedback', 'App Feedback', NULL, 22, false, true, '1bdb0795-da8e-448c-8673-9a6088caa479', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('app_feedback.template', 'Template', '1bdb0795-da8e-448c-8673-9a6088caa479', 23, false, true, 'f1135afb-3a2f-44b3-8cfd-98ec8b45a56b', '2026-07-10 15:09:55.59192+05:30', '2026-07-10 15:09:55.59192+05:30');


--
-- Data for Name: states; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.states (code, name, sort_order) VALUES ('AP', 'Andhra Pradesh', 0);
INSERT INTO public.states (code, name, sort_order) VALUES ('AR', 'Arunachal Pradesh', 1);
INSERT INTO public.states (code, name, sort_order) VALUES ('AS', 'Assam', 2);
INSERT INTO public.states (code, name, sort_order) VALUES ('BR', 'Bihar', 3);
INSERT INTO public.states (code, name, sort_order) VALUES ('CG', 'Chhattisgarh', 4);
INSERT INTO public.states (code, name, sort_order) VALUES ('GA', 'Goa', 5);
INSERT INTO public.states (code, name, sort_order) VALUES ('GJ', 'Gujarat', 6);
INSERT INTO public.states (code, name, sort_order) VALUES ('HR', 'Haryana', 7);
INSERT INTO public.states (code, name, sort_order) VALUES ('HP', 'Himachal Pradesh', 8);
INSERT INTO public.states (code, name, sort_order) VALUES ('JH', 'Jharkhand', 9);
INSERT INTO public.states (code, name, sort_order) VALUES ('KA', 'Karnataka', 10);
INSERT INTO public.states (code, name, sort_order) VALUES ('KL', 'Kerala', 11);
INSERT INTO public.states (code, name, sort_order) VALUES ('MP', 'Madhya Pradesh', 12);
INSERT INTO public.states (code, name, sort_order) VALUES ('MH', 'Maharashtra', 13);
INSERT INTO public.states (code, name, sort_order) VALUES ('MN', 'Manipur', 14);
INSERT INTO public.states (code, name, sort_order) VALUES ('ML', 'Meghalaya', 15);
INSERT INTO public.states (code, name, sort_order) VALUES ('MZ', 'Mizoram', 16);
INSERT INTO public.states (code, name, sort_order) VALUES ('NL', 'Nagaland', 17);
INSERT INTO public.states (code, name, sort_order) VALUES ('OD', 'Odisha', 18);
INSERT INTO public.states (code, name, sort_order) VALUES ('PB', 'Punjab', 19);
INSERT INTO public.states (code, name, sort_order) VALUES ('RJ', 'Rajasthan', 20);
INSERT INTO public.states (code, name, sort_order) VALUES ('SK', 'Sikkim', 21);
INSERT INTO public.states (code, name, sort_order) VALUES ('TN', 'Tamil Nadu', 22);
INSERT INTO public.states (code, name, sort_order) VALUES ('TG', 'Telangana', 23);
INSERT INTO public.states (code, name, sort_order) VALUES ('TR', 'Tripura', 24);
INSERT INTO public.states (code, name, sort_order) VALUES ('UP', 'Uttar Pradesh', 25);
INSERT INTO public.states (code, name, sort_order) VALUES ('UK', 'Uttarakhand', 26);
INSERT INTO public.states (code, name, sort_order) VALUES ('WB', 'West Bengal', 27);
INSERT INTO public.states (code, name, sort_order) VALUES ('AN', 'Andaman and Nicobar Islands', 28);
INSERT INTO public.states (code, name, sort_order) VALUES ('CH', 'Chandigarh', 29);
INSERT INTO public.states (code, name, sort_order) VALUES ('DN', 'Dadra and Nagar Haveli and Daman and Diu', 30);
INSERT INTO public.states (code, name, sort_order) VALUES ('DL', 'Delhi', 31);
INSERT INTO public.states (code, name, sort_order) VALUES ('JK', 'Jammu and Kashmir', 32);
INSERT INTO public.states (code, name, sort_order) VALUES ('LA', 'Ladakh', 33);
INSERT INTO public.states (code, name, sort_order) VALUES ('LD', 'Lakshadweep', 34);
INSERT INTO public.states (code, name, sort_order) VALUES ('PY', 'Puducherry', 35);


--
-- PostgreSQL database dump complete
--

\unrestrict SvoUDrXSAIE8HdwWPZgggyQJ2R5nlhuyVHi8VFBch8FN5QcL4u6ozLXiO7YGs04

