
import os
from mailersend import MailerSendClient, EmailBuilder

# Init client (set MAILERSEND_API_KEY in env)
MAILERSEND_API_KEY = os.environ.get("MAILERSEND_API_KEY")

ms = MailerSendClient(api_key=MAILERSEND_API_KEY)

def _safe_build(builder):
    """Build EmailRequest and handle SDK variations returning tuple/list or single object."""
    result = builder.build()
    if isinstance(result, (tuple, list)):
        if not result:
            raise RuntimeError("EmailBuilder.build() returned empty tuple/list")
        return result[0]
    return result


# Define the HTML template once (use placeholders: {$company}, {$name}, {$feedback_link})
HTML_TEMPLATE = """<!-- Preheader (hidden) -->
<span style="display:none !important;visibility:hidden;opacity:0;height:0;width:0;font-size:0;line-height:0;">
  Help {$company} improve — share a quick rating.
</span>

<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#eff6ff;padding:22px 0;">
  <tr>
    <td align="center">
      <table role="presentation" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 6px 18px rgba(15,23,42,0.06);">
        <tr>
          <td style="padding:22px 24px;font-family:Arial,Helvetica,sans-serif;text-align:left;color:#0f1724;">
            <h2 style="margin:0 0 8px 0;font-size:20px;">Hi {$name},</h2>

            <p style="margin:0 0 16px 0;color:#475569;font-size:15px;line-height:1.5;">
              Could you tell us how <strong>{$company}</strong> did? Your quick rating helps us improve the things that matter to you.
            </p>

            <div style="text-align:center;margin:18px 0;">
              <a href="{$feedback_link}"
                 role="button"
                 aria-label="Leave feedback for {$company}"
                 style="background:#3b82f6;color:#ffffff;padding:12px 22px;border-radius:8px;text-decoration:none;display:inline-block;font-weight:700;font-family:Arial,Helvetica,sans-serif;">
                Leave feedback
              </a>
            </div>

            <p style="margin:0 0 6px 0;color:#64748b;font-size:13px;">
              Two quick ratings + one optional line — that’s all we ask.
            </p>

            <p style="margin:10px 0 0 0;color:#94a3b8;font-size:12px;">
              Prefer to talk? Reply to this email and we’ll follow up.
            </p>
          </td>
        </tr>

        <tr>
          <td style="padding:12px 24px;background:#fbfdff;text-align:center;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#94a3b8;">
            {$company} • Registered in Australia • <a href="{$unsubscribe_link}" style="color:#94a3b8;text-decoration:underline;">Unsubscribe</a>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

"""


def send_feedback_emails(business_id, business_name, customers):
    if not customers or not isinstance(customers, (list, tuple)):
        raise ValueError("customers must be a non-empty list")

    feedback_link = f"https://www.reviewecho.org/review-form/{business_id}"
    results = []

    for c in customers:
        email_addr = (c.get("email") or "").strip() if isinstance(c, dict) else ""
        name = (c.get("name") or "").strip() if isinstance(c, dict) else ""

        if not email_addr or "@" not in email_addr:
            results.append({"email": email_addr, "success": False, "error": "invalid email"})
            continue

        # subject and text body
        if name:
            subject = f"Hey {name}, {business_name} would love your feedback"
            text_body = f"Hi {name},\n\nThank you for choosing {business_name}. Please take a minute to leave feedback: {feedback_link}\n\nThanks,\nThe {business_name} Team"
        else:
            subject = f"{business_name} would love your feedback"
            text_body = f"Hi there,\n\nThank you for choosing {business_name}. Please take a minute to leave feedback: {feedback_link}\n\nThanks,\nThe {business_name} Team"

        # RENDER placeholders in the HTML template per recipient
        html_body = (HTML_TEMPLATE
                     .replace("{$company}", business_name)
                     .replace("{$name}", name or "there")
                     .replace("{$feedback_link}", feedback_link))

        try:
            builder = (
                EmailBuilder()
                .from_email("feedback@reviewecho.org", business_name)
                .to_many([{"email": email_addr, "name": name}])
                .subject(subject)
                .text(text_body)
                .html(html_body)
            )

            email_request = _safe_build(builder)
            resp = ms.emails.send(email_request)
            results.append({"email": email_addr, "success": True, "response": str(resp)})
        except Exception as e:
            results.append({"email": email_addr, "success": False, "error": str(e)})

    return results


