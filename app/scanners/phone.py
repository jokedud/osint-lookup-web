import phonenumbers
from phonenumbers import carrier, geocoder, timezone
from phonenumbers.phonenumberutil import number_type, NumberParseException

from ..models import Result

TYPE_NAMES = {
    0: "fixed_line", 1: "mobile", 2: "fixed_or_mobile", 3: "toll_free",
    4: "premium_rate", 5: "shared_cost", 6: "voip", 7: "personal",
    8: "pager", 9: "uan", 10: "voicemail", 27: "unknown",
}


async def scan(number: str):
    number = number.strip()
    try:
        parsed = phonenumbers.parse(number, None)
    except NumberParseException as exc:
        yield Result(source="phonenumbers", category="phone",
                     site="Parse", status="error",
                     details={"error": str(exc)})
        return

    region = geocoder.region_code_for_number(parsed)
    valid = phonenumbers.is_valid_number(parsed)
    details = {
        "valid": valid,
        "possible": phonenumbers.is_possible_number(parsed),
        "region": region,
        "country_code": parsed.country_code,
        "location": geocoder.description_for_number(parsed, "en"),
        "carrier": carrier.name_for_number(parsed, "en"),
        "timezones": list(timezone.time_zones_for_number(parsed)),
        "type": TYPE_NAMES.get(number_type(parsed), "unknown"),
        "e164": phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164),
        "international": phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
        "national": phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.NATIONAL),
    }
    yield Result(
        source="phonenumbers", category="phone",
        site="Number info",
        status="info" if valid else "error",
        details={k: v for k, v in details.items() if v not in (None, "", [])},
    )

    if not valid:
        return

    digits = phonenumbers.format_number(
        parsed, phonenumbers.PhoneNumberFormat.E164).lstrip("+")
    links = [
        ("WhatsApp", f"https://wa.me/{digits}"),
        ("Telegram", f"https://t.me/+{digits}"),
        ("TrueCaller", f"https://www.truecaller.com/search/{(region or 'us').lower()}/{digits}"),
    ]
    for site, url in links:
        yield Result(source="phonenumbers", category="phone", site=site,
                     status="found", url=url,
                     details={"message": "Lookup link (verification required)"})
