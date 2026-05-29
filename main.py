#!/usr/bin/env python3
"""
投资大V观点日报H5发布 - GitHub Actions 云端自动化
每天18:40自动运行，不依赖本地环境。

环境变量（通过 GitHub Secrets 配置）:
  EMAIL_ADDRESS   - QQ邮箱地址
  EMAIL_AUTH_CODE - QQ邮箱IMAP/SMTP授权码
  NOTIFY_EMAIL    - 通知接收邮箱（默认同EMAIL_ADDRESS）
"""
import imaplib
import smtplib
import email
import os
import re
import sys
import html
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta


# ========== 配置 ==========
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_AUTH_CODE = os.environ.get("EMAIL_AUTH_CODE", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", EMAIL_ADDRESS)
IMAP_SERVER = "imap.qq.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465
SEARCH_DAYS = 2
PAGES_URL = os.environ.get("PAGES_URL", "https://<你的用户名>.github.io/kol-h5-publisher/")


def decode_mime(text):
    if text is None:
        return ""
    parts = decode_header(text)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(charset or "utf-8", errors="replace"))
            except Exception:
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def extract_body(msg):
    html_body = ""
    text_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/html" and not html_body:
                try:
                    html_body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    pass
            elif content_type == "text/plain" and not text_body:
                try:
                    text_body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                html_body = payload
            else:
                text_body = payload
        except Exception:
            pass
    if html_body:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_body, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text_body = soup.get_text(separator="\n", strip=True)
        except Exception:
            pass
    return text_body, html_body


def extract_h5_from_body(body_html):
    start = body_html.rfind("【HTML正文开始】")
    end = body_html.rfind("【HTML正文结束】")
    if start < 0 or end <= start:
        return None
    code = body_html[start + len("【HTML正文开始】"):end].strip()
    code = html.unescape(code)
    code = re.sub(r'^</?\w+[^>]*>\s*', '', code)
    code = re.sub(r'\s*</?\w+[^>]*>$', '', code)
    first_newline = code.find("\n")
    if 0 < first_newline < 100:
        candidate = code[:first_newline].strip()
        if candidate and not re.match(r'^[<.@*#{\[]', candidate):
            code = code[first_newline:].strip()
    return code if len(code) > 100 else None


def send_notification(subject, body):
    """通过QQ邮箱SMTP发送通知"""
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = NOTIFY_EMAIL
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_ADDRESS, EMAIL_AUTH_CODE)
            server.sendmail(EMAIL_ADDRESS, [NOTIFY_EMAIL], msg.as_string())
        print(f"📬 通知已发送到: {NOTIFY_EMAIL}")
    except Exception as e:
        print(f"⚠️ 通知发送失败: {e}")


def main():
    print("=" * 50)
    print(f"  投资大V观点日报H5 - 云端自动发布")
    print(f"  运行时间: {datetime.now():%Y-%m-%d %H:%M:%S} (北京时间)")
    print("=" * 50)

    if not EMAIL_ADDRESS or not EMAIL_AUTH_CODE:
        print("❌ 错误: 未配置邮箱地址或授权码")
        sys.exit(1)

    # 1. 连接QQ邮箱
    print(f"\n📧 连接QQ邮箱: {EMAIL_ADDRESS}")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_AUTH_CODE)
        mail.select("INBOX")
    except Exception as e:
        print(f"❌ 邮箱连接失败: {e}")
        sys.exit(1)

    # 2. 搜索邮件
    since_date = (datetime.now() - timedelta(days=SEARCH_DAYS)).strftime("%d-%b-%Y")
    status, messages = mail.search(None, f'(SINCE "{since_date}")')
    if status != "OK":
        print("❌ 搜索邮件失败")
        mail.logout()
        sys.exit(1)

    msg_ids = messages[0].split()
    print(f"找到 {len(msg_ids)} 封最近{SEARCH_DAYS}天的邮件")

    # 3. 查找目标邮件
    target_email = None
    for msg_id in reversed(msg_ids):
        status, data = mail.fetch(msg_id, "(RFC822)")
        if status != "OK":
            continue
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime(msg["Subject"])
        if "【投资大V观点日报】" in subject:
            date_str = msg.get("Date", "")
            try:
                date = parsedate_to_datetime(date_str)
            except Exception:
                date = datetime.now()
            body_text, body_html = extract_body(msg)
            target_email = {"subject": subject, "date": date.isoformat(),
                           "body_text": body_text, "body_html": body_html}
            print(f"✅ 找到目标邮件: {subject}")
            print(f"   发送时间: {date}")
            break

    mail.logout()

    # 4. 未找到目标邮件
    if target_email is None:
        msg_text = f"⏰ {datetime.now():%Y-%m-%d %H:%M}\n\n今日未找到投资大V观点日报邮件，H5未更新。"
        print(f"\n⚠️ {msg_text}")
        send_notification("日报H5: 今日未找到邮件", msg_text)
        with open("status.txt", "w", encoding="utf-8") as f:
            f.write("no_email")
        sys.exit(0)

    # 5. 提取H5源码
    html_code = extract_h5_from_body(target_email["body_html"])
    if html_code is None or len(html_code) < 100:
        msg_text = f"⏰ {datetime.now():%Y-%m-%d %H:%M}\n\n邮件格式异常，未提取到HTML正文，H5未更新。\n邮件标题: {target_email['subject']}"
        print(f"\n⚠️ {msg_text}")
        send_notification("日报H5: 格式异常", msg_text)
        with open("status.txt", "w", encoding="utf-8") as f:
            f.write("format_error")
        sys.exit(0)

    # 6. 覆盖写入
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_code)
    with open("status.txt", "w", encoding="utf-8") as f:
        f.write("success")

    # 7. 发送成功通知
    now = datetime.now()
    success_msg = (
        f"投资大V观点日报已更新\n\n"
        f"⏰ 更新时间: {now:%Y-%m-%d %H:%M} (北京时间)\n"
        f"📧 来源邮件: {target_email['subject']}\n"
        f"📄 H5大小: {len(html_code)} 字符\n"
        f"🔗 固定访问链接: {PAGES_URL}\n\n"
        f"---\n此通知由云端自动化任务自动发送"
    )
    print(f"\n✅ 投资大V观点日报已更新")
    print(f"   大小: {len(html_code)} 字符")
    send_notification(f"日报H5: 已更新 ({now:%m/%d})", success_msg)


if __name__ == "__main__":
    main()
