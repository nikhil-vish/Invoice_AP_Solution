"""
Email-to-Invoice Uploader
Polls an IMAP inbox for PDF attachments and uploads them to the Invoice AP Solution API.

Usage:
    1. Copy .env.example to .env and fill in your email credentials.
    2. Run: python email_uploader.py

Requirements:
    pip install python-dotenv
"""

import os
import imaplib
import email
from email.header import decode_header
import httpx
from dotenv import load_dotenv

load_dotenv()

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASS = os.getenv("IMAP_PASS", "")
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_UPLOAD_URL = f"{API_BASE_URL}/api/v1/invoices/upload"

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
MARK_AS_READ = os.getenv("MARK_AS_READ", "true").lower() == "true"


def connect_imap():
    print(f"Connecting to {IMAP_HOST}:{IMAP_PORT} as {IMAP_USER}...")
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASS)
    mail.select(IMAP_FOLDER)
    print("Connected and selected folder:", IMAP_FOLDER)
    return mail


def fetch_unread_pdf_attachments(mail):
    """Return list of (filename, bytes) for unread emails with PDF attachments."""
    status, messages = mail.search(None, "UNSEEN")
    if status != "OK":
        print("Failed to search inbox.")
        return []

    email_ids = messages[0].split()
    print(f"Found {len(email_ids)} unread email(s).")

    attachments = []
    for eid in email_ids:
        status, msg_data = mail.fetch(eid, "(RFC822)")
        if status != "OK":
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = decode_header(msg.get("Subject"))[0][0]
        if isinstance(subject, bytes):
            subject = subject.decode(decode_header(msg.get("Subject"))[0][1] or "utf-8")
        print(f"  Processing email: {subject}")

        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue

            filename = part.get_filename()
            if not filename:
                continue

            # Decode filename
            decoded = decode_header(filename)[0][0]
            if isinstance(decoded, bytes):
                filename = decoded.decode(decode_header(filename)[0][1] or "utf-8")

            if not filename.lower().endswith(".pdf"):
                print(f"    Skipping non-PDF attachment: {filename}")
                continue

            file_data = part.get_payload(decode=True)
            print(f"    Found PDF attachment: {filename} ({len(file_data)} bytes)")
            attachments.append((filename, file_data, eid))

        if MARK_AS_READ:
            mail.store(eid, "+FLAGS", "\\Seen")

    return attachments


def upload_invoice(filename, file_bytes):
    """Upload a PDF invoice to the API."""
    files = {"file": (filename, file_bytes, "application/pdf")}
    try:
        resp = httpx.post(API_UPLOAD_URL, files=files, timeout=60)
        if resp.status_code in (200, 201):
            data = resp.json()
            print(f"    Uploaded {filename}: draft_id={data.get('draft_id')}, status={data.get('status')}")
            return True
        else:
            print(f"    Upload failed for {filename}: HTTP {resp.status_code} - {resp.text[:200]}")
            return False
    except Exception as exc:
        print(f"    Upload error for {filename}: {exc}")
        return False


def poll_once():
    """Single poll cycle: connect, fetch, upload, disconnect."""
    try:
        mail = connect_imap()
        attachments = fetch_unread_pdf_attachments(mail)
        mail.logout()

        if attachments:
            print(f"Uploading {len(attachments)} attachment(s)...")
            for filename, data, _ in attachments:
                upload_invoice(filename, data)
        else:
            print("No new PDF attachments found.")
    except Exception as exc:
        print(f"Poll cycle error: {exc}")


def main():
    print("Starting Email-to-Invoice Uploader...")
    print(f"  IMAP: {IMAP_USER}@{IMAP_HOST}")
    print(f"  API:  {API_UPLOAD_URL}")
    print(f"  Poll interval: {POLL_INTERVAL_SECONDS}s")
    print("Press Ctrl+C to stop.\n")

    import time
    while True:
        poll_once()
        print(f"--- Sleeping {POLL_INTERVAL_SECONDS}s ---\n")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
