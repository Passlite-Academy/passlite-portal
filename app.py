from datetime import datetime, timedelta
import os
import sqlite3
import requests
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "passlite_secure_key"
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

import os 
# Securely load the Paystack Secret Key from environment variables
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY")

def init_db():
  conn = sqlite3.connect("schools.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS schools (
            school_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            paid_status INTEGER DEFAULT 0,
            expiry_date TEXT NOT NULL
        )
    """)
  conn.commit()
  conn.close()


init_db()


@app.route("/", methods=["GET"])
def home():
  return render_template("index.html")


@app.route("/initialize_payment", methods=["POST"])
def initialize_payment():
  school_id = request.form.get("school_id").strip().lower().replace(" ", "_")
  plan_type = request.form.get("plan_type")

  if not school_id:
    flash("Please enter a valid School ID.")
    return redirect(url_for("home"))

  # Set amount in kobo: ₦20,000 = 2000000 kobo, ₦25,000 = 2500000 kobo
  if plan_type == "junior":
    amount = 2000000
  else:
    amount = 2500000

  session["school_id"] = school_id
  session["school_name"] = school_id.replace("_", " ").title()
  session["section_type"] = plan_type

  # Initialize transaction with Paystack API
  url = "https://api.paystack.co/transaction/initialize"
  headers = {
      "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
      "Content-Type": "application/json",
  }
  data = {
      "email": f"{school_id}@passliteacademy.com",
      "amount": amount,
      "callback_url": url_for("payment_callback", _external=True),
      "metadata": {"school_id": school_id, "plan": plan_type},
  }

  try:
    response = requests.post(url, json=data, headers=headers, timeout=15)
    res_data = response.json()
  except Exception as e:
    return (
        f"Connection Error communicating with Paystack: {e}. Please check your"
        " internet connection."
    )

  if res_data.get("status"):
    auth_url = res_data["data"]["authorization_url"]
    return redirect(auth_url)
  else:
    # This will show you the exact error from Paystack if your key or setup has an issue
    error_message = res_data.get(
        "message", "Unknown error initializing payment."
    )
    return (
        f"<h3 style='color:red;'>Paystack Error: {error_message}</h3><p>Please"
        " check your Paystack Secret Key in app.py.</p><a"
        " href='/'>Back</a>"
    )


@app.route("/payment_callback")
def payment_callback():
  reference = request.args.get("reference")

  url = f"https://api.paystack.co/transaction/verify/{reference}"
  headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
  response = requests.get(url, headers=headers)
  res_data = response.json()

  if res_data.get("status") and res_data["data"]["status"] == "success":
    metadata = res_data["data"]["metadata"]
    school_id = metadata["school_id"]
    plan_type = metadata["plan"]

    expiry_date = (datetime.now() + timedelta(days=120)).strftime("%Y-%m-%d")

    conn = sqlite3.connect("schools.db")
    cursor = conn.cursor()
    cursor.execute(
        """
            INSERT INTO schools (school_id, name, paid_status, expiry_date) 
            VALUES (?, ?, 1, ?)
            ON CONFLICT(school_id) 
            DO UPDATE SET paid_status=1, expiry_date=?
        """,
        (
            school_id,
            school_id.replace("_", " ").title(),
            expiry_date,
            expiry_date,
        ),
    )
    conn.commit()
    conn.close()

    session["school_id"] = school_id
    session["section_type"] = plan_type
    session["paid_status"] = 1
    return redirect(url_for("dashboard"))
  else:
    flash("Payment was not successful. Access denied.")
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
  school_id = session.get("school_id")
  if not school_id:
    return redirect(url_for("home"))

  if session.get("paid_status") != 1:
    conn = sqlite3.connect("schools.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT paid_status, expiry_date FROM schools WHERE school_id = ?",
        (school_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row or row[0] == 0:
      return redirect(url_for("home"))

  section_type = session.get("section_type", "senior")
  return render_template(
      "portal.html",
      school={"name": session.get("school_name")},
      section_type=section_type,
  )


def calculate_grade(score):
  if score >= 75:
    return "A1", "Excellent"
  elif score >= 70:
    return "B2", "Very Good"
  elif score >= 65:
    return "B3", "Good"
  elif score >= 60:
    return "C4", "Credit"
  elif score >= 55:
    return "C5", "Credit"
  elif score >= 50:
    return "C6", "Average"
  elif score >= 45:
    return "D7", "Fair"
  elif score >= 40:
    return "E8", "Pass"
  else:
    return "F9", "Fail"


@app.route("/generate_report", methods=["POST"])
def generate_report():
  school_name = request.form.get("custom_school_name", "").upper()
  school_address = request.form.get("school_address")
  school_motto = request.form.get("school_motto")
  school_phone = request.form.get("school_phone")
  school_email = request.form.get("school_email")
  section_type = request.form.get("section_type", "senior")

  logo_filename = None
  if "school_logo" in request.files:
    file = request.files["school_logo"]
    if file and file.filename != "":
      filename = secure_filename(file.filename)
      file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
      logo_filename = filename

  student_name = request.form.get("student_name")
  student_id = request.form.get("student_id")
  student_class = request.form.get("student_class")
  department = request.form.get("department")
  no_in_class = request.form.get("no_in_class")
  dos = request.form.get("dos")
  attendance = request.form.get("attendance")
  absent = request.form.get("absent")

  psychos = {
      "Creative": request.form.get("psy_creative"),
      "Verbal Fluency": request.form.get("psy_verbal"),
      "Games": request.form.get("psy_games"),
      "Sports": request.form.get("psy_sports"),
      "Handling tools": request.form.get("psy_tools"),
      "Drawing & Painting": request.form.get("psy_draw"),
      "Music Skills": request.form.get("psy_music"),
  }
  award_won = request.form.get("award_won")

  traits = {
      "Punctuality": request.form.get("trait_punct"),
      "Neatness": request.form.get("trait_neat"),
      "Politeness": request.form.get("trait_polite"),
      "Honesty": request.form.get("trait_honesty"),
      "Relationship with others": request.form.get("trait_rel"),
      "Leadership": request.form.get("trait_lead"),
      "Emotional Stability": request.form.get("trait_emo"),
      "Attitude to school": request.form.get("trait_att"),
      "Attentiveness": request.form.get("trait_attn"),
      "Perseverance": request.form.get("trait_pers"),
  }

  bill_debt = int(float(request.form.get("bill_debt") or 0))
  bill_fees = int(float(request.form.get("bill_fees") or 0))
  bill_computer = int(float(request.form.get("bill_computer") or 0))
  bill_lessons = int(float(request.form.get("bill_lessons") or 0))
  bill_utility = int(float(request.form.get("bill_utility") or 0))
  total_bill = bill_debt + bill_fees + bill_computer + bill_lessons + bill_utility

  vacation_date = request.form.get("vacation_date")
  resumption_date = request.form.get("resumption_date")
  class_teacher_comment = request.form.get("class_teacher_comment")
  head_teacher_comment = request.form.get("head_teacher_comment")

  if section_type == "junior":
    custom_1 = request.form.get("add_sub_1_name", "").strip()
    custom_2 = request.form.get("add_sub_2_name", "").strip()
    custom_3 = request.form.get("add_sub_3_name", "").strip()

    raw_subjects = [
        ("Mathematics", "math"),
        ("English Language", "english"),
        ("Literature in English", "lit_english"),
        ("Basic Science", "basic_science"),
        ("Basic Technology", "basic_tech"),
        ("Home Economics", "home_eco"),
        ("Agric Science", "agric"),
        ("Social Studies", "social_studies"),
        ("Business Studies", "business_studies"),
        ("Civic Education", "civic"),
        ("Computer / ICT", "ict"),
        ("I R S", "irs"),
        ("C R S", "crs"),
        ("C C A", "cca"),
        ("Music", "music"),
        ("Yoruba", "yoruba"),
        (custom_1 if custom_1 else "Additional Subject 1", "add_sub_1"),
        (custom_2 if custom_2 else "Additional Subject 2", "add_sub_2"),
        (custom_3 if custom_3 else "Additional Subject 3", "add_sub_3"),
    ]
  else:
    raw_subjects = [
        ("English Language", "english"),
        ("Lit-in-English", "lit_english"),
        ("Mathematics", "math"),
        ("Physics", "physics"),
        ("Chemistry", "chemistry"),
        ("Biology", "biology"),
        ("Agric Science", "agric"),
        ("Geography", "geography"),
        ("Account", "account"),
        ("Commerce", "commerce"),
        ("Further maths", "further_maths"),
        ("Economics", "economics"),
        ("Marketing", "marketing"),
        ("Government", "government"),
        ("ICT", "ict"),
        ("Data Processing", "data_processing"),
        ("Civic Education", "civic"),
        ("Yoruba", "yoruba"),
        ("C R S", "crs"),
        ("Music", "music"),
    ]

  active_subjects = []
  total_obtained_marks = 0
  max_possible_marks = 0

  for name, key in raw_subjects:
    test_v = request.form.get(f"{key}_test")
    exam_v = request.form.get(f"{key}_exam")
    cumm_v = request.form.get(f"{key}_cumm")
    pos_v = request.form.get(f"{key}_pos")

    if test_v != "" or exam_v != "":
      test = int(float(test_v)) if test_v != "" else 0
      exam = int(float(exam_v)) if exam_v != "" else 0
      total = test + exam
      cumm = int(float(cumm_v)) if cumm_v != "" else "-"
      position = pos_v if pos_v != "" else "-"

      grade, remark = calculate_grade(total)
      active_subjects.append({
          "name": name,
          "test": test,
          "exam": exam,
          "total": total,
          "cumm": cumm,
          "position": position,
          "grade": grade,
          "remark": remark,
      })
      total_obtained_marks += total
      max_possible_marks += 100

  percentage = (
      round((total_obtained_marks / max_possible_marks) * 100)
      if max_possible_marks > 0
      else 0
  )
  overall_grade, _ = calculate_grade(percentage)

  return render_template(
      "report_card.html",
      school_name=school_name,
      school_address=school_address,
      school_motto=school_motto,
      school_phone=school_phone,
      school_email=school_email,
      logo_filename=logo_filename,
      student_name=student_name,
      student_id=student_id,
      student_class=student_class,
      department=department,
      no_in_class=no_in_class,
      dos=dos,
      attendance=attendance,
      absent=absent,
      active_subjects=active_subjects,
      total_obtained_marks=int(total_obtained_marks),
      max_possible_marks=int(max_possible_marks),
      percentage=percentage,
      overall_grade=overall_grade,
      psychos=psychos,
      award_won=award_won,
      traits=traits,
      bill_debt=bill_debt,
      bill_fees=bill_fees,
      bill_computer=bill_computer,
      bill_lessons=bill_lessons,
      bill_utility=bill_utility,
      total_bill=total_bill,
      vacation_date=vacation_date,
      resumption_date=resumption_date,
      class_teacher_comment=class_teacher_comment,
      head_teacher_comment=head_teacher_comment,
  )


if __name__ == "__main__":
  app.run(debug=True)
