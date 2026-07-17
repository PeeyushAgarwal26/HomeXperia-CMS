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
--  Contains: full schema for all 24 tables (admin_users, states, modules,
--  admin_user_module_permissions, refresh_tokens, password_reset_tokens,
--  activity_logs, parent_categories, child_categories, room_categories,
--  suppliers, supplier_child_categories, supplier_module_permissions,
--  customers, customer_suppliers, customer_login_events, filters,
--  filter_values, products, product_filter_values, product_upload_logs,
--  product_upload_log_items, notification_templates,
--  notification_template_suppliers) plus seed data for states (36) and
--  modules (25) — the read-only reference tables.
--  Deliberately excludes admin_users data: the super admin is created
--  per-environment via `./setup.sh setup` / `python -m
--  scripts.create_superadmin`, never baked into a checked-in file, since
--  there is no create-account page in this admin panel and a shared
--  credential in git would defeat the point. Also excludes every other
--  table's rows (categories, suppliers, customers, filters, products,
--  room_categories, etc.) — those are real operational data, not
--  reference/seed data.
--
--  ./setup.sh runs Alembic migrations + scripts/seed_reference_data.py by
--  default (see docs/03-backend-architecture.md); this dump is a faster
--  fresh-environment path or a reference artifact for DBAs, not required
--  for normal setup.
-- ============================================================

--

--
-- PostgreSQL database dump
--

\restrict GtHS80ZH0jph9D8urLvNrC1b7zaHBjgs17e6Nal2D7EFcRFgLtffiVyiz6mjCZm

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
    name character varying(250) NOT NULL,
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
-- Name: child_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.child_categories (
    parent_category_id uuid NOT NULL,
    name character varying(250) NOT NULL,
    icon_url character varying(500),
    sort_order smallint NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: customer_login_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_login_events (
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    logged_in_at timestamp with time zone DEFAULT now() NOT NULL,
    ip_address character varying(45)
);


--
-- Name: customer_suppliers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_suppliers (
    customer_id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    mapped_by uuid,
    mapped_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: customers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customers (
    name character varying(250) NOT NULL,
    date_of_start date,
    email character varying(255),
    phone_number character varying(20) NOT NULL,
    gst_number character varying(20),
    address character varying(255),
    pin_code character varying(10),
    state_code character varying(10),
    city character varying(100),
    profile_image_url character varying(500),
    device_limit smallint NOT NULL,
    active_device_count smallint NOT NULL,
    last_login_at timestamp with time zone,
    customer_code character varying(100) NOT NULL,
    password_hash character varying(255) NOT NULL,
    is_active boolean NOT NULL,
    created_by uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: filter_values; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.filter_values (
    filter_id uuid NOT NULL,
    child_category_id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    value character varying(250) NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: filters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.filters (
    name character varying(250) NOT NULL,
    is_active boolean NOT NULL,
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
-- Name: notification_template_suppliers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notification_template_suppliers (
    template_id uuid NOT NULL,
    supplier_id uuid NOT NULL
);


--
-- Name: notification_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notification_templates (
    heading character varying(250) NOT NULL,
    message character varying(2000) NOT NULL,
    image_url character varying(500),
    scheduled_at timestamp with time zone NOT NULL,
    is_sent boolean NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: parent_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parent_categories (
    name character varying(250) NOT NULL,
    icon_url character varying(500),
    sort_order smallint NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
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
-- Name: product_filter_values; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_filter_values (
    product_id uuid NOT NULL,
    filter_value_id uuid NOT NULL
);


--
-- Name: product_upload_log_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_upload_log_items (
    id uuid NOT NULL,
    log_id uuid NOT NULL,
    row_no integer NOT NULL,
    catalog_name character varying(250),
    is_success boolean NOT NULL,
    message character varying(1000),
    action character varying(20)
);


--
-- Name: product_upload_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_upload_logs (
    id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    uploaded_by uuid NOT NULL,
    file_name character varying(255) NOT NULL,
    total_rows integer NOT NULL,
    success_count integer NOT NULL,
    error_count integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    status character varying(20) NOT NULL,
    error_message character varying(1000)
);


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    child_category_id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    order_no integer NOT NULL,
    catalog_name character varying(250) NOT NULL,
    design_no character varying(100),
    bar_code character varying(100) NOT NULL,
    image_url character varying(500),
    available_quantity integer,
    rate numeric(10,2),
    length numeric(10,2) NOT NULL,
    width numeric(10,2) NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    shine_fabric smallint DEFAULT '0'::smallint NOT NULL,
    fabric_transparency smallint DEFAULT '0'::smallint NOT NULL
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
-- Name: room_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.room_categories (
    name character varying(250) NOT NULL,
    order_no integer NOT NULL,
    icon_url character varying(500),
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
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
-- Name: supplier_child_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.supplier_child_categories (
    supplier_id uuid NOT NULL,
    child_category_id uuid NOT NULL,
    granted_by uuid,
    granted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: supplier_module_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.supplier_module_permissions (
    supplier_id uuid NOT NULL,
    module_id uuid NOT NULL,
    granted_by uuid,
    granted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: suppliers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suppliers (
    name character varying(250) NOT NULL,
    start_of_subscription date,
    email character varying(255),
    phone_number character varying(20) NOT NULL,
    gst_number character varying(20),
    address character varying(255),
    pin_code character varying(10),
    state_code character varying(10) NOT NULL,
    city character varying(100) NOT NULL,
    web_link character varying(500),
    logo_url character varying(500),
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
-- Name: child_categories child_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_categories
    ADD CONSTRAINT child_categories_pkey PRIMARY KEY (id);


--
-- Name: customer_login_events customer_login_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_login_events
    ADD CONSTRAINT customer_login_events_pkey PRIMARY KEY (id);


--
-- Name: customer_suppliers customer_suppliers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_suppliers
    ADD CONSTRAINT customer_suppliers_pkey PRIMARY KEY (customer_id, supplier_id);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: filter_values filter_values_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filter_values
    ADD CONSTRAINT filter_values_pkey PRIMARY KEY (id);


--
-- Name: filters filters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filters
    ADD CONSTRAINT filters_pkey PRIMARY KEY (id);


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
-- Name: notification_template_suppliers notification_template_suppliers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_template_suppliers
    ADD CONSTRAINT notification_template_suppliers_pkey PRIMARY KEY (template_id, supplier_id);


--
-- Name: notification_templates notification_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_templates
    ADD CONSTRAINT notification_templates_pkey PRIMARY KEY (id);


--
-- Name: parent_categories parent_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parent_categories
    ADD CONSTRAINT parent_categories_pkey PRIMARY KEY (id);


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
-- Name: product_filter_values product_filter_values_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_filter_values
    ADD CONSTRAINT product_filter_values_pkey PRIMARY KEY (product_id, filter_value_id);


--
-- Name: product_upload_log_items product_upload_log_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_upload_log_items
    ADD CONSTRAINT product_upload_log_items_pkey PRIMARY KEY (id);


--
-- Name: product_upload_logs product_upload_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_upload_logs
    ADD CONSTRAINT product_upload_logs_pkey PRIMARY KEY (id);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


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
-- Name: room_categories room_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_categories
    ADD CONSTRAINT room_categories_pkey PRIMARY KEY (id);


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
-- Name: supplier_child_categories supplier_child_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_child_categories
    ADD CONSTRAINT supplier_child_categories_pkey PRIMARY KEY (supplier_id, child_category_id);


--
-- Name: supplier_module_permissions supplier_module_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_module_permissions
    ADD CONSTRAINT supplier_module_permissions_pkey PRIMARY KEY (supplier_id, module_id);


--
-- Name: suppliers suppliers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_pkey PRIMARY KEY (id);


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
-- Name: ix_child_categories_parent_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_categories_parent_category_id ON public.child_categories USING btree (parent_category_id);


--
-- Name: ix_customer_login_events_customer_id_logged_in_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_login_events_customer_id_logged_in_at ON public.customer_login_events USING btree (customer_id, logged_in_at);


--
-- Name: ix_customers_customer_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_customers_customer_code ON public.customers USING btree (customer_code) WHERE (deleted_at IS NULL);


--
-- Name: ix_customers_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_customers_email ON public.customers USING btree (email) WHERE (deleted_at IS NULL);


--
-- Name: ix_customers_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_is_active ON public.customers USING btree (is_active);


--
-- Name: ix_customers_phone_number; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_customers_phone_number ON public.customers USING btree (phone_number) WHERE (deleted_at IS NULL);


--
-- Name: ix_customers_state_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_state_code ON public.customers USING btree (state_code);


--
-- Name: ix_filter_values_child_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_filter_values_child_category_id ON public.filter_values USING btree (child_category_id);


--
-- Name: ix_filter_values_filter_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_filter_values_filter_id ON public.filter_values USING btree (filter_id);


--
-- Name: ix_filter_values_supplier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_filter_values_supplier_id ON public.filter_values USING btree (supplier_id);


--
-- Name: ix_filters_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_filters_name ON public.filters USING btree (name) WHERE (deleted_at IS NULL);


--
-- Name: ix_modules_parent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_modules_parent_id ON public.modules USING btree (parent_id);


--
-- Name: ix_parent_categories_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_parent_categories_name ON public.parent_categories USING btree (name) WHERE (deleted_at IS NULL);


--
-- Name: ix_password_reset_tokens_admin_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_password_reset_tokens_admin_user_id ON public.password_reset_tokens USING btree (admin_user_id);


--
-- Name: ix_product_upload_log_items_log_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_upload_log_items_log_id ON public.product_upload_log_items USING btree (log_id);


--
-- Name: ix_product_upload_logs_supplier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_upload_logs_supplier_id ON public.product_upload_logs USING btree (supplier_id);


--
-- Name: ix_products_bar_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_bar_code ON public.products USING btree (bar_code);


--
-- Name: ix_products_child_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_child_category_id ON public.products USING btree (child_category_id);


--
-- Name: ix_products_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_is_active ON public.products USING btree (is_active);


--
-- Name: ix_products_supplier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_supplier_id ON public.products USING btree (supplier_id);


--
-- Name: ix_refresh_tokens_admin_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_refresh_tokens_admin_user_id ON public.refresh_tokens USING btree (admin_user_id);


--
-- Name: ix_suppliers_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_suppliers_is_active ON public.suppliers USING btree (is_active);


--
-- Name: ix_suppliers_phone_number; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_suppliers_phone_number ON public.suppliers USING btree (phone_number) WHERE (deleted_at IS NULL);


--
-- Name: ix_suppliers_state_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_suppliers_state_code ON public.suppliers USING btree (state_code);


--
-- Name: ix_suppliers_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_suppliers_username ON public.suppliers USING btree (username) WHERE (deleted_at IS NULL);


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
-- Name: child_categories child_categories_parent_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_categories
    ADD CONSTRAINT child_categories_parent_category_id_fkey FOREIGN KEY (parent_category_id) REFERENCES public.parent_categories(id);


--
-- Name: customer_login_events customer_login_events_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_login_events
    ADD CONSTRAINT customer_login_events_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: customer_suppliers customer_suppliers_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_suppliers
    ADD CONSTRAINT customer_suppliers_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: customer_suppliers customer_suppliers_mapped_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_suppliers
    ADD CONSTRAINT customer_suppliers_mapped_by_fkey FOREIGN KEY (mapped_by) REFERENCES public.admin_users(id);


--
-- Name: customer_suppliers customer_suppliers_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_suppliers
    ADD CONSTRAINT customer_suppliers_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


--
-- Name: customers customers_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.admin_users(id);


--
-- Name: customers customers_state_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_state_code_fkey FOREIGN KEY (state_code) REFERENCES public.states(code);


--
-- Name: filter_values filter_values_child_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filter_values
    ADD CONSTRAINT filter_values_child_category_id_fkey FOREIGN KEY (child_category_id) REFERENCES public.child_categories(id);


--
-- Name: filter_values filter_values_filter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filter_values
    ADD CONSTRAINT filter_values_filter_id_fkey FOREIGN KEY (filter_id) REFERENCES public.filters(id);


--
-- Name: filter_values filter_values_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filter_values
    ADD CONSTRAINT filter_values_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id);


--
-- Name: modules modules_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.modules(id);


--
-- Name: notification_template_suppliers notification_template_suppliers_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_template_suppliers
    ADD CONSTRAINT notification_template_suppliers_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


--
-- Name: notification_template_suppliers notification_template_suppliers_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_template_suppliers
    ADD CONSTRAINT notification_template_suppliers_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.notification_templates(id) ON DELETE CASCADE;


--
-- Name: password_reset_tokens password_reset_tokens_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.admin_users(id) ON DELETE CASCADE;


--
-- Name: product_filter_values product_filter_values_filter_value_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_filter_values
    ADD CONSTRAINT product_filter_values_filter_value_id_fkey FOREIGN KEY (filter_value_id) REFERENCES public.filter_values(id) ON DELETE CASCADE;


--
-- Name: product_filter_values product_filter_values_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_filter_values
    ADD CONSTRAINT product_filter_values_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: product_upload_log_items product_upload_log_items_log_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_upload_log_items
    ADD CONSTRAINT product_upload_log_items_log_id_fkey FOREIGN KEY (log_id) REFERENCES public.product_upload_logs(id) ON DELETE CASCADE;


--
-- Name: product_upload_logs product_upload_logs_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_upload_logs
    ADD CONSTRAINT product_upload_logs_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id);


--
-- Name: product_upload_logs product_upload_logs_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_upload_logs
    ADD CONSTRAINT product_upload_logs_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.admin_users(id);


--
-- Name: products products_child_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_child_category_id_fkey FOREIGN KEY (child_category_id) REFERENCES public.child_categories(id);


--
-- Name: products products_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id);


--
-- Name: refresh_tokens refresh_tokens_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.admin_users(id) ON DELETE CASCADE;


--
-- Name: supplier_child_categories supplier_child_categories_child_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_child_categories
    ADD CONSTRAINT supplier_child_categories_child_category_id_fkey FOREIGN KEY (child_category_id) REFERENCES public.child_categories(id) ON DELETE CASCADE;


--
-- Name: supplier_child_categories supplier_child_categories_granted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_child_categories
    ADD CONSTRAINT supplier_child_categories_granted_by_fkey FOREIGN KEY (granted_by) REFERENCES public.admin_users(id);


--
-- Name: supplier_child_categories supplier_child_categories_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_child_categories
    ADD CONSTRAINT supplier_child_categories_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


--
-- Name: supplier_module_permissions supplier_module_permissions_granted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_module_permissions
    ADD CONSTRAINT supplier_module_permissions_granted_by_fkey FOREIGN KEY (granted_by) REFERENCES public.admin_users(id);


--
-- Name: supplier_module_permissions supplier_module_permissions_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_module_permissions
    ADD CONSTRAINT supplier_module_permissions_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.modules(id) ON DELETE CASCADE;


--
-- Name: supplier_module_permissions supplier_module_permissions_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_module_permissions
    ADD CONSTRAINT supplier_module_permissions_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


--
-- Name: suppliers suppliers_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.admin_users(id);


--
-- Name: suppliers suppliers_state_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_state_code_fkey FOREIGN KEY (state_code) REFERENCES public.states(code);


--
-- PostgreSQL database dump complete
--

\unrestrict GtHS80ZH0jph9D8urLvNrC1b7zaHBjgs17e6Nal2D7EFcRFgLtffiVyiz6mjCZm

--
-- PostgreSQL database dump
--

\restrict 47czzcPKreAEavkc5D8HQCewf6x2poQb4U266HSK6uJd6wulQwxsBXbJeLSnaRC

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

INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('dashboard', 'Dashboard', NULL, 0, true, true, 'a8ec61d1-ab84-4599-8e47-bbdeda1e6fef', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master.room_category', 'Room Category', '63c2805d-5527-4291-bfb6-44da8e6e92d3', 7, false, true, '725da421-96f4-47f5-8431-3a31060cacf4', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('activity', 'Activity', NULL, 8, false, true, '2eff812a-4ab3-4d1b-a9e8-b15c25364f43', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('activity.orders', 'Orders', '2eff812a-4ab3-4d1b-a9e8-b15c25364f43', 9, false, true, '14c83c85-6a05-4d0a-a23e-e3e08f7e3dcd', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('upload_product', 'Upload Product', NULL, 10, false, true, 'b8e747d4-d24b-468c-b44c-0c300c7254bc', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('user_management', 'User Management', NULL, 13, true, true, '8a6b1865-5d4d-42fd-98f8-d6829e5a918b', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('user_management.sub_admin', 'Sub Admin', '8a6b1865-5d4d-42fd-98f8-d6829e5a918b', 15, true, true, '69b691e6-6e54-4eb8-833b-552b09395216', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('logs', 'Logs', NULL, 17, false, true, 'e7d7a486-1a01-4828-be59-6143b58ea3ab', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('notification', 'Notification', NULL, 19, false, true, '1c15b4df-55ea-4b75-9573-3b256aa61683', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('app_feedback', 'App Feedback', NULL, 21, false, true, '8f7b217c-420c-4e35-8a9d-eddeae21e4cc', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('setting', 'Setting', NULL, 22, false, true, '67211ddd-48ae-4935-ad6c-a150469b5b51', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('setting.change_password', 'Change Password', '67211ddd-48ae-4935-ad6c-a150469b5b51', 23, true, true, '4d14ca3a-a566-4613-aaac-929f17f396c4', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('setting.log_off', 'Log Off', '67211ddd-48ae-4935-ad6c-a150469b5b51', 24, false, true, 'bca2cde4-7c80-440e-9d77-f4548ed9a191', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('user_management.customer', 'Customer', '8a6b1865-5d4d-42fd-98f8-d6829e5a918b', 14, true, true, '80c6b6c9-25fd-4cf7-891c-c7ad43c50587', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 14:13:15.618263+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('user_management.suppliers', 'Suppliers', '8a6b1865-5d4d-42fd-98f8-d6829e5a918b', 16, true, true, '7fb7decd-1174-45fa-8227-60e70827db5c', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 14:13:15.618263+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('logs.customer_login_history', 'Customer Login History', 'e7d7a486-1a01-4828-be59-6143b58ea3ab', 18, true, true, 'eaea4cc4-a170-4d37-8cda-ba03f3c0c79b', '2026-07-13 10:47:15.84916+05:30', '2026-07-14 11:20:40.890941+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master', 'Master', NULL, 1, true, true, '63c2805d-5527-4291-bfb6-44da8e6e92d3', '2026-07-13 10:47:15.84916+05:30', '2026-07-14 13:16:06.498611+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master.parent_category', 'Parent Category', '63c2805d-5527-4291-bfb6-44da8e6e92d3', 2, true, true, '9302553d-fb25-4877-b88e-8bdd4de72356', '2026-07-13 10:47:15.84916+05:30', '2026-07-14 13:16:06.498611+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master.child_category', 'Child Category', '63c2805d-5527-4291-bfb6-44da8e6e92d3', 3, true, true, '01ded099-96a9-4e68-918e-15b142668ffa', '2026-07-13 10:47:15.84916+05:30', '2026-07-14 13:16:06.498611+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master.filter', 'Filter', '63c2805d-5527-4291-bfb6-44da8e6e92d3', 4, true, true, '8545d6d7-1e6e-4f72-ab88-9bd143703c35', '2026-07-13 10:47:15.84916+05:30', '2026-07-15 10:57:37.646947+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master.filter_value', 'Filter Value', '63c2805d-5527-4291-bfb6-44da8e6e92d3', 5, true, true, '78df237c-e166-47bc-b478-30491344ec7a', '2026-07-13 10:47:15.84916+05:30', '2026-07-15 10:57:37.646947+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master.product', 'Product', '63c2805d-5527-4291-bfb6-44da8e6e92d3', 6, true, true, '691e98ab-8e9f-4d0a-9ef7-fbcd398325e9', '2026-07-13 10:47:15.84916+05:30', '2026-07-15 11:13:52.708942+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('upload_product.upload_files', 'Upload Files', 'b8e747d4-d24b-468c-b44c-0c300c7254bc', 11, true, true, '08387a0e-a14c-4413-9fac-ccd263b0799b', '2026-07-13 10:47:15.84916+05:30', '2026-07-17 11:34:20.010188+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('upload_product.log', 'Log', 'b8e747d4-d24b-468c-b44c-0c300c7254bc', 12, true, true, '5dea2e66-120b-40ff-bf40-e04859c6b90a', '2026-07-13 10:47:15.84916+05:30', '2026-07-17 11:34:20.010188+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('notification.template', 'Template', '1c15b4df-55ea-4b75-9573-3b256aa61683', 20, true, true, 'd9882670-f535-4515-96d9-ccbb59ffce59', '2026-07-13 10:47:15.84916+05:30', '2026-07-17 16:42:58.109446+05:30');


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

\unrestrict 47czzcPKreAEavkc5D8HQCewf6x2poQb4U266HSK6uJd6wulQwxsBXbJeLSnaRC

