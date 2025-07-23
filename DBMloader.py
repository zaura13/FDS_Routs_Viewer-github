# DBMloader.py
import sqlite3
from shapely.geometry import Polygon

DB_OPTIONS = {
    "DBM_2025-07-18.db": "DBM_2025-07-18.db",
    "Version 2": "DBM_v2.db",
    "Version 3": "DBM_v3.db"
}

def get_selected_db_path(session):
    selected_db = session.get('selected_db')
    if selected_db in DB_OPTIONS:
        return DB_OPTIONS[selected_db]
    return list(DB_OPTIONS.values())[0]

def load_fixpoints(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT Fixpoint, Latitude, Longitude FROM Fixpoints WHERE Kind IN ('RO', 'DM', 'ND')")
    fixpoints = cursor.fetchall()
    conn.close()
    return {name.strip(): (float(lat), float(lon)) for name, lat, lon in fixpoints}

def load_fir_polygons(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT latitude, longitude FROM FIR ORDER BY id")
    coords_georgia = cursor.fetchall()
    cursor.execute("SELECT latitude, longitude FROM Blacksea_poligon ORDER BY id")
    coords_blacksea = cursor.fetchall()
    conn.close()
    poly_georgia = Polygon([(lon, lat) for lat, lon in coords_georgia])
    poly_blacksea = Polygon([(lon, lat) for lat, lon in coords_blacksea])
    return poly_georgia.union(poly_blacksea)
