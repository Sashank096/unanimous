# U_NANI_MOUS

U_NANI_MOUS is a Flask application for building a professional profile, ATS-aware
resumes, and a shareable portfolio from one set of career details. It uses
Supabase for authentication, PostgreSQL, and image storage, and can be deployed
to Vercel.

## Features

- Email sign-up and sign-in with Supabase Auth, OTP email verification,
  password reset, and logout.
- Profile editing for name, headline, bio, contact details, location, profile
  photo, and professional links.
- A dashboard with profile completion, saved resumes, and portfolio status.
- Resume creation and editing with multiple templates, experience, education,
  projects, skills, font and accent options, and print-to-PDF.
- ATS feedback for pasted resume text, PDF uploads, job descriptions, and saved
  resumes. Results are heuristic guidance, not a guarantee of how an employer's
  ATS will rank a resume.
- Public portfolios with shareable slugs, themes, profile links, projects, and
  selected resume content.
- Optional Gemini-powered project/content enhancement.

## Technology

- Python 3.10+
- Flask and Jinja2
- Supabase Auth, PostgreSQL, Storage, and Edge Functions
- Vanilla JavaScript and CSS
- Vercel Python runtime

## Run locally

In PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in the required values in `.env`, then start the server:

```powershell
python app.py
```

Open <http://127.0.0.1:5000>.

If PowerShell blocks environment activation, run the interpreter and pip
directly with `.\.venv\Scripts\python.exe`.

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | Supabase publishable/anon key used by the app |
| `SECRET_KEY` | Yes in production | Signs Flask session cookies; use a long random value |
| `PUBLIC_APP_URL` | Recommended | Base URL used to create portfolio share links |
| `GEMINI_API_KEY` | Optional | Enables Gemini-backed enhancement endpoints |

Copy `.env.example` to `.env` as a starting point. Never commit `.env`, service
role keys, Resend credentials, or webhook signing secrets. The browser-facing
Supabase key is intended for client access; database RLS policies must remain
enabled.

## Supabase setup

1. Create or select a Supabase project and set its URL and publishable/anon key
   in `.env`.
2. In the Supabase SQL Editor, run the files in
   `supabase/migrations/` in filename order:
   - `20261002000000_profile_portfolio_tables.sql`
   - `20261002124500_public_profile_image_urls.sql`
3. Enable the Email provider in Supabase Auth. Configure the app's redirect and
   email OTP settings to match the deployed application.
4. The migrations create the `profile` and `profile_links` tables, row-level
   security policies, and the `profile-images` Storage bucket.

The profile row stores a Storage object path in `profile_image_url`. The
`profile_image_public_url` field is a clickable URL for the image in the
Supabase Table Editor. **Profile image URLs are public:** anyone who obtains a
URL can view that image. Do not store private images in this bucket.

### Optional email OTP delivery with Resend

The Supabase Edge Function in `supabase/functions/send-auth-email/` sends
Supabase Auth email-hook requests through Resend. To enable it:

1. Verify a sending domain in Resend and create an API key.
2. Deploy the function with the Supabase CLI:

   ```powershell
   supabase link --project-ref YOUR_PROJECT_REF
   supabase functions deploy send-auth-email
   ```

3. Set `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, and `SEND_EMAIL_HOOK_SECRETS` as
   **Supabase Edge Function secrets**. Use the full signing secret generated
   when configuring the hook. Keep these secrets out of `.env` and source
   control.
4. In Supabase Auth Hooks, configure an HTTP Send Email hook pointing to
   `https://YOUR_PROJECT_REF.supabase.co/functions/v1/send-auth-email`.
5. Test with an email address permitted by your Resend account.

The function verifies Supabase's signed webhook request. Do not disable or
remove that verification when deploying the endpoint.

## Main routes

| Route | Purpose |
| --- | --- |
| `/` | Landing page |
| `/signup`, `/verify-email`, `/login` | Authentication |
| `/forgot-password`, `/reset-password` | Password recovery |
| `/dashboard` | Signed-in user's dashboard |
| `/profile`, `/profile/edit` | View and edit career profile |
| `/portfolio` | Manage portfolio settings |
| `/portfolio/<slug>` | View a published portfolio |
| `/resume` | Browse resume templates |
| `/resume/new/<template_id>` | Create a resume from a template |
| `/resume/<resume_id>` | Edit and print a saved resume |
| `/ats` | Analyze pasted resume text or a PDF |
| `/ats/resume/<resume_id>` | Analyze a saved resume |

## Project layout

```text
app.py                         Flask routes and application logic
ats.py                         ATS analysis helpers
templates/                     Jinja2 pages and shared partials
static/css/                    Application, resume, and ATS styles
static/js/                     Browser interactions and resume builder
supabase/functions/             Supabase Edge Functions
supabase/migrations/            PostgreSQL schema and Storage setup
requirements.txt               Python dependencies
vercel.json                    Vercel routing/build configuration
```

## Data model overview

- `auth.users` is managed by Supabase Auth.
- `public.profile` stores one career profile per Auth user, including name,
  contact details, public portfolio settings, and profile photo paths/URLs.
- `public.profile_links` stores the user's many professional links, ordered by
  `display_order`.
- `public.resumes` stores saved resume content, associated with its owner.
- Profile photos are file objects in the `profile-images` Storage bucket; the
  profile table stores their object path and public URL, not image bytes.

Application tables and Storage should retain their row-level security and
object policies. Public portfolio/profile policies expose published profile
data; avoid adding broad anonymous access to private user records.

## Deploy to Vercel

1. Import this GitHub repository into Vercel and select the Python project.
2. Add `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SECRET_KEY`, and `PUBLIC_APP_URL`
   under the Vercel project's environment variables. Add `GEMINI_API_KEY` only
   if using the optional AI feature.
3. Deploy, then test authentication, profile uploads, resume saving, and public
   portfolio links against the production Supabase project.

The current deployment is <https://unanimous-topaz.vercel.app>.
Set a production `SECRET_KEY`; never use a development fallback in production.

## Notes

- ATS results are informational and should be reviewed by a person.
- AI enhancement is optional and requires a valid Gemini API key.
- Profile photo files are served from a public Storage bucket to support
  clickable image URLs in Supabase Table Editor.
- Keep dependencies in `requirements.txt` up to date when adding Python
  packages.
