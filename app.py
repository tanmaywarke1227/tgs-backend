"""
Term Grant Slip Digitalization System
Flask Backend — Production Ready
"""

from flask import Flask, request, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
import os
import json
from functools import wraps

# ── App Setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tgs-secret-key-change-in-production")

ALLOWED_ORIGINS = [
    "https://tgs-frontend-virid.vercel.app",
    "https://tgs-frontend-git-main-tanmay-warkes-projects.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
]

CORS(app, supports_credentials=True, origins=ALLOWED_ORIGINS,
     allow_headers=["Content-Type"], methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

@app.after_request
def after_request(response):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return response

# ── Firebase — LAZY init (never at startup) ───────────────────────────────────
_db = None

def get_db():
    global _db
    if _db is not None:
        return _db
    try:
        if not firebase_admin._apps:
            firebase_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
            service_account_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "serviceAccountKey.json")
            if firebase_json:
                service_account_info = json.loads(firebase_json)
                if "private_key" in service_account_info:
                    service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(service_account_info)
            elif os.path.exists(service_account_path):
                cred = credentials.Certificate(service_account_path)
            else:
                raise Exception("No Firebase credentials found!")
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
        print("Firebase connected")
        return _db
    except Exception as e:
        print(f"Firebase error: {e}")
        return None

# Email-to-UID map for fast direct document lookups (avoids slow collection scans)
EMAIL_TO_UID = {
    "rahul.sharma@student.edu": "student_001",
    "priya.patel@student.edu": "student_002",
    "arjun.singh@student.edu": "student_003",
    "amit.verma@college.edu": "faculty_001",
    "sneha.joshi@college.edu": "faculty_002",
    "rajesh.kumar@college.edu": "faculty_003",
    "priya.mehta@college.edu": "faculty_004",
    "admin@college.edu": "admin_001",
}

STUDENT_SUBJECTS = {
    "student_001": ["sub_001", "sub_002", "sub_003", "sub_004"],
    "student_002": ["sub_001", "sub_002", "sub_003", "sub_004"],
    "student_003": ["sub_001", "sub_002", "sub_003", "sub_004"],
}

FACULTY_STUDENTS = {
    "faculty_001": [("student_001","sub_001"),("student_002","sub_001"),("student_003","sub_001")],
    "faculty_002": [("student_001","sub_002"),("student_002","sub_002"),("student_003","sub_002")],
    "faculty_003": [("student_001","sub_003"),("student_002","sub_003"),("student_003","sub_003")],
    "faculty_004": [("student_001","sub_004"),("student_002","sub_004"),("student_003","sub_004")],
}

STUDENT_IDS = ["student_001", "student_002", "student_003"]
ALL_SUBJECT_IDS = ["sub_001", "sub_002", "sub_003", "sub_004"]

# ── Flask-Login ────────────────────────────────────────────────────────────────
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, uid, name, email, role):
        self.id = uid
        self.name = name
        self.email = email
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    try:
        database = get_db()
        if not database:
            return None
        doc = database.collection("users").document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            return User(data["uid"], data["name"], data["email"], data["role"])
    except Exception:
        pass
    return None

@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"error": "Authentication required"}), 401

# ── Role Decorator ─────────────────────────────────────────────────────────────
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Authentication required"}), 401
            if current_user.role not in roles:
                return jsonify({"error": "Access denied"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

# ── Email ──────────────────────────────────────────────────────────────────────
def send_email(to_email, subject, body_html):
    try:
        smtp_email = os.environ.get("SMTP_EMAIL", "")
        smtp_password = os.environ.get("SMTP_PASSWORD", "")
        if not smtp_email or not smtp_password:
            print("SMTP not configured. Skipping email.")
            return False
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Term Grant System <{smtp_email}>"
        msg["To"] = to_email
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def get_approval_email_body(student_name, subject_name, status, remark=""):
    color = "#22c55e" if status == "approved" else "#ef4444"
    status_text = "APPROVED" if status == "approved" else "REJECTED"
    remark_section = f"<p><b>Remark:</b> {remark}</p>" if remark else ""
    return f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
      <div style="background:#1e293b;padding:24px;border-radius:12px 12px 0 0;">
        <h2 style="color:white;margin:0;">Term Grant Slip Update</h2></div>
      <div style="background:#f8fafc;padding:24px;border-radius:0 0 12px 12px;border:1px solid #e2e8f0;">
        <p>Dear <b>{student_name}</b>,</p>
        <p>Your term grant slip for <b>{subject_name}</b> has been updated.</p>
        <div style="background:{color};color:white;padding:12px 20px;border-radius:8px;font-size:18px;font-weight:bold;display:inline-block;">{status_text}</div>
        {remark_section}
        <p style="margin-top:24px;">Log in to view all your approval statuses.</p>
      </div></body></html>"""

# ── Helper: update approval status ────────────────────────────────────────────
def _update_approval_status(approval_id, status, remark):
    database = get_db()
    if not database:
        return jsonify({"error": "Database unavailable"}), 503
    doc_ref = database.collection("approvals").document(approval_id)
    doc = doc_ref.get()
    if not doc.exists:
        return jsonify({"error": "Approval record not found"}), 404
    approval_data = doc.to_dict()
    doc_ref.update({
        "status": status,
        "remark": remark,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "emailNotified": False
    })
    notif_ref = database.collection("notifications").document()
    action = "approved" if status == "approved" else "rejected"
    notif_ref.set({
        "notifId": notif_ref.id,
        "userId": approval_data["studentId"],
        "message": f"{approval_data['facultyName']} {action} your term grant slip for {approval_data['subjectName']}.",
        "type": status,
        "read": False,
        "createdAt": datetime.now(timezone.utc).isoformat()
    })
    email_sent = send_email(
        to_email=approval_data["studentEmail"],
        subject=f"Term Grant Slip {status.title()} — {approval_data['subjectName']}",
        body_html=get_approval_email_body(approval_data["studentName"], approval_data["subjectName"], status, remark)
    )
    if email_sent:
        doc_ref.update({"emailNotified": True})
    return jsonify({
        "message": f"Student {status} successfully",
        "approvalId": approval_id,
        "status": status,
        "emailNotified": email_sent
    }), 200

# ── ROUTES ─────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "Term Grant Slip API", "version": "1.0.0"}), 200

# ── AUTH ───────────────────────────────────────────────────────────────────────

@app.route("/api/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    try:
        database = get_db()
        if not database:
            return jsonify({"error": "Database unavailable. Please try again in 30 seconds."}), 503
        uid = EMAIL_TO_UID.get(email)
        if not uid:
            return jsonify({"error": "Invalid email or password"}), 401
        doc = database.collection("users").document(uid).get()
        if not doc.exists:
            return jsonify({"error": "Invalid email or password"}), 401
        user_doc = doc.to_dict()
        if user_doc.get("password_hash") != password:
            return jsonify({"error": "Invalid email or password"}), 401
        user = User(user_doc["uid"], user_doc["name"], user_doc["email"], user_doc["role"])
        login_user(user)
        return jsonify({
            "message": "Login successful",
            "user": {
                "uid": user_doc["uid"],
                "name": user_doc["name"],
                "email": user_doc["email"],
                "role": user_doc["role"],
                "department": user_doc.get("department", ""),
                "rollNumber": user_doc.get("rollNumber", ""),
                "semester": user_doc.get("semester", ""),
            }
        }), 200
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route("/api/logout", methods=["POST"])
def logout():
    logout_user()
    return jsonify({"message": "Logged out successfully"}), 200

@app.route("/api/me", methods=["GET"])
@login_required
def get_current_user():
    try:
        database = get_db()
        doc = database.collection("users").document(current_user.id).get()
        if doc.exists:
            data = doc.to_dict()
            data.pop("password_hash", None)
            return jsonify(data), 200
        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── STUDENT ────────────────────────────────────────────────────────────────────

@app.route("/api/student/status", methods=["GET"])
@login_required
@role_required("student")
def get_student_status():
    try:
        database = get_db()
        if not database:
            return jsonify({"error": "Database unavailable"}), 503
        student_id = current_user.id
        subject_ids = STUDENT_SUBJECTS.get(student_id, ALL_SUBJECT_IDS)
        result = []
        for sid in subject_ids:
            doc = database.collection("approvals").document(f"{student_id}_{sid}").get()
            if doc.exists:
                data = doc.to_dict()
                result.append({
                    "approvalId": data["approvalId"],
                    "subjectId": data["subjectId"],
                    "subjectName": data["subjectName"],
                    "subjectCode": data["subjectCode"],
                    "facultyName": data["facultyName"],
                    "status": data["status"],
                    "remark": data.get("remark", ""),
                    "attendancePercentage": data.get("attendancePercentage", 0),
                    "updatedAt": data.get("updatedAt", ""),
                })
        total = len(result)
        approved = sum(1 for r in result if r["status"] == "approved")
        pending = sum(1 for r in result if r["status"] == "pending")
        rejected = sum(1 for r in result if r["status"] == "rejected")
        return jsonify({
            "approvals": result,
            "summary": {
                "total": total,
                "approved": approved,
                "pending": pending,
                "rejected": rejected,
                "allApproved": approved == total and total > 0
            }
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/student/subjects", methods=["GET"])
@login_required
@role_required("student")
def get_student_subjects():
    try:
        database = get_db()
        if not database:
            return jsonify({"error": "Database unavailable"}), 503
        subject_ids = STUDENT_SUBJECTS.get(current_user.id, ALL_SUBJECT_IDS)
        subjects = []
        for sid in subject_ids:
            sdoc = database.collection("subjects").document(sid).get()
            if sdoc.exists:
                subjects.append(sdoc.to_dict())
        return jsonify({"subjects": subjects}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/student/submissions", methods=["GET"])
@login_required
@role_required("student")
def get_student_submissions():
    # submissions collection not in use — return empty list gracefully
    return jsonify({"submissions": []}), 200

@app.route("/api/student/check-eligibility", methods=["GET"])
@login_required
@role_required("student")
def check_eligibility():
    try:
        database = get_db()
        if not database:
            return jsonify({"eligible": False, "message": "Database unavailable"}), 503
        student_id = current_user.id
        subject_ids = STUDENT_SUBJECTS.get(student_id, ALL_SUBJECT_IDS)
        if not subject_ids:
            return jsonify({"eligible": False, "message": "No subjects enrolled."}), 200
        all_approved = True
        for sid in subject_ids:
            doc = database.collection("approvals").document(f"{student_id}_{sid}").get()
            if not doc.exists or doc.to_dict().get("status") != "approved":
                all_approved = False
                break
        return jsonify({"eligible": all_approved}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── FACULTY ────────────────────────────────────────────────────────────────────

@app.route("/api/faculty/pending", methods=["GET"])
@login_required
@role_required("faculty")
def get_faculty_pending():
    try:
        database = get_db()
        if not database:
            return jsonify({"error": "Database unavailable"}), 503
        faculty_id = current_user.id
        pairs = FACULTY_STUDENTS.get(faculty_id, [])
        result = []
        for (student_id, subject_id) in pairs:
            doc = database.collection("approvals").document(f"{student_id}_{subject_id}").get()
            if doc.exists:
                data = doc.to_dict()
                result.append({
                    "approvalId": data["approvalId"],
                    "studentId": data["studentId"],
                    "studentName": data["studentName"],
                    "studentRoll": data["studentRoll"],
                    "subjectName": data["subjectName"],
                    "subjectCode": data["subjectCode"],
                    "status": data["status"],
                    "remark": data.get("remark", ""),
                    "attendancePercentage": data.get("attendancePercentage", 0),
                    "requestedAt": data.get("requestedAt", ""),
                })
        pending = [r for r in result if r["status"] == "pending"]
        approved = [r for r in result if r["status"] == "approved"]
        rejected = [r for r in result if r["status"] == "rejected"]
        return jsonify({
            "all": result, "pending": pending, "approved": approved, "rejected": rejected,
            "summary": {"total": len(result), "pending": len(pending),
                        "approved": len(approved), "rejected": len(rejected)}
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/faculty/approve", methods=["POST"])
@login_required
@role_required("faculty")
def approve_student():
    data = request.get_json()
    approval_id = data.get("approvalId")
    remark = data.get("remark", "")
    if not approval_id:
        return jsonify({"error": "approvalId is required"}), 400
    return _update_approval_status(approval_id, "approved", remark)

@app.route("/api/faculty/reject", methods=["POST"])
@login_required
@role_required("faculty")
def reject_student():
    data = request.get_json()
    approval_id = data.get("approvalId")
    remark = data.get("remark", "Attendance below required threshold.")
    if not approval_id:
        return jsonify({"error": "approvalId is required"}), 400
    return _update_approval_status(approval_id, "rejected", remark)

@app.route("/api/faculty/submissions", methods=["GET"])
@login_required
@role_required("faculty")
def get_faculty_submissions():
    return jsonify({"submissions": []}), 200

@app.route("/api/faculty/update-submission", methods=["PUT"])
@login_required
@role_required("faculty")
def update_submission():
    return jsonify({"message": "Not implemented"}), 200

@app.route("/api/faculty/verify-submission", methods=["POST"])
@login_required
@role_required("faculty")
def verify_submission():
    return jsonify({"message": "Not implemented"}), 200

# ── ADMIN ──────────────────────────────────────────────────────────────────────

@app.route("/api/admin/overview", methods=["GET"])
@login_required
@role_required("admin")
def admin_overview():
    try:
        database = get_db()
        if not database:
            return jsonify({"error": "Database unavailable"}), 503
        result = []
        for student_id in STUDENT_IDS:
            student_doc = database.collection("users").document(student_id).get()
            if not student_doc.exists:
                continue
            student = student_doc.to_dict()
            subject_ids = STUDENT_SUBJECTS.get(student_id, ALL_SUBJECT_IDS)
            approval_list = []
            for sid in subject_ids:
                adoc = database.collection("approvals").document(f"{student_id}_{sid}").get()
                if adoc.exists:
                    approval_list.append(adoc.to_dict())
            total = len(approval_list)
            approved = sum(1 for a in approval_list if a["status"] == "approved")
            rejected = sum(1 for a in approval_list if a["status"] == "rejected")
            pending = total - approved - rejected
            result.append({
                "uid": student["uid"],
                "name": student["name"],
                "rollNumber": student.get("rollNumber", ""),
                "email": student["email"],
                "semester": student.get("semester", ""),
                "totalSubjects": total,
                "approved": approved,
                "pending": pending,
                "rejected": rejected,
                "fullyApproved": approved == total and total > 0,
                "approvals": approval_list
            })
        return jsonify({"students": result, "total": len(result)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users", methods=["GET"])
@login_required
@role_required("admin")
def admin_users():
    try:
        database = get_db()
        if not database:
            return jsonify({"error": "Database unavailable"}), 503
        role = request.args.get("role")
        all_uids = list(EMAIL_TO_UID.values())
        users = []
        for uid in all_uids:
            doc = database.collection("users").document(uid).get()
            if doc.exists:
                data = doc.to_dict()
                if role and data.get("role") != role:
                    continue
                data.pop("password_hash", None)
                users.append(data)
        return jsonify({"users": users}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/approve-override", methods=["POST"])
@login_required
@role_required("admin")
def admin_override():
    data = request.get_json()
    approval_id = data.get("approvalId")
    status = data.get("status")
    remark = data.get("remark", "Admin override")
    if status not in ["approved", "rejected", "pending"]:
        return jsonify({"error": "Invalid status"}), 400
    return _update_approval_status(approval_id, status, remark)

# ── NOTIFICATIONS ──────────────────────────────────────────────────────────────

@app.route("/api/notifications", methods=["GET"])
@login_required
def get_notifications():
    try:
        database = get_db()
        if not database:
            return jsonify({"notifications": [], "unread": 0}), 200
        notifs = database.collection("notifications")\
            .where(filter=firestore.FieldFilter("userId", "==", current_user.id))\
            .limit(20).get()
        result = sorted([n.to_dict() for n in notifs],
                        key=lambda x: x.get("createdAt", ""), reverse=True)
        unread = sum(1 for n in result if not n.get("read", False))
        return jsonify({"notifications": result, "unread": unread}), 200
    except Exception as e:
        return jsonify({"notifications": [], "unread": 0}), 200

@app.route("/api/notifications/mark-read", methods=["POST"])
@login_required
def mark_notifications_read():
    try:
        database = get_db()
        if not database:
            return jsonify({"message": "ok"}), 200
        notifs = database.collection("notifications")\
            .where(filter=firestore.FieldFilter("userId", "==", current_user.id))\
            .where(filter=firestore.FieldFilter("read", "==", False)).get()
        for n in notifs:
            n.reference.update({"read": True})
        return jsonify({"message": "All notifications marked as read"}), 200
    except Exception as e:
        return jsonify({"message": "ok"}), 200

# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port,
            debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")