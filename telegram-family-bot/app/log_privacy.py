"""Remove common credential forms before sending diagnostic excerpts."""
import re


def redact(text):
    value = str(text)
    value = re.sub(r'(https?://)[^\s/@]+:[^\s/@]+@', r'\1[redacted]@', value)
    value = re.sub(r'(?i)(bearer\s+)[\w.~-]+', r'\1[redacted]', value)
    value = re.sub(r'''(?i)((?:access_token|api_key|password|bot_token|token)["']?\s*[=:]\s*["']?)[^\s&,;"']+''',
                   r'\1[redacted]', value)
    value = re.sub(r'\b\d{6,}:[A-Za-z0-9_-]{20,}\b', '[redacted]', value)
    return value
