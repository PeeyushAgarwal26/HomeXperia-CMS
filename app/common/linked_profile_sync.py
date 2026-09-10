"""Field mirroring between a Customer and Supplier row linked via
Customer.linked_supplier_id / Supplier.linked_customer_id. The two rows are
fully independent accounts (own login, own password) but represent the same
real-world business — see the "Mirrors Supplier.logo_url" comment on
Customer.logo_url — so these fields stay in sync whenever either side is
updated, self-service or admin, in either direction."""

SHARED_LINKED_PROFILE_FIELDS = (
    "name",
    "email",
    "phone_number",
    "gst_number",
    "address",
    "pin_code",
    "state_code",
    "city",
    "logo_url",
    "profile_image_url",
)


def shared_profile_fields(data: dict) -> dict:
    """Narrows an update payload down to just the fields that exist on both
    Customer and Supplier and are meant to mirror between them — excludes
    account-specific fields like customer_code/username/password_hash/
    is_active/device_limit/web_link that must never cross over."""
    return {key: data[key] for key in SHARED_LINKED_PROFILE_FIELDS if key in data}
