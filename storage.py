from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import os
import openai


# Replace with your real values
SUPABASE_URL = "https://gmpxcungtwhjrhygqvdk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdtcHhjdW5ndHdoanJoeWdxdmRrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQyODQ1NjIsImV4cCI6MjA2OTg2MDU2Mn0.T6FLVh783wgB0Sq6uAY1JHTjpYpkx0Wy7zVapxwA-zE"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize OpenAI client
openai.api_key = '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'


def add(table, data):
    try:
        response = supabase.table(table).insert(data).execute()
        inserted_id = response.data[0]['id'] if response.data else None
        return {'success': True, 'id': inserted_id}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def fetch(table, filters=None, multi_filters=None, gte_filters=None):
    try:
        query = supabase.table(table).select('*')
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        if multi_filters:
            for key, value_list in multi_filters.items():
                query = query.in_(key, value_list)
        if gte_filters:
            for key, value in gte_filters.items():
                query = query.gte(key, value)
        return query.execute().data
    except Exception as e:
        print("Error in fetch:", e)
        return None


def validate(email, password):
    try:
        result = fetch("users", filters={"email": email, "password": password})
        if result and len(result) == 1:
            return True, result[0]
        return False, None
    except Exception as e:
        print("Login error:", e)
        return False, None


def delete_multiple(table, id_list):
    """
    Deletes multiple rows by ID from a Supabase table.

    Args:
        table (str): Table name.
        id_list (list): List of record IDs to delete.

    Returns:
        dict: Success or error message.
    """
    try:
        response = supabase.table(table).delete().in_("id", id_list).execute()
        return {'success': True, 'response': response}
    except Exception as e:
        return {'success': False, 'error': dict(e).get("message")}


def delete(table, record_id):
    """
    Deletes a row from the specified Supabase table by ID.

    Args:
        table (str): Table name.
        record_id (int or str): ID of the record to delete.

    Returns:
        dict: Success or error message.
    """
    try:
        response = supabase.table(table).delete().eq("id", record_id).execute()

        # If the data is empty, the record may not exist
        if not response.data:
            return {'success': False, 'error': 'Record not found'}

        return {'success': True}

    except Exception as e:
        print(f"Delete error on table '{table}': {e}")
        return {'error': str(e), 'success': False}


def bulk_update(table: str, rows: list[dict], primary_key: str):
    """
    Update many rows in `table` in one request.

    Args:
        table       (str)          : table name
        rows        (list[dict])   : list of row dictionaries (must all include primary_key)
        primary_key (str)          : name of the primary‑key column

    Returns:
        dict with:
            success (bool)
            updated (int)  – how many rows Supabase reports as updated
            skipped (int)  – rows skipped because they lacked the PK
            error   (str | None)
            data    (list | None) – rows returned from Supabase on success
    """
    try:
        if not rows:
            return {
                "success": False,
                "error": "No rows provided.",
                "updated": 0,
                "skipped": 0
            }

        # Split into valid / invalid rows
        valid_rows = [r for r in rows if primary_key in r]
        skipped_rows = len(rows) - len(valid_rows)

        if not valid_rows:
            return {
                "success": False,
                "error": f"No rows contained primary key '{primary_key}'.",
                "updated": 0,
                "skipped": skipped_rows
            }

        # 1‑call bulk upsert (update existing, ignore non‑matches)
        response = (supabase.table(table).upsert(
            valid_rows, on_conflict=primary_key,
            ignore_duplicates=False).execute())

        # Supabase returns updated rows in .data
        updated_rows = len(response.data) if response.data else 0

        if response.error:
            return {
                "success": False,
                "error": str(response.error),
                "updated": updated_rows,
                "skipped": skipped_rows
            }

        return {
            "success": True,
            "updated": updated_rows,
            "skipped": skipped_rows,
            "data": response.data
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "updated": 0,
            "skipped": len(rows)
        }


def update_row_by_primary_key(table, data, primary_key):
    """
    Update one row in the table where primary_key = data[primary_key].

    Args:
        table (str): Table name
        data (dict): Fields to update (must include the primary key)
        primary_key (str): The name of the primary key column

    Returns:
        dict: Success status or error message
    """
    try:
        if primary_key not in data:
            raise ValueError(f"Missing primary key '{primary_key}' in data.")

        record = data.copy()
        key_value = record.pop(primary_key)

        response = supabase.table(table).update(record).eq(
            primary_key, key_value).execute()

        # Check if update affected any records
        if not response.data:
            return {
                'error': 'Record not found or nothing updated.',
                'success': False
            }

        return {'success': True, 'data': response.data}

    except Exception as e:
        return {'error': str(e), 'success': False}


def bulk_update_by_field(table, filter_field, filter_values, update_data):
    """
    Perform a bulk update on a table where filter_field is in filter_values.

    Args:
        table (str): Table name.
        filter_field (str): Column to filter by (e.g., 'campaign_id').
        filter_values (list): List of values to match.
        update_data (dict): Fields and values to update.

    Returns:
        dict: Success status and response data or error message.
    """
    try:
        response = (supabase.table(table).update(update_data).in_(
            filter_field, filter_values).execute())

        return {'success': True, 'data': response.data}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def upsert(table: str, data):
    """
    Performs a bulk upsert into the specified table using Supabase.

    Args:
        table (str): Table name as a string.
        data (List[Dict]): List of dictionaries representing rows to insert/update.

    Returns:
        dict: { success: bool, data: list (on success), error: str (on failure) }
    """
    try:
        if not data:
            raise ValueError("Data list is empty")

        response = supabase.table(table).upsert(data).execute()
        print('supabase response : ', response)
        # If response.data is None or empty, treat as failure
        if response:
            return {'success': True, 'data': response.data}

        return {'error': 'No data returned from upsert', 'success': False}

    except Exception as e:
        return {'error': str(e), 'success': False}


# Initialize the database

import httpx  # for network errors


def get_user_by_email(email):
    try:
        response = supabase.table("users").select("*").eq(
            "email", email).limit(1).execute()
        print('server response:', response)

        # Check if response is successful and has a valid data field
        if hasattr(response, 'status_code') and response.status_code != 200:
            return False, f"Supabase error: Status code {response.status_code}"

        if not hasattr(response, 'data') or response.data is None:
            return False, "Supabase error: Invalid response format"

        if len(response.data) == 0:
            return False, "No user found with that email"

        return True, response.data[0]

    except httpx.ConnectError:
        return False, "Network error: Failed to connect to Supabase"
    except httpx.ReadTimeout:
        return False, "Network error: Supabase request timed out"
    except httpx.RequestError as e:
        return False, f"Network error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def get_business_settings(user_id):
    """Get business settings for a user"""
    try:
        response = supabase.table("business_settings").select("*").eq(
            "user_id", user_id).limit(1).execute()
        if response.data and len(response.data) > 0:
            return True, response.data[0]
        return True, None
    except Exception as e:
        return False, str(e)


def save_business_settings(user_id,
                           business_name,
                           google_review_link,
                           form_settings=None):
    """Save or update business settings"""
    try:
        # Check if settings exist
        existing = supabase.table("business_settings").select("*").eq(
            "user_id", user_id).execute()

        data = {
            "user_id": user_id,
            "business_name": business_name,
            "google_review_link": google_review_link,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # Add form customization settings if provided
        if form_settings:
            data.update({
                "form_primary_color":
                form_settings.get("primary_color", "#3B82F6"),
                "form_secondary_color":
                form_settings.get("secondary_color", "#8B5CF6"),
                "form_logo_url":
                form_settings.get("logo_url", ""),
                "form_welcome_message":
                form_settings.get("welcome_message", ""),
                "form_background_style":
                form_settings.get("background_style", "gradient"),
                "form_gradient_start_color":
                form_settings.get("gradient_start_color", "#667eea"),
                "form_gradient_end_color":
                form_settings.get("gradient_end_color", "#764ba2"),
            })

        if existing.data and len(existing.data) > 0:
            # Update existing
            response = supabase.table("business_settings").update(data).eq(
                "user_id", user_id).execute()
        else:
            # Create new
            data["created_at"] = datetime.now(timezone.utc).isoformat()
            response = supabase.table("business_settings").insert(
                data).execute()

        return {'success': True, 'data': response.data}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def save_form_customization(user_id, customization_data):
    """Save form customization settings separately"""
    try:
        # Get existing business settings
        existing = supabase.table("business_settings").select("*").eq(
            "user_id", user_id).execute()

        if not existing.data:
            return {'success': False, 'error': 'Business settings not found'}

        # Prepare gradient settings as JSON string to store in existing field
        gradient_settings = {
            "direction": customization_data.get("gradient_direction", "135deg"),
            "angle": customization_data.get("gradient_angle", "135")
        }

        update_data = {
            "form_primary_color":
            customization_data.get("primary_color", "#3B82F6"),
            "form_secondary_color":
            customization_data.get("secondary_color", "#8B5CF6"),
            "form_gradient_start_color":
            customization_data.get("gradient_start_color", "#667eea"),
            "form_gradient_end_color":
            customization_data.get("gradient_end_color", "#764ba2"),
            "form_logo_url":
            customization_data.get("logo_url", ""),
            "form_welcome_message":
            customization_data.get("welcome_message", ""),
            "form_background_style":
            customization_data.get("background_style", "gradient"),
            # Store gradient settings in the welcome message field as JSON when not used
            "form_gradient_settings": str(gradient_settings) if customization_data.get("background_style") == "gradient" else "",
            "updated_at":
            datetime.now(timezone.utc).isoformat()
        }

        response = supabase.table("business_settings").update(update_data).eq(
            "user_id", user_id).execute()
        return {'success': True, 'data': response.data}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_dashboard_stats(user_id):
    """Get dashboard statistics for a user's business"""
    try:
        # Get business settings to find business_id
        business_settings = supabase.table("business_settings").select(
            "id").eq("user_id", user_id).execute()

        if not business_settings.data:
            return {
                'total_reviews': 0,
                'average_rating': 0.0,
                'public_reviews': 0,
                'private_reviews': 0,
                'rating_change': 0.0,
                'review_change': 0.0,
                'satisfaction_rate': 0.0
            }

        business_id = business_settings.data[0]['id']

        # Get all reviews for this business
        all_reviews = supabase.table("reviews").select("*").eq(
            "business_id", business_id).execute()

        if not all_reviews.data:
            return {
                'total_reviews': 0,
                'average_rating': 0.0,
                'public_reviews': 0,
                'private_reviews': 0,
                'rating_change': 0.0,
                'review_change': 0.0,
                'satisfaction_rate': 0.0
            }

        reviews = all_reviews.data
        total_reviews = len(reviews)

        # Calculate average rating
        if total_reviews > 0:
            total_rating = sum(review['rating'] for review in reviews)
            average_rating = round(total_rating / total_reviews, 1)
        else:
            average_rating = 0.0

        # Count public vs private reviews
        public_reviews = len(
            [r for r in reviews if r.get('review_type') == 'public'])
        private_reviews = len(
            [r for r in reviews if r.get('review_type') == 'private'])

        # Calculate satisfaction rate (4+ star reviews)
        high_ratings = len([r for r in reviews if r['rating'] >= 4])
        satisfaction_rate = round((high_ratings / total_reviews *
                                   100), 1) if total_reviews > 0 else 0.0

        # Calculate changes (mock data for now - you could implement actual historical tracking)
        rating_change = round((average_rating - 4.0) * 2.5,
                              1)  # Mock calculation
        review_change = round(min(15.3, total_reviews * 0.8),
                              1)  # Mock calculation

        return {
            'total_reviews': total_reviews,
            'average_rating': average_rating,
            'public_reviews': public_reviews,
            'private_reviews': private_reviews,
            'rating_change': rating_change,
            'review_change': review_change,
            'satisfaction_rate': satisfaction_rate
        }

    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        return {
            'total_reviews': 0,
            'average_rating': 0.0,
            'public_reviews': 0,
            'private_reviews': 0,
            'rating_change': 0.0,
            'review_change': 0.0,
            'satisfaction_rate': 0.0
        }


def get_recent_activity(user_id):
    """Get recent activity for dashboard"""
    try:
        activities = []

        # Get business settings
        business_settings = supabase.table("business_settings").select("*").eq(
            "user_id", user_id).execute()

        if business_settings.data:
            business_id = business_settings.data[0]['id']
            business_name = business_settings.data[0]['business_name']

            # Get recent reviews (last 8 for more activity)
            recent_reviews = supabase.table("reviews").select("*").eq(
                "business_id",
                business_id).order("created_at", desc=True).limit(8).execute()

            for review in recent_reviews.data:
                created_at = datetime.fromisoformat(
                    review['created_at'].replace('Z', '+00:00'))
                time_ago = get_time_ago(created_at)

                if review['review_type'] == 'public':
                    activities.append({
                        'icon': 'fas fa-star',
                        'color': 'green',
                        'title': f" {review['rating']}-star public review",
                        'description':
                        f"Customer: {review['customer_name']} - Redirected to Google",
                        'time': time_ago
                    })
                else:
                    activities.append({
                        'icon': 'fas fa-comment-dots',
                        'color': 'yellow',
                        'title': f" Private feedback received",
                        'description':
                        f"{review['rating']} stars - Internal improvement opportunity",
                        'time': time_ago
                    })

            # Add QR code/poster generation activity (mock recent activity)
            if business_settings.data[0].get('google_review_link'):
                activities.append({
                    'icon': 'fas fa-qrcode',
                    'color': 'blue',
                    'title': ' Review QR code ready',
                    'description': 'Customers can scan to leave reviews',
                    'time': '2 hours ago'
                })

                activities.append({
                    'icon': 'fas fa-image',
                    'color': 'blue',
                    'title': 'Marketing posters available',
                    'description': 'Download professional review posters',
                    'time': '3 hours ago'
                })

            # Add business settings update activity
            if business_settings.data[0].get('updated_at'):
                settings_updated = datetime.fromisoformat(
                    business_settings.data[0]['updated_at'].replace(
                        'Z', '+00:00'))
                activities.append({
                    'icon': 'fas fa-cog',
                    'color': 'blue',
                    'title': 'Business profile updated',
                    'description': f'{business_name} settings configured',
                    'time': get_time_ago(settings_updated)
                })

        # Add current session activity
        activities.append({
            'icon': 'fas fa-chart-line',
            'color': 'blue',
            'title': 'Dashboard accessed',
            'description': 'Viewing business analytics and performance',
            'time': 'Just now'
        })

        # Sort activities by recency (keep review order but mix with other activities)
        # Limit to 3 most recent activities
        return activities[:3]

    except Exception as e:
        print(f"Error getting recent activity: {e}")
        return [{
            'icon': 'fas fa-rocket',
            'color': 'blue',
            'title': 'Welcome to your dashboard',
            'description':
            'Configure business settings to start collecting reviews',
            'time': 'Just now'
        }, {
            'icon': 'fas fa-star',
            'color': 'green',
            'title': 'Review system ready',
            'description': 'Smart filtering will boost your online reputation',
            'time': '1 minute ago'
        }]


def get_time_ago(timestamp):
    """Convert timestamp to human readable time ago"""
    now = datetime.now(timezone.utc)
    diff = now - timestamp

    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "Just now"


def get_user_settings(user_id):
    """Get user settings with defaults"""
    try:
        response = supabase.table("user_settings").select("*").eq("user_id", user_id).limit(1).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]
        else:
            # Return default settings
            return {
                "email_notifications": True,
                "push_notifications": False,
                "marketing_emails": False
            }
    except Exception as e:
        print(f"Error getting user settings: {e}")
        return {
            "email_notifications": True,
            "push_notifications": False,
            "marketing_emails": False
        }


def save_user_settings(user_id, settings_data):
    """Save or update user settings"""
    try:
        # Check if settings exist
        existing = supabase.table("user_settings").select("*").eq("user_id", user_id).execute()

        data = {
            "user_id": user_id,
            "email_notifications": settings_data.get("email_notifications", True),
            "push_notifications": settings_data.get("push_notifications", False),
            "marketing_emails": settings_data.get("marketing_emails", False),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        if existing.data and len(existing.data) > 0:
            # Update existing settings
            response = supabase.table("user_settings").update(data).eq("user_id", user_id).execute()
        else:
            # Create new settings
            data["created_at"] = datetime.now(timezone.utc).isoformat()
            response = supabase.table("user_settings").insert(data).execute()

        return {'success': True, 'data': response.data}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def save_review_submission(business_id,
                           customer_name,
                           customer_email,
                           rating,
                           review_text,
                           review_type='public'):
    """Save a review submission"""
    try:
        data = {
            "business_id": business_id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "rating": rating,
            "review_text": review_text,
            "review_type": review_type,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        response = supabase.table("reviews").insert(data).execute()
        return {'success': True, 'data': response.data}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_reviews_for_business(user_id, limit=50):
    """Get reviews for a business"""
    try:
        # First get the business_id
        business_settings = supabase.table("business_settings").select(
            "id").eq("user_id", user_id).execute()
        if not business_settings.data:
            return {'success': True, 'data': []}

        business_id = business_settings.data[0]['id']

        response = supabase.table("reviews").select("*").eq(
            "business_id",
            business_id).order("created_at", desc=True).limit(limit).execute()
        return {'success': True, 'data': response.data}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def generate_ai_review_summary(user_id, force_regenerate=False):
    """Generate AI-powered review summary with SWOT analysis and caching"""
    try:
        # Get business info
        business_settings = supabase.table("business_settings").select("*").eq(
            "user_id", user_id
        ).execute()
        if not business_settings.data:
            return {'success': False, 'error': 'Business not found'}

        business_info = business_settings.data[0]
        business_id = business_info['id']
        business_name = business_info['business_name']

        # Get reviews
        reviews_response = supabase.table("reviews").select("*").eq(
            "business_id", business_id
        ).order("created_at", desc=True).execute()
        reviews = reviews_response.data

        if not reviews or len(reviews) < 2:
            return {
                'success': False,
                'error': 'Need at least 2 reviews for meaningful analysis'
            }

        # Check cache unless forcing regeneration
        if not force_regenerate:
            cached_summary = get_cached_ai_summary(user_id)
            if cached_summary:
                return {'success': True, 'data': cached_summary, 'cached': True}

        # Prepare review texts for AI
        review_texts = [
            {
                'rating': r['rating'],
                'text': r['review_text'],
                'type': r['review_type'],
                'date': r['created_at']
            }
            for r in reviews
        ]

        # Enhanced AI prompt with comprehensive business analysis structure
        ai_prompt = f"""
Analyze the following customer reviews for {business_name} and provide a comprehensive business intelligence report in JSON format.

Your analysis should include:
1. Overall sentiment (positive/negative/mixed)
2. Executive summary (2-3 sentences overview of business performance)
3. Detailed analysis (10-20 sentences covering strengths, issues, and strategic recommendations)
4. Key strengths (3-5 bullet points of what the business does well)
5. Areas for improvement (3-5 bullet points of specific issues to address)
6. Customer satisfaction insights (patterns and trends analysis)
7. Competitive positioning (how the business stands in the market based on feedback)
8. Risk assessment (potential threats or concerns from customer feedback)
9. Growth opportunities (specific areas for expansion or improvement)
10. Actionable recommendations (5-7 specific action items the business should implement)

Return ONLY a JSON object in this exact format:
{{
  "overall_sentiment": "positive|negative|mixed",
  "executive_summary": "Brief 2-3 sentence overview of business performance and current state",
  "detailed_analysis": "A comprehensive 10-20 sentence analysis depending on review numbers that covers business strengths, identifies issues and problems, analyzes customer feedback patterns, and provides clear recommendations for what the company should do going forward to improve and grow",
  "key_strengths": ["Strength 1", "Strength 2" ...],
  "areas_for_improvement": ["Improvement area 1", "Improvement area 2" ...],
  "customer_satisfaction_insights": "2-3 sentences analyzing customer satisfaction patterns, trends, and overall experience quality",
  "competitive_positioning": "2-3 sentences about how the business positions against competitors based on customer feedback",
  "risk_assessment": "2-3 sentences identifying potential risks, threats, or recurring issues that need attention",
  "growth_opportunities": "2-3 sentences outlining specific opportunities for business growth and expansion",
  "actionable_recommendations": ["Action 1", "Action 2" ...]
}}

Customer feedback data:
{review_texts}
"""

        # Call OpenAI
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are a business analyst expert specializing in customer feedback analysis. Provide only valid JSON output."
                },
                {"role": "user", "content": ai_prompt}
            ],
            max_tokens=4000,
            temperature=0.3
        )

        ai_analysis = response.choices[0].message.content.strip()

        # Clean up AI output
        if ai_analysis.startswith("```json"):
            ai_analysis = ai_analysis[7:-3].strip()
        elif ai_analysis.startswith("```"):
            ai_analysis = ai_analysis[3:-3].strip()

        # Parse JSON
        import json
        try:
            analysis_data = json.loads(ai_analysis)
        except json.JSONDecodeError as e:
            return {'success': False, 'error': f'AI returned invalid JSON: {e}'}

        # Expected schema for the enhanced structure
        expected_schema = {
            "overall_sentiment": "mixed",
            "executive_summary": "",
            "detailed_analysis": "",
            "key_strengths": [],
            "areas_for_improvement": [],
            "customer_satisfaction_insights": "",
            "competitive_positioning": "",
            "risk_assessment": "",
            "growth_opportunities": "",
            "actionable_recommendations": []
        }

        # Enforce schema types and update analysis_data to match the expected structure
        cleaned_analysis_data = {}
        for key, default_value in expected_schema.items():
            if key in ["key_strengths", "areas_for_improvement", "actionable_recommendations"]:
                # Ensure these are lists
                value = analysis_data.get(key, default_value)
                cleaned_analysis_data[key] = value if isinstance(value, list) else []
            else:
                cleaned_analysis_data[key] = analysis_data.get(key, default_value)

        analysis_data = cleaned_analysis_data


        # Final return
        summary_data = {
            'analysis': analysis_data,
            'review_count': len(reviews),
            'business_name': business_name,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'overall_sentiment': analysis_data.get('overall_sentiment', 'mixed')
        }

        # Cache result
        ids = save_ai_summary_cache(user_id, summary_data)


        return {'success': True, 'data': summary_data, 'cached': False, "id": ids, "gen": ids != None}

    except Exception as e:
        return {'success': False, 'error': f'AI analysis failed: {str(e)}'}



def get_cached_ai_summary(user_id):
    """Get cached AI summary if available and recent"""
    try:
        # Get business settings
        business_settings = supabase.table("business_settings").select("*").eq(
            "user_id", user_id).execute()
        if not business_settings.data:
            return None

        # Check if cached summary exists and is recent (within 24 hours)
        cached_summary = business_settings.data[0].get('ai_summary_cache')
        cached_at = business_settings.data[0].get('ai_summary_cached_at')

        if cached_summary and cached_at:
            cached_time = datetime.fromisoformat(cached_at.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)

            # If cache is less than 24 hours old, return it
            if (now - cached_time).total_seconds() < 86400:  # 24 hours
                import json
                return json.loads(cached_summary)

        return None
    except Exception as e:
        print(f"Error getting cached summary: {e}")
        return None


def save_ai_summary_cache(user_id, summary_data):
    """Save AI summary to cache and history"""
    try:
        business_settings = supabase.table("business_settings").select("*").eq(
            "user_id", user_id).execute()
        if not business_settings.data:
            return

        business_id = business_settings.data[0]['id']

        # Save to reports history table
        report_data = {
            "business_id": business_id,
            "report_data": summary_data,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_type": "ai_analysis"
        }

        response = supabase.table("ai_reports").insert(report_data).execute()

        if response.data and len(response.data) > 0:
            inserted_id = response.data[0].get('id')
        else:
            inserted_id = None

        return inserted_id

        # Cache is now handled through reports table only
        pass

    except Exception as e:
        print(f"Error saving report: {e}")


def get_ai_reports_history(user_id, limit=10):
    """Get AI reports history for a business"""
    try:
        business_settings = supabase.table("business_settings").select("*").eq(
            "user_id", user_id).execute()
        if not business_settings.data:
            return {'success': False, 'error': 'Business not found'}

        business_id = business_settings.data[0]['id']

        reports = supabase.table("ai_reports").select("*").eq(
            "business_id", business_id).order("generated_at", desc=True).limit(limit).execute()

        return {'success': True, 'data': reports.data}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_ai_report_by_id(user_id, report_id):
    """Get specific AI report by ID"""
    try:
        business_settings = supabase.table("business_settings").select("*").eq(
            "user_id", user_id).execute()
        if not business_settings.data:
            return {'success': False, 'error': 'Business not found'}

        business_id = business_settings.data[0]['id']

        report = supabase.table("ai_reports").select("*").eq(
            "id", report_id).eq("business_id", business_id).execute()

        if not report.data:
            return {'success': False, 'error': 'Report not found'}

        return {'success': True, 'data': report.data[0]}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_ai_summary_for_dashboard(user_id):
    """Get latest AI summary for dashboard display"""
    try:
        # Get business settings to find business_id
        business_settings = supabase.table("business_settings").select("id").eq("user_id", user_id).execute()

        if not business_settings.data:
            print(f"No business settings found for user {user_id}")
            return None

        business_id = business_settings.data[0]['id']

        # Get latest AI report
        latest_report = supabase.table("ai_reports")\
            .select("*")\
            .eq("business_id", business_id)\
            .order("generated_at", desc=True)\
            .limit(1)\
            .execute()

        print(f"AI reports query result for business {business_id}: {len(latest_report.data) if latest_report.data else 0} reports found")

        if not latest_report.data:
            print(f"No AI reports found for business {business_id}")
            return None

        report_data = latest_report.data[0]['report_data']
        print(f"Found report data structure: {list(report_data.keys()) if isinstance(report_data, dict) else 'Not a dict'}")

        # Extract data from the nested analysis structure
        analysis = report_data.get('analysis', {})

        # Extract summary information for dashboard with safe access using the enhanced keys
        summary = {
            'overall_sentiment': analysis.get('overall_sentiment', 'neutral'),
            'executive_summary': analysis.get('executive_summary', 'No executive summary available'),
            'detailed_analysis': analysis.get('detailed_analysis', 'No analysis available'),
            'key_strengths': analysis.get('key_strengths', []),
            'areas_for_improvement': analysis.get('areas_for_improvement', []),
            'customer_satisfaction_insights': analysis.get('customer_satisfaction_insights', ''),
            'competitive_positioning': analysis.get('competitive_positioning', ''),
            'risk_assessment': analysis.get('risk_assessment', ''),
            'growth_opportunities': analysis.get('growth_opportunities', ''),
            'actionable_recommendations': analysis.get('actionable_recommendations', []),
            'review_count': report_data.get('review_count', 0),
            'generated_at': latest_report.data[0]['generated_at']
        }

        print(f"Dashboard summary prepared successfully with sentiment: {summary['overall_sentiment']}")
        return summary

    except Exception as e:
        print(f"Error getting AI summary for dashboard: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return None


def create_trial_subscription(user_id):
    """Create a 7-day trial subscription for new user"""
    try:
        trial_end = datetime.now(timezone.utc) + timedelta(days=7)

        subscription_data = {
            "user_id": user_id,
            "tier": "base",  # Give full access during trial
            "status": "trialing",
            "trial_end": trial_end.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        response = supabase.table("subscriptions").insert(subscription_data).execute()
        return {'success': True, 'data': response.data}
    except Exception as e:
        print(f"Error creating trial subscription: {e}")
        return {'success': False, 'error': str(e)}


def create_paid_subscription(user_id, tier, stripe_subscription_id):
    """Create or update paid subscription"""
    try:
        print(f"🔄 Starting subscription creation - User: {user_id}, Tier: {tier}, Stripe: {stripe_subscription_id}")

        # Validate inputs
        if not user_id or not tier or not stripe_subscription_id:
            error_msg = f"Missing parameters - user_id: {user_id}, tier: {tier}, stripe_id: {stripe_subscription_id}"
            print(f"❌ {error_msg}")
            return {'success': False, 'error': error_msg}

        # Convert user_id to int
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            error_msg = f"Invalid user_id format: {user_id}"
            print(f"❌ {error_msg}")
            return {'success': False, 'error': error_msg}

        # Check if user exists
        print(f"🔍 Checking if user {user_id} exists...")
        user_check = supabase.table("users").select("id, email").eq("id", user_id).execute()
        print(f"🔍 User check result: {user_check.data}")

        if not user_check.data:
            error_msg = f"User {user_id} not found in database"
            print(f"❌ {error_msg}")
            return {'success': False, 'error': error_msg}

        # Check existing subscriptions
        print(f"🔍 Checking existing subscriptions for user {user_id}...")
        existing = supabase.table("subscriptions").select("*").eq("user_id", user_id).execute()
        print(f"🔍 Existing subscriptions: {existing.data}")

        # Prepare subscription data
        current_time = datetime.now(timezone.utc).isoformat()
        subscription_data = {
            "user_id": user_id,
            "tier": str(tier),
            "status": "active",
            "stripe_subscription_id": str(stripe_subscription_id),
            "trial_end": None,
            "updated_at": current_time
        }

        print(f"📝 Subscription data prepared: {subscription_data}")

        try:
            if existing.data and len(existing.data) > 0:
                # Update existing subscription
                print(f"📝 Updating existing subscription for user {user_id}")
                response = supabase.table("subscriptions").update(subscription_data).eq("user_id", user_id).execute()
                operation_type = "UPDATE"
            else:
                # Create new subscription
                print(f"✨ Creating new subscription for user {user_id}")
                subscription_data["created_at"] = current_time
                response = supabase.table("subscriptions").insert(subscription_data).execute()
                operation_type = "INSERT"

            print(f"📝 {operation_type} response received")
            print(f"📝 Response data: {response.data}")
            print(f"📝 Response count: {response.count}")

            # Check for Supabase errors
            if hasattr(response, 'error') and response.error:
                error_msg = f"Supabase error: {response.error}"
                print(f"❌ {error_msg}")
                return {'success': False, 'error': error_msg}

            # Verify response data
            if response.data:
                print(f"✅ {operation_type} successful for user {user_id}")

                # Immediate verification
                verify_result = supabase.table("subscriptions").select("*").eq("user_id", user_id).execute()
                print(f"🔍 Immediate verification: {verify_result.data}")

                return {'success': True, 'data': response.data, 'operation': operation_type}
            else:
                error_msg = f"No data returned from {operation_type} operation"
                print(f"❌ {error_msg}")
                return {'success': False, 'error': error_msg}

        except Exception as db_error:
            error_msg = f"Database operation failed: {str(db_error)}"
            print(f"❌ {error_msg}")
            import traceback
            print(f"❌ Database traceback: {traceback.format_exc()}")
            return {'success': False, 'error': error_msg}

    except Exception as e:
        error_msg = f"General exception: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        print(f"❌ General traceback: {traceback.format_exc()}")
        return {'success': False, 'error': error_msg}


def get_user_subscription_status(user_id):
    """Get user's current subscription status"""
    try:
        response = supabase.table("subscriptions").select("*").eq("user_id", user_id).limit(1).execute()

        if not response.data:
            return {
                'has_active_subscription': False,
                'in_trial': False,
                'tier': None,
                'trial_days_left': 0,
                'expires_at': None
            }

        subscription = response.data[0]
        now = datetime.now(timezone.utc)

        # Check if in trial
        if subscription['status'] == 'trialing' and subscription['trial_end']:
            trial_end = datetime.fromisoformat(subscription['trial_end'].replace('Z', '+00:00'))
            if trial_end > now:
                trial_days_left = (trial_end - now).days
                return {
                    'has_active_subscription': True,
                    'in_trial': True,
                    'tier': subscription['tier'],
                    'trial_days_left': trial_days_left,
                    'expires_at': trial_end
                }

        # Check if has active paid subscription
        if subscription['status'] == 'active':
            return {
                'has_active_subscription': True,
                'in_trial': False,
                'tier': subscription['tier'],
                'trial_days_left': 0,
                'expires_at': None  # For monthly subscriptions, we don't track exact end date
            }

        # Subscription expired or cancelled
        return {
            'has_active_subscription': False,
            'in_trial': False,
            'tier': subscription['tier'],
            'trial_days_left': 0,
            'expires_at': None
        }

    except Exception as e:
        print(f"Error getting subscription status: {e}")
        return {
            'has_active_subscription': False,
            'in_trial': False,
            'tier': None,
            'trial_days_left': 0,
            'expires_at': None
        }


def get_user_subscription_info(user_id):
    """Get user's subscription information including Stripe ID"""
    try:
        response = supabase.table("subscriptions").select("*").eq("user_id", user_id).limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error getting subscription info: {e}")
        return None


def cancel_user_subscription(user_id):
    """Mark user subscription as cancelled"""
    try:
        update_data = {
            "status": "cancelled",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        response = supabase.table("subscriptions").update(update_data).eq("user_id", user_id).execute()
        return {'success': True, 'data': response.data}
    except Exception as e:
        print(f"Error cancelling subscription: {e}")
        return {'success': False, 'error': str(e)}


def handle_subscription_cancelled(stripe_subscription_id):
    """Handle webhook when Stripe subscription is cancelled"""
    try:
        update_data = {
            "status": "cancelled",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        response = supabase.table("subscriptions").update(update_data).eq("stripe_subscription_id", stripe_subscription_id).execute()
        return {'success': True, 'data': response.data}
    except Exception as e:
        print(f"Error handling cancelled subscription: {e}")
        return {'success': False, 'error': str(e)}


def handle_payment_failed(stripe_subscription_id):
    """Handle webhook when payment fails"""
    try:
        update_data = {
            "status": "past_due",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        response = supabase.table("subscriptions").update(update_data).eq("stripe_subscription_id", stripe_subscription_id).execute()
        return {'success': True, 'data': response.data}
    except Exception as e:
        print(f"Error handling failed payment: {e}")
        return {'success': False, 'error': str(e)}


def handle_subscription_created(stripe_subscription_id, user_id, tier):
    """Handle webhook when Stripe subscription is created"""
    try:
        update_data = {
            "stripe_subscription_id": stripe_subscription_id,
            "tier": tier,
            "status": "active",
            "trial_end": None,  # Clear trial when subscription starts
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        response = supabase.table("subscriptions").update(update_data).eq("user_id", user_id).execute()
        return {'success': True, 'data': response.data}
    except Exception as e:
        print(f"Error handling subscription created: {e}")
        return {'success': False, 'error': str(e)}


def get_business_id(user_id):
    """Get business_id for a user"""
    try:
        response = supabase.table("business_settings").select("id").eq("user_id", user_id).limit(1).execute()
        if response.data:
            return response.data[0]['id']
        return None
    except Exception as e:
        print(f"Error getting business ID: {e}")
        return None


def validate_email(email):
    """Validate email format"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_phone(phone):
    """Validate phone format"""
    import re
    # Remove any non-digit characters
    digits_only = re.sub(r'\D', '', phone)
    # Accept phone numbers with 10-15 digits
    return len(digits_only) >= 10 and len(digits_only) <= 15


def get_customers_for_business(business_id):
    """Get all customers for a business"""
    try:
        response = supabase.table("customers").select("*").eq("business_id", business_id).order("created_at", desc=True).execute()
        return {'success': True, 'data': response.data}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def add_customer(business_id, name, email, phone):
    """Add a new customer"""
    try:
        # Check for duplicate email if provided
        if email:
            existing = supabase.table("customers").select("id").eq("business_id", business_id).eq("email", email).execute()
            if existing.data:
                return {'success': False, 'error': 'A customer with this email already exists'}

        customer_data = {
            "business_id": business_id,
            "name": name,
            "email": email if email else None,
            "phone": phone if phone else None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        response = supabase.table("customers").insert(customer_data).execute()
        return {'success': True, 'data': response.data[0]}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def import_customers_from_csv(business_id, file, name_col, email_col, phone_col):
    """Import customers from CSV file"""
    try:
        import csv
        import io

        # Read CSV content
        csv_content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))

        imported_count = 0
        skipped_count = 0
        errors = []

        for row_num, row in enumerate(csv_reader, start=2):
            try:
                name = row.get(name_col, '').strip()
                email = row.get(email_col, '').strip() if email_col else ''
                phone = row.get(phone_col, '').strip() if phone_col else ''

                if not name:
                    errors.append(f"Row {row_num}: Name is required")
                    continue

                if not email and not phone:
                    errors.append(f"Row {row_num}: Either email or phone is required")
                    continue

                # Validate email if provided
                if email and not validate_email(email):
                    errors.append(f"Row {row_num}: Invalid email format")
                    continue

                # Validate phone if provided
                if phone and not validate_phone(phone):
                    errors.append(f"Row {row_num}: Invalid phone format")
                    continue

                # Check for duplicate email
                if email:
                    existing = supabase.table("customers").select("id").eq("business_id", business_id).eq("email", email).execute()
                    if existing.data:
                        skipped_count += 1
                        continue

                # Add customer
                result = add_customer(business_id, name, email, phone)
                if result['success']:
                    imported_count += 1
                else:
                    errors.append(f"Row {row_num}: {result['error']}")

            except Exception as row_error:
                errors.append(f"Row {row_num}: {str(row_error)}")

        if errors and imported_count == 0:
            return {'success': False, 'error': '; '.join(errors[:3])}

        return {
            'success': True,
            'imported': imported_count,
            'skipped': skipped_count,
            'errors': errors
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}






def get_recent_feedback_requests(business_id):
    """Get recent feedback requests for a business"""
    try:
        response = supabase.table("feedback_requests").select("*").eq("business_id", business_id).order("sent_at", desc=True).limit(50).execute()
        return response.data
    except Exception as e:
        print(f"Error getting feedback requests: {e}")
        return []


def get_customer_by_email_or_phone(user_id, email, phone):
    """Check if a customer with this email or phone already exists for this user's business"""
    try:
        business_id = get_business_id(user_id)
        if not business_id:
            return None
            
        query = supabase.table("customers").select("id").eq("business_id", business_id)
        
        if email and phone:
            # Check for either email OR phone match
            response = query.or_(f"email.eq.{email},phone.eq.{phone}").execute()
        elif email:
            response = query.eq("email", email).execute()
        elif phone:
            response = query.eq("phone", phone).execute()
        else:
            return None
            
        return response.data[0] if response.data else None
        
    except Exception as e:
        print(f"Error checking customer duplicates: {e}")
        return None


def bulk_add_customers(business_id, customers_data):
    """Add multiple customers in one operation"""
    try:
        # Validate and prepare customer data
        valid_customers = []
        
        for customer in customers_data:
            name = (customer.get('name') or '').strip() if customer else ''
            email = (customer.get('email') or '').strip() if customer else ''
            phone = (customer.get('phone') or '').strip() if customer else ''

            
            # Name is optional - use email prefix if not provided
            if not name and email:
                name = email.split('@')[0]
            elif not name:
                name = 'Unknown'
                
            if not email and not phone:
                continue
                
            # Validate email format if provided
            if email and not validate_email(email):
                continue
                
            # Validate phone format if provided  
            if phone and not validate_phone(phone):
                continue
            
            # Check for duplicate email in this business
            if email:
                existing = supabase.table("customers").select("id").eq("business_id", business_id).eq("email", email).execute()
                if existing.data:
                    continue
            
            # Prepare customer data
            customer_data = {
                "business_id": business_id,
                "name": name,
                "email": email if email else None,
                "phone": phone if phone else None,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            valid_customers.append(customer_data)
        
        if not valid_customers:
            return {'success': False, 'error': 'No valid customers to add'}
        
        # Insert all customers at once
        response = supabase.table("customers").insert(valid_customers).execute()
        
        return {
            'success': True,
            'added': len(valid_customers),
            'data': response.data
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def delete_customers(business_id, customer_ids):
    """Delete selected customers"""
    try:
        # Verify customers belong to this business
        customers = supabase.table("customers").select("id").eq("business_id", business_id).in_("id", customer_ids).execute()
        valid_ids = [c['id'] for c in customers.data]

        if not valid_ids:
            return {'success': False, 'error': 'No valid customers to delete'}

        # Delete customers
        response = supabase.table("customers").delete().in_("id", valid_ids).execute()

        return {
            'success': True,
            'deleted': len(valid_ids)
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}