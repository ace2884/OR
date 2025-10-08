from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
from math import radians, sin, cos, sqrt, atan2
import folium

app = Flask(__name__)
CORS(app)

# Helper: load geocache from backend folder
BASE_DIR = os.path.dirname(__file__)
POSSIBLE_GEOCACHE = [
    os.path.join(BASE_DIR, '..', 'BE', 'geocache_hyd.json'),
    os.path.join(BASE_DIR, '..', 'backend2', 'geocache_hyd.json'),
    os.path.join(BASE_DIR, 'geocache_hyd.json')
]

GEOCACHE = {}
for p in POSSIBLE_GEOCACHE:
    p = os.path.normpath(p)
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                GEOCACHE = json.load(f)
            break
        except Exception:
            continue


def haversine(a, b):
    """Return distance in kilometers between two (lat,lon) pairs."""
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a_val = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2 * atan2(sqrt(a_val), sqrt(1-a_val))
    return 6371.0 * c


def greedy_route_from_coords(locations, depot=None):
    """Greedy nearest-neighbor route using GEOCACHE coordinates.
    locations: list of location keys present in GEOCACHE
    depot: location key (optional)
    returns route (list of location keys) and total distance (km)
    """
    # Map to coordinates
    coords = {}
    for loc in locations:
        if loc in GEOCACHE:
            # ensure (lat,lon) tuple
            val = GEOCACHE[loc]
            coords[loc] = (float(val[0]), float(val[1]))
    if not coords:
        return [], 0.0

    nodes = list(coords.keys())
    start = depot if depot in coords else nodes[0]
    route = [start]
    visited = {start}
    total = 0.0
    current = start

    while len(visited) < len(nodes):
        # find nearest unvisited
        nearest = None
        ndist = float('inf')
        for n in nodes:
            if n in visited:
                continue
            d = haversine(coords[current], coords[n])
            if d < ndist:
                ndist = d
                nearest = n
        if nearest is None:
            break
        route.append(nearest)
        total += ndist
        visited.add(nearest)
        current = nearest

    return route, round(total, 2)


def assign_locations(employees, customers):
    """Assign customers to employees based on problem_occured and availability
    employees: list of {e_id,name,problem_occured,availability}
    customers: list of {location,problem_occured}
    returns list of assignments: [{e_id,name,assigned_locations}]
    """
    assignments = []
    # Build customer lists per problem
    by_problem = {}
    for c in customers:
        loc = c.get('location')
        prob = c.get('problem_occured')
        if not loc or not prob:
            continue
        by_problem.setdefault(prob, []).append(loc)

    for emp in employees:
        avail = str(emp.get('availability', '')).strip().lower()
        if avail not in ('yes', '1', 'true', 'available'):
            continue
        prob = emp.get('problem_occured')
        locs = by_problem.get(prob, [])
        if locs:
            assignments.append({
                'e_id': emp.get('e_id'),
                'name': emp.get('name'),
                'assigned_locations': locs,
                'problem_occured': prob
            })
    return assignments


def load_json_candidates():
    """Try to find customers and employees JSON files in common locations."""
    candidates = {}
    # customers - prefer backend/customers_data.json
    cust_paths = [
        os.path.normpath(os.path.join(BASE_DIR, '..', 'backend', 'customers_data.json')),
        os.path.normpath(os.path.join(BASE_DIR, '..', 'BE', 'customers_data.json')),
        os.path.normpath(os.path.join(BASE_DIR, '..', 'backend', 'customers.json'))
    ]
    for p in cust_paths:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # customers_data.json may have top-level 'customers' list
                if isinstance(data, dict) and 'customers' in data:
                    candidates['customers'] = data['customers']
                elif isinstance(data, list):
                    candidates['customers'] = data
                else:
                    candidates['customers'] = []
                break
            except Exception:
                continue
    # employees - prefer BE/employees.json
    emp_paths = [
        os.path.normpath(os.path.join(BASE_DIR, 'employees.json')),
        os.path.normpath(os.path.join(BASE_DIR, '..', 'BE', 'employees_data.json')),
        os.path.normpath(os.path.join(BASE_DIR, '..', 'BE', 'employees.json'))
    ]
    for p in emp_paths:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # employees file may have { 'employees': [...] } or list
                if isinstance(data, dict) and 'employees' in data:
                    candidates['employees'] = data['employees']
                elif isinstance(data, list):
                    candidates['employees'] = data
                else:
                    candidates['employees'] = []
                break
            except Exception:
                continue

    # default to empty lists
    candidates.setdefault('customers', [])
    candidates.setdefault('employees', [])
    return candidates


def generate_route_map_html(emp_name, route):
    """Create a folium map and return rendered HTML as a string (no files written)."""
    route_coords = []
    for loc in route:
        coord = GEOCACHE.get(loc)
        if coord:
            route_coords.append((float(coord[0]), float(coord[1])))
    if not route_coords:
        return None

    center_lat = sum(c[0] for c in route_coords) / len(route_coords)
    center_lon = sum(c[1] for c in route_coords) / len(route_coords)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
    # Add markers: start (green), intermediate (blue), end (red)
    for i, (loc, coord) in enumerate(zip(route, route_coords)):
        color = 'blue'
        icon_color = 'blue'
        if i == 0:
            color = 'green'
            icon_color = 'green'
        elif i == len(route_coords) - 1:
            color = 'red'
            icon_color = 'red'
        folium.Marker(location=coord, popup=f"Stop {i+1}: {loc}", tooltip=f"Stop {i+1}",
                      icon=folium.Icon(color=icon_color)).add_to(m)

    # Draw route line and add simple segment popups showing distance
    if len(route_coords) > 1:
        # full route polyline
        folium.PolyLine(route_coords, color='red', weight=3, opacity=0.8).add_to(m)
        # add small circle markers between consecutive points with distance in popup
        for i in range(len(route_coords) - 1):
            a = route_coords[i]
            b = route_coords[i+1]
            seg_mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            seg_dist = round(haversine(a, b), 2)
            folium.CircleMarker(location=seg_mid, radius=3, color='black', fill=True,
                                fill_color='black', popup=f"{seg_dist} km").add_to(m)
    # Render HTML string
    return m.get_root().render()


@app.route('/assign_locations', methods=['POST'])
def assign_locations_endpoint():
    """POST body can contain { 'e_id':..., 'name':..., optional 'depot': ... }
    The endpoint will load customers & employees data, compute assignments,
    generate an optimized route for the requested employee and return route,
    distance_km and map_html (string) so frontend can display it without new files.
    """
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        return jsonify({'error': 'Invalid JSON body', 'details': str(e)}), 400

    e_id = payload.get('e_id')
    name = payload.get('name')
    depot = payload.get('depot')

    # Load data
    data = load_json_candidates()
    employees = data.get('employees', [])
    customers = data.get('customers', [])

    if not employees:
        return jsonify({'error': 'No employee data found'}), 404
    if not customers:
        return jsonify({'error': 'No customer data found'}), 404

    assignments = assign_locations(employees, customers)

    emp = None
    if e_id:
        emp = next((a for a in assignments if str(a.get('e_id')) == str(e_id)), None)
    elif name:
        emp = next((a for a in assignments if str(a.get('name')).strip().lower() == str(name).strip().lower()), None)
    else:
        return jsonify({'error': 'Provide e_id or name in JSON body'}), 400

    if not emp:
        return jsonify({'error': 'Employee not found or no assigned locations'}), 404

    locations = emp.get('assigned_locations', [])
    # Filter locations to those present in GEOCACHE
    locs_with_coords = [loc for loc in locations if loc in GEOCACHE]

    route, dist = greedy_route_from_coords(locs_with_coords, depot)

    map_html = generate_route_map_html(emp.get('name', 'employee'), route)

    return jsonify({
        'e_id': emp.get('e_id'),
        'name': emp.get('name'),
        'route': route,
        'distance_km': dist,
        'map_html': map_html
    })


@app.route('/optimized_route', methods=['POST'])
def optimized_route():
    """Return optimized list of locations and distance for given employee (e_id or name).
    Body: { 'e_id':..., 'name':..., optional 'depot': ... }
    """
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        return jsonify({'error': 'Invalid JSON body', 'details': str(e)}), 400

    e_id = payload.get('e_id')
    name = payload.get('name')
    depot = payload.get('depot')

    data = load_json_candidates()
    employees = data.get('employees', [])
    customers = data.get('customers', [])

    assignments = assign_locations(employees, customers)

    emp = None
    if e_id:
        emp = next((a for a in assignments if str(a.get('e_id')) == str(e_id)), None)
    elif name:
        emp = next((a for a in assignments if str(a.get('name')).strip().lower() == str(name).strip().lower()), None)
    else:
        return jsonify({'error': 'Provide e_id or name in JSON body'}), 400

    if not emp:
        return jsonify({'error': 'Employee not found or no assigned locations'}), 404

    locations = emp.get('assigned_locations', [])
    locs_with_coords = [loc for loc in locations if loc in GEOCACHE]
    route, dist = greedy_route_from_coords(locs_with_coords, depot)

    return jsonify({'e_id': emp.get('e_id'), 'name': emp.get('name'), 'route': route, 'distance_km': dist})


@app.route('/optimized_map', methods=['POST'])
def optimized_map():
    """Return optimized map HTML for given employee (e_id or name). Body same as /optimized_route."""
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        return jsonify({'error': 'Invalid JSON body', 'details': str(e)}), 400

    e_id = payload.get('e_id')
    name = payload.get('name')
    depot = payload.get('depot')

    data = load_json_candidates()
    employees = data.get('employees', [])
    customers = data.get('customers', [])

    assignments = assign_locations(employees, customers)

    emp = None
    if e_id:
        emp = next((a for a in assignments if str(a.get('e_id')) == str(e_id)), None)
    elif name:
        emp = next((a for a in assignments if str(a.get('name')).strip().lower() == str(name).strip().lower()), None)
    else:
        return jsonify({'error': 'Provide e_id or name in JSON body'}), 400

    if not emp:
        return jsonify({'error': 'Employee not found or no assigned locations'}), 404

    locations = emp.get('assigned_locations', [])
    locs_with_coords = [loc for loc in locations if loc in GEOCACHE]
    route, dist = greedy_route_from_coords(locs_with_coords, depot)

    map_html = generate_route_map_html(emp.get('name', 'employee'), route)
    if not map_html:
        return jsonify({'error': 'Failed to generate map (no coordinates)'}), 500

    return jsonify({'e_id': emp.get('e_id'), 'name': emp.get('name'), 'map_html': map_html, 'distance_km': dist})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=True)
