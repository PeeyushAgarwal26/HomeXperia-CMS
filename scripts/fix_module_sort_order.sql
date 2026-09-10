-- Reconciles modules.sort_order/parent_id/name/is_buildable to match
-- MODULE_TREE in scripts/seed_reference_data.py (backend fix, 2026-08-10).
--
-- Background: the admin sidebar order must be fixed and independent of
-- which modules any given admin/sub-admin/supplier happens to be assigned —
-- assigning or revoking access must never reshuffle the remaining items.
-- seed_module_catalog() already guarantees this going forward (sort_order
-- is fully code-owned, reconciled from MODULE_TREE on every run); this
-- script applies the same canonical order directly to an environment this
-- session cannot run the seed script against (dev/staging/prod).
--
-- Canonical top-level order: Dashboard, Master, Orders, Upload Product,
-- User Management, Logs, QR Code, Notification, Theme Configuration,
-- AI Credits, Cache Management.
--
-- Idempotent and safe to re-run. Never touches is_active (the only column
-- anything else in the app ever mutates — see module_catalog/repository.py).
--
-- Usage: psql "$DATABASE_URL" -f scripts/fix_module_sort_order.sql
--    or: paste into any SQL client connected to the target database.
BEGIN;

-- 1) Insert any missing module keys (parent_id filled in in step 2).
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'dashboard', 'Dashboard', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'master', 'Master', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'master.parent_category', 'Parent Category', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'master.child_category', 'Child Category', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'master.filter', 'Filter', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'master.filter_value', 'Filter Value', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'master.product', 'Product', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'master.room_category', 'Room Category', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'orders', 'Orders', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'upload_product', 'Upload Product', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'upload_product.upload_files', 'Upload Files', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'upload_product.log', 'Log', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'user_management', 'User Management', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'user_management.customer', 'Customer', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'user_management.sub_admin', 'Sub Admin', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'user_management.suppliers', 'Suppliers', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'logs', 'Logs', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'logs.customer_login_history', 'Customer Login History', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'logs.supplier_login_history', 'Supplier Login History', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'logs.sub_admin_login_history', 'Sub Admin Login History', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'qr_code', 'QR Code', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'qr_generator', 'QR Code Generator', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'qr_generator.saved_list', 'Generated QR Codes', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'notification', 'Notification', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'notification.template', 'Template', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'theme_configuration', 'Theme Configuration', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'ai_credits', 'AI Credits', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'visualizer_admin', 'Cache Management', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'app_feedback', 'App Feedback', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'setting', 'Setting', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'setting.change_password', 'Change Password', 0, TRUE, TRUE) ON CONFLICT (key) DO NOTHING;
INSERT INTO modules (id, key, name, sort_order, is_buildable, is_active) VALUES (gen_random_uuid(), 'setting.log_off', 'Log Off', 0, FALSE, TRUE) ON CONFLICT (key) DO NOTHING;

-- 2) Reconcile sort_order/parent_id/name/is_buildable for every module.
UPDATE modules SET sort_order = 0, parent_id = NULL, name = 'Dashboard', is_buildable = TRUE WHERE key = 'dashboard';
UPDATE modules SET sort_order = 1, parent_id = NULL, name = 'Master', is_buildable = FALSE WHERE key = 'master';
UPDATE modules SET sort_order = 2, parent_id = (SELECT id FROM modules WHERE key = 'master'), name = 'Parent Category', is_buildable = FALSE WHERE key = 'master.parent_category';
UPDATE modules SET sort_order = 3, parent_id = (SELECT id FROM modules WHERE key = 'master'), name = 'Child Category', is_buildable = FALSE WHERE key = 'master.child_category';
UPDATE modules SET sort_order = 4, parent_id = (SELECT id FROM modules WHERE key = 'master'), name = 'Filter', is_buildable = FALSE WHERE key = 'master.filter';
UPDATE modules SET sort_order = 5, parent_id = (SELECT id FROM modules WHERE key = 'master'), name = 'Filter Value', is_buildable = FALSE WHERE key = 'master.filter_value';
UPDATE modules SET sort_order = 6, parent_id = (SELECT id FROM modules WHERE key = 'master'), name = 'Product', is_buildable = FALSE WHERE key = 'master.product';
UPDATE modules SET sort_order = 7, parent_id = (SELECT id FROM modules WHERE key = 'master'), name = 'Room Category', is_buildable = FALSE WHERE key = 'master.room_category';
UPDATE modules SET sort_order = 8, parent_id = NULL, name = 'Orders', is_buildable = TRUE WHERE key = 'orders';
UPDATE modules SET sort_order = 9, parent_id = NULL, name = 'Upload Product', is_buildable = FALSE WHERE key = 'upload_product';
UPDATE modules SET sort_order = 10, parent_id = (SELECT id FROM modules WHERE key = 'upload_product'), name = 'Upload Files', is_buildable = FALSE WHERE key = 'upload_product.upload_files';
UPDATE modules SET sort_order = 11, parent_id = (SELECT id FROM modules WHERE key = 'upload_product'), name = 'Log', is_buildable = FALSE WHERE key = 'upload_product.log';
UPDATE modules SET sort_order = 12, parent_id = NULL, name = 'User Management', is_buildable = TRUE WHERE key = 'user_management';
UPDATE modules SET sort_order = 13, parent_id = (SELECT id FROM modules WHERE key = 'user_management'), name = 'Customer', is_buildable = TRUE WHERE key = 'user_management.customer';
UPDATE modules SET sort_order = 14, parent_id = (SELECT id FROM modules WHERE key = 'user_management'), name = 'Sub Admin', is_buildable = TRUE WHERE key = 'user_management.sub_admin';
UPDATE modules SET sort_order = 15, parent_id = (SELECT id FROM modules WHERE key = 'user_management'), name = 'Suppliers', is_buildable = TRUE WHERE key = 'user_management.suppliers';
UPDATE modules SET sort_order = 16, parent_id = NULL, name = 'Logs', is_buildable = FALSE WHERE key = 'logs';
UPDATE modules SET sort_order = 17, parent_id = (SELECT id FROM modules WHERE key = 'logs'), name = 'Customer Login History', is_buildable = FALSE WHERE key = 'logs.customer_login_history';
UPDATE modules SET sort_order = 18, parent_id = (SELECT id FROM modules WHERE key = 'logs'), name = 'Supplier Login History', is_buildable = TRUE WHERE key = 'logs.supplier_login_history';
UPDATE modules SET sort_order = 19, parent_id = (SELECT id FROM modules WHERE key = 'logs'), name = 'Sub Admin Login History', is_buildable = TRUE WHERE key = 'logs.sub_admin_login_history';
UPDATE modules SET sort_order = 20, parent_id = NULL, name = 'QR Code', is_buildable = FALSE WHERE key = 'qr_code';
UPDATE modules SET sort_order = 21, parent_id = (SELECT id FROM modules WHERE key = 'qr_code'), name = 'QR Code Generator', is_buildable = TRUE WHERE key = 'qr_generator';
UPDATE modules SET sort_order = 22, parent_id = (SELECT id FROM modules WHERE key = 'qr_code'), name = 'Generated QR Codes', is_buildable = TRUE WHERE key = 'qr_generator.saved_list';
UPDATE modules SET sort_order = 23, parent_id = NULL, name = 'Notification', is_buildable = FALSE WHERE key = 'notification';
UPDATE modules SET sort_order = 24, parent_id = (SELECT id FROM modules WHERE key = 'notification'), name = 'Template', is_buildable = FALSE WHERE key = 'notification.template';
UPDATE modules SET sort_order = 25, parent_id = NULL, name = 'Theme Configuration', is_buildable = FALSE WHERE key = 'theme_configuration';
UPDATE modules SET sort_order = 26, parent_id = NULL, name = 'AI Credits', is_buildable = TRUE WHERE key = 'ai_credits';
UPDATE modules SET sort_order = 27, parent_id = NULL, name = 'Cache Management', is_buildable = TRUE WHERE key = 'visualizer_admin';
UPDATE modules SET sort_order = 28, parent_id = NULL, name = 'App Feedback', is_buildable = FALSE WHERE key = 'app_feedback';
UPDATE modules SET sort_order = 29, parent_id = NULL, name = 'Setting', is_buildable = FALSE WHERE key = 'setting';
UPDATE modules SET sort_order = 30, parent_id = (SELECT id FROM modules WHERE key = 'setting'), name = 'Change Password', is_buildable = TRUE WHERE key = 'setting.change_password';
UPDATE modules SET sort_order = 31, parent_id = (SELECT id FROM modules WHERE key = 'setting'), name = 'Log Off', is_buildable = FALSE WHERE key = 'setting.log_off';

COMMIT;
