import os
import smtplib
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
DOCTOR_EMAIL = os.getenv("DOCTOR_EMAIL")

print("--- SMTP Diagnostics ---")
print(f"Host: {SMTP_HOST}")
print(f"Port: {SMTP_PORT}")
print(f"User: {SMTP_USER}")
print(f"Password set: {'Yes' if SMTP_PASSWORD and SMTP_PASSWORD != 'your_16_char_app_password' else 'No (or placeholder)'}")
print(f"Doctor Email: {DOCTOR_EMAIL}")

if not SMTP_USER or not SMTP_PASSWORD or SMTP_PASSWORD == "your_16_char_app_password":
    print("\n[ERROR] SMTP credentials are not configured in .env.")
    exit(1)

try:
    print("\nAttempting connection to SMTP server...")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        print("Connection secure. Attempting login...")
        server.login(SMTP_USER, SMTP_PASSWORD)
        print("Login successful!")
        
        print(f"Attempting to send test email to {DOCTOR_EMAIL}...")
        msg = f"Subject: SMTP Test\n\nThis is a test email from the HD Dashboard diagnostics script."
        server.sendmail(SMTP_USER, DOCTOR_EMAIL, msg)
        print("Email sent successfully!")
except smtplib.SMTPAuthenticationError:
    print("\n[ERROR] SMTP Authentication Failed. Check your App Password.")
    print("Hint: If using Gmail, you MUST use a 16-character 'App Password', not your regular account password.")
except Exception as e:
    print(f"\n[ERROR] An unexpected error occurred: {e}")
