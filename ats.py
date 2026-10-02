"""Free, key-less ATS analyser. Deterministic, explainable scoring."""
import re

SECTIONS = {
    "Summary": r"\b(summary|objective|profile|about me)\b",
    "Experience": r"\b(experience|internship|work history|employment)\b",
    "Education": r"\b(education|academic|qualification)\b",
    "Skills": r"\b(skills|technologies|tech stack|tools)\b",
    "Projects": r"\b(projects?|hackathons?)\b",
}
VERBS = set("""built developed designed implemented created led managed delivered improved optimized automated
analyzed engineered launched deployed integrated reduced increased architected collaborated tested resolved
authored coordinated presented researched migrated streamlined trained mentored organized""".split())
WEAK = ["responsible for", "worked on", "helped with", "duties included", "hard working", "team player", "detail oriented"]
STOP = set("""a an the and or of to in for with on at by from as is are be we you your our will this that it their
they can able have has strong good work working experience years year team role using use etc including such
should must ability skills knowledge looking join candidate required preferred plus new""".split())


def _words(t):
    return re.findall(r"[a-zA-Z][a-zA-Z+#.\-]{1,}", t.lower())


def jd_keywords(jd, limit=25):
    counts = {}
    for w in _words(jd):
        w = w.strip(".-")
        if len(w) > 2 and w not in STOP:
            counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]]


def analyze(resume, jd=""):
    text = (resume or "").strip()
    low = text.lower()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    words = _words(text)
    checks, fixes = [], []

    def add(name, got, mx, note):
        checks.append({"name": name, "got": round(got, 1), "max": mx, "note": note})

    # 1. Contact (15)
    has = {"Email": bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)),
           "Phone": bool(re.search(r"(\+?\d[\d\s\-()]{8,}\d)", text)),
           "LinkedIn/GitHub": bool(re.search(r"linkedin\.com|github\.com", low))}
    miss = [k for k, v in has.items() if not v]
    add("Contact details", 15 * (3 - len(miss)) / 3, 15, "All found" if not miss else "Missing: " + ", ".join(miss))
    if miss: fixes.append("Add " + ", ".join(miss) + " at the top, as plain text (not inside an image).")

    # 2. Sections (20)
    found = [k for k, p in SECTIONS.items() if re.search(p, low)]
    core = [k for k in ("Experience", "Education", "Skills") if k in found]
    add("Standard sections", 20 * (len(core) / 3 * 0.75 + (0.25 if len(found) >= 4 else len(found) / 16)), 20,
        "Found: " + (", ".join(found) or "none"))
    for k in ("Experience", "Education", "Skills"):
        if k not in found: fixes.append(f'Add a clearly titled "{k}" section - ATS parsers look for these exact headings.')

    # 3. Bullets: action verbs + numbers (20)
    bullets = [
        re.sub(r"^[\u2022\u2023\u25aa\u25cf\u25e6\-* \t]+", "", line)
        for line in lines
        if re.match(r"^\s*[\u2022\u2023\u25aa\u25cf\u25e6\-*]\s+", line)
    ]
    verb_hits = sum(1 for b in bullets if b.split() and b.split()[0].lower().rstrip(",") in VERBS)
    num_hits = sum(1 for b in bullets if re.search(r"\d+\s?%|\d{2,}|\$\s?\d|\b\d+x\b", b))
    n = max(len(bullets), 1)
    add("Action verbs", 10 * verb_hits / n, 10, f"{verb_hits}/{len(bullets)} bullets start with a strong verb")
    add("Measurable impact", 10 * min(num_hits / max(n * 0.4, 1), 1), 10, f"{num_hits}/{len(bullets)} bullets contain numbers")
    if verb_hits / n < 0.6:
        fixes.append('Use concise bullets and start each with a strong verb like "Built", "Automated", or "Reduced".')
    if num_hits / n < 0.4: fixes.append("Add real numbers (users, %, time saved, team size) to at least 40% of bullets. Only use true figures.")

    # 4. Length & readability (10)
    wc = len(words)
    ok_len = 250 <= wc <= 800
    add("Length", 10 if ok_len else 5 if 150 <= wc <= 1000 else 2, 10, f"{wc} words (ideal 250-800 for a student/fresher)")
    if not ok_len: fixes.append("Aim for one page: 250-800 words.")

    # 5. Red flags (10)
    flags = [w for w in WEAK if w in low]
    if re.search(r"\b(i am|i have|my)\b", low): flags.append("first-person pronouns")
    if re.search(r"[\u2502\u2503\u2551\u25a0-\u25ff]|\|\s*\|", text): flags.append("tables/special symbols")
    add("Red flags", max(10 - 3 * len(flags), 0), 10, "None" if not flags else "Found: " + ", ".join(flags))
    if flags: fixes.append("Remove: " + ", ".join(flags) + ".")

    # 6. Job description match (25) - only when JD pasted
    matched, missing = [], []
    if jd.strip():
        kws = jd_keywords(jd)
        rw = set(_words(text))
        matched = [k for k in kws if k in rw or k in low]
        missing = [k for k in kws if k not in matched]
        add("Job keyword match", 25 * len(matched) / max(len(kws), 1), 25, f"{len(matched)}/{len(kws)} key terms found")
        if missing: fixes.append("Naturally work these JD terms into skills/bullets (only if true): " + ", ".join(missing[:10]) + ".")

    got = sum(c["got"] for c in checks)
    mx = sum(c["max"] for c in checks)
    score = round(100 * got / mx) if mx else 0
    verdict = "Strong" if score >= 80 else "Good, needs polish" if score >= 60 else "Needs work"
    return {"score": score, "verdict": verdict, "checks": checks, "fixes": fixes[:8],
            "matched": matched, "missing": missing, "has_jd": bool(jd.strip())}
