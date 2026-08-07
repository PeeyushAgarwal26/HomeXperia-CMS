-- ============================================================
--  HomeXperia Admin CMS  |  Schema + Reference Data  v1
-- ============================================================
--  Generated via pg_dump from the Alembic-managed schema — this file is a
--  snapshot, not the source of truth. Alembic migrations (alembic/versions/)
--  are canonical; regenerate this file after adding a migration:
--
--    pg_dump --schema-only --no-owner --no-privileges -T alembic_version \
--        -h <host> -U <user> -d <db> > /tmp/schema.sql
--    pg_dump --data-only --no-owner --column-inserts --disable-triggers \
--        -t states -t modules \
--        -h <host> -U <user> -d <db> > /tmp/seed.sql
--    cat /tmp/schema.sql /tmp/seed.sql > homexperia_v1.sql
--
--  Contains: full schema for all 46 tables currently under Alembic
--  (see alembic/versions/ for the authoritative, up-to-date list — this
--  comment intentionally doesn't enumerate them all, to avoid silently
--  going stale here the way an earlier "20 tables" list once did) plus
--  seed data for states (36) and modules (32) — the read-only reference
--  tables.
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

\restrict GDCxfvkzXyCHiAvaXhEtdg95xw7hA9mBOqnfFwVV3bHtPzcP0IaWSyOSsxqXwzf

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
-- Name: admin_user_login_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_user_login_events (
    id uuid NOT NULL,
    admin_user_id uuid NOT NULL,
    logged_in_at timestamp with time zone DEFAULT now() NOT NULL,
    ip_address character varying(45),
    user_agent character varying(255)
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
    email character varying(255),
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
-- Name: ai_credit_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_credit_transactions (
    id uuid NOT NULL,
    supplier_id uuid,
    customer_id uuid,
    room_id character varying(250),
    room_category_name character varying(250),
    is_curtain_room boolean NOT NULL,
    action_type character varying(30) NOT NULL,
    tooltip_element_label character varying(250),
    product_id uuid,
    credits_charged integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    billed_customer_id uuid
);


--
-- Name: cart_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cart_items (
    id uuid NOT NULL,
    cart_id uuid NOT NULL,
    product_id uuid NOT NULL,
    quantity integer NOT NULL,
    uom character varying(50) NOT NULL
);


--
-- Name: carts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.carts (
    customer_id uuid NOT NULL,
    status character varying(20) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
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
-- Name: cities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cities (
    id uuid NOT NULL,
    state_code character varying(10) NOT NULL,
    name character varying(100) NOT NULL,
    sort_order smallint NOT NULL
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
-- Name: customer_refresh_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_refresh_tokens (
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    issued_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    ip_address character varying(45),
    user_agent character varying(255)
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
    deleted_at timestamp with time zone,
    linked_supplier_id uuid
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
-- Name: order_invoice_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.order_invoice_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_items (
    id uuid NOT NULL,
    order_id uuid NOT NULL,
    product_id uuid,
    catalog_name character varying(250) NOT NULL,
    design_no character varying(100),
    image_url character varying(500),
    uom character varying(50) NOT NULL,
    rate numeric(10,2) NOT NULL,
    quantity integer NOT NULL,
    amount numeric(12,2) NOT NULL,
    supplier_name character varying(250),
    category_name character varying(250),
    width numeric(10,2)
);


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    customer_id uuid NOT NULL,
    invoice_number character varying(50) NOT NULL,
    client_name character varying(250) NOT NULL,
    client_email character varying(255) NOT NULL,
    client_whatsapp_no character varying(20) NOT NULL,
    owner_email character varying(255) NOT NULL,
    owner_whatsapp_no character varying(20) NOT NULL,
    total_amount numeric(12,2) NOT NULL,
    notes character varying(1000),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
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
    uploaded_by uuid,
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
    deleted_at timestamp with time zone
);


--
-- Name: qr_catalogue_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.qr_catalogue_entries (
    customer_id uuid NOT NULL,
    filter_value character varying(250) NOT NULL,
    catalog_name character varying(250) NOT NULL,
    room_category_image_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    override_image_url character varying(500)
);


--
-- Name: qr_catalogue_entry_hotspots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.qr_catalogue_entry_hotspots (
    qr_catalogue_entry_id uuid NOT NULL,
    hotspot_id uuid,
    product_id uuid NOT NULL,
    inline_label character varying(250),
    inline_type character varying(50),
    inline_x double precision,
    inline_y double precision,
    inline_mask_image_url character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL
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
-- Name: room_category_image_hotspots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.room_category_image_hotspots (
    room_category_image_id uuid NOT NULL,
    label character varying(250) NOT NULL,
    type character varying(50) NOT NULL,
    options character varying(500),
    confidence numeric(4,3),
    description character varying(1000),
    mask_image_url character varying(500) NOT NULL,
    is_uploaded_to_cdn boolean NOT NULL,
    x numeric(6,4) NOT NULL,
    y numeric(6,4) NOT NULL,
    order_no integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    sub_type character varying(50)
);


--
-- Name: room_category_image_suppliers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.room_category_image_suppliers (
    room_category_image_id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    mapped_by uuid,
    mapped_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: room_category_images; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.room_category_images (
    room_category_id uuid NOT NULL,
    order_no integer NOT NULL,
    image_url character varying(500) NOT NULL,
    is_uploaded_to_cdn boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: saved_qr_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.saved_qr_codes (
    customer_id uuid NOT NULL,
    filter_values character varying(1000),
    brand_logo_url character varying(500),
    image_url character varying(500) NOT NULL,
    created_by uuid,
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
-- Name: supplier_ai_credit_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.supplier_ai_credit_batches (
    supplier_id uuid,
    batch_date date NOT NULL,
    amount_granted integer NOT NULL,
    amount_remaining integer NOT NULL,
    subscription_year_number integer NOT NULL,
    source character varying(30) NOT NULL,
    note character varying(500),
    created_by uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    customer_id uuid,
    CONSTRAINT ck_ai_credit_batches_exactly_one_owner CHECK (((supplier_id IS NOT NULL) <> (customer_id IS NOT NULL)))
);


--
-- Name: supplier_ai_credit_ledger_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.supplier_ai_credit_ledger_entries (
    supplier_id uuid,
    period_start date NOT NULL,
    period_end date NOT NULL,
    credits_allocated integer NOT NULL,
    credits_carried_forward integer NOT NULL,
    credits_used_mask_generated integer NOT NULL,
    credits_used_curtain_applied integer NOT NULL,
    credits_purchased integer NOT NULL,
    closing_balance integer NOT NULL,
    credits_lapsed integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    customer_id uuid,
    CONSTRAINT ck_ai_credit_ledger_exactly_one_owner CHECK (((supplier_id IS NOT NULL) <> (customer_id IS NOT NULL)))
);


--
-- Name: supplier_ai_credit_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.supplier_ai_credit_settings (
    supplier_id uuid,
    monthly_base_allocation integer NOT NULL,
    tier character varying(50),
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    customer_id uuid,
    CONSTRAINT ck_ai_credit_settings_exactly_one_owner CHECK (((supplier_id IS NOT NULL) <> (customer_id IS NOT NULL)))
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
-- Name: supplier_customer_themes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.supplier_customer_themes (
    supplier_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    primary_color character varying(20),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    secondary_color character varying(20)
);


--
-- Name: supplier_login_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.supplier_login_events (
    id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    logged_in_at timestamp with time zone DEFAULT now() NOT NULL,
    ip_address character varying(45),
    user_agent character varying(255)
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
-- Name: supplier_refresh_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.supplier_refresh_tokens (
    id uuid NOT NULL,
    supplier_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    issued_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    ip_address character varying(45),
    user_agent character varying(255)
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
    deleted_at timestamp with time zone,
    linked_customer_id uuid
);


--
-- Name: tooltip_usages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tooltip_usages (
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    room_id character varying(255) NOT NULL,
    hotspot_id character varying(255) NOT NULL,
    category character varying(50),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: usage_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usage_logs (
    customer_id uuid NOT NULL,
    room_id character varying(255),
    source character varying(50) NOT NULL,
    curtain_style character varying(100),
    input_tokens integer NOT NULL,
    output_tokens integer NOT NULL,
    total_tokens integer NOT NULL,
    openai_status character varying(20),
    segmentation_status character varying(20),
    generation_units integer NOT NULL,
    tooltip_units integer NOT NULL,
    error character varying(2000),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: activity_logs activity_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_pkey PRIMARY KEY (id);


--
-- Name: admin_user_login_events admin_user_login_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_user_login_events
    ADD CONSTRAINT admin_user_login_events_pkey PRIMARY KEY (id);


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
-- Name: ai_credit_transactions ai_credit_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_credit_transactions
    ADD CONSTRAINT ai_credit_transactions_pkey PRIMARY KEY (id);


--
-- Name: cart_items cart_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT cart_items_pkey PRIMARY KEY (id);


--
-- Name: carts carts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.carts
    ADD CONSTRAINT carts_pkey PRIMARY KEY (id);


--
-- Name: child_categories child_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_categories
    ADD CONSTRAINT child_categories_pkey PRIMARY KEY (id);


--
-- Name: cities cities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities
    ADD CONSTRAINT cities_pkey PRIMARY KEY (id);


--
-- Name: customer_login_events customer_login_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_login_events
    ADD CONSTRAINT customer_login_events_pkey PRIMARY KEY (id);


--
-- Name: customer_refresh_tokens customer_refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_refresh_tokens
    ADD CONSTRAINT customer_refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: customer_refresh_tokens customer_refresh_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_refresh_tokens
    ADD CONSTRAINT customer_refresh_tokens_token_hash_key UNIQUE (token_hash);


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
-- Name: order_items order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (id);


--
-- Name: orders orders_invoice_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_invoice_number_key UNIQUE (invoice_number);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


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
-- Name: qr_catalogue_entries qr_catalogue_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qr_catalogue_entries
    ADD CONSTRAINT qr_catalogue_entries_pkey PRIMARY KEY (id);


--
-- Name: qr_catalogue_entry_hotspots qr_catalogue_entry_hotspots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qr_catalogue_entry_hotspots
    ADD CONSTRAINT qr_catalogue_entry_hotspots_pkey PRIMARY KEY (id);


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
-- Name: room_category_image_hotspots room_category_image_hotspots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_category_image_hotspots
    ADD CONSTRAINT room_category_image_hotspots_pkey PRIMARY KEY (id);


--
-- Name: room_category_image_suppliers room_category_image_suppliers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_category_image_suppliers
    ADD CONSTRAINT room_category_image_suppliers_pkey PRIMARY KEY (room_category_image_id, supplier_id);


--
-- Name: room_category_images room_category_images_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_category_images
    ADD CONSTRAINT room_category_images_pkey PRIMARY KEY (id);


--
-- Name: saved_qr_codes saved_qr_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_qr_codes
    ADD CONSTRAINT saved_qr_codes_pkey PRIMARY KEY (id);


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
-- Name: supplier_ai_credit_batches supplier_ai_credit_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_batches
    ADD CONSTRAINT supplier_ai_credit_batches_pkey PRIMARY KEY (id);


--
-- Name: supplier_ai_credit_ledger_entries supplier_ai_credit_ledger_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_ledger_entries
    ADD CONSTRAINT supplier_ai_credit_ledger_entries_pkey PRIMARY KEY (id);


--
-- Name: supplier_ai_credit_settings supplier_ai_credit_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_settings
    ADD CONSTRAINT supplier_ai_credit_settings_pkey PRIMARY KEY (id);


--
-- Name: supplier_child_categories supplier_child_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_child_categories
    ADD CONSTRAINT supplier_child_categories_pkey PRIMARY KEY (supplier_id, child_category_id);


--
-- Name: supplier_customer_themes supplier_customer_themes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_customer_themes
    ADD CONSTRAINT supplier_customer_themes_pkey PRIMARY KEY (id);


--
-- Name: supplier_login_events supplier_login_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_login_events
    ADD CONSTRAINT supplier_login_events_pkey PRIMARY KEY (id);


--
-- Name: supplier_module_permissions supplier_module_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_module_permissions
    ADD CONSTRAINT supplier_module_permissions_pkey PRIMARY KEY (supplier_id, module_id);


--
-- Name: supplier_refresh_tokens supplier_refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_refresh_tokens
    ADD CONSTRAINT supplier_refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: supplier_refresh_tokens supplier_refresh_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_refresh_tokens
    ADD CONSTRAINT supplier_refresh_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: suppliers suppliers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_pkey PRIMARY KEY (id);


--
-- Name: tooltip_usages tooltip_usages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tooltip_usages
    ADD CONSTRAINT tooltip_usages_pkey PRIMARY KEY (id);


--
-- Name: supplier_ai_credit_ledger_entries uq_ai_credit_ledger_customer_period; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_ledger_entries
    ADD CONSTRAINT uq_ai_credit_ledger_customer_period UNIQUE (customer_id, period_start);


--
-- Name: supplier_ai_credit_ledger_entries uq_ai_credit_ledger_supplier_period; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_ledger_entries
    ADD CONSTRAINT uq_ai_credit_ledger_supplier_period UNIQUE (supplier_id, period_start);


--
-- Name: qr_catalogue_entries uq_qr_catalogue_entry_customer_filter; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qr_catalogue_entries
    ADD CONSTRAINT uq_qr_catalogue_entry_customer_filter UNIQUE (customer_id, filter_value);


--
-- Name: supplier_customer_themes uq_supplier_customer_themes_pair; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_customer_themes
    ADD CONSTRAINT uq_supplier_customer_themes_pair UNIQUE (supplier_id, customer_id);


--
-- Name: tooltip_usages uq_tooltip_usages_room_hotspot_customer; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tooltip_usages
    ADD CONSTRAINT uq_tooltip_usages_room_hotspot_customer UNIQUE (room_id, hotspot_id, customer_id);


--
-- Name: usage_logs uq_usage_logs_room_customer; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_logs
    ADD CONSTRAINT uq_usage_logs_room_customer UNIQUE (room_id, customer_id);


--
-- Name: usage_logs usage_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_logs
    ADD CONSTRAINT usage_logs_pkey PRIMARY KEY (id);


--
-- Name: ix_activity_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_activity_logs_action ON public.activity_logs USING btree (action);


--
-- Name: ix_activity_logs_admin_user_id_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_activity_logs_admin_user_id_created_at ON public.activity_logs USING btree (admin_user_id, created_at);


--
-- Name: ix_admin_user_login_events_admin_user_id_logged_in_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_admin_user_login_events_admin_user_id_logged_in_at ON public.admin_user_login_events USING btree (admin_user_id, logged_in_at);


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
-- Name: ix_ai_credit_settings_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_ai_credit_settings_customer_id ON public.supplier_ai_credit_settings USING btree (customer_id) WHERE (customer_id IS NOT NULL);


--
-- Name: ix_ai_credit_settings_supplier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_ai_credit_settings_supplier_id ON public.supplier_ai_credit_settings USING btree (supplier_id) WHERE (supplier_id IS NOT NULL);


--
-- Name: ix_ai_credit_transactions_billed_customer_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_credit_transactions_billed_customer_created ON public.ai_credit_transactions USING btree (billed_customer_id, created_at);


--
-- Name: ix_ai_credit_transactions_supplier_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_credit_transactions_supplier_created ON public.ai_credit_transactions USING btree (supplier_id, created_at);


--
-- Name: ix_cart_items_cart_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cart_items_cart_id ON public.cart_items USING btree (cart_id);


--
-- Name: ix_child_categories_parent_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_categories_parent_category_id ON public.child_categories USING btree (parent_category_id);


--
-- Name: ix_cities_state_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cities_state_code ON public.cities USING btree (state_code);


--
-- Name: ix_customer_login_events_customer_id_logged_in_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_login_events_customer_id_logged_in_at ON public.customer_login_events USING btree (customer_id, logged_in_at);


--
-- Name: ix_customer_refresh_tokens_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_refresh_tokens_customer_id ON public.customer_refresh_tokens USING btree (customer_id);


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
-- Name: ix_customers_linked_supplier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_customers_linked_supplier_id ON public.customers USING btree (linked_supplier_id) WHERE (deleted_at IS NULL);


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
-- Name: ix_order_items_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_items_order_id ON public.order_items USING btree (order_id);


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
-- Name: ix_qr_catalogue_entry_hotspots_entry_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_qr_catalogue_entry_hotspots_entry_id ON public.qr_catalogue_entry_hotspots USING btree (qr_catalogue_entry_id);


--
-- Name: ix_refresh_tokens_admin_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_refresh_tokens_admin_user_id ON public.refresh_tokens USING btree (admin_user_id);


--
-- Name: ix_room_category_image_hotspots_image_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_room_category_image_hotspots_image_id ON public.room_category_image_hotspots USING btree (room_category_image_id);


--
-- Name: ix_supplier_ai_credit_batches_customer_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_supplier_ai_credit_batches_customer_date ON public.supplier_ai_credit_batches USING btree (customer_id, batch_date);


--
-- Name: ix_supplier_ai_credit_batches_supplier_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_supplier_ai_credit_batches_supplier_date ON public.supplier_ai_credit_batches USING btree (supplier_id, batch_date);


--
-- Name: ix_supplier_customer_themes_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_supplier_customer_themes_customer_id ON public.supplier_customer_themes USING btree (customer_id);


--
-- Name: ix_supplier_login_events_supplier_id_logged_in_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_supplier_login_events_supplier_id_logged_in_at ON public.supplier_login_events USING btree (supplier_id, logged_in_at);


--
-- Name: ix_supplier_refresh_tokens_supplier_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_supplier_refresh_tokens_supplier_id ON public.supplier_refresh_tokens USING btree (supplier_id);


--
-- Name: ix_suppliers_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_suppliers_is_active ON public.suppliers USING btree (is_active);


--
-- Name: ix_suppliers_linked_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_suppliers_linked_customer_id ON public.suppliers USING btree (linked_customer_id) WHERE (deleted_at IS NULL);


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
-- Name: ix_tooltip_usages_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tooltip_usages_customer_id ON public.tooltip_usages USING btree (customer_id);


--
-- Name: ux_carts_customer_open; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_carts_customer_open ON public.carts USING btree (customer_id) WHERE ((status)::text = 'open'::text);


--
-- Name: activity_logs activity_logs_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.admin_users(id);


--
-- Name: admin_user_login_events admin_user_login_events_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_user_login_events
    ADD CONSTRAINT admin_user_login_events_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.admin_users(id) ON DELETE CASCADE;


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
-- Name: ai_credit_transactions ai_credit_transactions_billed_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_credit_transactions
    ADD CONSTRAINT ai_credit_transactions_billed_customer_id_fkey FOREIGN KEY (billed_customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: ai_credit_transactions ai_credit_transactions_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_credit_transactions
    ADD CONSTRAINT ai_credit_transactions_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: ai_credit_transactions ai_credit_transactions_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_credit_transactions
    ADD CONSTRAINT ai_credit_transactions_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- Name: ai_credit_transactions ai_credit_transactions_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_credit_transactions
    ADD CONSTRAINT ai_credit_transactions_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


--
-- Name: cart_items cart_items_cart_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT cart_items_cart_id_fkey FOREIGN KEY (cart_id) REFERENCES public.carts(id) ON DELETE CASCADE;


--
-- Name: cart_items cart_items_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT cart_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: carts carts_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.carts
    ADD CONSTRAINT carts_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: child_categories child_categories_parent_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_categories
    ADD CONSTRAINT child_categories_parent_category_id_fkey FOREIGN KEY (parent_category_id) REFERENCES public.parent_categories(id);


--
-- Name: cities cities_state_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities
    ADD CONSTRAINT cities_state_code_fkey FOREIGN KEY (state_code) REFERENCES public.states(code);


--
-- Name: customer_login_events customer_login_events_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_login_events
    ADD CONSTRAINT customer_login_events_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: customer_refresh_tokens customer_refresh_tokens_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_refresh_tokens
    ADD CONSTRAINT customer_refresh_tokens_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


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
-- Name: customers customers_linked_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_linked_supplier_id_fkey FOREIGN KEY (linked_supplier_id) REFERENCES public.suppliers(id);


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
-- Name: order_items order_items_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: order_items order_items_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE SET NULL;


--
-- Name: orders orders_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


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
-- Name: qr_catalogue_entries qr_catalogue_entries_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qr_catalogue_entries
    ADD CONSTRAINT qr_catalogue_entries_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: qr_catalogue_entries qr_catalogue_entries_room_category_image_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qr_catalogue_entries
    ADD CONSTRAINT qr_catalogue_entries_room_category_image_id_fkey FOREIGN KEY (room_category_image_id) REFERENCES public.room_category_images(id) ON DELETE CASCADE;


--
-- Name: qr_catalogue_entry_hotspots qr_catalogue_entry_hotspots_hotspot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qr_catalogue_entry_hotspots
    ADD CONSTRAINT qr_catalogue_entry_hotspots_hotspot_id_fkey FOREIGN KEY (hotspot_id) REFERENCES public.room_category_image_hotspots(id) ON DELETE CASCADE;


--
-- Name: qr_catalogue_entry_hotspots qr_catalogue_entry_hotspots_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qr_catalogue_entry_hotspots
    ADD CONSTRAINT qr_catalogue_entry_hotspots_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: qr_catalogue_entry_hotspots qr_catalogue_entry_hotspots_qr_catalogue_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qr_catalogue_entry_hotspots
    ADD CONSTRAINT qr_catalogue_entry_hotspots_qr_catalogue_entry_id_fkey FOREIGN KEY (qr_catalogue_entry_id) REFERENCES public.qr_catalogue_entries(id) ON DELETE CASCADE;


--
-- Name: refresh_tokens refresh_tokens_admin_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.admin_users(id) ON DELETE CASCADE;


--
-- Name: room_category_image_hotspots room_category_image_hotspots_room_category_image_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_category_image_hotspots
    ADD CONSTRAINT room_category_image_hotspots_room_category_image_id_fkey FOREIGN KEY (room_category_image_id) REFERENCES public.room_category_images(id) ON DELETE CASCADE;


--
-- Name: room_category_image_suppliers room_category_image_suppliers_mapped_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_category_image_suppliers
    ADD CONSTRAINT room_category_image_suppliers_mapped_by_fkey FOREIGN KEY (mapped_by) REFERENCES public.admin_users(id);


--
-- Name: room_category_image_suppliers room_category_image_suppliers_room_category_image_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_category_image_suppliers
    ADD CONSTRAINT room_category_image_suppliers_room_category_image_id_fkey FOREIGN KEY (room_category_image_id) REFERENCES public.room_category_images(id) ON DELETE CASCADE;


--
-- Name: room_category_image_suppliers room_category_image_suppliers_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_category_image_suppliers
    ADD CONSTRAINT room_category_image_suppliers_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


--
-- Name: room_category_images room_category_images_room_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.room_category_images
    ADD CONSTRAINT room_category_images_room_category_id_fkey FOREIGN KEY (room_category_id) REFERENCES public.room_categories(id) ON DELETE CASCADE;


--
-- Name: saved_qr_codes saved_qr_codes_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_qr_codes
    ADD CONSTRAINT saved_qr_codes_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.admin_users(id);


--
-- Name: saved_qr_codes saved_qr_codes_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_qr_codes
    ADD CONSTRAINT saved_qr_codes_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: supplier_ai_credit_batches supplier_ai_credit_batches_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_batches
    ADD CONSTRAINT supplier_ai_credit_batches_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.admin_users(id);


--
-- Name: supplier_ai_credit_batches supplier_ai_credit_batches_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_batches
    ADD CONSTRAINT supplier_ai_credit_batches_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: supplier_ai_credit_batches supplier_ai_credit_batches_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_batches
    ADD CONSTRAINT supplier_ai_credit_batches_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


--
-- Name: supplier_ai_credit_ledger_entries supplier_ai_credit_ledger_entries_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_ledger_entries
    ADD CONSTRAINT supplier_ai_credit_ledger_entries_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: supplier_ai_credit_ledger_entries supplier_ai_credit_ledger_entries_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_ledger_entries
    ADD CONSTRAINT supplier_ai_credit_ledger_entries_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


--
-- Name: supplier_ai_credit_settings supplier_ai_credit_settings_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_settings
    ADD CONSTRAINT supplier_ai_credit_settings_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: supplier_ai_credit_settings supplier_ai_credit_settings_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_ai_credit_settings
    ADD CONSTRAINT supplier_ai_credit_settings_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


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
-- Name: supplier_customer_themes supplier_customer_themes_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_customer_themes
    ADD CONSTRAINT supplier_customer_themes_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: supplier_customer_themes supplier_customer_themes_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_customer_themes
    ADD CONSTRAINT supplier_customer_themes_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


--
-- Name: supplier_login_events supplier_login_events_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_login_events
    ADD CONSTRAINT supplier_login_events_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


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
-- Name: supplier_refresh_tokens supplier_refresh_tokens_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supplier_refresh_tokens
    ADD CONSTRAINT supplier_refresh_tokens_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE CASCADE;


--
-- Name: suppliers suppliers_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.admin_users(id);


--
-- Name: suppliers suppliers_linked_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_linked_customer_id_fkey FOREIGN KEY (linked_customer_id) REFERENCES public.customers(id);


--
-- Name: suppliers suppliers_state_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_state_code_fkey FOREIGN KEY (state_code) REFERENCES public.states(code);


--
-- Name: tooltip_usages tooltip_usages_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tooltip_usages
    ADD CONSTRAINT tooltip_usages_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: usage_logs usage_logs_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_logs
    ADD CONSTRAINT usage_logs_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict GDCxfvkzXyCHiAvaXhEtdg95xw7hA9mBOqnfFwVV3bHtPzcP0IaWSyOSsxqXwzf

--
-- PostgreSQL database dump
--

\restrict TC9EgvfepVCKFSMKnTWnLxDdBbasUXfXin6muWDpXElNZfrqATPT48n4biCTmgx

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

SET SESSION AUTHORIZATION DEFAULT;

ALTER TABLE public.modules DISABLE TRIGGER ALL;

INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('dashboard', 'Dashboard', NULL, 0, true, true, 'a8ec61d1-ab84-4599-8e47-bbdeda1e6fef', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('master.room_category', 'Room Category', '63c2805d-5527-4291-bfb6-44da8e6e92d3', 7, false, true, '725da421-96f4-47f5-8431-3a31060cacf4', '2026-07-13 10:47:15.84916+05:30', '2026-07-13 10:47:15.84916+05:30');
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
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('theme_configuration', 'Theme Configuration', NULL, 1001, false, true, '76bb1dcf-46bb-46b8-9667-1c6af10200d7', '2026-07-24 14:42:40.459966+05:30', '2026-07-24 16:58:30.887525+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('orders', 'Orders', NULL, 9, true, true, '14c83c85-6a05-4d0a-a23e-e3e08f7e3dcd', '2026-07-13 10:47:15.84916+05:30', '2026-07-28 14:46:34.267796+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('logs.supplier_login_history', 'Supplier Login History', 'e7d7a486-1a01-4828-be59-6143b58ea3ab', 1000, true, true, '1f3b6a9e-7c2d-4a5e-9b1a-6d2c4e8f0a11', '2026-07-20 16:31:09.209896+05:30', '2026-07-20 16:31:09.209896+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('logs.sub_admin_login_history', 'Sub Admin Login History', 'e7d7a486-1a01-4828-be59-6143b58ea3ab', 1001, true, true, '7ea8a238-d4b4-455a-9903-9722ae593aae', '2026-07-30 16:16:34.087402+05:30', '2026-07-30 16:16:34.087402+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('qr_code', 'QR Code', NULL, 1003, false, true, '6e1f68de-3474-40d7-abe8-0cbe19f9e013', '2026-07-30 18:12:36.965129+05:30', '2026-07-30 18:12:36.965129+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('qr_generator', 'QR Code Generator', '6e1f68de-3474-40d7-abe8-0cbe19f9e013', 0, true, true, '3d6c2bce-d10b-4fbe-97f7-e0a2b8636e05', '2026-07-28 16:49:53.085261+05:30', '2026-07-28 16:49:53.085261+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('qr_generator.saved_list', 'Generated QR Codes', '6e1f68de-3474-40d7-abe8-0cbe19f9e013', 1, true, true, '382c0edf-32b1-4917-92b3-5c9c96380c51', '2026-07-30 18:12:36.965129+05:30', '2026-07-30 18:12:36.965129+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('ai_credits', 'AI Credits', NULL, 1004, true, true, '48bb84de-ffba-4e6e-8a57-df8457f6a45e', '2026-08-05 11:49:15.891284+05:30', '2026-08-05 11:49:15.891284+05:30');
INSERT INTO public.modules (key, name, parent_id, sort_order, is_buildable, is_active, id, created_at, updated_at) VALUES ('visualizer_admin', 'Cache Management', NULL, 1002, true, true, 'a76d63a9-5674-4bf0-9822-e1631b945060', '2026-07-27 11:14:23.087322+05:30', '2026-08-06 15:10:54.90317+05:30');


ALTER TABLE public.modules ENABLE TRIGGER ALL;

--
-- Data for Name: states; Type: TABLE DATA; Schema: public; Owner: -
--

ALTER TABLE public.states DISABLE TRIGGER ALL;

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


ALTER TABLE public.states ENABLE TRIGGER ALL;

--
-- PostgreSQL database dump complete
--

\unrestrict TC9EgvfepVCKFSMKnTWnLxDdBbasUXfXin6muWDpXElNZfrqATPT48n4biCTmgx

