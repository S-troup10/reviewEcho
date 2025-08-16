import os
from dotenv import load_dotenv
from functools import wraps
from flask import (Flask, session, render_template, request, flash, redirect,
                   url_for, jsonify)

import stripe
import gunicorn
load_dotenv()

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from flask_dance.contrib.google import make_google_blueprint, google
import storage 

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")


# Stripe configuration
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

app.config.update(
    SESSION_COOKIE_SECURE=False,  # allow cookies over HTTP
    SESSION_COOKIE_SAMESITE='Lax',  # normal default
    SESSION_PERMANENT=True  # keep session persistent
)


# --- Session Config ---
@app.before_request
def make_session_permanent():
    session.permanent = True


# --- Auth Helpers ---
def is_authenticated():
    return session.get("logged_in", False)


def require_login(f):

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            flash("You must be logged in.", "error")
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)

    return wrapper




def require_subscription(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            flash("You must be logged in.", "error")
            return redirect(url_for("login_page"))

        user_id = session.get("user_id")

        # Check if subscription_status is already stored
        if 'subscription_status' not in session:
            session['subscription_status'] = storage.get_user_subscription_status(user_id)

        subscription_status = session['subscription_status']

        if not subscription_status.get('has_active_subscription'):
            flash("This feature requires an active subscription.", "error")
            return redirect(url_for("pricing"))

        return f(*args, **kwargs)

    return wrapper


def require_pro_subscription(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            flash("You must be logged in.", "error")
            return redirect(url_for("login_page"))

        user_id = session.get("user_id")

        # Check if subscription_status is already stored
        if 'subscription_status' not in session:
            session['subscription_status'] = storage.get_user_subscription_status(user_id)

        subscription_status = session['subscription_status']

        if not subscription_status.get('has_active_subscription'):
            flash("This feature requires an active subscription.", "error")
            return redirect(url_for("pricing"))

        if subscription_status.get('tier') != 'pro':
            flash("This feature requires a Pro subscription.", "error")
            return redirect(url_for("pricing"))

        return f(*args, **kwargs)

    return wrapper
 

#-- google --
google_bp = make_google_blueprint(
    client_id=os.environ.get("CLIENT_ID"),
    client_secret=os.environ.get("CLIENT_SECRET"),
    scope=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
    redirect_url="/login/google/success"  # Custom redirect after OAuth login
)
app.register_blueprint(google_bp, url_prefix="/auth")




@app.route("/privacy")
def privacy():
    return render_template("privacy.html")
    
@app.route("/terms")
def terms():
    return render_template("terms.html")
    

@app.route("/login/google/success")
def google_login_success():
    if not google.authorized:
        flash("Google login failed. Please try again.", "error")
        return redirect(url_for("login_page"))

    resp = google.get("/oauth2/v2/userinfo")
    if not resp.ok:
        flash("Failed to fetch user info from Google.", "error")
        return redirect(url_for("login_page"))

    user_info = resp.json()
    email = user_info.get("email")
    first = user_info.get("given_name", "")
    last = user_info.get("family_name", "")

    if not email:
        flash("Could not get email from Google account.", "error")
        return redirect(url_for("login_page"))

    # Replace this with your real user storage lookup
    existing_user = storage.fetch("users", {"email": email})
    if not existing_user:
        # Create new user in your DB
        result = storage.add(
            "users",
            {
                "first_name": first,
                "last_name": last,
                "business": "ReviewEcho User",
                "email": email,
                "password": "",  # OAuth users don’t need passwords
            })
        if not result.get("success"):
            flash("Error creating your account. Please try again.", "error")
            return redirect(url_for("login_page"))
        user_id = result["id"]
        # Create 7-day trial subscription
        storage.create_trial_subscription(user_id)
        session["show_welcome_demo"] = True
    else:
        user_id = existing_user[0]["id"]

    # Log user in
    session["logged_in"] = True
    session["user_id"] = user_id

    flash(f"Welcome {first}! You have been logged in with Google.", "success")
    return redirect(url_for("dashboard"))


# --- Routes ---
@app.route("/")
def index():

    if session.get("logged_in") == True:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/debug-session")
def debug_session():
    return {
        "session_keys": list(session.keys()),
        "google_oauth_token": session.get("google_oauth_token"),
        "logged_in": session.get("logged_in"),
        "user_id": session.get("user_id"),
    }

@app.route("/export", methods=["GET", "POST"])
@require_login
def export():
    if request.method == "POST":
        import pandas as pd
        from datetime import datetime
        from flask import Response
        import io

        data_type = request.form.get('data_type')
        format_type = request.form.get('format')

        if not data_type or not format_type:
            flash("Please select both data type and format.", "error")
            return render_template("export.html")

        user_id = session.get("user_id")

        try:
            # Get data based on selected type
            if data_type == "reviews":
                # Get business ID first
                business_settings = storage.fetch("business_settings", {"user_id": user_id})
                if not business_settings:
                    flash("No business settings found. Please configure your business first.", "error")
                    return render_template("export.html")

                business_id = business_settings[0]['id']
                reviews = storage.fetch("reviews", {"business_id": business_id})

                if not reviews:
                    flash("No reviews found to export.", "error")
                    return render_template("export.html")

                # Prepare reviews data
                data = []
                for review in reviews:
                    data.append({
                        'Customer Name': review.get('customer_name', ''),
                        'Customer Email': review.get('customer_email', ''),
                        'Rating': review.get('rating', ''),
                        'Review Text': review.get('review_text', ''),
                        'Review Type': review.get('review_type', ''),
                        'Date Created': review.get('created_at', '')
                    })
                filename = f"reviews_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            elif data_type == "customers":
                # Get business ID first
                business_settings = storage.fetch("business_settings", {"user_id": user_id})
                if not business_settings:
                    flash("No business settings found. Please configure your business first.", "error")
                    return render_template("export.html")

                business_id = business_settings[0]['id']
                customers = storage.fetch("customers", {"business_id": business_id})

                if not customers:
                    flash("No customers found to export.", "error")
                    return render_template("export.html")

                # Prepare customers data
                data = []
                for customer in customers:
                    data.append({
                        'Name': customer.get('name', ''),
                        'Email': customer.get('email', ''),
                        'Phone': customer.get('phone', ''),
                        'Date Added': customer.get('created_at', '')
                    })
                filename = f"customers_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            else:
                flash("Invalid data type selected.", "error")
                return render_template("export.html")

            # Create DataFrame
            df = pd.DataFrame(data)

            if format_type == "csv":
                # Generate CSV
                output = io.StringIO()
                df.to_csv(output, index=False)
                output.seek(0)

                return Response(
                    output.getvalue(),
                    mimetype="text/csv",
                    headers={"Content-disposition": f"attachment; filename={filename}.csv"}
                )

            elif format_type == "xlsx":
                # Generate Excel file
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Data')
                output.seek(0)

                return Response(
                    output.getvalue(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-disposition": f"attachment; filename={filename}.xlsx"}
                )

            elif format_type == "json":
                # Generate JSON
                json_output = df.to_json(orient='records', indent=2)

                return Response(
                    json_output,
                    mimetype="application/json",
                    headers={"Content-disposition": f"attachment; filename={filename}.json"}
                )

            else:
                flash("Invalid format selected.", "error")
                return render_template("export.html")

        except Exception as e:
            flash(f"Error generating export: {str(e)}", "error")
            return render_template("export.html")

    return render_template("export.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        first = request.form.get("first_name")
        last = request.form.get("last_name")
        business = request.form.get("business_name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not all([first, last, business, email, password, confirm_password]):
            flash("Please fill out all fields.", "error")
        elif password != confirm_password:
            flash("Passwords do not match.", "error")
        else:
            result = storage.add(
                "users", {
                    "first_name": first,
                    "last_name": last,
                    "business": business,
                    "email": email,
                    "password": password,
                })

            if result.get('success'):
                user_id = result["id"]
                # Create 7-day trial subscription
                storage.create_trial_subscription(user_id)
                
                # Log user in immediately and redirect to welcome demo
                session["logged_in"] = True
                session["user_id"] = user_id
                session["show_welcome_demo"] = True
                flash("Welcome! Your 7-day free trial has started.", "success")
                return redirect(url_for("dashboard"))
            else:
                flash(f"An error occurred: {result.get('error')}", "error")
                print("Signup error:", result.get('error'))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        success, user = storage.validate(email, password)
        if success:
            session.clear()
            session["logged_in"] = True
            session["user_id"] = user.get("id")
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials.", "error")
    return render_template("login.html")


@app.route("/dashboard")
@require_subscription
def dashboard():
    user_id = session.get("user_id")
    user_data = storage.fetch("users", {"id": user_id})
    if user_data and len(user_data) > 0:
        # Get business settings
        success, business_settings = storage.get_business_settings(user_id)
        if not success:
            business_settings = None

        # Get dashboard statistics
        stats = storage.get_dashboard_stats(user_id)
        recent_activity = storage.get_recent_activity(user_id)

        # Get AI summary with debugging
        print(f"Getting AI summary for user {user_id}")
        ai_summary = storage.get_ai_summary_for_dashboard(user_id)
        print(f"AI summary result: {ai_summary is not None}")
        if ai_summary:
            print(f"AI summary keys: {list(ai_summary.keys())}")

        # Check if we should show welcome demo
        show_welcome_demo = session.pop("show_welcome_demo", False)

        return render_template("dashboard.html",
                               current_user=user_data[0],
                               business_settings=business_settings,
                               stats=stats,
                               recent_activity=recent_activity,
                               ai_summary=ai_summary,
                               show_welcome_demo=show_welcome_demo)
    else:
        flash("User not found.", "error")
        return redirect(url_for("login_page"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/support", methods=["POST", "GET"])
def support() :
    if request.method == "POST" :
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get("message")

        data = {
            "name": name,
            "email" : email,
            "message" : message,
            "pending" : True
        }

        resp = storage.add("support_messages", data)

        if resp.get("success") == True:
            flash("Thank you, Your message has been received, and our support team will get back to you as soon as possible.")
            return render_template("support.html", complete=1)

        else :
            flash(f"an error occured, {resp.get("error")}")
            return render_template("support.html", complete=0)

    return render_template("support.html", complete=0)



@app.route("/admin")
def admin():
    
    if session.get("user_id", 0) != 1 :
        return redirect(url_for("index"))
    users = storage.fetch("users")
    messages = storage.fetch("support_messages", {"pending" : True})
    return render_template("admin.html", messages = messages, users=users)


@app.route("/business-settings", methods=["GET", "POST"])
@require_subscription
def business_settings():
    user_id = session.get("user_id")

    if request.method == "POST":
        business_name = request.form.get("business_name")
        google_review_link = request.form.get("google_review_link")

        if not all([business_name, google_review_link]):
            flash("Please fill out all fields.", "error")
        else:
            result = storage.save_business_settings(user_id, business_name,
                                                    google_review_link)
            if result.get('success'):
                flash("Business settings saved successfully!", "success")
                return redirect(url_for("dashboard"))
            else:
                flash(f"Error saving settings: {result.get('error')}", "error")

    # Get existing settings
    success, settings = storage.get_business_settings(user_id)
    if not success:
        flash("Error loading business settings.", "error")
        settings = None

    return render_template("business_settings.html", settings=settings)


@app.route("/review-form/<int:business_id>")
def review_form(business_id):
    # Get business info
    business_data = storage.fetch("business_settings", {"id": business_id})
    if not business_data:
        return render_template("403.html",
                               error_message="Business not found"), 404

    return render_template("review_form.html",
                           business=business_data[0],
                           hide=True)


@app.route("/submit-review/<int:business_id>", methods=["POST"])
def submit_review(business_id):
    customer_name = request.form.get("customer_name")
    customer_email = request.form.get("customer_email")
    rating = int(request.form.get("rating", 0))
    review_text = request.form.get("review_text")

    if not all([customer_name, customer_email, rating, review_text]):
        flash("Please fill out all fields.", "error")
        return redirect(url_for("review_form", business_id=business_id))

    if rating >= 4:
        # Save as public review and redirect to Google
        result = storage.save_review_submission(business_id, customer_name,
                                                customer_email, rating,
                                                review_text, 'public')
        if result.get('success'):
            # Get Google review link
            business_data = storage.fetch("business_settings",
                                          {"id": business_id})
            if business_data and business_data[0].get('google_review_link'):
                return render_template(
                    "redirect_to_google.html",
                    google_link=business_data[0]['google_review_link'],
                    business_name=business_data[0]['business_name'],
                    hide=True)
        flash("Thank you for your positive review!", "success")
        return redirect(url_for("review_form", business_id=business_id))
    else:
        # Redirect to private feedback form
        return redirect(
            url_for("private_feedback_form",
                    business_id=business_id,
                    customer_name=customer_name,
                    customer_email=customer_email,
                    rating=rating,
                    review_text=review_text))


@app.route("/private-feedback/<int:business_id>")
def private_feedback_form(business_id):
    # Get pre-filled data from URL params
    customer_name = request.args.get("customer_name", "")
    customer_email = request.args.get("customer_email", "")
    rating = request.args.get("rating", "")
    review_text = request.args.get("review_text", "")

    business_data = storage.fetch("business_settings", {"id": business_id})
    if not business_data:
        return render_template("403.html",
                               error_message="Business not found"), 404

    return render_template("private_feedback.html",
                           business=business_data[0],
                           customer_name=customer_name,
                           customer_email=customer_email,
                           rating=rating,
                           review_text=review_text,
                           hide=True)


@app.route("/submit-private-feedback/<int:business_id>", methods=["POST"])
def submit_private_feedback(business_id):
    customer_name = request.form.get("customer_name")
    customer_email = request.form.get("customer_email")
    rating = int(request.form.get("rating", 0))
    review_text = request.form.get("review_text")
    private_feedback = request.form.get("private_feedback", "")

    # Save as private feedback
    full_feedback = f"Original Review: {review_text}\n\nAdditional Feedback: {private_feedback}"

    result = storage.save_review_submission(business_id, customer_name,
                                            customer_email, rating,
                                            full_feedback, 'private')

    if result.get('success'):
        return render_template("feedback_thank_you.html", hide=True)
    else:
        flash("Error submitting feedback. Please try again.", "error")
        return redirect(
            url_for("private_feedback_form", business_id=business_id))


@app.route("/settings", methods=["GET", "POST"])
@require_login
def settings():
    user_id = session.get("user_id")

    if request.method == "POST":
        # Get form data
        settings_data = {
            "email_notifications":
            request.form.get("email_notifications") == "on",
            "push_notifications":
            request.form.get("push_notifications") == "on",
            "marketing_emails": request.form.get("marketing_emails") == "on"
        }

        # Save settings
        result = storage.save_user_settings(user_id, settings_data)
        if result.get('success'):
            flash("Settings saved successfully!", "success")
            return redirect(url_for("settings"))
        else:
            flash(f"Error saving settings: {result.get('error')}", "error")

    # Get current user data and settings
    user_data = storage.fetch("users", {"id": user_id})
    current_user = user_data[0] if user_data else None

    # Get user settings
    user_settings = storage.get_user_settings(user_id)

    return render_template("settings.html",
                           current_user=current_user,
                           settings=user_settings)


@app.route("/reviews")
@require_login
def view_reviews():
    user_id = session.get("user_id")
    reviews_result = storage.get_reviews_for_business(user_id)

    if reviews_result.get('success'):
        reviews = reviews_result.get('data', [])
        return render_template("view_reviews.html", reviews=reviews)
    else:
        flash("Error loading reviews.", "error")
        return redirect(url_for("dashboard"))





from datetime import datetime, timedelta, timezone

@app.route("/ai-review-summary")
@require_pro_subscription
def ai_review_summary():
    user_id = session.get("user_id")
    force_regenerate = request.args.get('regenerate') == 'true'

    now = datetime.now(timezone.utc)

    last_generated_str = session.get('last_report_generated_at')
    last_generated = None
    if last_generated_str:
        try:
            last_generated = datetime.fromisoformat(last_generated_str)
        except ValueError:
            last_generated = None

    elapsed = now - last_generated if last_generated else timedelta(minutes=9999)

    # If last generation was less than 5 minutes ago, redirect immediately
    if elapsed < timedelta(minutes=5):
        flash("You can only generate one report every 5 minutes. Please try again later.", "warning")
        return redirect(url_for("ai_reports_history"))

    # More than 5 minutes passed, generate fresh report if requested or cache if no regenerate param
    summary_result = storage.generate_ai_review_summary(user_id, force_regenerate)

    # If generation succeeded, update last generation time
    if summary_result.get('success'):
        session['last_report_generated_at'] = now.isoformat()

        summary_data = summary_result.get('data')
        is_cached = summary_result.get('cached', False)
        rep_id = summary_data.get('report_id') or summary_data.get('id')
        return render_template(
            "ai_review_summary.html",
            summary=summary_data,
            is_cached=is_cached,
            report_id=rep_id
        )
    else:
        flash(f"AI Analysis Error: {summary_result.get('error')}", "error")
        return redirect(url_for("view_reviews"))







@app.route("/ai-reports")
@require_pro_subscription
def ai_reports_history():
    user_id = session.get("user_id")
    reports_result = storage.get_ai_reports_history(user_id)

    if reports_result.get('success'):
        reports = reports_result.get('data', [])
        return render_template("ai_reports_history.html", reports=reports)
    else:
        flash("Error loading reports history.", "error")
        return redirect(url_for("dashboard"))


@app.route("/ai-report/<int:report_id>")
@require_pro_subscription
def view_ai_report(report_id):
    user_id = session.get("user_id")
    report_result = storage.get_ai_report_by_id(user_id, report_id)

    if report_result.get('success'):
        report = report_result.get('data')
        return render_template("ai_review_summary.html",
                               summary=report['report_data'],
                               is_cached=True,
                               is_historical=True,
                               report_date=report['generated_at'])
    else:
        flash("Report not found.", "error")
        return redirect(url_for("ai_reports_history"))


@app.route("/form-customization", methods=["GET", "POST"])
@require_login
def form_customization():
    user_id = session.get("user_id")

    if request.method == "POST":
        customization_data = {
            "primary_color": request.form.get("primary_color", "#3B82F6"),
            "secondary_color": request.form.get("secondary_color", "#8B5CF6"),
            "gradient_start_color": request.form.get("gradient_start_color", '#667eea'),
            "gradient_end_color": request.form.get("gradient_end_color", '#764ba2'),
            "welcome_message": request.form.get("welcome_message", ""),
            "logo_url": request.form.get("logo_url", ""),
            "background_style": request.form.get("background_style", "gradient"),
            "gradient_direction": request.form.get("gradient_direction", "135deg"),
            "gradient_angle": request.form.get("gradient_angle", "135")
        }


        result = storage.save_form_customization(user_id, customization_data)
        if result.get('success'):
            flash("Form customization saved successfully!", "success")
            return redirect(url_for("form_customization"))
        else:
            flash(f"Error saving customization: {result.get('error')}",
                  "error")

    # Get existing settings
    success, settings = storage.get_business_settings(user_id)
    if not success:
        flash("Error loading settings.", "error")
        settings = None

    # Color options
    color_options = [{
        'name': 'Blue',
        'value': '#3B82F6'
    }, {
        'name': 'Purple',
        'value': '#8B5CF6'
    }, {
        'name': 'Green',
        'value': '#059669'
    }, {
        'name': 'Red',
        'value': '#DC2626'
    }, {
        'name': 'Orange',
        'value': '#F59E0B'
    }, {
        'name': 'Pink',
        'value': '#EC4899'
    }, {
        'name': 'Teal',
        'value': '#0D9488'
    }, {
        'name': 'Indigo',
        'value': '#4F46E5'
    }, {
        'name': 'White',
        'value': '#FFFFFF'
    }, {
        'name': 'Black',
        'value': "#000000"
    }]

    background_styles = [{
        'name': 'Gradient',
        'value': 'gradient'
    }, {
        'name': 'Solid Color',
        'value': 'solid'
    }, {
        'name': 'Minimal White',
        'value': 'minimal'
    }, {
        'name': 'Dark Theme',
        'value': 'dark'
    }]

    return render_template("form_customization.html",
                           settings=settings,
                           colors=color_options,
                           background_styles=background_styles)


@app.route("/pricing")
def pricing():
    if not is_authenticated():
        return render_template("pricing.html", subscription_status=None)

    user_id = session.get("user_id")
    subscription_status = storage.get_user_subscription_status(user_id)
    return render_template("pricing.html",
                           subscription_status=subscription_status)






# Centralized price config (keep in code or load from env/DB)
PRICES = {
    "base": {"amount": 3400, "name": "Base Plan"},   # $34.00
    "pro":  {"amount": 4800, "name": "Pro Plan"},    # $48.00
}
CURRENCY = "usd"
BILLING_INTERVAL = "month"

# --- Routes ---

@app.route("/create-checkout-session", methods=["POST"])
@require_login
def create_checkout_session():
    tier = request.form.get("tier")
    if not tier:
        flash("Invalid plan selected.", "error")
        return redirect(url_for("pricing"))
    return redirect(url_for("subscribe", tier=tier))


@app.route("/subscribe/<tier>")
@require_login
def subscribe(tier):
    """Create a Checkout Session and mark a pending subscription in DB."""
    if not stripe.api_key:
        flash("Payment system not configured. Please contact support.", "error")
        return redirect(url_for("pricing"))

    user_id = session.get("user_id")
    user_data = storage.fetch("users", {"id": user_id})
    if not user_data:
        flash("User not found.", "error")
        return redirect(url_for("pricing"))
    user = user_data[0]

    if tier not in PRICES:
        flash("Invalid plan selected.", "error")
        return redirect(url_for("pricing"))

    try:
        # Create a Stripe Checkout Session for a MONTHLY subscription
        checkout_session = stripe.checkout.Session.create(
            customer_email=user["email"],
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{
                "price_data": {
                    "currency": CURRENCY,
                    "product_data": {
                        "name": PRICES[tier]["name"],
                        "description": f"{PRICES[tier]['name']} - Monthly Subscription",
                    },
                    "unit_amount": PRICES[tier]["amount"],
                    "recurring": {"interval": BILLING_INTERVAL},
                },
                "quantity": 1,
            }],
            success_url=request.host_url + "subscription-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "pricing",
            metadata={
                "user_id": str(user_id),
                "tier": tier,
                "business_name": user.get("business", "N/A"),
            },
            subscription_data={
                "metadata": {
                    "user_id": str(user_id),
                    "tier": tier,
                }
            },
        )

        # Mark "pending" so the dashboard can reflect immediate state
        try:
            storage.mark_pending_subscription(int(user_id), tier)
        except Exception as db_e:
            # Non-fatal; webhook is still the source of truth
            print(f"⚠️ Could not mark pending subscription for user {user_id}: {db_e}")

        print(f"📝 Created checkout session for user {user_id} with tier {tier}")
        return redirect(checkout_session.url)

    except Exception as e:
        print(f"❌ Stripe checkout error: {e}")
        flash("Error creating checkout session. Please try again.", "error")
        return redirect(url_for("pricing"))


@app.route("/subscription-success")
@require_login
def subscription_success():
    """Show confirmation after Stripe checkout — NO DB writes here."""
    session_id = request.args.get("session_id")
    if not session_id:
        flash("Invalid session.", "error")
        return redirect(url_for("pricing"))

    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        if checkout_session.mode != "subscription":
            flash("Invalid checkout session.", "error")
            return redirect(url_for("pricing"))
        flash("Thanks for subscribing! Your subscription is being activated — this may take a minute.", "success")
    except Exception as e:
        print(f"⚠️ Error retrieving checkout session: {e}")
        flash("Payment processed, activation pending. Please check your dashboard shortly.", "warning")

    return redirect(url_for("dashboard"))


@app.route("/manage-subscription")
@require_login
def manage_subscription():
    """Redirect to Stripe Customer Portal for subscription management."""
    return redirect(url_for("create_customer_portal"))


@app.route("/create-customer-portal", methods=["POST"])
@require_login
def create_customer_portal():
    """Create Stripe Customer Portal session (uses stored stripe_customer_id)."""
    user_id = session.get("user_id")
    subscription_info = storage.get_user_subscription_info(user_id)

    if not subscription_info or not subscription_info.get("stripe_customer_id"):
        flash("No active subscription found.", "error")
        return redirect(url_for("pricing"))

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=subscription_info["stripe_customer_id"],
            return_url=request.host_url + "pricing",
        )
        return redirect(portal_session.url)

    except Exception as e:
        print(f"❌ Error creating customer portal: {e}")
        flash("Unable to access subscription management. Please contact support.", "error")
        return redirect(url_for("pricing"))


# --- Stripe Webhook ---

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events. This is the SINGLE source of truth."""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    # Require a webhook secret in production
    if not STRIPE_WEBHOOK_SECRET:
        print("❌ STRIPE_WEBHOOK_SECRET is not set. Refusing webhook.")
        return jsonify({"error": "Webhook not configured"}), 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError as e:
        print(f"❌ Invalid Stripe signature: {e}")
        return jsonify({"error": "Invalid signature"}), 400
    except ValueError as e:
        print(f"❌ Invalid payload: {e}")
        return jsonify({"error": "Invalid payload"}), 400
    except Exception as e:
        print(f"❌ Webhook construct error: {e}")
        return jsonify({"error": "Webhook error"}), 400

    event_type = event["type"]
    obj = event["data"]["object"]
    print(f"🔔 Received Stripe webhook: {event_type}")

    try:
        if event_type == "customer.subscription.created":
            handle_subscription_created(obj)
        elif event_type == "customer.subscription.updated":
            handle_subscription_updated(obj)
        elif event_type == "customer.subscription.deleted":
            handle_subscription_deleted(obj)
        elif event_type == "invoice.payment_succeeded":
            handle_payment_succeeded(obj)
        elif event_type == "invoice.payment_failed":
            handle_payment_failed(obj)
        else:
            print(f"⚠️ Unhandled event type: {event_type}")
    except Exception as e:
        print(f"❌ Error handling {event_type}: {e}")

    return jsonify({"status": "success"}), 200


# --- Webhook Handlers ---

def handle_subscription_created(subscription):
    """Create/attach subscription on first creation. Idempotent."""
    try:
        stripe_subscription_id = subscription["id"]
        customer_id = subscription["customer"]
        status = subscription["status"]
        metadata = subscription.get("metadata", {})
        user_id = metadata.get("user_id")
        tier = metadata.get("tier", "base")

        if not user_id:
            print(f"⚠️ No user_id in subscription metadata: {stripe_subscription_id}")
            return

        # Idempotency: skip if we already have this subscription recorded
        try:
            existing = storage.get_subscription_by_stripe_id(stripe_subscription_id)
        except Exception as e:
            existing = None
            print(f"⚠️ DB check failed for {stripe_subscription_id}: {e}")

        if existing:
            print(f"ℹ️ Subscription {stripe_subscription_id} already exists, skipping insert")
            return

        # Promote "pending" to a real subscription (or create if pending missing)
        result = storage.handle_subscription_created(
            stripe_subscription_id=stripe_subscription_id,
            user_id=int(user_id),
            tier=tier,
            stripe_customer_id=customer_id
        )

        if result.get("success"):
            print(f"✅ DB updated for subscription creation: {stripe_subscription_id}")
        else:
            print(f"❌ DB update failed (created): {result.get('error')}")

    except Exception as e:
        print(f"❌ Error in handle_subscription_created: {e}")


def handle_subscription_updated(subscription):
    """Update status and metadata on any Stripe subscription changes."""
    try:
        stripe_subscription_id = subscription["id"]
        status = subscription["status"]

        result = storage.handle_subscription_updated(stripe_subscription_id, status)
        if result.get("success"):
            print(f"🔄 DB updated: {stripe_subscription_id} → {status}")
        else:
            print(f"❌ DB update failed (updated): {result.get('error')}")
    except Exception as e:
        print(f"❌ Error in handle_subscription_updated: {e}")


def handle_subscription_deleted(subscription):
    """Mark canceled in DB."""
    try:
        stripe_subscription_id = subscription["id"]

        result = storage.handle_subscription_cancelled(stripe_subscription_id)
        if result.get("success"):
            print(f"🗑️ DB updated: {stripe_subscription_id} canceled")
        else:
            print(f"❌ DB update failed (deleted): {result.get('error')}")
    except Exception as e:
        print(f"❌ Error in handle_subscription_deleted: {e}")


def handle_payment_succeeded(invoice):
    """Payment succeeded — mark paid and ensure active status."""
    try:
        subscription_id = invoice.get("subscription")
        if not subscription_id:
            print("ℹ️ invoice.payment_succeeded without subscription id")
            return

        result = storage.handle_payment_succeeded(subscription_id)
        if result.get("success"):
            print(f"💰 Payment success recorded for {subscription_id}")
        else:
            print(f"❌ DB update failed (payment_succeeded): {result.get('error')}")
    except Exception as e:
        print(f"❌ Error in handle_payment_succeeded: {e}")


def handle_payment_failed(invoice):
    """Payment failed — mark past_due or similar."""
    try:
        subscription_id = invoice.get("subscription")
        if not subscription_id:
            print("ℹ️ invoice.payment_failed without subscription id")
            return

        result = storage.handle_payment_failed(subscription_id)
        if result.get("success"):
            print(f"⚠️ Payment failure recorded for {subscription_id}")
        else:
            print(f"❌ DB update failed (payment_failed): {result.get('error')}")
    except Exception as e:
        print(f"❌ Error in handle_payment_failed: {e}")





@app.route("/customer-management")
@require_login
def customer_management():
    user_id = session.get("user_id")

    # Get business settings to find business_id
    business_settings = storage.fetch("business_settings", {"user_id": user_id})

    if not business_settings:
        flash("Please configure your business settings first.", "error")
        return redirect(url_for("business_settings"))

    business_id = business_settings[0].get('id')

    # Get customers for this business
    customers_result = storage.get_customers_for_business(business_id)
    customers = customers_result.get('data', []) if customers_result.get('success') else []

    # Get recent feedback requests
    feedback_requests = storage.get_recent_feedback_requests(business_id)

    return render_template("customer_management.html", 
                         customers=customers,
                         feedback_requests=feedback_requests,
                         business_id=business_id)


@app.route("/add-customer", methods=["POST"])
@require_login
def add_customer():
    user_id = session.get("user_id")
    business_id = storage.get_business_id(user_id)

    if not business_id:
        return {'success': False, 'error': 'Business not found'}, 400

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()

    # Validate required fields
    if not name:
        return {'success': False, 'error': 'Customer name is required'}, 400

    if not email and not phone:
        return {'success': False, 'error': 'Either email or phone is required'}, 400

    # Validate email format if provided
    if email and not storage.validate_email(email):
        return {'success': False, 'error': 'Invalid email format'}, 400

    # Validate phone format if provided
    if phone and not storage.validate_phone(phone):
        return {'success': False, 'error': 'Invalid phone format'}, 400

    # Add customer
    result = storage.add_customer(business_id, name, email, phone)

    if result.get('success'):
        return {'success': True, 'customer': result['data']}
    else:
        return {'success': False, 'error': result.get('error', 'Failed to add customer')}, 400


@app.route("/import-customers", methods=["POST"])
@require_login
def import_customers():
    user_id = session.get("user_id")
    business_id = storage.get_business_id(user_id)

    if not business_id:
        return {'success': False, 'error': 'Business not found'}, 400

    if 'csv_file' not in request.files:
        return {'success': False, 'error': 'No file uploaded'}, 400

    file = request.files['csv_file']
    if file.filename == '':
        return {'success': False, 'error': 'No file selected'}, 400

    # Get column mappings from form
    name_col = request.form.get('name_column')
    email_col = request.form.get('email_column') 
    phone_col = request.form.get('phone_column')

    if not name_col:
        return {'success': False, 'error': 'Name column mapping is required'}, 400

    # Process CSV file
    result = storage.import_customers_from_csv(business_id, file, name_col, email_col, phone_col)

    return result


@app.route("/send-feedback-requests", methods=["POST"])
@require_login
def send_feedback_requests():
    user_id = session.get("user_id")
    business_id = storage.get_business_id(user_id)

    if not business_id:
        return jsonify({'success': False, 'error': 'Business not found'}), 400

    customer_ids = request.form.getlist('customer_ids')
    method = request.form.get('method', 'both')  # Default to 'both' for automatic contact method selection
    custom_message = request.form.get('custom_message', '').strip()

    if not customer_ids:
        return jsonify({'success': False, 'error': 'No customers selected'}), 400

    # Always use 'both' method to send via all available contact methods
    method = 'both'

    # Send feedback requests
    result = storage.send_feedback_requests(business_id, customer_ids, method, custom_message)

    return jsonify(result)


@app.route("/customers/bulk", methods=["POST"])
@require_login
def bulk_add_customers():
    """Add multiple customers from JSON array"""
    try:
        customers_data = request.get_json()
        if not customers_data or not isinstance(customers_data, list):
            return jsonify({'success': False, 'error': 'Invalid data format'})

        user_id = session.get('user_id')
        
        # Get business_id from user_id
        business_id = storage.get_business_id(user_id)
        if not business_id:
            return jsonify({'success': False, 'error': 'Business not found. Please configure your business settings first.'})

        # Use the bulk_add_customers function from storage
        result = storage.bulk_add_customers(business_id, customers_data)
        
        if result.get('success'):
            return jsonify({'success': True, 'added': result.get('added', 0)})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error occurred')})

    except Exception as e:
        print(f"Error in bulk_add_customers: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'})


@app.route("/delete-customers", methods=["POST"])
@require_login
def delete_customers():
    user_id = session.get("user_id")
    business_id = storage.get_business_id(user_id)

    if not business_id:
        return {'success': False, 'error': 'Business not found'}, 400

    customer_ids = request.form.getlist('customer_ids')

    if not customer_ids:
        return {'success': False, 'error': 'No customers selected'}, 400

    result = storage.delete_customers(business_id, customer_ids)

    return result


@app.route("/poster/<int:business_id>")
def poster_generator(business_id):
    # Get business info
    business_data = storage.fetch("business_settings", {"id": business_id})
    if not business_data:
        return render_template("403.html",
                               error_message="Business not found"), 404

    # Define poster templates
    poster_templates = [{
        'id': 'modern',
        'name': 'Modern Minimalist',
        'description': 'Clean and professional design',
        'preview_color': '#3B82F6'
    }, {
        'id': 'gradient',
        'name': 'Gradient Style',
        'description': 'Eye-catching gradient background',
        'preview_color': '#8B5CF6'
    }, {
        'id': 'classic',
        'name': 'Classic Business',
        'description': 'Traditional and trustworthy',
        'preview_color': '#059669'
    }, {
        'id': 'vibrant',
        'name': 'Vibrant Colors',
        'description': 'Bold and attention-grabbing',
        'preview_color': '#DC2626'
    }, {
        'id': 'elegant',
        'name': 'Elegant Dark',
        'description': 'Sophisticated dark theme',
        'preview_color': '#1F2937'
    }, {
        'id': 'warm',
        'name': 'Warm & Friendly',
        'description': 'Inviting orange tones',
        'preview_color': '#F59E0B'
    }]

    # Color options
    color_options = [{
        'name': 'Blue',
        'value': '#3B82F6'
    }, {
        'name': 'Purple',
        'value': '#8B5CF6'
    }, {
        'name': 'Green',
        'value': '#059669'
    }, {
        'name': 'Red',
        'value': '#DC2626'
    }, {
        'name': 'Orange',
        'value': '#F59E0B'
    }, {
        'name': 'Pink',
        'value': '#EC4899'
    }, {
        'name': 'Teal',
        'value': '#0D9488'
    }, {
        'name': 'Indigo',
        'value': '#4F46E5'
    }]

    return render_template(
        "poster_generator.html",
        business=business_data[0],
        templates=poster_templates,
        colors=color_options,
    )


# --- Error Handlers ---
@app.errorhandler(404)
def not_found(error):
    return render_template("403.html", error_message="Page not found"), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("403.html",
                           error_message="Internal server error"), 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
