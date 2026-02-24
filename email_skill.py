"""
skills/email_skill.py — Email management skill for MAX.

Uses IMAP (read) and SMTP (send) — works with Gmail, Outlook,
Fastmail, ProtonMail Bridge, and any standard email provider.

⚠️  SAFETY NOTE: send_email and delete_email are marked confirm_required=True.
    MAX will always ask the user to confirm before taking these actions.
"""

import asyncio
import email as email_lib
import imaplib
import logging
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from skills.base import BaseSkill, skill_action

logger = logging.getLogger("MAX.skills.email")


class EmailSkill(BaseSkill):
    name = "email"
    description = "Read, search, draft, send, and organize email via IMAP/SMTP"

    def __init__(self, settings=None):
        super().__init__(settings)
        self.imap_host = os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
        self.imap_port = int(os.getenv("EMAIL_IMAP_PORT", "993"))
        self.smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.email_address = os.getenv("EMAIL_ADDRESS", "")
        self.email_password = os.getenv("EMAIL_PASSWORD", "")

    def _get_imap(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        conn.login(self.email_address, self.email_password)
        return conn

    @skill_action(description="List recent emails from your inbox (subject, from, date, ID)")
    async def list_inbox(self, count: int = 10, folder: str = "INBOX") -> str:
        """Fetch recent email headers."""
        def _fetch():
            conn = self._get_imap()
            conn.select(folder)
            _, data = conn.search(None, "ALL")
            ids = data[0].split()
            recent_ids = ids[-count:][::-1]  # Most recent first

            results = []
            for msg_id in recent_ids:
                _, msg_data = conn.fetch(msg_id, "(ENVELOPE)")
                raw = msg_data[0][1].decode()
                results.append(f"ID:{msg_id.decode()} | {raw[:150]}")

            conn.logout()
            return "\n".join(results)

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            return f"Recent emails ({folder}):\n{result}"
        except Exception as e:
            logger.error(f"list_inbox failed: {e}")
            return f"Could not list inbox: {str(e)}"

    @skill_action(description="Read the full content of an email by its ID")
    async def read_email(self, email_id: str, folder: str = "INBOX") -> str:
        """Read the body of a specific email."""
        def _fetch():
            conn = self._get_imap()
            conn.select(folder)
            _, data = conn.fetch(email_id.encode(), "(RFC822)")
            raw_email = data[0][1]
            msg = email_lib.message_from_bytes(raw_email)

            subject = msg.get("Subject", "No Subject")
            sender = msg.get("From", "Unknown")
            date = msg.get("Date", "Unknown")
            body = ""

            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    if ctype == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

            conn.logout()
            return f"From: {sender}\nDate: {date}\nSubject: {subject}\n\n{body[:2000]}"

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            return result
        except Exception as e:
            return f"Could not read email {email_id}: {str(e)}"

    @skill_action(
        description="Send an email. Always confirms with user before sending.",
        confirm_required=True
    )
    async def send_email(self, to: str, subject: str, body: str) -> str:
        """Send an email. Requires user confirmation."""
        def _send():
            msg = MIMEMultipart()
            msg["From"] = self.email_address
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_address, self.email_password)
                server.sendmail(self.email_address, to, msg.as_string())

        try:
            await asyncio.get_event_loop().run_in_executor(None, _send)
            return f"✅ Email sent to {to} with subject: {subject}"
        except Exception as e:
            return f"❌ Failed to send email: {str(e)}"

    @skill_action(
        description="Move an email to trash (delete). Always confirms with user first.",
        confirm_required=True
    )
    async def delete_email(self, email_id: str, folder: str = "INBOX") -> str:
        """Move an email to trash. Requires user confirmation."""
        def _delete():
            conn = self._get_imap()
            conn.select(folder)
            conn.store(email_id.encode(), "+FLAGS", "\\Deleted")
            conn.expunge()
            conn.logout()

        try:
            await asyncio.get_event_loop().run_in_executor(None, _delete)
            return f"✅ Email {email_id} moved to trash"
        except Exception as e:
            return f"❌ Failed to delete email: {str(e)}"

    @skill_action(description="Search emails by keyword in subject or body")
    async def search_emails(self, query: str, folder: str = "INBOX", limit: int = 10) -> str:
        """Search for emails matching a keyword."""
        def _search():
            conn = self._get_imap()
            conn.select(folder)
            _, data = conn.search(None, f'SUBJECT "{query}"')
            ids = data[0].split()
            if not ids:
                _, data = conn.search(None, f'TEXT "{query}"')
                ids = data[0].split()

            results = []
            for msg_id in ids[-limit:][::-1]:
                _, msg_data = conn.fetch(msg_id, "(ENVELOPE)")
                raw = msg_data[0][1].decode()
                results.append(f"ID:{msg_id.decode()} | {raw[:120]}")

            conn.logout()
            return "\n".join(results) if results else "No results found"

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, _search)
            return f"Search results for '{query}':\n{result}"
        except Exception as e:
            return f"Search failed: {str(e)}"
