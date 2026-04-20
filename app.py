"""
Term Grant Slip Digitalization System
Flask Backend — Main Application

WEEK 6: Backend API Development
WEEK 9: Full workflow
WEEK 10: Email notifications
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
from functools import wraps

# ── App Setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tgs-secret-key-change-in-production")

CORS(app, supports_credentials=True, origins=[
    "http://localhost:5173",
    "http://localhost:5000",
    os.environ.get("FRONTEND_URL", "https://tgs-frontend-git-main-tanmay-warkes-projects.vercel.app/")
])

# ── Firebase Setup ─────────────────────────────────────────────────────────────
def init_firebase():
    if not firebase_admin._apps:
        # In production, use environment variable for service account JSON
        service_account_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "serviceAccountKey.json")
        if os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
        else:
            # For Render deployment — use environment variable
            import json
            service_account_info = json.loads(os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "{}"))
            cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_firebase()

# ── Flask-Login Setup ─────────────────────────────────────────────────────────
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
        doc = db.collection("users").document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            return User(data["uid"], data["name"], data["email"], data["role"])
    except Exception:
        pass
    return None

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

# ── Email Helper ──────────────────────────────────────────────────────────────
def send_email(to_email, subject, body_html):
    """Send email via SMTP (Gmail)"""
    try:
        smtp_email = os.environ.get("SMTP_EMAIL", "")
        smtp_password = os.environ.get("SMTP_PASSWORD", "")

        if not smtp_email or not smtp_password:
            print("⚠️  SMTP credentials not configured. Skipping email.")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Term Grant System <{smtp_email}>"
        msg["To"] = to_email

        part = MIMEText(body_html, "html")
        msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())

        print(f"✅ Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False

def get_approval_email_body(student_name, subject_name, status, remark=""):
    color = "#22c55e" if status == "approved" else "#ef4444"
    status_text = "APPROVED ✅" if status == "approved" else "REJECTED ❌"
    remark_section = f"<p><b>Remark:</b> {remark}</p>" if remark else ""

    return f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
      <div style="background: #1e293b; padding: 24px; border-radius: 12px 12px 0 0;">
        <h2 style="color: white; margin: 0;">Term Grant Slip Update</h2>
      </div>
      <div style="background: #f8fafc; padding: 24px; border-radius: 0 0 12px 12px; border: 1px solid #e2e8f0;">
        <p>Dear <b>{student_name}</b>,</p>
        <p>Your term grant slip request for <b>{subject_name}</b> has been updated.</p>
        <div style="background: {color}; color: white; padding: 12px 20px; border-radius: 8px; display: inline-block; font-size: 18px; font-weight: bold;">
          {status_text}
        </div>
        {remark_section}
        <p style="margin-top: 24px;">Please log in to your dashboard to view the complete status of all your approvals.</p>
        <p style="color: #64748b; font-size: 12px;">This is an automated notification from the Term Grant Slip System.</p>
      </div>
    </body></html>
    """

# ─────────────────────────────────────────────────────────────────────────────
# WEEK 6 — API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

# ── AUTH ENDPOINTS ────────────────────────────────────────────────────────────

@app.route("/api/login", methods=["POST"])
def login():
    """Login API for all roles"""
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    # Find user by email
    users_ref = db.collection("users").where("email", "==", email).limit(1).get()

    if not users_ref:
        return jsonify({"error": "Invalid email or password"}), 401

    user_doc = users_ref[0].to_dict()

    # Simple password check (in production, use bcrypt)
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


@app.route("/api/logout", methods=["POST"])
@login_required
def logout():
    """Logout current user"""
    logout_user()
    return jsonify({"message": "Logged out successfully"}), 200


@app.route("/api/me", methods=["GET"])
@login_required
def get_current_user():
    """Get current logged-in user info"""
    doc = db.collection("users").document(current_user.id).get()
    if doc.exists:
        data = doc.to_dict()
        data.pop("password_hash", None)  # Never send password
        return jsonify(data), 200
    return jsonify({"error": "User not found"}), 404


# ── STUDENT ENDPOINTS ─────────────────────────────────────────────────────────

@app.route("/api/student/status", methods=["GET"])
@login_required
@role_required("student")
def get_student_status():
    """Get all approval statuses for the logged-in student"""
    student_id = current_user.id

    approvals = db.collection("approvals")\
        .where("studentId", "==", student_id)\
        .get()

    result = []
    for doc in approvals:
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

    # Summary counts
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


@app.route("/api/student/subjects", methods=["GET"])
@login_required
@role_required("student")
def get_student_subjects():
    """Get subjects enrolled for the logged-in student"""
    student_doc = db.collection("users").document(current_user.id).get()
    if not student_doc.exists:
        return jsonify({"error": "Student not found"}), 404

    student_data = student_doc.to_dict()
    subject_ids = student_data.get("subjects", [])

    subjects = []
    for sid in subject_ids:
        sdoc = db.collection("subjects").document(sid).get()
        if sdoc.exists:
            subjects.append(sdoc.to_dict())

    return jsonify({"subjects": subjects}), 200


@app.route("/api/student/submissions", methods=["GET"])
@login_required
@role_required("student")
def get_student_submissions():
    """Get all submission statuses for the logged-in student"""
    student_id = current_user.id
    submissions = db.collection("submissions").where("studentId", "==", student_id).get()
    
    result = []
    for doc in submissions:
        result.append(doc.to_dict())
        
    return jsonify({"submissions": result}), 200


@app.route("/api/student/check-eligibility", methods=["GET"])
@login_required
@role_required("student")
def check_eligibility():
    """Check if all subjects are verified to unlock certificate/hall ticket"""
    student_id = current_user.id
    
    student_doc = db.collection("users").document(student_id).get()
    if not student_doc.exists:
        return jsonify({"error": "Student not found"}), 404
        
    student_data = student_doc.to_dict()
    subject_ids = student_data.get("subjects", [])
    
    if not subject_ids:
        return jsonify({"eligible": False, "message": "No subjects enrolled."}), 200
        
    submissions = db.collection("submissions").where("studentId", "==", student_id).get()
    verified_subjects = set()
    for doc in submissions:
        data = doc.to_dict()
        if data.get("is_verified", False):
            verified_subjects.add(data.get("subjectId"))
            
    is_eligible = len(subject_ids) > 0 and all(sid in verified_subjects for sid in subject_ids)
    
    return jsonify({"eligible": is_eligible}), 200


# ── FACULTY ENDPOINTS ─────────────────────────────────────────────────────────

@app.route("/api/faculty/pending", methods=["GET"])
@login_required
@role_required("faculty")
def get_faculty_pending():
    """Get all pending approval requests for this faculty"""
    faculty_id = current_user.id

    approvals = db.collection("approvals")\
        .where("facultyId", "==", faculty_id)\
        .get()

    result = []
    for doc in approvals:
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
        "all": result,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "summary": {
            "total": len(result),
            "pending": len(pending),
            "approved": len(approved),
            "rejected": len(rejected),
        }
    }), 200


@app.route("/api/faculty/approve", methods=["POST"])
@login_required
@role_required("faculty")
def approve_student():
    """Approve a student's term grant slip"""
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
    """Reject a student's term grant slip"""
    data = request.get_json()
    approval_id = data.get("approvalId")
    remark = data.get("remark", "Attendance below required threshold.")

    if not approval_id:
        return jsonify({"error": "approvalId is required"}), 400

    return _update_approval_status(approval_id, "rejected", remark)


def _update_approval_status(approval_id, status, remark):
    """Helper: update approval status and send email"""
    doc_ref = db.collection("approvals").document(approval_id)
    doc = doc_ref.get()

    if not doc.exists:
        return jsonify({"error": "Approval record not found"}), 404

    approval_data = doc.to_dict()

    # Update Firestore
    doc_ref.update({
        "status": status,
        "remark": remark,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "emailNotified": False
    })

    # Add notification
    notif_ref = db.collection("notifications").document()
    action = "approved" if status == "approved" else "rejected"
    notif_ref.set({
        "notifId": notif_ref.id,
        "userId": approval_data["studentId"],
        "message": f"{approval_data['facultyName']} {action} your term grant slip for {approval_data['subjectName']}.",
        "type": status,
        "read": False,
        "createdAt": datetime.now(timezone.utc).isoformat()
    })

    # Send email notification (WEEK 10)
    email_sent = send_email(
        to_email=approval_data["studentEmail"],
        subject=f"Term Grant Slip {status.title()} — {approval_data['subjectName']}",
        body_html=get_approval_email_body(
            approval_data["studentName"],
            approval_data["subjectName"],
            status,
            remark
        )
    )

    if email_sent:
        doc_ref.update({"emailNotified": True})

    return jsonify({
        "message": f"Student {status} successfully",
        "approvalId": approval_id,
        "status": status,
        "emailNotified": email_sent
    }), 200


@app.route("/api/faculty/submissions", methods=["GET"])
@login_required
@role_required("faculty")
def get_faculty_submissions():
    """Get assignments submission statuses of students for this faculty's subjects"""
    faculty_id = current_user.id
    
    submissions = db.collection("submissions").where("facultyId", "==", faculty_id).get()
    result = [doc.to_dict() for doc in submissions]
    
    return jsonify({"submissions": result}), 200


@app.route("/api/faculty/update-submission", methods=["PUT"])
@login_required
@role_required("faculty")
def update_submission():
    """Update checkbox values for a submission"""
    data = request.get_json()
    submission_id = data.get("submissionId")
    if not submission_id:
        return jsonify({"error": "submissionId is required"}), 400
        
    # which fields they are trying to update
    updates = {}
    for key in ["ta1", "ta2", "repeat_ta", "assignment1", "assignment2", "assignment3"]:
        if key in data:
            updates[key] = data[key]
            
    if not updates:
        return jsonify({"message": "No updates provided"}), 200
        
    doc_ref = db.collection("submissions").document(submission_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        return jsonify({"error": "Submission not found"}), 404
        
    if doc.to_dict().get("is_verified", False):
        return jsonify({"error": "Cannot edit verified submissions"}), 400
        
    updates["timestamp"] = datetime.now(timezone.utc).isoformat()
    doc_ref.update(updates)
    
    return jsonify({"message": "Updated successfully"}), 200


@app.route("/api/faculty/verify-submission", methods=["POST"])
@login_required
@role_required("faculty")
def verify_submission():
    """Verify a submission if all required components are true"""
    data = request.get_json()
    submission_id = data.get("submissionId")
    
    if not submission_id:
        return jsonify({"error": "submissionId is required"}), 400
        
    doc_ref = db.collection("submissions").document(submission_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        return jsonify({"error": "Submission not found"}), 404
        
    submission_data = doc.to_dict()
    # Check if ta1, ta2, and all assignments are true
    ta1 = submission_data.get("ta1", False)
    ta2 = submission_data.get("ta2", False)
    ass1 = submission_data.get("assignment1", False)
    ass2 = submission_data.get("assignment2", False)
    ass3 = submission_data.get("assignment3", False)
    
    if not (ta1 and ta2 and ass1 and ass2 and ass3):
        return jsonify({"error": "All TA and Assignments must be completed before verification"}), 400
        
    doc_ref.update({
        "is_verified": True,
        "verified_by": current_user.name,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    return jsonify({"message": "Submission verified successfully!"}), 200


# ── ADMIN ENDPOINTS ───────────────────────────────────────────────────────────

@app.route("/api/admin/overview", methods=["GET"])
@login_required
@role_required("admin")
def admin_overview():
    """Admin: full overview of all students and approval status"""
    students = db.collection("users").where("role", "==", "student").get()
    result = []

    for student_doc in students:
        student = student_doc.to_dict()
        approvals = db.collection("approvals")\
            .where("studentId", "==", student["uid"])\
            .get()

        approval_list = [a.to_dict() for a in approvals]
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


@app.route("/api/admin/users", methods=["GET"])
@login_required
@role_required("admin")
def admin_users():
    """Admin: get all users"""
    role = request.args.get("role")
    query = db.collection("users")
    if role:
        query = query.where("role", "==", role)

    users = []
    for doc in query.get():
        data = doc.to_dict()
        data.pop("password_hash", None)
        users.append(data)

    return jsonify({"users": users}), 200


@app.route("/api/admin/approve-override", methods=["POST"])
@login_required
@role_required("admin")
def admin_override():
    """Admin: override approval status"""
    data = request.get_json()
    approval_id = data.get("approvalId")
    status = data.get("status")
    remark = data.get("remark", "Admin override")

    if status not in ["approved", "rejected", "pending"]:
        return jsonify({"error": "Invalid status"}), 400

    return _update_approval_status(approval_id, status, remark)


# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────

@app.route("/api/notifications", methods=["GET"])
@login_required
def get_notifications():
    """Get notifications for current user"""
    notifs = db.collection("notifications")\
        .where("userId", "==", current_user.id)\
        .order_by("createdAt", direction=firestore.Query.DESCENDING)\
        .limit(20)\
        .get()

    result = [n.to_dict() for n in notifs]
    unread = sum(1 for n in result if not n.get("read", False))

    return jsonify({"notifications": result, "unread": unread}), 200


@app.route("/api/notifications/mark-read", methods=["POST"])
@login_required
def mark_notifications_read():
    """Mark all notifications as read"""
    notifs = db.collection("notifications")\
        .where("userId", "==", current_user.id)\
        .where("read", "==", False)\
        .get()

    for n in notifs:
        n.reference.update({"read": True})

    return jsonify({"message": "All notifications marked as read"}), 200


# ── HEALTH CHECK ──────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "Term Grant Slip API",
        "version": "1.0.0"
    }), 200


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
