"""RouteGuard settings shared by all files."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "routeguard.db")
UA = {"User-Agent": "RouteGuard-student-app/3.0"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
CAR = "https://router.project-osrm.org/route/v1/driving/"
FOOT = "https://routing.openstreetmap.de/routed-foot/route/v1/driving/"
BIKE = "https://routing.openstreetmap.de/routed-bike/route/v1/driving/"
ROAD = "Auto / Cab / Bike taxi"
NAN = float("nan")
MAX_WALK_MIN = 15  # longest walk to a stop that we accept

GTFS_URL = "https://raw.githubusercontent.com/ungalsoththu/ChennaiGTFS/main/data/chennai-unified-gtfs.zip"
GTFS_FILE = os.path.join(BASE_DIR, "chennai-gtfs.zip")  # downloaded once, then reused
RTYPE = {"0": "Tram", "1": "Metro", "2": "Train", "3": "Bus"}

WEIGHTS = {"Balanced": dict(cost=.30, time=.40, buf=.30),
           "Cheapest": dict(cost=.60, time=.20, buf=.20),
           "Fastest": dict(cost=.10, time=.60, buf=.30),
           "Most spare time": dict(cost=.20, time=.20, buf=.60)}
