import re

EMAIL = r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
PHONE = r"(?<!\w)\+?\d[\d\s().-]{7,}\d"
TOKEN = r"(?i)(?:bearer\s+|(?:sk|ghp|token|api_key)[_-])[\w.-]+"
INJECTION = re.compile(r"ignore.{0,40}(?:instructions|rules)|system\s*prompt|"
                       r"(?:auto|bypass|disable).{0,20}(?:approv|guard|safety)|"
                       r"(?:reveal|send|print).{0,20}(?:secret|token|password)", re.I | re.S)


def redact(value):
    if isinstance(value, dict):
        return {k: v if k in {"tokens", "generated_tokens", "prompt_tokens", "completion_tokens"}
                and isinstance(v, (int, float)) and not isinstance(v, bool)
                else "[REDACTED]" if any(s in k.lower() for s in
                ("password", "token", "authorization", "cookie", "secret", "email"))
                else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        for pattern in (EMAIL, PHONE, TOKEN, r"\b(?:\d[ -]?){13,19}\b"):
            value = re.sub(pattern, "[REDACTED]", value)
    return value


def risks(text: str) -> list[str]:
    flags = []
    if INJECTION.search(text):
        flags.append("prompt_injection")
    for name, pattern in {
        "off_platform": r"telegram|whatsapp|outside.{0,15}platform|wire transfer|crypto payment",
        "free_work": r"free (?:sample|work|test)|unpaid (?:test|trial)",
        "guarantee": r"guarantee.{0,15}(?:success|results|returns|100%)",
        "contact_details": EMAIL,
    }.items():
        if re.search(pattern, text, re.I):
            flags.append(name)
    return flags
