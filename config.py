"""RouteGuard settings shared by all files."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "routeguard.db")
UA = {"User-Agent": "RouteGuard-student-app/4.0"}
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

# The three honesty labels used on every number in the app
V, E, U = "Verified", "Estimated", "Unavailable"
LEGEND = {V: "straight from a data source (timetable, map) or typed by you",
          E: "calculated by the app or a routing engine, so it can be wrong",
          U: "no data exists, so the app does not guess"}

# How much each factor matters for each priority (each row adds up to 1)
WEIGHTS = {"Balanced": dict(cost=.25, time=.25, buf=.25, rel=.25),
           "Cheapest": dict(cost=.55, time=.15, buf=.15, rel=.15),
           "Fastest": dict(cost=.10, time=.55, buf=.20, rel=.15),
           "Most spare time": dict(cost=.15, time=.15, buf=.55, rel=.15),
           "Most reliable": dict(cost=.10, time=.15, buf=.20, rel=.55)}

# ASSUMPTIONS (not measured). Free live delay data does not exist, so these are
# rough starting points. Change them if you have better numbers.
# REL_BASE = how dependable the mode is, out of 100.
# DELAY    = extra share of the moving time that delays could add.
REL_BASE = {"Walk": 95, "Cycle": 90, ROAD: 65, "Metro": 90, "Train": 80,
            "Tram": 75, "Bus": 65, "Transit": 65}
DELAY = {"Walk": .05, "Cycle": .10, ROAD: .50, "Metro": .10, "Train": .25,
         "Tram": .25, "Bus": .40, "Transit": .40}
HEADWAY_PENALTY = 0.8   # reliability points lost per minute between vehicles
