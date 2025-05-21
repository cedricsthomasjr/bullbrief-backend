import re

def normalize_section_name(name):
    name = name.lower()
    if "business" in name: return "Business Summary"
    if "swot" in name: return "SWOT"
    if "outlook" in name: return "Outlook"
    return name.title()

def split_sections(text):
    pattern = r"(?:^|\n)(#{1,3}|\*+)?\s*(Business Summary|SWOT(?: Analysis)?|Outlook)\s*[:\-–]*\s*\n"
    matches = list(re.finditer(pattern, text, re.IGNORECASE))

    if not matches:
        return {"Business Summary": "", "SWOT": "", "Outlook": ""}

    sections = {}
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_name = normalize_section_name(match.group(2))
        sections[section_name] = text[start:end].strip()

    for key in ["Business Summary", "SWOT", "Outlook"]:
        sections.setdefault(key, "")

    return sections
