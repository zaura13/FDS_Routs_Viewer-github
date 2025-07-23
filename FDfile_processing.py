import re

def parse_uploaded_file(filepath):
    flights = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            line_clean = line.strip('\x02\x03')
            fields = line_clean.split(',')

            if len(fields) > 55:
                flight = {
                    "callsign": fields[1].strip(),
                    "activation_time": fields[2].strip(),
                    "end_time": fields[4].strip(),
                    "FP_route": fields[22].strip(),
                    "route_list": [],
                    "ENTRY": fields[41].strip(),
                    "exit": fields[42].strip()
                }
                # print(flight)

                try:
                    offset = int(fields[54].strip())
                    start_index = 55 + offset
                    for i in range(start_index, len(fields), 3):
                        point = fields[i].strip()
                        if point:
                            flight["route_list"].append(point)
                    #print(flight["callsign"])
                    #print(flight["FP_route"])
                    #print(flight["route_list"])
                    #print(flight["ENTRY"])
                    # print(flight["exit"])


                except ValueError:
                    # თუ 55-ე ველი ცარიელია ან არასწორია
                    pass

                flights.append(flight)
    return flights

def parse_coord(coord_str):
    match = re.match(r"(\d{2})(\d{2})([NS])(\d{3})(\d{2})([EW])", coord_str)
    if not match:
        return None
    lat_deg, lat_min, lat_hem, lon_deg, lon_min, lon_hem = match.groups()
    lat = int(lat_deg) + int(lat_min) / 60.0
    lon = int(lon_deg) + int(lon_min) / 60.0
    if lat_hem == 'S':
        lat *= -1
    if lon_hem == 'W':
        lon *= -1
    return (lat, lon)
