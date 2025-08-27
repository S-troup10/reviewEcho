import clicksend_client
from clicksend_client import SmsMessage, SmsMessageCollection
from clicksend_client.rest import ApiException
import os

import ast

API_KEY = os.environ.get("CLICKSEND_API_KEY")
USERNAME = os.environ.get("CLICKSEND_USERNAME")

# Configure API client
configuration = clicksend_client.Configuration()
configuration.username = USERNAME
configuration.password = API_KEY
api_instance = clicksend_client.SMSApi(clicksend_client.ApiClient(configuration))

def send_sms(business_id, business_name, customers):
    feedback_link = f"https://www.reviewecho.org/review-form/{business_id}"

    numbers = [{'phone': c.get("phone"), 'name': c.get("name", 'there')} for c in customers]

    messages = [
        SmsMessage(
            source="python",
            body=f"Hey {num['name']}, thanks for choosing {business_name}. We'd love to hear your feedback. Share your thoughts here: {feedback_link}",
            to=num['phone']
        )
        for num in numbers if num.get('phone')
    ]

    if not messages:
        return {"success": False, "error": "No valid phone numbers to send SMS to."}

    sms_messages = SmsMessageCollection(messages=messages)

    try:
   
        # Send messages
        api_response = api_instance.sms_send_post(sms_messages)
        print("API response type:", type(api_response))


        

        api_response = ast.literal_eval(api_response)
        # ✅ Directly use api_response as dict
        
        if api_response.get('http_code') != 200:
            return {"error": "API responded with an error code", "success": False}

        if api_response.get('response_code', '').lower() == 'success':
            return {"success": True, "raw": api_response}

        # fallback for unexpected type
        return {"success": False, "error": "Unexpected API response format", "raw": api_response}

    except ApiException as e:
        print("ApiException:", e)
        return {"error": str(e), "success": False}

