"""BE/customers_api.py

Flask API to create and retrieve customer tickets.
- POST /customers : create a new ticket for a customer (generates unique ticket_number)
- GET /customers  : list tickets, optional filters: username, ticket_number

Data is persisted to: d:/OR_EXP/backend/customers_data.json

Notes:
- ticket_number is unique and auto-generated as 'T' + zero-padded 4-digit number (e.g. T0101)
- Multiple tickets per username are allowed
- Uses a simple file lock to avoid concurrent writes
"""

from flask import Flask, request, jsonify, abort
import json
import os
from threading import Lock
from datetime import datetime
from typing import Dict, Any, List

app = Flask(__name__)

# File paths
BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # d:/OR_EXP
CUSTOMERS_JSON_PATH = os.path.join(BASE_DIR, 'backend', 'customers_data.json')

# In-process lock to avoid concurrent writes
file_lock = Lock()

# Utility functions

def _read_customers_file() -> Dict[str, Any]:
    if not os.path.exists(CUSTOMERS_JSON_PATH):
        # Initialize structure
        data = {"customers": [], "metadata": {"total_customers": 0, "locations_count": 0, "problem_types": [], "created_date": datetime.now().strftime('%Y-%m-%d')}}
        return data
    with open(CUSTOMERS_JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_customers_file(data: Dict[str, Any]):
    # Write atomically
    temp_path = CUSTOMERS_JSON_PATH + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, CUSTOMERS_JSON_PATH)


def _generate_next_ticket_number(customers: List[Dict[str, Any]]) -> str:
    # Ticket format: T#### (zero-padded). Find max existing numeric part and add 1
    max_num = 0
    for c in customers:
        tn = c.get('ticket_number', '')
        if isinstance(tn, str) and tn.startswith('T') and tn[1:].isdigit():
            try:
                num = int(tn[1:])
                if num > max_num:
                    max_num = num
            except ValueError:
                continue
    next_num = max_num + 1
    return f"T{next_num:04d}"


def _validate_customer_payload(payload: Dict[str, Any]) -> List[str]:
    required = ['username', 'location', 'contact', 'problem_occured']
    missing = [r for r in required if r not in payload or payload[r] in (None, '')]
    return missing


@app.route('/customers', methods=['POST'])
def create_customer_ticket():
    """Create a new customer ticket. Payload must include username, location, contact, problem_occured.
    Returns the created ticket (with ticket_number).
    """
    payload = request.get_json()
    if not payload:
        return jsonify({'error': 'Invalid or missing JSON payload'}), 400

    missing = _validate_customer_payload(payload)
    if missing:
        return jsonify({'error': 'Missing required fields', 'missing': missing}), 400

    with file_lock:
        data = _read_customers_file()
        customers = data.get('customers', [])

        # Generate unique ticket_number
        ticket_number = _generate_next_ticket_number(customers)

        new_ticket = {
            'username': payload['username'],
            'ticket_number': ticket_number,
            'location': payload['location'],
            'contact': payload['contact'],
            'problem_occured': payload['problem_occured']
        }

        customers.append(new_ticket)

        # Update metadata
        data['customers'] = customers
        data['metadata'] = data.get('metadata', {})
        data['metadata']['total_customers'] = len(customers)
        data['metadata']['created_date'] = data['metadata'].get('created_date', datetime.now().strftime('%Y-%m-%d'))

        # Write back to file
        try:
            _write_customers_file(data)
        except Exception as e:
            return jsonify({'error': 'Failed to save data', 'details': str(e)}), 500

    return jsonify(new_ticket), 201


@app.route('/customers', methods=['GET'])
def list_customers():
    """List customer tickets. Optional query params: username, ticket_number"""
    username = request.args.get('username')
    ticket_number = request.args.get('ticket_number')

    data = _read_customers_file()
    customers = data.get('customers', [])

    # Apply filters
    if username:
        customers = [c for c in customers if c.get('username') == username]
    if ticket_number:
        customers = [c for c in customers if c.get('ticket_number') == ticket_number]

    return jsonify({'customers': customers, 'count': len(customers)}), 200


if __name__ == '__main__':
    # Only for local debugging; use a proper WSGI server in production
    app.run(host='0.0.0.0', port=5000, debug=True)
