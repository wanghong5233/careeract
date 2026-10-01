import re
import unicodedata

RESTRICTED_CONTENT_MESSAGE = (
    "内容可能含证件/账户号码或登录凭据，本次未保存或发送给模型。"
    "请移除受限信息后重试；需要填写时由你在目标网站直接输入。"
)

_RESTRICTED_KEYS = frozenset(
    {
        "id_number",
        "identity_number",
        "passport_number",
        "bank_account",
        "bank_card",
        "password",
        "passwd",
        "otp",
        "verification_code",
        "api_key",
        "access_token",
        "refresh_token",
        "cookie",
        "authorization",
        "身份证号",
        "身份证号码",
        "证件号",
        "护照号",
        "银行卡号",
        "密码",
        "验证码",
        "secret",
        "secret_key",
        "private_key",
        "credential",
        "credentials",
        "token",
    }
)
_RESTRICTED_PATTERNS = (
    re.compile(r"(?<![0-9A-Za-z_-])(?:[0-9][\s-]?){12,18}[0-9xX](?![0-9A-Za-z_-])"),
    re.compile(r"(?<!\d)[0-9]{3}-[0-9]{2}-[0-9]{4}(?!\d)"),
    re.compile(r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}\b"),
    re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    re.compile(
        r"(?:密码|验证码|口令|护照号(?:码)?|银行卡号|身份证号(?:码)?|"
        r"\b(?:password|passwd|otp|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
        r"authorization|cookie|passport[_ -]?(?:no|number))\b)"
        r"[\"']?\s*[:=：]\s*[\"']?[^\s,;，；\"']{2,}",
        re.IGNORECASE,
    ),
)


class RestrictedContent(Exception):
    def __init__(self) -> None:
        super().__init__(RESTRICTED_CONTENT_MESSAGE)


def normalized_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value)
        if unicodedata.category(character) != "Cf"
    )


def ensure_career_content(value: object) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                if (
                    isinstance(key, str)
                    and normalized_text(key).strip().lower() in _RESTRICTED_KEYS
                    and child not in (None, "")
                ):
                    raise RestrictedContent
                pending.extend((key, child))
        elif isinstance(current, (list, tuple)):
            pending.extend(current)
        elif isinstance(current, (str, int)) and not isinstance(current, bool):
            text = normalized_text(str(current))
            if any(pattern.search(text) for pattern in _RESTRICTED_PATTERNS):
                raise RestrictedContent
