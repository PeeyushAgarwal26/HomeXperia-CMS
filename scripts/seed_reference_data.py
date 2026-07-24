"""Seeds states + the module/permission catalog. Idempotent — safe to re-run.

Usage: python -m scripts.seed_reference_data
"""

import asyncio

from sqlalchemy import select

import app.db.models  # noqa: F401 — registers every table so cross-model FKs resolve
from app.db.session import AsyncSessionFactory
from app.modules.geo.models import City, State
from app.modules.module_catalog.models import Module

# code -> (name, sort_order). 28 states + 8 union territories of India.
STATES: list[tuple[str, str]] = [
    ("AP", "Andhra Pradesh"), ("AR", "Arunachal Pradesh"), ("AS", "Assam"),
    ("BR", "Bihar"), ("CG", "Chhattisgarh"), ("GA", "Goa"), ("GJ", "Gujarat"),
    ("HR", "Haryana"), ("HP", "Himachal Pradesh"), ("JH", "Jharkhand"),
    ("KA", "Karnataka"), ("KL", "Kerala"), ("MP", "Madhya Pradesh"),
    ("MH", "Maharashtra"), ("MN", "Manipur"), ("ML", "Meghalaya"),
    ("MZ", "Mizoram"), ("NL", "Nagaland"), ("OD", "Odisha"), ("PB", "Punjab"),
    ("RJ", "Rajasthan"), ("SK", "Sikkim"), ("TN", "Tamil Nadu"),
    ("TG", "Telangana"), ("TR", "Tripura"), ("UP", "Uttar Pradesh"),
    ("UK", "Uttarakhand"), ("WB", "West Bengal"),
    ("AN", "Andaman and Nicobar Islands"), ("CH", "Chandigarh"),
    ("DN", "Dadra and Nagar Haveli and Daman and Diu"), ("DL", "Delhi"),
    ("JK", "Jammu and Kashmir"), ("LA", "Ladakh"), ("LD", "Lakshadweep"),
    ("PY", "Puducherry"),
]

# state_code -> city names. A suggestion list, not an exhaustive one — the City field
# stays free text (see geo/models.py::City), so gaps here just mean typing instead of
# picking. Order within each state is the dropdown's display order.
CITIES: dict[str, list[str]] = {
    "AP": ["Visakhapatnam", "Vijayawada", "Guntur", "Nellore", "Kurnool", "Kakinada",
           "Rajahmundry", "Tirupati", "Kadapa", "Anantapur", "Eluru", "Ongole",
           "Chittoor", "Srikakulam", "Vizianagaram"],
    "AR": ["Itanagar", "Naharlagun", "Pasighat", "Tawang", "Ziro", "Bomdila"],
    "AS": ["Guwahati", "Dibrugarh", "Silchar", "Jorhat", "Nagaon", "Tinsukia",
           "Tezpur", "Karimganj", "Sivasagar", "Bongaigaon"],
    "BR": ["Patna", "Gaya", "Bhagalpur", "Muzaffarpur", "Purnia", "Darbhanga",
           "Bihar Sharif", "Arrah", "Begusarai", "Katihar", "Munger", "Chhapra"],
    "CG": ["Raipur", "Bhilai", "Bilaspur", "Korba", "Durg", "Rajnandgaon",
           "Jagdalpur", "Ambikapur"],
    "GA": ["Panaji", "Margao", "Vasco da Gama", "Mapusa", "Ponda"],
    "GJ": ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Bhavnagar", "Jamnagar",
           "Gandhinagar", "Junagadh", "Anand", "Morbi", "Nadiad", "Mehsana",
           "Bharuch", "Navsari", "Valsad"],
    "HR": ["Gurugram", "Faridabad", "Panipat", "Ambala", "Karnal", "Hisar",
           "Rohtak", "Yamunanagar", "Panchkula", "Sonipat", "Bhiwani", "Sirsa"],
    "HP": ["Shimla", "Manali", "Dharamshala", "Solan", "Mandi", "Kullu", "Una",
           "Bilaspur"],
    "JH": ["Ranchi", "Jamshedpur", "Dhanbad", "Bokaro", "Deoghar", "Hazaribagh",
           "Giridih"],
    "KA": ["Bengaluru", "Mysuru", "Hubballi", "Mangaluru", "Belagavi", "Davangere",
           "Bellary", "Tumkur", "Shivamogga", "Udupi", "Gulbarga", "Bidar", "Hospet"],
    "KL": ["Thiruvananthapuram", "Kochi", "Kozhikode", "Kannur", "Thrissur",
           "Kollam", "Alappuzha", "Palakkad", "Malappuram", "Kottayam"],
    "MP": ["Bhopal", "Indore", "Jabalpur", "Gwalior", "Ujjain", "Sagar", "Ratlam",
           "Satna", "Rewa", "Dewas", "Burhanpur"],
    "MH": ["Mumbai", "Pune", "Nagpur", "Nashik", "Chhatrapati Sambhajinagar",
           "Solapur", "Kolhapur", "Amravati", "Sangli", "Malegaon", "Akola",
           "Bhiwandi", "Ichalkaranji", "Panvel", "Thane", "Navi Mumbai"],
    "MN": ["Imphal", "Thoubal", "Bishnupur"],
    "ML": ["Shillong", "Tura", "Jowai"],
    "MZ": ["Aizawl", "Lunglei", "Champhai"],
    "NL": ["Kohima", "Dimapur", "Mokokchung"],
    "OD": ["Bhubaneswar", "Cuttack", "Rourkela", "Berhampur", "Sambalpur", "Puri",
           "Balasore"],
    "PB": ["Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Bathinda", "Mohali",
           "Hoshiarpur", "Pathankot", "Moga"],
    "RJ": ["Jaipur", "Jodhpur", "Udaipur", "Kota", "Bikaner", "Ajmer", "Bhilwara",
           "Alwar", "Bhiwadi", "Sikar", "Pali", "Sri Ganganagar", "Tonk",
           "Chittorgarh", "Barmer"],
    "SK": ["Gangtok", "Namchi", "Gyalshing"],
    "TN": ["Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem",
           "Tirunelveli", "Tiruppur", "Erode", "Vellore", "Thoothukudi", "Karur",
           "Namakkal", "Dindigul"],
    "TG": ["Hyderabad", "Warangal", "Nizamabad", "Karimnagar", "Khammam",
           "Secunderabad"],
    "TR": ["Agartala", "Udaipur", "Dharmanagar"],
    "UP": ["Lucknow", "Kanpur", "Ghaziabad", "Agra", "Varanasi", "Meerut",
           "Prayagraj", "Bareilly", "Aligarh", "Moradabad", "Saharanpur",
           "Gorakhpur", "Noida", "Firozabad", "Jhansi", "Muzaffarnagar", "Mathura",
           "Bhadohi", "Mirzapur", "Rampur", "Shahjahanpur"],
    "UK": ["Dehradun", "Haridwar", "Roorkee", "Haldwani", "Rudrapur", "Nainital",
           "Rishikesh"],
    "WB": ["Kolkata", "Howrah", "Durgapur", "Asansol", "Siliguri", "Malda",
           "Bardhaman", "Kharagpur", "Haldia"],
    "AN": ["Port Blair"],
    "CH": ["Chandigarh"],
    "DN": ["Silvassa", "Daman"],
    "DL": ["New Delhi", "Delhi"],
    "JK": ["Srinagar", "Jammu", "Anantnag", "Baramulla", "Sopore"],
    "LA": ["Leh", "Kargil"],
    "LD": ["Kavaratti"],
    "PY": ["Puducherry", "Karaikal", "Yanam", "Mahe"],
}

# (key, name, parent_key, is_buildable) — order matters, parents before children.
# Confirmed against the real live site's admin-menu HTML — see
# docs/06-legacy-site-audit.md §1. This corrected a wrong, screenshot-guessed
# tree that had Master missing 3 of its 6 children, Activity wrongly
# carrying Filter/Product as children, and Template nested under App
# Feedback instead of Notification (App Feedback is actually a plain leaf).
MODULE_TREE: list[tuple[str, str, str | None, bool]] = [
    ("dashboard", "Dashboard", None, True),
    ("master", "Master", None, False),
    ("master.parent_category", "Parent Category", "master", False),
    ("master.child_category", "Child Category", "master", False),
    ("master.filter", "Filter", "master", False),
    ("master.filter_value", "Filter Value", "master", False),
    ("master.product", "Product", "master", False),
    ("master.room_category", "Room Category", "master", False),
    ("activity", "Activity", None, False),
    ("activity.orders", "Orders", "activity", False),
    ("upload_product", "Upload Product", None, False),
    ("upload_product.upload_files", "Upload Files", "upload_product", False),
    ("upload_product.log", "Log", "upload_product", False),
    ("user_management", "User Management", None, True),
    ("user_management.customer", "Customer", "user_management", True),
    ("user_management.sub_admin", "Sub Admin", "user_management", True),
    ("user_management.suppliers", "Suppliers", "user_management", True),
    ("logs", "Logs", None, False),
    ("logs.customer_login_history", "Customer Login History", "logs", False),
    ("logs.login_history", "Login History", "logs", True),
    ("notification", "Notification", None, False),
    ("notification.template", "Template", "notification", False),
    ("theme_configuration", "Theme Configuration", None, False),
    ("app_feedback", "App Feedback", None, False),
    ("setting", "Setting", None, False),
    ("setting.change_password", "Change Password", "setting", True),
    ("setting.log_off", "Log Off", "setting", False),
]



async def seed_states(session) -> None:
    existing = await session.scalar(select(State.code).limit(1))
    if existing:
        print("States already seeded — skipping.")
        return
    for sort_order, (code, name) in enumerate(STATES):
        session.add(State(code=code, name=name, sort_order=sort_order))
    print(f"Seeded {len(STATES)} states.")


async def seed_cities(session) -> None:
    existing = await session.scalar(select(City.id).limit(1))
    if existing:
        print("Cities already seeded — skipping.")
        return
    total = 0
    for state_code, names in CITIES.items():
        for sort_order, name in enumerate(names):
            session.add(City(state_code=state_code, name=name, sort_order=sort_order))
            total += 1
    print(f"Seeded {total} cities.")


async def seed_module_catalog(session) -> None:
    existing = await session.scalar(select(Module.key).limit(1))
    if existing:
        print("Module catalog already seeded — skipping.")
        return

    key_to_id: dict[str, object] = {}
    for sort_order, (key, name, parent_key, is_buildable) in enumerate(MODULE_TREE):
        module = Module(
            key=key,
            name=name,
            parent_id=key_to_id.get(parent_key) if parent_key else None,
            sort_order=sort_order,
            is_buildable=is_buildable,
        )
        session.add(module)
        await session.flush()  # need module.id before it can be a parent
        key_to_id[key] = module.id
    print(f"Seeded {len(MODULE_TREE)} module catalog entries.")


async def main() -> None:
    async with AsyncSessionFactory() as session:
        await seed_states(session)
        await seed_cities(session)
        await seed_module_catalog(session)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
