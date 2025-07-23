import os
import re
from flask import Flask, request, render_template, session
import folium
import sqlite3
from shapely.geometry import Polygon, MultiPolygon
from folium.plugins import PolyLineTextPath
from FDfile_processing import parse_uploaded_file, parse_coord
from DBMloader import get_selected_db_path, load_fixpoints, load_fir_polygons, DB_OPTIONS

app = Flask(__name__)
app.secret_key = 'change_this_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def clear_upload_folder():
    folder = app.config['UPLOAD_FOLDER']
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")

@app.route('/', methods=['GET', 'POST'])
def index():
    selected_db = session.get('selected_db', list(DB_OPTIONS.keys())[0])
    selected_flights_raw = session.get('selected_flights', [])

    if request.method == 'POST':
        # DB ვერსიის არჩევა
        if 'db_option' in request.form:
            selected_db = request.form['db_option']
            if selected_db in DB_OPTIONS:
                session['selected_db'] = selected_db

        # ფაილის ატვირთვა
        if 'flightfile' in request.files:
            file = request.files['flightfile']
            if file.filename == '':
                return render_template("index.html", message="No file selected.", db_options=DB_OPTIONS, selected_db=selected_db, selected_flights_raw=selected_flights_raw)
            if not file.filename.lower().endswith('.txt'):
                return render_template("index.html", message="Only .txt files are supported.", db_options=DB_OPTIONS, selected_db=selected_db, selected_flights_raw=selected_flights_raw)

            # ძველი ფაილების წაშლა
            clear_upload_folder()

            from werkzeug.utils import secure_filename
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            if not os.path.isfile(filepath):
                return render_template("index.html", message="File was not saved correctly.", db_options=DB_OPTIONS, selected_db=selected_db, selected_flights_raw=selected_flights_raw)

            session['filename'] = filename
            flights = parse_uploaded_file(filepath)
            session['selected_flights'] = []
            return render_template("index.html", flights=flights, db_options=DB_OPTIONS, selected_db=selected_db, selected_flights_raw=[])

    flights = []
    filename = session.get('filename')
    if filename:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.isfile(filepath):
            flights = parse_uploaded_file(filepath)
        else:
            session.pop('filename', None)
            return render_template("index.html", message="Uploaded file not found. Please upload again.", db_options=DB_OPTIONS, selected_db=selected_db, selected_flights_raw=selected_flights_raw)

    return render_template("index.html",
                           db_options=DB_OPTIONS,
                           selected_db=selected_db,
                           flights=flights,
                           selected_flights_raw=selected_flights_raw)


@app.route('/show', methods=['POST'])
def show_selected():
    selected_flights_raw = request.form.getlist('selected_flights')
    session['selected_flights'] = selected_flights_raw
    filename = session.get('filename')
    selected_db = session.get('selected_db', list(DB_OPTIONS.keys())[0])
    db_path = DB_OPTIONS.get(selected_db, list(DB_OPTIONS.values())[0])

    if not filename:
        return render_template("index.html", message="Please upload a file first", db_options=DB_OPTIONS, selected_db=selected_db)

    flights = parse_uploaded_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    if not selected_flights_raw:
        return render_template("index.html", flights=flights, message="No flights selected", db_options=DB_OPTIONS, selected_db=selected_db)

    pattern = r'^(.+?) \((.+?) - (.+?)\)$'
    selected_flights = []
    for val in selected_flights_raw:
        m = re.match(pattern, val)
        if m:
            callsign, activation_time, end_time = m.groups()
            selected_flights.append({
                "callsign": callsign,
                "activation_time": activation_time,
                "end_time": end_time
            })

    filtered_flights = []
    for flight in flights:
        for sel in selected_flights:
            if (flight['callsign'] == sel['callsign'] and
                flight['activation_time'] == sel['activation_time'] and
                flight['end_time'] == sel['end_time']):
                filtered_flights.append(flight)
                break

    if not filtered_flights:
        return render_template("index.html", flights=flights, message="No matching flights found", db_options=DB_OPTIONS, selected_db=selected_db)

    fixpoint_coords = load_fixpoints(db_path)
    fir_poly = load_fir_polygons(db_path)

    m = folium.Map(location=[42.0, 44.5], zoom_start=6)

    # Fixpoints layer
    fixpoints_group = folium.FeatureGroup(name="Fixpoints")
    for name, (lat, lon) in fixpoint_coords.items():
        folium.Marker(
            [lat, lon],
            icon=folium.DivIcon(
                icon_size=(150, 36),
                icon_anchor=(7, 20),
                html=f'<div style="font-size: 6pt; color: black;">* {name}</div>'
            )
        ).add_to(fixpoints_group)
    fixpoints_group.add_to(m)

    # FIR polygon layer
    fir_group = folium.FeatureGroup(name="FIR Boundaries")
    if isinstance(fir_poly, MultiPolygon):
        for poly in fir_poly.geoms:
            coords = [(lat, lon) for lon, lat in poly.exterior.coords]
            folium.Polygon(
                locations=coords,
                color='blue',
                fill=True,
                fill_color='#F7E094',
                fill_opacity=0.1,
                weight=2,
            ).add_to(fir_group)
    else:
        coords = [(lat, lon) for lon, lat in fir_poly.exterior.coords]
        folium.Polygon(
            locations=coords,
            color='blue',
            fill=True,
            fill_color='#F7E094',
            fill_opacity=0.1,
            weight=2,
        ).add_to(fir_group)
    fir_group.add_to(m)

    # Airways layer (toggleable)
    airways_group = folium.FeatureGroup(name="Airways", show=True)
    conn_aw = sqlite3.connect(db_path)
    cursor_aw = conn_aw.cursor()
    cursor_aw.execute("SELECT name, pathpoints FROM airways")
    routes = cursor_aw.fetchall()
    conn_aw.close()

    for name, pathpoints_str in routes:
        pathpoints = [p.strip() for p in pathpoints_str.split(",")]
        coordinates = []
        missing_points = False
        for point in pathpoints:
            if point in fixpoint_coords:
                coordinates.append(fixpoint_coords[point])
            else:
                missing_points = True
        if len(coordinates) >= 2 and not missing_points:
            folium.PolyLine(
                locations=coordinates,
                color='grey',
                weight=2.5,
                opacity=0.8,
                popup=name,
                tooltip=name
            ).add_to(airways_group)
    airways_group.add_to(m)

    # Selected flights FP_route (red) and route_list (orange)
    flights_group = folium.FeatureGroup(name="FP_route")
    flights_route_list_group = folium.FeatureGroup(name="route_list")

    # ENTRY/EXIT group
    entry_exit_group = folium.FeatureGroup(name="ENTRY/EXIT Points")

    for flight in filtered_flights:
        for label, key, color in [
            ('ENTRY', 'ENTRY', 'green'),
            ('EXIT', 'exit', 'red')
        ]:
            point_name = flight.get(key)
            if point_name in fixpoint_coords:
                lat, lon = fixpoint_coords[point_name]

                folium.Marker(
                    [lat, lon],
                    icon=folium.DivIcon(html=f"""
                        <div style="
                            font-size: 12px;
                            color: Black;
                            background-color: {color};
                            font-weight: bold;
                            padding: 2px 6px;
                            border-radius: 4px;
                            box-shadow: 1px 1px 4px rgba(0,0,0,0.3);
                        ">
                            {label}
                        </div>
                    """)
                ).add_to(entry_exit_group)
    entry_exit_group.add_to(m)

    for flight in filtered_flights:
        # FP_route (red)
        route_str = flight['FP_route']
        route_points = [p.strip() for p in route_str.split() if p]
        coordinates_fp = []
        missing_fp = []

        for p in route_points:
            if p in fixpoint_coords:
                coordinates_fp.append(fixpoint_coords[p])
            elif re.match(r"^\d{4}[NS]\d{5}[EW]$", p):
                coord = parse_coord(p)
                if coord:
                    coordinates_fp.append(coord)
                else:
                    missing_fp.append(p)
            else:
                missing_fp.append(p)

        if len(coordinates_fp) >= 2:
            line_fp = folium.PolyLine(
                locations=coordinates_fp,
                color='red',
                weight=3,
                opacity=0.9,
                popup=f"Flight: {flight['callsign']}<br>Activated: {flight['activation_time']}<br>Ended: {flight['end_time']} (FP_route)",
                tooltip=f"{flight['callsign']} FP_route"
            )
            line_fp.add_to(flights_group)

            start_coord = coordinates_fp[0]
            folium.map.Marker(
                location=start_coord,
                icon=folium.DivIcon(
                    html=f'<div style="font-weight:bold; color:black; font-size:12px;">{flight["callsign"]}</div>'
                )
            ).add_to(flights_group)

            arrow_fp = PolyLineTextPath(
                line_fp,
                ' ► ',
                repeat=True,
                offset=7,
                attributes={'fill': 'red', 'font-weight': 'bold', 'font-size': '16'}
            )
            arrow_fp.add_to(flights_group)

        # route_list (orange)
        route_list_points = flight.get('route_list', [])
        coordinates_rl = []
        missing_rl = []

        for p in route_list_points:
            if p in fixpoint_coords:
                coordinates_rl.append(fixpoint_coords[p])
            elif re.match(r"^\d{4}[NS]\d{5}[EW]$", p):
                coord = parse_coord(p)
                if coord:
                    coordinates_rl.append(coord)
                else:
                    missing_rl.append(p)
            else:
                missing_rl.append(p)

        if len(coordinates_rl) >= 2:
            line_rl = folium.PolyLine(
                locations=coordinates_rl,
                color='orange',
                weight=3,
                opacity=0.9,
                popup=f"Flight: {flight['callsign']}<br>Activated: {flight['activation_time']}<br>Ended: {flight['end_time']} (route_list)",
                tooltip=f"{flight['callsign']} route_list"
            )
            line_rl.add_to(flights_route_list_group)

            arrow_rl = PolyLineTextPath(
                line_rl,
                ' ► ',
                repeat=True,
                offset=7,
                attributes={'fill': 'orange ', 'font-weight': 'bold', 'font-size': '16'}
            )
            arrow_rl.add_to(flights_route_list_group)

    flights_group.add_to(m)
    flights_route_list_group.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    map_html = m._repr_html_()
    return render_template("index.html", map_html=map_html, flights=flights, db_options=DB_OPTIONS, selected_db=selected_db)


if __name__ == "__main__":
    app.run(debug=True, host="192.168.1.203", port=8080)
