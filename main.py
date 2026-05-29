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
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta


EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_AUTH_CODE = os.environ.get("EMAIL_AUTH_CODE", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", EMAIL_ADDRESS)
IMAP_SERVER = "imap.qq.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465
SEARCH_DAYS = 2
PAGES_URL = "https://marlieswalter195-lab.github.io/kol-h5-publisher/"


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
    """提取邮件正文，返回原始HTML"""
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html" and not html_body:
                try:
                    html_body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    pass
    else:
        try:
            if msg.get_content_type() == "text/html":
                html_body = msg.get_payload(decode=True).decode(
                    msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            pass
    return html_body


def extract_h5_from_body(body_html):
    """从邮件正文提取Base64编码的H5源码并解码，补全HTML文档结构"""
    import base64
    import html as html_mod

    content = None

    # 新格式：Base64编码
    start = body_html.rfind("【HTML_BASE64_START】")
    end = body_html.rfind("【HTML_BASE64_END】")
    if start >= 0 and end > start:
        b64 = body_html[start + len("【HTML_BASE64_START】"):end].strip()
        b64 = re.sub(r'</?\w+[^>]*>', '', b64)
        b64 = html_mod.unescape(b64)
        b64 = b64.replace('\r', '').replace('\n', '').replace(' ', '')
        try:
            decoded = base64.b64decode(b64).decode("utf-8")
            if len(decoded) > 200:
                content = decoded
        except Exception:
            pass

    # 旧格式兼容
    if not content:
        start = body_html.rfind("【HTML正文开始】")
        end = body_html.rfind("【HTML正文结束】")
        if start >= 0 and end > start:
            raw = body_html[start + len("【HTML正文开始】"):end].strip()
            raw = html_mod.unescape(raw)
            raw = re.sub(r'^</?\w+[^>]*>\s*', '', raw)
            raw = re.sub(r'\s*</?\w+[^>]*>$', '', raw)
            if len(raw) > 100:
                content = raw

    if not content:
        return None

    # 如果已经有完整HTML结构（<html>或<!DOCTYPE），直接返回
    if '<!DOCTYPE html>' in content.lower() or '<html' in content.lower():
        return content

    # 需要补全文档结构：分离CSS和正文内容
    # 跳过首行标题
    first_nl = content.find("\n")
    if 0 < first_nl < 100:
        candidate = content[:first_nl].strip()
        if candidate and not re.match(r'^[<.@*#{\[a-z]', candidate):
            content = content[first_nl:].strip()

    lines = content.split("\n")
    content_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (stripped and not stripped.startswith(".") and 
            not stripped.startswith("#") and not stripped.startswith("@") and
            not stripped.startswith("*") and not stripped.startswith("body") and
            not stripped.startswith("}") and not stripped.startswith("/") and
            not stripped.startswith(":") and not re.match(r'^[a-z-]+', stripped)):
            content_start = i
            break

    css = "\n".join(lines[:content_start]).strip()
    body_content = "\n".join(lines[content_start:]).strip()

    # 提取日期作为标题
    date_match = re.search(r'(\d{4})年(\d{2})月(\d{2})日', content)
    title = f"投资大V观点日报 - {date_match.group(0)}" if date_match else "投资大V观点日报"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
{body_content}
</body>
</html>"""

    return html if len(html) > 200 else None


def send_notification(subject, body):
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

    print(f"\n📧 连接QQ邮箱: {EMAIL_ADDRESS}")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_AUTH_CODE)
        mail.select("INBOX")
    except Exception as e:
        print(f"❌ 邮箱连接失败: {e}")
        sys.exit(1)

    since_date = (datetime.now() - timedelta(days=SEARCH_DAYS)).strftime("%d-%b-%Y")
    status, messages = mail.search(None, f'(SINCE "{since_date}")')
    if status != "OK":
        print("❌ 搜索邮件失败")
        mail.logout()
        sys.exit(1)

    msg_ids = messages[0].split()
    print(f"找到 {len(msg_ids)} 封最近{SEARCH_DAYS}天的邮件")

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
            body_html = extract_body(msg)
            target_email = {"subject": subject, "date": date.isoformat(),
                           "body_html": body_html}
            print(f"✅ 找到目标邮件: {subject}")
            print(f"   发送时间: {date}")
            break

    mail.logout()

    if target_email is None:
        msg_text = f"⏰ {datetime.now():%Y-%m-%d %H:%M}\n\n今日未找到投资大V观点日报邮件，H5未更新。"
        print(f"\n⚠️ {msg_text}")
        send_notification("日报H5: 今日未找到邮件", msg_text)
        with open("status.txt", "w", encoding="utf-8") as f:
            f.write("no_email")
        sys.exit(0)

    html_code = extract_h5_from_body(target_email["body_html"])
    if html_code is None or len(html_code) < 200:
        msg_text = f"⏰ {datetime.now():%Y-%m-%d %H:%M}\n\n邮件格式异常，未提取到HTML正文，H5未更新。\n邮件标题: {target_email['subject']}"
        print(f"\n⚠️ {msg_text}")
        send_notification("日报H5: 格式异常", msg_text)
        with open("status.txt", "w", encoding="utf-8") as f:
            f.write("format_error")
        sys.exit(0)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_code)
    with open("status.txt", "w", encoding="utf-8") as f:
        f.write("success")

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
