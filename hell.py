from flask import Flask, request, jsonify
from datetime import datetime
import random 
# NOTE: In a production environment, you would need to install 'flask-cors' 
# and initialize it to allow the React frontend to communicate with this backend.
from flask_cors import CORS 

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_very_secret_key_for_hackathon' 
CORS(app) # Enable CORS for frontend communication (REQUIRED for React app)

# --- MOCK DATABASE STRUCTURES ---
# In a real app, these would connect to PostgreSQL or Firestore
COMPANIES = {}      
USERS = {}          
EXPENSES = {}       

# Stores the Admin-configured rules
APPROVAL_RULES = {} 

# Global ID counters
NEXT_COMPANY_ID = 1
NEXT_USER_ID = 1
NEXT_EXPENSE_ID = 1

# --- CONSTANTS ---
ROLES = ["Admin", "Manager", "Employee", "Finance", "Director"] 
DEFAULT_ENV_CURRENCY = "USD" 

# --- MOCK AUTH/HELPER FUNCTIONS ---

def get_current_user(user_id):
    """Mocks fetching user data and role based on a provided ID."""
    return USERS.get(user_id)

def create_initial_company_and_admin(user_email):
    """Auto-creates Company and Admin User on first signup."""
    global NEXT_COMPANY_ID, NEXT_USER_ID
    
    company_id = NEXT_COMPANY_ID
    COMPANIES[company_id] = {
        'id': company_id,
        'name': f"Default Company {company_id}",
        'currency': DEFAULT_ENV_CURRENCY 
    }
    NEXT_COMPANY_ID += 1

    user_id = NEXT_USER_ID
    USERS[user_id] = {
        'id': user_id,
        'company_id': company_id,
        'email': user_email,
        'role': 'Admin',
        'manager_id': None 
    }
    NEXT_USER_ID += 1
    return USERS[user_id]

def find_user_by_role(company_id, role):
    """Finds the first user with a specific role in a company."""
    # Priority given to finding an actual user for the role
    for user in USERS.values():
        if user.get('company_id') == company_id and user.get('role') == role:
            return user
    return None

def mock_currency_conversion(amount, from_currency, to_currency):
    """
    MOCK: Placeholder for api.exchangerate-api.com integration.
    Generates a fixed conversion rate for consistency in the demo.
    """
    if from_currency.upper() == to_currency.upper():
        return float(amount)
    
    # Mocking a fixed rate for consistency (e.g., 1 EUR = 1.08 USD)
    if from_currency.upper() == 'EUR' and to_currency.upper() == 'USD':
        mock_rate = 1.08
    elif from_currency.upper() == 'GBP' and to_currency.upper() == 'USD':
        mock_rate = 1.25
    else:
        # Fallback rate
        mock_rate = 1.05 
        
    return round(float(amount) * mock_rate, 2)

def apply_conditional_rules(company_id, approvals_history):
    """
    Checks if the conditional rules defined by the Admin have been met
    to trigger an early Auto-Approval, based on the problem statement logic.
    """
    rules = APPROVAL_RULES.get(company_id, {}).get('conditional', {})
    flow_steps = APPROVAL_RULES.get(company_id, {}).get('steps', [])
    flow_roles = {step['role'] for step in flow_steps}
    
    # 1. Specific Approver Rule 
    if rules.get('type') == 'Specific' and rules.get('required_role'):
        required_role = rules['required_role']
        specific_approved = any(a['role'] == required_role and a['status'] == 'Approved' for a in approvals_history)
        
        if specific_approved:
            return True, f"Conditional Rule Met: Specific approver ({required_role}) Approved."
            
    # 2. Percentage Rule 
    if rules.get('type') == 'Percentage' and rules.get('threshold'):
        threshold = rules['threshold'] / 100.0
        
        # Count the number of unique roles that have approved so far
        approved_roles = {a['role'] for a in approvals_history if a['status'] == 'Approved' and a['role'] in flow_roles}
        
        if len(flow_roles) > 0 and (len(approved_roles) / len(flow_roles)) >= threshold:
            return True, f"Conditional Rule Met: {rules['threshold']}% of approvers have approved."
    
    # 3. Hybrid Rule: Check if EITHER condition is met.
    if rules.get('type') == 'Hybrid' and rules.get('specific_role') and rules.get('threshold'):
        
        # Check Specific Role part
        specific_role = rules['specific_role']
        specific_approved = any(a['role'] == specific_role and a['status'] == 'Approved' for a in approvals_history)
        if specific_approved:
            return True, f"Conditional Hybrid Rule Met: Specific approver ({specific_role}) Approved."

        # Check Percentage part
        threshold = rules['threshold'] / 100.0
        approved_roles = {a['role'] for a in approvals_history if a['status'] == 'Approved' and a['role'] in flow_roles}
        if len(flow_roles) > 0 and (len(approved_roles) / len(flow_roles)) >= threshold:
            return True, f"Conditional Hybrid Rule Met: {rules['threshold']}% of approvers have approved."

    return False, None

# -------------------------------------------------------------------
# 1. AUTHENTICATION & INITIAL SETUP
# -------------------------------------------------------------------

@app.route('/signup', methods=['POST'])
def signup():
    """Handles initial setup: Company and Admin User auto-creation."""
    data = request.json
    user_email = data.get('email')

    if not USERS:
        admin_user = create_initial_company_and_admin(user_email)
        return jsonify({
            "message": "Initial Company and Admin User auto-created successfully. Use ID 1 to manage.",
            "user_id": admin_user['id'],
            "role": admin_user['role'],
            "company_currency": COMPANIES[admin_user['company_id']]['currency']
        }), 201
    else:
        return jsonify({"message": "Use /admin/manage_user to create other employees."}), 400

# -------------------------------------------------------------------
# 2. ADMIN USER MANAGEMENT
# -------------------------------------------------------------------

@app.route('/admin/manage_user', methods=['POST'])
def manage_user():
    """Admin can create employees/managers and define relationships."""
    
    # MOCK: Assume 'user_id' 1 is the Admin making this request
    admin_user = get_current_user(1)
    if not admin_user or admin_user['role'] != 'Admin':
        return jsonify({"message": "Permission denied. Requires Admin role."}), 403

    data = request.json
    new_email = data.get('email')
    new_role = data.get('role')
    manager_id_to_assign = data.get('manager_id')

    if new_role not in ROLES:
        return jsonify({"message": f"Invalid role. Must be one of: {', '.join(ROLES)}."}), 400

    global NEXT_USER_ID
    user_id = NEXT_USER_ID
    
    # Validation
    if manager_id_to_assign:
        manager_user = get_current_user(manager_id_to_assign)
        if not manager_user or manager_user['role'] not in ['Manager', 'Admin']:
            return jsonify({"message": "Invalid manager_id. Manager must have Manager/Admin role."}), 400
    
    # Create the user
    USERS[user_id] = {
        'id': user_id,
        'company_id': admin_user['company_id'],
        'email': new_email,
        'role': new_role,
        'manager_id': manager_id_to_assign
    }
    NEXT_USER_ID += 1

    return jsonify({
        "message": f"{new_role} {new_email} created successfully.",
        "user_id": user_id,
        "manager_id": manager_id_to_assign
    }), 201

# -------------------------------------------------------------------
# 3. ADMIN: CONFIGURE APPROVAL RULES
# -------------------------------------------------------------------

@app.route('/admin/approval_flow', methods=['POST'])
def configure_approval_flow():
    """Admin defines the multi-level sequential and conditional approval rules."""
    
    # MOCK: User 1 is Admin
    admin_user = get_current_user(1) 
    if not admin_user or admin_user['role'] != 'Admin':
        return jsonify({"message": "Permission denied. Requires Admin role."}), 403

    data = request.json
    company_id = admin_user['company_id']

    if 'flow_steps' in data and 'conditional_rule' in data:
        valid_roles = all(step['role'] in ROLES for step in data['flow_steps'])
        if not valid_roles:
            return jsonify({"message": "One or more roles in flow_steps are invalid."}), 400

        APPROVAL_RULES[company_id] = {
            'steps': data['flow_steps'],
            'conditional': data['conditional_rule']
        }
        return jsonify({
            "message": "Approval flow configured successfully.",
            "steps_count": len(data['flow_steps'])
        }), 201
    
    return jsonify({"message": "Missing 'flow_steps' or 'conditional_rule' in request."}), 400

# -------------------------------------------------------------------
# 4. EXPENSE SUBMISSION (Employee Role)
# -------------------------------------------------------------------

@app.route('/expenses/submit', methods=['POST'])
def submit_expense():
    """Employee submits expense and initiates the multi-level approval workflow."""

    # MOCK: Assuming employee_id=3 based on __main__ setup for demonstration
    employee_id = 3
    current_user = get_current_user(employee_id)
    if not current_user or current_user['role'] != 'Employee':
        return jsonify({"message": "Permission denied. Requires Employee role."}), 403

    data = request.json
    required_fields = ['amount', 'currency', 'category', 'description', 'date']
    if not all(field in data for field in required_fields):
        return jsonify({"message": "Missing required expense field(s)."}), 400

    flow = APPROVAL_RULES.get(current_user['company_id'])
    if not flow:
         return jsonify({"message": "Approval flow not configured by Admin. Cannot submit."}), 500

    # --- Determine the first approver based on Admin's first step ---
    first_step = flow['steps'][0] 
    first_approver_id = None
    
    if first_step.get('role') == 'Manager' and first_step.get('is_manager_approver', False):
        # NOTE: The provided setup uses the employee's assigned manager as the first step.
        first_approver_id = current_user['manager_id']
    else:
        # Fallback to finding a user with the required role (e.g., 'Finance', 'Director')
        next_role_user = find_user_by_role(current_user['company_id'], first_step['role'])
        if next_role_user:
            first_approver_id = next_role_user['id']
            
    if not first_approver_id:
        return jsonify({"message": f"Cannot find an approver for the first step ({first_step['role']})."}), 500

    global NEXT_EXPENSE_ID
    expense_id = NEXT_EXPENSE_ID
    
    EXPENSES[expense_id] = {
        'id': expense_id,
        'user_id': current_user['id'],
        'amount': data['amount'],
        'currency': data['currency'].upper(), # Standardize currency
        'category': data['category'],
        'description': data['description'],
        'date': data['date'],
        'status': 'Submitted',
        'current_step': 1, # Start at step 1
        'current_approver_id': first_approver_id,
        'approvals_history': [] # Track all actions
    }
    NEXT_EXPENSE_ID += 1

    return jsonify({
        "message": "Expense submitted successfully, initiating multi-step approval.",
        "expense_id": expense_id,
        "next_approver_id": first_approver_id
    }), 201

# -------------------------------------------------------------------
# 5. MANAGER/ADMIN: VIEW EXPENSES & APPROVE/REJECT
# -------------------------------------------------------------------

@app.route('/expenses/pending/<int:approver_id>', methods=['GET'])
def view_pending_expenses(approver_id):
    """Approver views expenses waiting for their approval, with converted amount."""
    approver = get_current_user(approver_id)
    if not approver or approver['role'] not in ['Admin', 'Manager', 'Finance', 'Director']:
        return jsonify({"message": "Permission denied. Approver role required."}), 403

    company_currency = COMPANIES[approver['company_id']]['currency']
    
    pending_expenses = []
    for expense in EXPENSES.values():
        if expense['current_approver_id'] == approver_id and expense['status'] == 'Submitted':
            
            # --- Currency Conversion for Manager's View ---
            converted_amount = mock_currency_conversion(
                expense['amount'], 
                expense['currency'], 
                company_currency
            )
            
            # The frontend relies on these keys for display
            pending_expenses.append({
                'expense_id': expense['id'],
                'employee_email': get_current_user(expense['user_id'])['email'],
                'amount_original': f"{expense['amount']} {expense['currency']}",
                'amount_company_currency': f"{converted_amount} {company_currency}",
                'description': expense['description'],
                'category': expense['category']
            })
            
    return jsonify({
        "message": f"{len(pending_expenses)} expense(s) pending your approval.",
        "company_currency": company_currency,
        "pending_expenses": pending_expenses
    })


@app.route('/expenses/<int:expense_id>/action', methods=['POST'])
def handle_approval_action(expense_id):
    """Handles an approver's action (Approve/Reject) and routes the expense."""

    data = request.json
    approver_id = data.get('approver_id') 
    action = data.get('action') # 'approve' or 'reject'
    
    approver = get_current_user(approver_id)
    if not approver or approver['role'] not in ['Admin', 'Manager', 'Finance', 'Director']:
        return jsonify({"message": "Permission denied. Invalid approver ID or role."}), 403

    expense = EXPENSES.get(expense_id)
    if not expense:
        return jsonify({"message": "Expense not found."}), 404
        
    if expense['current_approver_id'] != approver['id']:
        return jsonify({"message": "You are not the current designated approver for this expense."}), 403

    # --- Log the approval/rejection ---
    expense['approvals_history'].append({
        'approver_id': approver['id'],
        'role': approver['role'],
        'status': action.capitalize(),
        'comment': data.get('comment', ''),
        'timestamp': datetime.now().isoformat()
    })
    
    if action == 'reject':
        expense['status'] = 'Rejected'
        expense['current_approver_id'] = None
        return jsonify({"message": "Expense claim **Rejected**."})
        
    # --- Check Conditional Rules for Auto-Approval (Complex Flow) ---
    is_conditionally_approved, rule_message = apply_conditional_rules(approver['company_id'], expense['approvals_history'])
    
    if is_conditionally_approved:
        expense['status'] = 'Approved'
        expense['current_approver_id'] = None
        # Add a final approval log entry for clarity
        expense['approvals_history'].append({
            'approver_id': 'System',
            'role': 'Auto-Approval Engine',
            'status': 'Approved',
            'comment': rule_message,
            'timestamp': datetime.now().isoformat()
        })
        return jsonify({"message": f"Expense **AUTO-APPROVED**! {rule_message}"})

    # --- Advance to Next Step (Sequential Flow) ---
    flow = APPROVAL_RULES[approver['company_id']]['steps']
    current_step_index = expense['current_step'] - 1
    
    if current_step_index + 1 < len(flow):
        # Move to the next step
        expense['current_step'] += 1
        next_step = flow[expense['current_step'] - 1]
        
        # Find the next approver
        next_approver_user = find_user_by_role(approver['company_id'], next_step['role'])
        
        if next_approver_user:
            expense['current_approver_id'] = next_approver_user['id']
            return jsonify({
                "message": "Expense approved. Routed to next approver.",
                "next_approver_role": next_step['role'],
                "next_approver_id": expense['current_approver_id']
            })
        else:
            expense['status'] = 'Approval Halted'
            expense['current_approver_id'] = None
            return jsonify({"message": f"Expense approved, but could not find a user for role {next_step['role']}. Approval Halted."})
    else:
        # Final step approved
        expense['status'] = 'Approved'
        expense['current_approver_id'] = None
        return jsonify({"message": "Expense **Fully Approved**!"})

# -------------------------------------------------------------------
# INITIAL SETUP AND RUN
# -------------------------------------------------------------------

if __name__ == '__main__':
    # --- Initial Setup for Testing ---
    # This block creates all necessary users and rules for the frontend to work immediately.
    
    admin_user = create_initial_company_and_admin("admin@company.com") # ID 1: Admin
    company_id = admin_user['company_id']

    # Create Manager, Employee, Finance, Director
    global NEXT_USER_ID
    
    USERS[NEXT_USER_ID] = {'id': NEXT_USER_ID, 'company_id': company_id, 'email': 'manager@company.com', 'role': 'Manager', 'manager_id': 1}
    manager_id = NEXT_USER_ID # ID 2: Manager
    NEXT_USER_ID += 1

    USERS[NEXT_USER_ID] = {'id': NEXT_USER_ID, 'company_id': company_id, 'email': 'employee@company.com', 'role': 'Employee', 'manager_id': manager_id}
    # ID 3: Employee (Reports to Manager ID 2)
    NEXT_USER_ID += 1 

    USERS[NEXT_USER_ID] = {'id': NEXT_USER_ID, 'company_id': company_id, 'email': 'finance@company.com', 'role': 'Finance', 'manager_id': 1}
    finance_id = NEXT_USER_ID # ID 4: Finance
    NEXT_USER_ID += 1

    USERS[NEXT_USER_ID] = {'id': NEXT_USER_ID, 'company_id': company_id, 'email': 'director@company.com', 'role': 'Director', 'manager_id': 1}
    # ID 5: Director
    NEXT_USER_ID += 1
    
    # --- Auto-Configure the Approval Flow for testing Step 4 logic ---
    APPROVAL_RULES[company_id] = {
        'steps': [
            {'step': 1, 'role': 'Manager', 'is_manager_approver': True}, # Manager (ID 2)
            {'step': 2, 'role': 'Finance'},                              # Finance (ID 4)
            {'step': 3, 'role': 'Director'}                              # Director (ID 5)
        ],
        # Conditional Rule: Auto-approve if Director approves (Test the "Specific approver rule")
        'conditional': {
            'type': 'Specific', 
            'required_role': 'Director',
            'threshold': 100 # Not used for 'Specific' type, but included for completeness
        }
    }
    
    print("\n--- Backend Initialization Complete ---")
    print(f"Company Currency: {COMPANIES[company_id]['currency']}")
    print(f"Employee (ID 3) reports to Manager (ID {manager_id})")
    print(f"Approval Flow: Manager -> Finance -> Director (Conditional: Director Approved = Auto-Approve)")
    print("-------------------------------------------\n")

    app.run(debug=True, port=5000)