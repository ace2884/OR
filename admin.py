from flask import Flask, request, jsonify
from flask_cors import CORS
import csv
import json
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Security / upload settings
# Limit uploads to 16 MB
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Folder to save uploaded CSV and generated JSON (absolute paths relative to this file)
BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
JSON_FILE = os.path.join(BASE_DIR, 'employees.json')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Allowed extensions
ALLOWED_EXT = {'.csv'}


@app.route('/')
def home():
    return "Employee Upload API is Running!"


# ==============================
# 1️⃣ ADMIN UPLOAD EMPLOYEE CSV
# ==============================
@app.route('/upload_employees', methods=['POST'])
def upload_employees():
    # Accept common field names for the uploaded file to be more forgiving
    file = (
        request.files.get('file')
        or request.files.get('csv')
        or request.files.get('upload')
    )

    if not file:
        return jsonify({
            'error': 'No file part in request',
            'hint': 'Send multipart/form-data POST with form field named "file" (or "csv").'
        }), 400

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    _, ext = os.path.splitext(filename)
    if ext.lower() not in ALLOWED_EXT:
        return jsonify({'error': 'Invalid file format. Only CSV allowed.'}), 400

    # Save the uploaded CSV temporarily (use secure filename)
    csv_path = os.path.join(UPLOAD_FOLDER, filename)

    try:
        file.save(csv_path)

        # Convert CSV → JSON
        employees = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                employee_data = {
                    "e_id": row.get("e_id"),
                    "name": row.get("name"),
                    "skill": row.get("skill"),
                    "problem_occured": row.get("problem_occured"),
                    "availability": row.get("availability")
                }
                employees.append(employee_data)

        # Save as JSON atomically
        tmp_json = JSON_FILE + '.tmp'
        with open(tmp_json, 'w', encoding='utf-8') as f:
            json.dump(employees, f, indent=3, ensure_ascii=False)
        os.replace(tmp_json, JSON_FILE)

        return jsonify({
            'message': f'{len(employees)} employees uploaded and saved successfully!',
            'json_file': JSON_FILE
        })

    except Exception as e:
        return jsonify({'error': 'Failed to process uploaded file', 'details': str(e)}), 500

    finally:
        # Cleanup uploaded CSV
        try:
            if os.path.exists(csv_path):
                os.remove(csv_path)
        except Exception:
            pass
# ==============================
# 2️⃣ FETCH ALL EMPLOYEE DATA
# ==============================
@app.route('/employees', methods=['GET'])
def get_employees():
    if not os.path.exists(JSON_FILE):
        return jsonify({'error': 'Employee data not found. Please upload first.'}), 404
    
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        employees = json.load(f)
    # Optional query filters
    availability = request.args.get('availability')
    skill = request.args.get('skill')
    problem = request.args.get('problem_occured')

    filtered = employees
    if availability:
        filtered = [e for e in filtered if str(e.get('availability','')).strip().lower() == availability.strip().lower()]
    if skill:
        filtered = [e for e in filtered if str(e.get('skill','')).strip().lower() == skill.strip().lower()]
    if problem:
        filtered = [e for e in filtered if str(e.get('problem_occured','')).strip().lower() == problem.strip().lower()]

    return jsonify(filtered)


# ==========================================
# 3️⃣ FILTER EMPLOYEES BY PROBLEM OCCURRED
# ==========================================


@app.route('/employees/filter', methods=['GET', 'POST'])
def filter_employees():
    # Safely parse JSON body (if any) without raising on bad JSON
    json_body = request.get_json(silent=True)

    # Prefer query params, fall back to JSON body
    problem = request.args.get('problem_occured') or (json_body.get('problem_occured') if isinstance(json_body, dict) else None)
    availability = request.args.get('availability') or (json_body.get('availability') if isinstance(json_body, dict) else None)

    if not problem:
        return jsonify({'error': 'Please provide problem_occured'}), 400

    if not os.path.exists(JSON_FILE):
        return jsonify({'error': 'Employee data not found. Please upload first.'}), 404

    # Load employees with guarded JSON decode
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            employees = json.load(f)
    except json.JSONDecodeError:
        return jsonify({'error': 'Employee data file is corrupted (invalid JSON).'}), 500
    except Exception as e:
        return jsonify({'error': 'Failed to read employee data', 'details': str(e)}), 500

    def normalize_text(v):
        return str(v).strip().lower() if v is not None else ''

    # Normalize desired availability into category sets for flexible matching
    def availability_matches(emp_av_raw, desired_raw):
        if not desired_raw:
            return True
        emp_av = normalize_text(emp_av_raw)
        desired = normalize_text(desired_raw)
        true_set = {'yes', 'true', '1', 'available', 'y'}
        false_set = {'no', 'false', '0', 'n'}
        if desired in true_set:
            return emp_av in true_set
        if desired in false_set:
            return emp_av in false_set
        # fallback to substring compare
        return desired in emp_av

    desired_problem = normalize_text(problem)

    filtered = [
        emp for emp in employees
        if normalize_text(emp.get('problem_occured')) == desired_problem
    ]

    if availability:
        filtered = [emp for emp in filtered if availability_matches(emp.get('availability'), availability)]

    return jsonify(filtered)

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
