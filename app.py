import json
import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from supabase import create_client, Client
from ats import analyze as ats_analyze
from werkzeug.middleware.proxy_fix import ProxyFix

# Vercel injects environment variables directly. For local development, also
# load the Vercel CLI's `.env.local` file when it exists.
load_dotenv(".env.local")
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

SUPABASE_URL = os.environ.get("SUPABASE_URL") or "https://example.supabase.co"
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY") or "placeholder-anon-key"
PUBLIC_APP_URL = (os.environ.get("PUBLIC_APP_URL") or "").rstrip("/")
if not PUBLIC_APP_URL and os.environ.get("VERCEL_URL"):
    PUBLIC_APP_URL = f"https://{os.environ['VERCEL_URL'].rstrip('/')}"
if not PUBLIC_APP_URL:
    # Keep shared links useful during local development after the production
    # app has been deployed. Override this with PUBLIC_APP_URL for a custom domain.
    PUBLIC_APP_URL = "https://unanimous-topaz.vercel.app"


def require_supabase_env():
    """Validate the required Supabase settings only when the app actually
    tries to talk to Supabase. Importing the module should remain possible in
    local/test environments where the secret variables are not set yet."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key or not url.startswith(("http://", "https://")):
        raise RuntimeError(
            "Missing or invalid SUPABASE_URL or SUPABASE_ANON_KEY. On Vercel: "
            "Project Settings -> Environment Variables -> add both for the "
            "Production environment, then redeploy."
        )
    if key.startswith(("http://", "https://")):
        raise RuntimeError(
            "SUPABASE_ANON_KEY looks like a URL instead of an anon key. "
            "Check your .env / Vercel environment variables."
        )

# Matches the "U_NANI_MOUS — Frontend Developer Handoff" database contract:
# public.profile (singular) + public.profile_links, public "profile-images"
# storage bucket, path {user_id}/profile.jpg, signed URLs for display.
PROFILE_IMAGE_BUCKET = "profile-images"
ALLOWED_PHOTO_EXT = {"png", "jpg", "jpeg", "webp"}
SIGNED_URL_TTL = 3600  # seconds

# Free tier, no credit card — https://aistudio.google.com/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# 16 templates matching real, recognized resume categories (ATS-friendly
# categories referenced from published resume-template guides), each with
# a genuinely distinct layout in resume-templates.css — not just recolors.
RESUME_TEMPLATES = [
    {"id": "basic",       "name": "Basic",        "tagline": "Plain single column, front-loads your content — the safest choice for any ATS"},
    {"id": "minimalist",  "name": "Minimalist",   "tagline": "Thin rules, generous whitespace, nothing fighting for attention"},
    {"id": "traditional", "name": "Traditional",  "tagline": "Centered serif header, formal structure — a safe, conservative choice"},
    {"id": "modern",      "name": "Modern",       "tagline": "Bold dark name block up top — built to make a first impression"},
    {"id": "it",          "name": "IT Resume",    "tagline": "High-contrast two-column split, built for technical depth"},
    {"id": "functional",  "name": "Functional",   "tagline": "Skills lead, experience follows — good for career changers"},
    {"id": "professional","name": "Professional", "tagline": "One strategic block of color, otherwise all business"},
    {"id": "college",     "name": "College",      "tagline": "Education comes first — built for students and recent grads"},
    {"id": "creative",    "name": "Creative",     "tagline": "Gradient header block for design, content, and creative roles"},
    {"id": "skill-based", "name": "Skill-Based",  "tagline": "Leads with skills, not job titles — for career pivots"},
    {"id": "hybrid",      "name": "Hybrid",       "tagline": "Dark sidebar plus chronological main column, best of both formats"},
    {"id": "general",     "name": "General",      "tagline": "Bold, memorable header — a safe fit for sales and business roles"},
    {"id": "executive",   "name": "Executive",    "tagline": "Understated two-column layout for senior-level candidates"},
    {"id": "simple",      "name": "Simple",       "tagline": "One accent color, everything else out of the way"},
    {"id": "tech",        "name": "Tech",         "tagline": "Terminal-inspired monospace, four-block layout for devs"},
    {"id": "combined",    "name": "Combined",     "tagline": "Reverse-chronological experience next to a full skills breakdown"},
]
TEMPLATE_MAP = {t["id"]: t for t in RESUME_TEMPLATES}

ACCENT_PRESETS = ["#c9ff45", "#6fffd1", "#4d8bff", "#ff9d6f", "#c96fff", "#ff5a5a", "#ffd166"]
FONT_PRESETS = ["Manrope", "Georgia", "DM Mono", "Inter", "Poppins"]

PORTFOLIO_THEMES = [
    {"id": "studio", "name": "Studio", "description": "Editorial, spacious, and minimal"},
    {"id": "aurora", "name": "Aurora", "description": "Soft gradients with a luminous feel"},
    {"id": "mono", "name": "Mono", "description": "Sharp monochrome layout for makers"},
    {"id": "bold", "name": "Bold", "description": "Large type and high-contrast blocks"},
    {"id": "paper", "name": "Paper", "description": "Warm, calm, and print-inspired"},
    {"id": "terminal", "name": "Terminal", "description": "Technical grid with developer energy"},
    {"id": "gallery", "name": "Gallery", "description": "Visual-first showcase for creative work"},
    {"id": "signal", "name": "Signal", "description": "Bright accent details and clear structure"},
    {"id": "soft", "name": "Soft", "description": "Rounded cards and friendly spacing"},
    {"id": "executive", "name": "Executive", "description": "Refined presentation for senior profiles"},
    {"id": "grid", "name": "Grid", "description": "Organized modular portfolio system"},
    {"id": "night", "name": "Night", "description": "Cinematic dark theme with neon detail"},
]
PORTFOLIO_THEME_MAP = {theme["id"]: theme for theme in PORTFOLIO_THEMES}
# Three genuinely different page structures; the 12 themes are palettes on top.
THEME_LAYOUT = {
    "studio": "editorial", "paper": "editorial", "soft": "editorial", "executive": "editorial",
    "mono": "sidebar", "terminal": "sidebar", "night": "sidebar", "signal": "sidebar",
    "aurora": "showcase", "bold": "showcase", "gallery": "showcase", "grid": "showcase",
}

# These fields form the shared career identity. Resumes and the public
# portfolio can specialize the presentation, but they should not duplicate
# the person's core identity and introduction.
PROFILE_FIELDS = ["full_name", "headline", "bio", "mobile_number", "location"]
PROFILE_REQUIRED = ["full_name", "mobile_number", "location"]

# Suggested platforms for profile_links, with a base domain used to expand
# a bare handle ("sashankreddy") into a full URL. "Other"/unlisted platforms
# just require a full URL from the person.
PLATFORM_DOMAINS = {
    "LinkedIn": "linkedin.com/in",
    "GitHub": "github.com",
    "LeetCode": "leetcode.com",
    "CodeChef": "codechef.com",
    "HackerRank": "hackerrank.com",
    "Kaggle": "kaggle.com",
    "Google Scholar": "scholar.google.com/citations?user=",
}
PLATFORM_CHOICES = list(PLATFORM_DOMAINS) + ["Portfolio", "Other"]


# ---------------------------------------------------------------------------
# Supabase client helpers
# ---------------------------------------------------------------------------
def anon_client() -> Client:
    """A fresh client using only the public anon key — fine for the OTP
    send/verify calls, which don't need a user session yet."""
    require_supabase_env()
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def authed_client() -> Client:
    """A client whose requests carry the signed-in user's own access token,
    so every query is subject to that user's Row Level Security policies —
    they can only ever read/write their own profile and resume rows."""
    require_supabase_env()
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    access_token = session.get("sb_access_token")
    refresh_token = session.get("sb_refresh_token")
    if access_token and refresh_token:
        try:
            client.auth.set_session(access_token, refresh_token)
        except Exception:
            pass
        # Belt-and-braces: also attach the token directly to the REST client,
        # since set_session's internal sync can vary by supabase-py version.
        client.postgrest.auth(access_token)
    return client


def refresh_if_needed():
    """Supabase access tokens expire (~1hr). If ours has gone stale, use the
    refresh token to get a new one before the next request fails."""
    refresh_token = session.get("sb_refresh_token")
    if not refresh_token:
        return
    try:
        client = anon_client()
        result = client.auth.refresh_session(refresh_token)
        if result and result.session:
            session["sb_access_token"] = result.session.access_token
            session["sb_refresh_token"] = result.session.refresh_token
    except Exception:
        pass


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        refresh_if_needed()
        return view(*args, **kwargs)
    return wrapped


def current_user_id():
    return session["user"]["id"]


def slugify(value):
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "portfolio"


def profile_slug(profile):
    return profile.get("public_slug") or slugify(profile.get("full_name") or profile.get("email") or "portfolio")


def ensure_public_profile_fields(client, profile):
    """Persist a stable, collision-resistant slug for existing profiles."""
    if profile.get("public_slug"):
        return profile
    base = slugify(profile.get("full_name") or profile.get("email") or "portfolio")
    stable_slug = f"{base}-{str(profile.get('user_id', ''))[:8]}"
    result = (client.table("profile").update({"public_slug": stable_slug})
              .eq("id", profile["id"]).execute())
    if result.data:
        return result.data[0]
    profile["public_slug"] = stable_slug
    return profile


def profile_public_url(profile, external=False):
    return public_portfolio_url(profile_slug(profile)) if external else url_for(
        "public_portfolio", slug=profile_slug(profile)
    )


def public_portfolio_url(slug):
    """Use the deployed domain for links shared outside the local machine."""
    path = url_for("public_portfolio", slug=slug)
    if PUBLIC_APP_URL:
        return f"{PUBLIC_APP_URL}{path}"
    return url_for("public_portfolio", slug=slug, _external=True)


def portfolio_theme_url(slug, theme_id):
    return f"{public_portfolio_url(slug)}?theme={theme_id}"


app.jinja_env.globals["portfolio_theme_url"] = portfolio_theme_url


def portfolio_checklist(profile, links, resumes):
    """Return beginner-friendly completion guidance without inventing facts."""
    content = (resumes[0].get("content") or {}) if resumes else {}
    return [
        {"label": "Your name", "done": bool((profile.get("full_name") or "").strip()), "required": True},
        {"label": "Professional headline", "done": bool((profile.get("headline") or "").strip()), "required": True},
        {"label": "Short introduction", "done": bool((profile.get("bio") or "").strip()), "required": True},
        {"label": "Email or phone", "done": bool((profile.get("email") or profile.get("mobile_number") or "").strip()), "required": True},
        {"label": "At least one resume", "done": bool(resumes), "required": True},
        {"label": "Skills", "done": bool(content.get("skills")), "required": False},
        {"label": "Projects or experience", "done": bool(content.get("projects") or content.get("experience")), "required": False},
        {"label": "Education", "done": bool(content.get("education")), "required": False},
        {"label": "Professional links", "done": bool(links), "required": False},
    ]


# ---------------------------------------------------------------------------
# public.profile + public.profile_links
# ---------------------------------------------------------------------------
def get_or_create_profile(client, uid, email="", default_name=""):
    res = client.table("profile").select("*").eq("user_id", uid).execute()
    if res.data:
        return ensure_public_profile_fields(client, res.data[0])
    insert = client.table("profile").insert({
        "user_id": uid, "full_name": default_name, "email": email,
        "mobile_number": "", "location": "", "headline": "", "bio": "",
        "profile_image_public": False, "public_slug": f"{slugify(default_name or email or 'portfolio')}-{str(uid)[:8]}",
        "portfolio_published": False,
    }).execute()
    return insert.data[0]


def get_profile_links(client, profile_id):
    res = (client.table("profile_links").select("*")
           .eq("profile_id", profile_id).order("display_order").execute())
    return res.data or []


def latest_resume(client, uid):
    rows = (
        client.table("resumes")
        .select("*")
        .eq("user_id", uid)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def portfolio_content(content):
    """Return only complete, presentable entries for the public portfolio."""
    content = content or {}
    experience = [
        item for item in content.get("experience", [])
        if isinstance(item, dict) and (
            str(item.get("title") or "").strip() or str(item.get("org") or "").strip()
        )
    ]
    education = [
        item for item in content.get("education", [])
        if isinstance(item, dict) and (
            str(item.get("degree") or "").strip() or str(item.get("school") or "").strip()
        )
    ]
    projects = [
        item for item in content.get("projects", [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    skills = [
        skill.strip() for skill in content.get("skills", [])
        if isinstance(skill, str) and skill.strip()
    ]
    return {
        "summary": str(content.get("summary") or "").strip(),
        "experience": experience,
        "education": education,
        "projects": projects,
        "skills": skills,
    }


def replace_profile_links(client, profile_id, links):
    """links: list of (platform_name, url). Simplest correct approach for a
    small personal project — clear and re-insert rather than diffing ids."""
    client.table("profile_links").delete().eq("profile_id", profile_id).execute()
    rows = [
        {"profile_id": profile_id, "platform_name": platform, "url": url, "display_order": i}
        for i, (platform, url) in enumerate(links) if platform and url
    ]
    if rows:
        client.table("profile_links").insert(rows).execute()


def profile_completion(profile, links):
    fields = ["full_name", "headline", "bio", "mobile_number", "location", "profile_image_url"]
    filled = sum(1 for f in fields if (profile.get(f) or "").strip())
    total = len(fields) + 1  # +1 for "has at least one link"
    if links:
        filled += 1
    return round((filled / total) * 100)


def normalize_link(platform, handle_or_url):
    v = (handle_or_url or "").strip()
    if not v:
        return ""
    if v.startswith("http://") or v.startswith("https://"):
        return v
    base = PLATFORM_DOMAINS.get(platform)
    if not base:
        return "https://" + v.lstrip("/")
    return f"https://{base}/{v.lstrip('@').strip('/')}"


def display_link(url):
    """Strip the protocol (and www.) for clean on-resume display, the way
    people conventionally write links on a printed resume: 'github.com/x'
    instead of 'https://github.com/x'."""
    v = (url or "").strip()
    for prefix in ("https://", "http://"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    if v.startswith("www."):
        v = v[4:]
    return v.rstrip("/")


app.jinja_env.filters["display_link"] = display_link


def upload_profile_photo(client, file_storage, uid):
    """Upload to the profile-images bucket at {uid}/profile.jpg and return
    the storage path to save in profile.profile_image_url."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in ALLOWED_PHOTO_EXT:
        raise ValueError("Profile photo must be a PNG, JPG, JPEG, or WEBP image.")
    if file_storage.mimetype and not file_storage.mimetype.startswith("image/"):
        raise ValueError("The selected profile photo is not a supported image.")
    path = f"{uid}/profile.jpg"
    file_bytes = file_storage.read()
    if not file_bytes:
        raise ValueError("The selected profile photo is empty.")
    client.storage.from_(PROFILE_IMAGE_BUCKET).upload(
        path, file_bytes, {"content-type": file_storage.mimetype or "image/jpeg", "upsert": "true"}
    )
    return path


def signed_photo_url(client, path):
    """Turn a stored storage path into a short-lived (1hr) signed URL for
    display. Returns None if there's no photo or the signed-url call fails
    (e.g. missing storage RLS policy) rather than raising."""
    if not path:
        return None
    try:
        res = client.storage.from_(PROFILE_IMAGE_BUCKET).create_signed_url(path, SIGNED_URL_TTL)
        return res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
    except Exception:
        return None


def public_photo_url(client, path):
    """Return a stable URL for an image in the public profile-images bucket."""
    if not path:
        return None
    return client.storage.from_(PROFILE_IMAGE_BUCKET).get_public_url(path)


def upload_project_image(client, file_storage, uid):
    if not file_storage or not file_storage.filename:
        raise ValueError("Choose an image first.")
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in ALLOWED_PHOTO_EXT:
        raise ValueError("Project images must be PNG, JPG, JPEG, or WEBP files.")
    if file_storage.mimetype and not file_storage.mimetype.startswith("image/"):
        raise ValueError("The selected project file is not an image.")
    file_bytes = file_storage.read()
    if not file_bytes:
        raise ValueError("The selected project image is empty.")
    path = f"{uid}/projects/{uuid.uuid4().hex}.{ext}"
    client.storage.from_(PROFILE_IMAGE_BUCKET).upload(
        path, file_bytes, {"content-type": file_storage.mimetype or "image/jpeg", "upsert": "false"}
    )
    return public_photo_url(client, path)


VERB_MAP = [
    (r"^(worked on|working on|work on)\b", "Developed"), (r"^(made|make|created|create)\b", "Built"),
    (r"^(did|do|done)\b", "Delivered"), (r"^(helped|help)\b", "Supported"),
    (r"^(used|use|using)\b", "Leveraged"), (r"^(learned|learnt|learn)\b", "Gained hands-on skills in"),
    (r"^(built|build|building)\b", "Built"), (r"^(designed|design)\b", "Designed"),
    (r"^(led|lead|managed)\b", "Led"), (r"^(tested|test)\b", "Tested"),
    (r"^(fixed|fix)\b", "Resolved"), (r"^(wrote|write)\b", "Authored"),
]
TECH_CASE = {"python": "Python", "flask": "Flask", "react": "React", "javascript": "JavaScript",
             "html": "HTML", "css": "CSS", "sql": "SQL", "api": "API", "apis": "APIs", "github": "GitHub",
             "supabase": "Supabase", "mysql": "MySQL", "java": "Java", "node": "Node.js", "ml": "ML", "ai": "AI"}


def local_enhance(text, kind="bullet"):
    """Free, key-less rewrite: fixes tense/voice, strong verb, tech casing.
    Never invents facts or numbers."""
    value = re.sub(r"\s+", " ", (text or "").strip())
    if not value:
        raise ValueError("Nothing to enhance yet - write a draft first.")
    value = re.sub(r"^[\s\u2022*-]+", "", value)
    value = re.sub(r"\b(i am|i'm|i have|i was|i did|my|we)\b\s*", "", value, flags=re.IGNORECASE).strip(" ,.")
    value = re.sub(r"\b(\w+)\s+\1\b", r"\1", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(and|also|so|then)\s+(and|also|so|then)\b", r"\1", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(a lot of|very|really|basically|just)\b\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b([A-Za-z.]+)\b", lambda m: TECH_CASE.get(m.group(1).lower(), m.group(1)), value)
    if kind != "summary":
        for pat, verb in VERB_MAP:
            if re.match(pat, value, flags=re.IGNORECASE):
                value = verb + value[re.match(pat, value, flags=re.IGNORECASE).end():]
                break
    value = value[:1].upper() + value[1:]
    if value and value[-1] not in ".!?":
        value += "."
    return value


def call_gemini_enhance(text, kind="bullet"):
    """Enhance resume content with Gemini, falling back to local rewriting."""
    if not text or not text.strip():
        raise ValueError("Nothing to enhance yet — write a draft first.")
    if not GEMINI_API_KEY:
        return local_enhance(text, kind)

    if kind == "summary":
        instruction = (
            "Rewrite this resume summary to be concise, confident, and ATS-friendly. "
            "2-3 sentences max. No first-person 'I'. Return only the rewritten text, nothing else."
        )
    else:
        instruction = (
            "Rewrite this single resume bullet point to start with a strong action verb, "
            "be specific and quantified where plausible, and read as one ATS-friendly line. "
            "Return only the rewritten bullet, nothing else — no quotes, no bullet symbol."
        )

    # Try gemini-2.0-flash first, then gemini-1.5-flash
    candidate_models = [GEMINI_MODEL, "gemini-2.0-flash", "gemini-1.5-flash"]
    # De-duplicate while preserving order
    models_to_try = list(dict.fromkeys([m for m in candidate_models if m]))

    last_error = None
    for model in models_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            resp = requests.post(
                url,
                json={"contents": [{"parts": [{"text": f"{instruction}\n\nText:\n{text.strip()}"}]}]},
                timeout=12,
            )
            if resp.status_code == 200:
                data = resp.json()
                if "candidates" in data and data["candidates"]:
                    parts = data["candidates"][0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        res_text = parts[0]["text"].strip()
                        # Strip accidental surrounding quotes or bullet chars
                        res_text = re.sub(r'^[•\-\*"]\s*', '', res_text).rstrip('"')
                        return res_text
            last_error = f"Model {model} returned status {resp.status_code}: {resp.text}"
        except Exception as exc:
            last_error = str(exc)
            continue

    print(f"[call_gemini_enhance] Gemini API calls failed ({last_error}), using local enhancer.")
    return local_enhance(text, kind)


@app.route("/api/enhance", methods=["POST"])
@login_required
def api_enhance():
    body = request.get_json(silent=True) or {}
    try:
        result = call_gemini_enhance(body.get("text", ""), body.get("kind", "bullet"))
        return jsonify({"ok": True, "text": result, "source": "gemini" if GEMINI_API_KEY else "local"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/project-image", methods=["POST"])
@login_required
def api_project_image():
    try:
        image_url = upload_project_image(authed_client(), request.files.get("image"), current_user_id())
        return jsonify({"ok": True, "url": image_url})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def empty_resume_content():
    return {"headline": "", "summary": "", "experience": [], "education": [], "projects": [], "skills": []}


def prefill_content_from_profile(profile):
    # Keep the core identity consistent across every output. Experience,
    # education, projects, and skills remain resume-specific until they are
    # moved into the structured career workspace.
    content = empty_resume_content()
    content["headline"] = profile.get("headline") or ""
    content["summary"] = profile.get("bio") or ""
    return content


def contact_lines(profile, links):
    """Build the flat contact-line list every resume/gallery preview uses:
    location, mobile, email, then every saved profile_link's URL."""
    lines = [profile.get("location", ""), profile.get("mobile_number", ""), profile.get("email", "")]
    lines += [l["url"] for l in links]
    return lines


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", user=session.get("user"))


# ---------------------------------------------------------------------------
# Email + password auth — separate sign-up and log-in flows.
# ---------------------------------------------------------------------------
def establish_session(result, email, default_name):
    """Shared by signup/login: store the Supabase session, ensure a profile
    row exists, and populate session['user']."""
    session["sb_access_token"] = result.session.access_token
    session["sb_refresh_token"] = result.session.refresh_token
    uid = result.user.id
    client = authed_client()
    try:
        profile = get_or_create_profile(client, uid, email=email, default_name=default_name)
    except Exception as exc:
        # Almost always: the "profile" table is missing, or its RLS policy
        # doesn't allow this user to INSERT their own row (needs a policy
        # like `auth.uid() = user_id` for INSERT). Surface it instead of a
        # bare 500 so `vercel logs` shows the real Postgrest error.
        print(f"[establish_session] profile insert/select failed for uid={uid}: {exc}")
        raise RuntimeError(
            "Could not create your profile in Supabase. Check that the "
            "'profile' table exists and has an RLS policy allowing INSERT "
            "for auth.uid() = user_id."
        ) from exc
    session["user"] = {"id": uid, "email": email, "name": profile.get("full_name") or default_name}
    return profile


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:
            flash("Fill in your name, email, and a password of at least 6 characters.", "error")
            return render_template("signup.html")

        try:
            client = anon_client()
            result = client.auth.sign_up({
                "email": email, "password": password,
                "options": {"data": {"name": name}},
            })
        except Exception as exc:
            flash(f"Couldn't create your account: {exc}", "error")
            return render_template("signup.html")

        if not result.session:
            flash("Account created — enter the OTP sent to your email.", "ok")
            return render_template("verify_email.html", email=email)

        try:
            establish_session(result, email, name)
        except Exception as exc:
            flash(f"Account created, but setup failed: {exc}", "error")
            return render_template("signup.html")

        flash("Welcome! Let's set up your profile — this is what every resume you build will pull from.", "ok")
        return redirect(url_for("profile_edit"))

    return render_template("signup.html")


@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    email = (request.values.get("email") or "").strip().lower()
    if request.method == "POST":
        token = request.form.get("token", "").strip()
        if not email or not token:
            flash("Enter your email and the OTP from your message.", "error")
            return render_template("verify_email.html", email=email)
        try:
            client = anon_client()
            result = client.auth.verify_otp({
                "email": email,
                "token": token,
                "type": "signup",
            })
            metadata = result.user.user_metadata or {}
            name = metadata.get("name")
            if not isinstance(name, str) or not name.strip():
                name = email.split("@")[0]
            establish_session(result, email, name.strip())
        except Exception as exc:
            print(f"[verify_email] OTP verification failed for {email}: {exc}")
            flash("That OTP is invalid or expired. Request a new one and try again.", "error")
            return render_template("verify_email.html", email=email)
        flash("Email verified. Welcome to U_NANI_MOUS.", "ok")
        return redirect(url_for("profile_edit"))
    return render_template("verify_email.html", email=email)


@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    email = (request.form.get("email") or "").strip().lower()
    if not email:
        flash("Enter your email address before requesting another code.", "error")
        return redirect(url_for("verify_email"))
    try:
        anon_client().auth.resend({"type": "signup", "email": email})
    except Exception as exc:
        print(f"[resend_otp] failed for {email}: {exc}")
        flash("Could not resend the code. Wait a minute and try again.", "error")
        return redirect(url_for("verify_email", email=email))
    flash("A new OTP was requested. Check your inbox and spam folder.", "ok")
    return redirect(url_for("verify_email", email=email))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Enter your email and password.", "error")
            return render_template("login.html")

        try:
            client = anon_client()
            result = client.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as exc:
            flash("Wrong email or password — try again.", "error")
            return render_template("login.html")

        try:
            profile = establish_session(result, email, email.split("@")[0])
        except Exception as exc:
            flash(f"Signed in, but setup failed: {exc}", "error")
            return render_template("login.html")
        is_new = not any((profile.get(f) or "").strip() for f in PROFILE_REQUIRED)
        if is_new:
            return redirect(url_for("profile_edit"))
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    try:
        anon_client().auth.sign_out()
    except Exception:
        pass
    session.clear()
    return redirect(url_for("index"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Enter your account email.", "error")
            return render_template("forgot_password.html")
        try:
            redirect_to = url_for("reset_password", _external=True)
            anon_client().auth.reset_password_for_email(email, {"redirect_to": redirect_to})
        except Exception:
            pass  # Never reveal whether an email exists — same message either way.
        flash("If that email has an account, a reset link is on its way. Check your inbox (and spam folder).", "ok")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password")
def reset_password():
    # The recovery token arrives in the URL fragment (#access_token=...),
    # which the browser never sends to the server — so this page just
    # renders a shell and handles the token entirely in JS. See
    # templates/reset_password.html.
    return render_template("reset_password.html", supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY)


# ---------------------------------------------------------------------------
# Dashboard / profile / resumes
# ---------------------------------------------------------------------------
@app.route("/portfolio")
@login_required
def portfolio_view():
    uid = current_user_id()
    client = authed_client()
    profile = get_or_create_profile(client, uid)
    links = get_profile_links(client, profile["id"])
    photo_url = signed_photo_url(client, profile.get("profile_image_url"))
    resumes = client.table("resumes").select("*").eq("user_id", uid).order("updated_at", desc=True).execute().data
    portfolio_slug = profile_slug(profile)
    if request.args.get("save") and request.args.get("theme") in PORTFOLIO_THEME_MAP:
        try:
            client.table("profile").update({"portfolio_theme": request.args["theme"]}).eq("user_id", uid).execute()
            flash("Theme saved - your shared link now always uses it.", "ok")
        except Exception:
            flash("Add the portfolio_theme column in Supabase first (see SQL in chat).", "error")
    return render_template(
        "portfolio.html",
        user=session.get("user"),
        profile=profile,
        links=links,
        photo_url=photo_url,
        portfolio_slug=portfolio_slug,
        portfolio_url=portfolio_theme_url(portfolio_slug, request.args.get("theme", "studio")),
        resumes=resumes,
        template_map=TEMPLATE_MAP,
        portfolio_themes=PORTFOLIO_THEMES,
        selected_theme=request.args.get("theme", "studio"),
        portfolio_checklist=portfolio_checklist(profile, links, resumes),
    )


@app.route("/portfolio/<slug>")
def public_portfolio(slug):
    client = anon_client()
    profile_result = (client.table("profile").select("*")
                      .eq("public_slug", slug)
                      .eq("portfolio_published", True)
                      .limit(1).execute())
    profile = profile_result.data[0] if profile_result.data else None

    if not profile:
        return render_template("portfolio_public.html", user=None, profile=None, not_found=True)

    theme_id = request.args.get("theme") or profile.get("portfolio_theme") or "studio"
    if theme_id not in PORTFOLIO_THEME_MAP:
        theme_id = "studio"
    links = get_profile_links(client, profile["id"])
    photo_url = (
        public_photo_url(client, profile.get("profile_image_url"))
        if profile.get("profile_image_public")
        else None
    )
    first_resume = latest_resume(client, profile["user_id"]) or {}
    content = portfolio_content(first_resume.get("content"))
    return render_template(
        "portfolio_public.html",
        user=None,
        profile=profile,
        links=links,
        photo_url=photo_url,
        not_found=False,
        resumes=[first_resume] if first_resume else [],
        content=content,
        portfolio_url=public_portfolio_url(slug),
        summary=content["summary"] or (profile.get("bio") or ""),
        experience=content["experience"],
        education=content["education"],
        projects=content["projects"],
        skills=content["skills"],
        portfolio_theme=theme_id,
        portfolio_layout=THEME_LAYOUT[theme_id],
    )


@app.route("/dashboard")
@login_required
def dashboard():
    uid = current_user_id()
    client = authed_client()
    user_session = session.get("user") or {}

    try:
        profile = get_or_create_profile(client, uid, email=user_session.get("email", ""), default_name=user_session.get("name", ""))
    except Exception as e:
        print(f"[dashboard] profile load failed: {e}")
        profile = {"id": uid, "full_name": user_session.get("name", ""), "email": user_session.get("email", ""), "location": "", "mobile_number": ""}

    try:
        links = get_profile_links(client, profile.get("id")) if profile.get("id") else []
    except Exception as e:
        print(f"[dashboard] links load failed: {e}")
        links = []

    try:
        resumes_res = client.table("resumes").select("*").eq("user_id", uid).order("updated_at", desc=True).execute()
        resumes = resumes_res.data or []
    except Exception as e:
        print(f"[dashboard] resumes table load failed: {e}")
        resumes = []

    portfolio_slug = profile_slug(profile) if profile.get("id") else ""
    return render_template(
        "dashboard.html",
        user=user_session,
        profile=profile,
        completion=profile_completion(profile, links),
        resumes=resumes,
        template_map=TEMPLATE_MAP,
        portfolio_slug=portfolio_slug, portfolio_url=public_portfolio_url(portfolio_slug),
    )


@app.route("/profile")
@login_required
def profile_view():
    uid = current_user_id()
    client = authed_client()
    profile = get_or_create_profile(client, uid)
    links = get_profile_links(client, profile["id"])
    photo_url = signed_photo_url(client, profile.get("profile_image_url"))
    return render_template("profile.html", user=session.get("user"), profile=profile, links=links,
                            photo_url=photo_url, completion=profile_completion(profile, links))


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def profile_edit():
    uid = current_user_id()
    client = authed_client()
    profile = get_or_create_profile(client, uid, email=session["user"]["email"])

    if request.method == "POST":
        values = {f: request.form.get(f, "").strip() for f in PROFILE_FIELDS}

        try:
            new_photo_path = upload_profile_photo(client, request.files.get("photo"), uid)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("profile_edit"))
        if new_photo_path:
            values["profile_image_url"] = new_photo_path
            values["profile_image_public_url"] = public_photo_url(client, new_photo_path)
        values["profile_image_public"] = request.form.get("profile_image_public") == "on"
        values["portfolio_published"] = request.form.get("portfolio_published") == "on"

        if values["portfolio_published"]:
            resumes = (
                client.table("resumes")
                .select("content")
                .eq("user_id", uid)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
                .data
                or []
            )
            content = (resumes[0].get("content") or {}) if resumes else {}
            has_portfolio_content = any(
                content.get(section)
                for section in ("summary", "experience", "education", "projects", "skills")
            )
            if not values["full_name"] or not values["headline"] or not values["bio"] or not has_portfolio_content:
                values["portfolio_published"] = False
                flash("Add your name, headline, bio, and resume content before publishing your portfolio.", "error")

        client.table("profile").update(values).eq("user_id", uid).execute()

        platforms = request.form.getlist("link_platform[]")
        urls = request.form.getlist("link_url[]")
        labels = request.form.getlist("link_label[]")
        links = []
        for i, (platform, raw_url) in enumerate(zip(platforms, urls)):
            platform = (platform or "").strip()
            if platform == "Other":
                platform = (labels[i] if i < len(labels) else "").strip() or "Other"
            links.append((platform, normalize_link(platform, raw_url)))
        replace_profile_links(client, profile["id"], links)

        session["user"]["name"] = values["full_name"] or session["user"]["name"]
        flash("Profile saved.", "ok")
        return redirect(url_for("profile_view"))

    links = get_profile_links(client, profile["id"])
    photo_url = signed_photo_url(client, profile.get("profile_image_url"))
    return render_template("profile_edit.html", user=session.get("user"), profile=profile,
                            links=links, photo_url=photo_url, platform_choices=PLATFORM_CHOICES)

@app.route("/ats", methods=["GET", "POST"])
@login_required
def ats_check():
    result, resume_text, jd = None, "", ""
    if request.method == "POST":
        resume_text = request.form.get("resume", "")
        jd = request.form.get("jd", "")
        f = request.files.get("file")
        pdf_uploaded = bool(f and f.filename and f.filename.lower().endswith(".pdf"))
        if pdf_uploaded:
            try:
                from pypdf import PdfReader
                resume_text = "\n".join((p.extract_text() or "") for p in PdfReader(f).pages)
                if len(resume_text.strip()) < 50:
                    flash("This PDF has no readable text - which is exactly what an ATS would see too. Use a text-based PDF.", "error")
                    resume_text = ""
            except Exception:
                flash("Could not read that PDF - paste the text instead.", "error")
                resume_text = ""
        if resume_text.strip():
            result = ats_analyze(resume_text, jd)
        elif not pdf_uploaded:
            flash("Upload a PDF or paste your resume text.", "error")
    return render_template(
        "ats.html", result=result, resume_text=resume_text, jd=jd,
        resume_id=None, resume_title=None,
        analysis_action=url_for("ats_check"),
    )


def resume_text_for_ats(content, profile, user, links):
    """Flatten structured resume data into the text an ATS can evaluate."""
    lines = [
        profile.get("full_name") or user.get("name") or "",
        content.get("headline") or profile.get("headline") or "",
        user.get("email") or profile.get("email") or "",
        profile.get("mobile_number") or "",
        profile.get("location") or "",
    ]
    lines.extend(link.get("url", "") for link in links if link.get("url"))

    summary = content.get("summary")
    if summary:
        lines.extend(["", "Summary", str(summary)])

    for key, heading, fields in (
        ("experience", "Experience", ("title", "org", "start", "end", "desc")),
        ("education", "Education", ("degree", "school", "start", "end", "desc")),
        ("projects", "Projects", ("name", "link", "desc")),
    ):
        entries = content.get(key) or []
        if not isinstance(entries, list):
            continue
        section_lines = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            section_lines.extend(
                str(entry[field]).strip()
                for field in fields
                if field != "desc"
                if entry.get(field) and str(entry[field]).strip()
            )
            description = str(entry.get("desc") or "")
            section_lines.extend(
                "• " + line.lstrip("•-*▪ ").strip()
                for line in description.splitlines()
                if line.strip()
            )
        if section_lines:
            lines.extend(["", heading, *section_lines])

    skills = content.get("skills") or []
    if isinstance(skills, list) and skills:
        lines.extend(["", "Skills", ", ".join(str(skill) for skill in skills if skill)])
    return "\n".join(str(line) for line in lines if line)


@app.route("/ats/resume/<resume_id>", methods=["GET", "POST"])
@login_required
def ats_resume_check(resume_id):
    uid = current_user_id()
    client = authed_client()
    response = (
        client.table("resumes").select("*")
        .eq("id", resume_id).eq("user_id", uid).execute()
    )
    if not response.data:
        flash("Resume not found.", "error")
        return redirect(url_for("resume_gallery"))

    row = response.data[0]
    profile = get_or_create_profile(client, uid)
    links = get_profile_links(client, profile["id"])
    resume_text = resume_text_for_ats(
        row.get("content") or {}, profile, session.get("user") or {}, links,
    )
    jd = request.form.get("jd", "") if request.method == "POST" else ""
    result = ats_analyze(resume_text, jd) if request.method == "POST" else ats_analyze(resume_text)
    return render_template(
        "ats.html", result=result, resume_text=resume_text, jd=jd,
        resume_id=resume_id, resume_title=row.get("title"),
        analysis_action=url_for("ats_resume_check", resume_id=resume_id),
    )


@app.route("/resume")
@login_required
def resume_gallery():
    uid = current_user_id()
    client = authed_client()
    profile = get_or_create_profile(client, uid)
    links = get_profile_links(client, profile["id"])
    photo_url = signed_photo_url(client, profile.get("profile_image_url"))
    resume = latest_resume(client, uid) or {}
    resume_content = resume.get("content") or {}
    return render_template("resume_templates.html", user=session.get("user"),
                            profile=profile, links=links, photo_url=photo_url,
                            resume_content=resume_content or {}, templates=RESUME_TEMPLATES)


@app.route("/resume/new/<template_id>")
@login_required
def resume_new(template_id):
    if template_id not in TEMPLATE_MAP:
        flash("Unknown template.", "error")
        return redirect(url_for("resume_gallery"))

    uid = current_user_id()
    client = authed_client()
    profile = get_or_create_profile(client, uid)
    content = prefill_content_from_profile(profile)

    row = client.table("resumes").insert({
        "user_id": uid,
        "title": f"{profile.get('full_name') or 'My'} — resume",
        "template_id": template_id,
        "content": content,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute().data[0]
    return redirect(url_for("resume_builder", resume_id=row["id"]))


@app.route("/resume/<resume_id>", methods=["GET", "POST"])
@login_required
def resume_builder(resume_id):
    uid = current_user_id()
    client = authed_client()
    res = client.table("resumes").select("*").eq("id", resume_id).eq("user_id", uid).execute()
    if not res.data:
        flash("Resume not found.", "error")
        return redirect(url_for("resume_gallery"))
    row = res.data[0]

    if request.method == "POST":
        content_raw = request.form.get("content_json", "{}")
        try:
            content = json.loads(content_raw)
        except (ValueError, TypeError):
            content = empty_resume_content()

        template_id = request.form.get("template_id", row.get("template_id", ""))
        if template_id not in TEMPLATE_MAP:
            template_id = row.get("template_id", RESUME_TEMPLATES[0]["id"])
        font = request.form.get("font", "Manrope")
        if font not in FONT_PRESETS:
            font = "Manrope"
        accent = request.form.get("accent", "#c9ff45")
        if accent not in ACCENT_PRESETS:
            accent = "#c9ff45"

        client.table("resumes").update({
            "title": request.form.get("title", "Untitled resume").strip() or "Untitled resume",
            "template_id": template_id,
            "font": font,
            "accent": accent,
            "content": content,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", resume_id).eq("user_id", uid).execute()
        flash("Resume saved. Your portfolio now uses this version.", "ok")
        if request.form.get("intent") == "ats":
            return redirect(url_for("ats_resume_check", resume_id=resume_id))
        return redirect(url_for("resume_builder", resume_id=resume_id))

    profile = get_or_create_profile(client, uid)
    links = get_profile_links(client, profile["id"])
    photo_url = signed_photo_url(client, profile.get("profile_image_url"))
    content = row.get("content") or {}
    template = TEMPLATE_MAP.get(row.get("template_id"), RESUME_TEMPLATES[0])
    return render_template(
        "resume_builder.html", user=session.get("user"), resume=row, profile=profile,
        links=links, photo_url=photo_url, content=content, template=template,
        templates=RESUME_TEMPLATES, accents=ACCENT_PRESETS, fonts=FONT_PRESETS,
    )


@app.route("/resume/<resume_id>/delete", methods=["POST"])
@login_required
def resume_delete(resume_id):
    uid = current_user_id()
    authed_client().table("resumes").delete().eq("id", resume_id).eq("user_id", uid).execute()
    flash("Resume deleted.", "ok")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
