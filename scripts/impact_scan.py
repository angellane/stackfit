#!/usr/bin/env python3
"""
impact_scan.py - Estimate the blast radius of adding an integration.

Answers "what does this actually touch in *this* repo": which files are likely
to change, which infrastructure is missing, which env vars appear, and a
transparent effort band with its inputs shown rather than a number pulled from
the air.

Standard library only, Python 3.8+. Read-only, offline, deterministic.

Usage:
    python3 impact_scan.py --domain payments [PATH]
    python3 impact_scan.py --domain auth . --format json
    python3 impact_scan.py --list-domains

Exit codes: 0 ok, 2 bad arguments or path.
"""

import argparse
import json
import os
import posixpath
import re
import signal
import sys

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "__pycache__", ".venv", "venv", "dist",
    "build", "out", ".next", ".nuxt", ".svelte-kit", "target", "coverage",
    ".pytest_cache", ".mypy_cache", ".terraform", ".turbo", ".cache", "Pods",
    ".gradle", ".idea", ".dart_tool", "bin", "obj",
}

CODE_EXTS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".rb", ".go", ".rs",
    ".java", ".kt", ".swift", ".cs", ".php", ".ex", ".exs", ".vue", ".svelte",
    ".prisma", ".sql", ".graphql", ".scala", ".dart",
}

MAX_FILE_BYTES = 300_000

# Each domain describes what an integration in that area normally has to touch.
# `roles` map a human role -> (path regex, content regex). Either may be None.
DOMAINS = {
    "auth": {
        "label": "authentication / identity",
        "base_effort_days": (3, 8),
        "needs": ["session or token handling", "user record", "route protection"],
        "roles": {
            "user model / schema": (
                r"(models?|schema|entities)[./_-]|user\.(ts|js|py|rb|go|prisma)$",
                r"\b(class|model|table|interface)\s+Users?\b|users?\s*\(|@Entity",
            ),
            "existing auth logic": (
                r"(auth|login|signin|signup|session|register|password)",
                r"\b(signIn|sign_in|login|authenticate|jwt|bcrypt|hashPassword|set_password)\b",
            ),
            "route guards / middleware": (
                r"(middleware|guard|interceptor|decorator|permission)",
                r"\b(requireAuth|isAuthenticated|login_required|before_action|AuthGuard|getServerSession)\b",
            ),
            "protected pages / endpoints": (
                r"(pages|app|routes|views|controllers|api)/",
                r"\b(currentUser|current_user|req\.user|session\.user|useSession|request\.user)\b",
            ),
        },
    },
    "payments": {
        "label": "payments / subscriptions / billing",
        "base_effort_days": (5, 12),
        "needs": ["webhook endpoint", "idempotent event handling", "subscription state in DB",
                  "customer <-> user mapping"],
        "roles": {
            "user / account model": (
                r"(models?|schema|entities)[./_-]|user\.(ts|js|py|rb|go|prisma)$",
                r"\b(class|model|table|interface)\s+(Users?|Accounts?|Organizations?)\b",
            ),
            "existing billing / plan logic": (
                r"(billing|payment|subscription|plan|pricing|checkout|invoice|tier|quota)",
                r"\b(stripe|paddle|subscription|invoice|checkout|plan_id|priceId)\b",
            ),
            "webhook handlers": (
                r"(webhook|hooks?/|callback)",
                r"\b(webhook|constructEvent|verify_signature|X-Signature|rawBody)\b",
            ),
            "entitlement / gating checks": (
                None,
                r"\b(isPro|is_premium|hasAccess|can_access|entitle|feature_flag|planLimit)\b",
            ),
            "API route surface": (
                r"(app|pages|src)/api/|routes/|controllers/|urls\.py$",
                None,
            ),
        },
    },
    "storage": {
        "label": "file storage / uploads / media",
        "base_effort_days": (2, 6),
        "needs": ["upload endpoint or signed URLs", "file metadata records", "access control"],
        "roles": {
            "upload handling": (
                r"(upload|file|media|attachment|image|avatar|document)",
                r"\b(multipart|FormData|multer|upload|put_object|createReadStream|ActiveStorage)\b",
            ),
            "file metadata model": (
                r"(models?|schema|entities)",
                r"\b(file|attachment|media|document|asset)s?\b.*\b(url|key|path|bucket|mime)\b",
            ),
            "serving / rendering": (
                None,
                r"\b(src=\{|getSignedUrl|presigned|publicUrl|CDN_URL|image_url)\b",
            ),
        },
    },
    "email": {
        "label": "transactional email",
        "base_effort_days": (1, 4),
        "needs": ["template rendering", "sender identity/domain verification", "delivery failure handling"],
        "roles": {
            "existing send calls": (
                r"(mail|email|notify|smtp)",
                r"\b(sendMail|send_mail|sendEmail|deliver_now|EmailMessage|nodemailer|resend)\b",
            ),
            "templates": (
                r"(templates?|emails?)/",
                r"\b(subject|preheader|render_to_string|MjmlTemplate)\b",
            ),
            "trigger points": (
                None,
                r"\b(welcome|password_reset|reset_password|verify_email|receipt|invitation)\b",
            ),
        },
    },
    "notifications": {
        "label": "push / in-app / multi-channel notifications",
        "base_effort_days": (3, 8),
        "needs": ["device token or subscription storage", "user preferences", "delivery fan-out"],
        "roles": {
            "notification models": (
                r"(notification|alert|inbox|device|token)",
                r"\b(Notification|DeviceToken|push_token|subscription_endpoint)\b",
            ),
            "existing delivery paths": (
                None,
                r"\b(sendPush|notify|firebase|fcm|apns|OneSignal|web-push)\b",
            ),
            "user preference handling": (
                r"(settings|preferences|profile)",
                r"\b(notification_preferences|emailOptIn|unsubscribe)\b",
            ),
        },
    },
    "search": {
        "label": "search / indexing",
        "base_effort_days": (4, 10),
        "needs": ["index sync on write", "reindex/backfill job", "query surface"],
        "roles": {
            "searchable models": (
                r"(models?|schema|entities)",
                r"\b(title|name|description|body|content|tags)\b",
            ),
            "existing query logic": (
                r"(search|query|filter|browse)",
                r"\b(ILIKE|LIKE '%|full_text|tsvector|match\(|\.search\()\b",
            ),
            "write paths needing index sync": (
                None,
                r"\b(create|update|destroy|save|insert|upsert)\b.*\b(record|document|item|post|product)\b",
            ),
        },
    },
    "analytics": {
        "label": "product analytics / event tracking",
        "base_effort_days": (1, 4),
        "needs": ["event naming scheme", "identity stitching", "consent handling"],
        "roles": {
            "existing tracking": (
                None,
                r"\b(track\(|analytics\.|gtag|dataLayer|posthog|mixpanel|amplitude|segment)\b",
            ),
            "app entry points": (
                r"(_app|layout|main|index|App)\.(tsx|ts|jsx|js|vue|svelte)$",
                None,
            ),
            "key user actions": (
                None,
                r"\b(onSubmit|onClick|handleSignup|handlePurchase|checkout)\b",
            ),
        },
    },
    "realtime": {
        "label": "realtime / websockets / presence",
        "base_effort_days": (4, 10),
        "needs": ["persistent connection support at the host", "auth on connect", "fan-out strategy"],
        "roles": {
            "existing socket code": (
                r"(socket|ws|realtime|channel|presence|live)",
                r"\b(WebSocket|socket\.io|subscribe\(|broadcast|ActionCable|channels)\b",
            ),
            "state that must sync": (
                None,
                r"\b(useState|useEffect|store|reducer|observable)\b",
            ),
        },
    },
    "ai": {
        "label": "LLM / AI features",
        "base_effort_days": (3, 10),
        "needs": ["streaming response path", "token/cost controls", "prompt + eval storage"],
        "roles": {
            "existing model calls": (
                None,
                r"\b(openai|anthropic|completions|chat\.completions|messages\.create|embedding)\b",
            ),
            "content to embed or index": (
                r"(documents?|content|posts?|articles?|knowledge)",
                None,
            ),
            "streaming-capable endpoints": (
                r"(api|routes)/",
                r"\b(ReadableStream|StreamingResponse|text/event-stream|SSE)\b",
            ),
        },
    },
    "database": {
        "label": "database / backend platform change",
        "base_effort_days": (8, 25),
        "needs": ["dual-write or cutover plan", "schema parity", "connection pooling"],
        "roles": {
            "data access layer": (
                r"(db|database|models?|repositor|dao|prisma|schema)",
                r"\b(createClient|connect\(|Session\(|Pool\(|PrismaClient|createConnection)\b",
            ),
            "queries spread through app": (
                None,
                r"\b(findMany|findOne|SELECT |\.query\(|session\.execute|\.objects\.)\b",
            ),
            "migrations": (
                r"(migrations?|alembic|db/migrate)",
                None,
            ),
        },
    },
    "jobs": {
        "label": "background jobs / queues / scheduling",
        "base_effort_days": (3, 8),
        "needs": ["a runtime that can execute jobs", "retry and dead-letter policy",
                  "idempotent job bodies"],
        "roles": {
            "work that should be async": (
                None,
                r"\b(send_?mail|sendEmail|generate|process|import|export|sync|resize|transcode)\b",
            ),
            "existing job or worker code": (
                r"(worker|job|task|queue|cron|scheduler|celery|sidekiq)",
                r"\b(shared_task|@task|Queue\(|enqueue|perform_later|schedule)\b",
            ),
            "long request handlers": (
                r"(api|routes|controllers|views)",
                r"\b(await |time\.sleep|requests\.post|fetch\()\b",
            ),
        },
    },
    "sms": {
        "label": "SMS / voice messaging",
        "base_effort_days": (1, 4),
        "needs": ["phone number storage and validation", "opt-out handling",
                  "delivery status callbacks"],
        "roles": {
            "phone number storage": (
                r"(models?|schema|entities|user|profile|contact)",
                r"\b(phone|mobile|msisdn|phone_number|phoneNumber)\b",
            ),
            "existing send paths": (
                None,
                r"\b(twilio|vonage|nexmo|sendSms|send_sms|messages\.create)\b",
            ),
            "verification flows": (
                r"(verify|otp|2fa|mfa|confirm)",
                r"\b(otp|verification_code|verifyCode|two_factor)\b",
            ),
        },
    },
    "feature-flags": {
        "label": "feature flags / experimentation",
        "base_effort_days": (1, 5),
        "needs": ["evaluation at the right layer", "a default when the service is down",
                  "flag cleanup discipline"],
        "roles": {
            "existing conditionals worth flagging": (
                None,
                r"\b(isEnabled|featureFlag|feature_flag|ENABLE_|is_beta|rollout)\b",
            ),
            "config and settings": (
                r"(config|settings|constants|env)",
                None,
            ),
            "app entry points": (
                r"(_app|layout|main|index|App|providers?)\.(tsx|ts|jsx|js|vue|svelte|py)$",
                None,
            ),
        },
    },
    "cms": {
        "label": "content management / headless CMS",
        "base_effort_days": (3, 10),
        "needs": ["content model design", "preview and draft handling",
                  "cache invalidation on publish"],
        "roles": {
            "content currently in code or the database": (
                r"(content|posts?|articles?|pages?|blog|docs?|marketing)",
                r"\b(title|slug|body|excerpt|published_at|publishedAt)\b",
            ),
            "rendering layer": (
                r"(pages|app|templates|views|components)/",
                r"\b(getStaticProps|getStaticPaths|render_template|revalidate)\b",
            ),
            "existing CMS clients": (
                None,
                r"\b(contentful|sanity|strapi|payload|prismic|wordpress|ghost)\b",
            ),
        },
    },
    "observability": {
        "label": "error tracking / logging / APM",
        "base_effort_days": (1, 5),
        "needs": ["release and environment tagging", "PII scrubbing",
                  "alert routing to someone who acts on it"],
        "roles": {
            "existing logging and error handling": (
                r"(logger|logging|error|exception|monitor)",
                r"\b(console\.error|logger\.|logging\.|captureException|traceback)\b",
            ),
            "app entry and middleware": (
                r"(middleware|_app|main|index|server|wsgi|asgi)",
                None,
            ),
            "build config for source maps": (
                r"(next\.config|webpack|vite\.config|rollup|tsconfig)",
                None,
            ),
        },
    },
    "i18n": {
        "label": "internationalisation / localisation",
        "base_effort_days": (4, 15),
        "needs": ["locale routing or detection", "a translation workflow for non-developers",
                  "pluralisation and date/number formatting"],
        "roles": {
            "hardcoded user-facing strings": (
                r"(components?|pages|views|templates)/",
                r">[A-Z][a-z]+ [a-z ]{8,}<|\"[A-Z][a-z]+ [a-z ]{10,}\"",
            ),
            "existing translation setup": (
                r"(locales?|i18n|translations?|lang)",
                r"\b(useTranslation|gettext|t\(|i18n|FormattedMessage)\b",
            ),
            "routing": (
                r"(routes?|urls\.py|app/|pages/)",
                None,
            ),
        },
    },
    "documents": {
        "label": "PDF / document generation and signing",
        "base_effort_days": (2, 8),
        "needs": ["a rendering runtime that fits the host", "template versioning",
                  "storage for generated artefacts"],
        "roles": {
            "existing generation code": (
                r"(pdf|invoice|report|receipt|contract|document|export)",
                r"\b(pdfkit|puppeteer|weasyprint|reportlab|wkhtmltopdf|docx)\b",
            ),
            "templates": (
                r"(templates?|views)/",
                None,
            ),
            "data that feeds documents": (
                r"(models?|schema|entities)",
                r"\b(invoice|order|contract|agreement)\b",
            ),
        },
    },
    "maps": {
        "label": "maps / geocoding / location",
        "base_effort_days": (2, 8),
        "needs": ["coordinate storage and spatial queries", "API key restriction",
                  "usage caps to control cost"],
        "roles": {
            "location data": (
                r"(models?|schema|address|location|place|venue|store)",
                r"\b(latitude|longitude|lat\b|lng\b|geo|address|postcode|zip)\b",
            ),
            "existing map usage": (
                None,
                r"\b(mapbox|google\.maps|leaflet|GoogleMap|geocod)\b",
            ),
            "search and filter by distance": (
                None,
                r"\b(radius|nearby|distance|within|bounds)\b",
            ),
        },
    },
    "video": {
        "label": "video / audio streaming and calls",
        "base_effort_days": (4, 15),
        "needs": ["upload and transcoding pipeline or realtime SFU",
                  "playback access control", "bandwidth cost control"],
        "roles": {
            "existing media handling": (
                r"(video|audio|media|stream|call|room|meeting)",
                r"\b(mux|cloudflare.?stream|agora|daily|livekit|twilio.?video|hls|webrtc)\b",
            ),
            "media records": (
                r"(models?|schema|entities)",
                r"\b(duration|thumbnail|playback|asset_id|transcode)\b",
            ),
            "player or call UI": (
                r"(components?|pages|views)/",
                r"\b(<video|<audio|player|VideoPlayer)\b",
            ),
        },
    },
    "generic": {
        "label": "general third-party integration",
        "base_effort_days": (2, 8),
        "needs": ["credential storage and rotation", "error, timeout and retry handling",
                  "a local development path that doesn't need production keys"],
        "roles": {
            "existing outbound API clients": (
                r"(client|api|service|integration|adapter|provider|gateway)",
                r"\b(fetch\(|axios|requests\.|http\.|HttpClient|urlopen)\b",
            ),
            "configuration and credentials": (
                r"(config|settings|constants|env|secrets)",
                r"\b(API_KEY|SECRET|TOKEN|process\.env|os\.environ|getenv)\b",
            ),
            "data models the feature would extend": (
                r"(models?|schema|entities|prisma)",
                None,
            ),
            "app entry points": (
                r"(_app|layout|main|index|server|App)\.(tsx|ts|jsx|js|py|rb|go)$",
                None,
            ),
        },
    },
}

DOMAIN_ALIASES = {
    "authentication": "auth", "login": "auth", "identity": "auth", "sso": "auth",
    "billing": "payments", "subscriptions": "payments", "subscription": "payments",
    "payment": "payments", "checkout": "payments", "monetization": "payments",
    "files": "storage", "uploads": "storage", "upload": "storage", "media": "storage",
    "mail": "email", "transactional-email": "email",
    "push": "notifications", "notification": "notifications", "messaging": "notifications",
    "indexing": "search", "full-text-search": "search",
    "tracking": "analytics", "telemetry": "analytics", "events": "analytics",
    "websockets": "realtime", "presence": "realtime", "collaboration": "realtime",
    "llm": "ai", "genai": "ai", "rag": "ai", "embeddings": "ai",
    "db": "database", "backend": "database", "baas": "database",
    "queue": "jobs", "queues": "jobs", "background-jobs": "jobs", "worker": "jobs",
    "workers": "jobs", "cron": "jobs", "scheduling": "jobs", "scheduler": "jobs",
    "text-messages": "sms", "texting": "sms", "voice": "sms", "otp": "sms",
    "flags": "feature-flags", "feature-flag": "feature-flags",
    "experimentation": "feature-flags", "ab-testing": "feature-flags",
    "content": "cms", "headless-cms": "cms", "blog": "cms",
    "monitoring": "observability", "error-tracking": "observability",
    "logging": "observability", "apm": "observability", "tracing": "observability",
    "localization": "i18n", "localisation": "i18n", "translation": "i18n",
    "internationalization": "i18n", "translations": "i18n",
    "pdf": "documents", "pdfs": "documents", "invoicing": "documents",
    "e-signature": "documents", "esign": "documents", "signing": "documents",
    "geocoding": "maps", "location": "maps", "geo": "maps", "mapping": "maps",
    "streaming": "video", "transcoding": "video", "webrtc": "video",
    "video-calls": "video", "audio": "video",
}

# Infrastructure checks: (path regex, description, dependency markers).
# Dependency markers matter because a capability can come from a library rather
# than a directory name - a repo with Celery in requirements.txt has a job
# runner even if no folder is called "worker". Without this, impact_scan would
# contradict analyze_stack, which reads manifests.
INFRA_CHECKS = {
    "http_endpoint": (
        r"(app|pages|src)/api/|routes/|controllers/|urls\.py$|functions/|handlers/",
        "inbound HTTP route surface (needed for webhooks and OAuth callbacks)",
        ["django", "flask", "fastapi", "express", "fastify", "hono", "koa",
         "rails", "sinatra", "laravel", "next", "nuxt", "gin", "echo", "axum",
         "actix-web", "phoenix", "nestjs", "starlette"],
    ),
    "background_jobs": (
        r"(worker|job|task|queue|celery|sidekiq|cron|scheduler)",
        "background job runner (needed for retries, reconciliation, async work)",
        ["celery", "sidekiq", "resque", "bullmq", "bull", "rq", "dramatiq",
         "inngest", "temporal", "temporalio", "graphile-worker", "agenda",
         "kombu", "sqs", "faktory", "hangfire", "quartz", "node-cron", "node-schedule",
         "croner", "apscheduler", "rufus-scheduler"],
    ),
    "migrations": (
        r"(migrations?|alembic|db/migrate|prisma/migrations|drizzle)",
        "migration tooling (needed for any schema change)",
        ["alembic", "prisma", "drizzle-kit", "flyway", "liquibase",
         "django", "activerecord", "knex", "typeorm", "golang-migrate"],
    ),
    "tests": (
        r"(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.[a-z]+$|(^|/)test_[^/]+\.py$",
        "test suite (lowers regression risk on stateful integrations)",
        [],
    ),
    "env_template": (
        r"\.env\.(example|sample|template|dist)$|env\.example$",
        "env template (where new credentials get documented)",
        [],
    ),
    "secrets_management": (
        r"(secrets?|vault|\.github/workflows|k8s|helm)",
        "somewhere to put production secrets",
        [],
    ),
}

# Work that runs without a request keeps running after a user loses access, so
# for features that gate access it needs the same check as the routes. Finding
# it takes two signals together: something that runs on a schedule or in a
# worker, and something that spends money per call. Neither alone is enough -
# plenty of jobs are free, and plenty of paid calls happen inside requests.
ACCESS_DOMAINS = {"payments", "auth"}

SCHEDULE_PATTERNS = [
    ("setInterval loop", r"\bsetInterval\s*\("),
    ("cron schedule", r"\bcron\.schedule\s*\(|\bnew\s+CronJob\s*\(|\bschedule\.scheduleJob\s*\("),
    ("NestJS schedule", r"@(Cron|Interval)\s*\("),
    # BullMQ's Worker takes a processor as its second argument; a browser Web
    # Worker takes an options object, so exclude a literal `{` there.
    ("queue worker", r"\bnew\s+Worker\s*\(\s*['\"][^'\"]+['\"]\s*,\s*[^{\s]"),
    ("Celery task", r"@(shared_task|app\.task|celery\.task)\b|\bbeat_schedule\b"),
    ("APScheduler", r"\b(BlockingScheduler|BackgroundScheduler|AsyncIOScheduler)\s*\(|\.add_job\s*\("),
    ("schedule library", r"\bschedule\.every\s*\("),
    ("Sidekiq / ActiveJob", r"\binclude\s+Sidekiq::(Job|Worker)\b|<\s*(ApplicationJob|ActiveJob::Base)\b"),
    ("Inngest function", r"\binngest\.createFunction\s*\("),
    ("Trigger.dev task", r"\b(schedules\.)?task\s*\(\s*\{\s*id\s*:"),
    ("Workers cron handler", r"\basync\s+scheduled\s*\("),
    ("ticker / cron loop", r"\btime\.NewTicker\s*\(|\bcron\.New\s*\("),
    ("polling loop", r"\bwhile\s*\(?\s*(True|true)\s*\)?\s*[:{][\s\S]{0,800}?\bsleep\s*\("),
]
SCHEDULE_RES = [(label, re.compile(pattern)) for label, pattern in SCHEDULE_PATTERNS]

# setInterval in a UI component is client polling, not a job.
CLIENT_EXTS = {".tsx", ".jsx", ".vue", ".svelte"}

OUTBOUND_PATTERNS = [
    ("HTTP request", r"\bfetch\s*\(|\baxios\b|\bgot\s*\(|\brequests\.(get|post|put|patch|request)\s*\("
                     r"|\bhttpx\.|\baiohttp\b|\burllib\.request\b|\bhttp\.(Get|Post|NewRequest)\b"
                     r"|\bNet::HTTP\b|\bFaraday\b|\bHTTParty\b"),
    ("OpenAI", r"\bopenai\b"),
    ("Anthropic", r"\banthropic\b"),
    ("Google AI", r"@google/genai|@google/generative-ai|google\.generativeai|google\.genai|\bvertexai\b"),
    ("AI SDK", r"\b(generateText|streamText|generateObject|streamObject)\s*\("),
    ("Twilio", r"\btwilio\b"),
    ("email API", r"\b(resend|sendgrid|postmark|mailgun|nodemailer)\b"),
    ("AWS SDK", r"@aws-sdk/|\bboto3\b"),
]
OUTBOUND_RES = [(label, re.compile(pattern, re.I)) for label, pattern in OUTBOUND_PATTERNS]

# Presence of these words is weak evidence of a real check; their absence is
# the strong signal, which is why the output says "none seen" rather than "ok".
ACCESS_CHECK_RE = re.compile(
    r"\b(subscriptions?|subscribed|entitle\w*|isPro|is_pro|isPremium|is_premium|hasAccess|"
    r"has_access|canAccess|can_access|planLimit|plan_limit|billing|trial\w*|"
    r"active_subscription|plan(Id|_id|Status|_status))\b")

WORKER_PATH_RE = re.compile(
    r"(^|/)(workers?|jobs?|crons?|schedulers?|tasks|queues?|consumers?)(/|\.[a-z]+$)", re.I)
TEST_PATH_RE = re.compile(INFRA_CHECKS["tests"][0], re.I)

JS_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s+|\brequire\s*\(\s*|\bimport\s*\(\s*)['"]((?:\.{1,2}|@|~)/[^'"]+)['"]""")
PY_IMPORT_RE = re.compile(r"^\s*from\s+(\.*)([\w.]*)\s+import\b", re.M)
JS_EXTS = [".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx"]
BACKGROUND_CAP = 20


def _resolve_import(rel, spec, code_set, python=False):
    """Resolve one import to a repo file, or None. Relative, `@/` and `~/` only."""
    here = posixpath.dirname(rel)
    if python:
        dots, module = spec
        parts = [p for p in module.split(".") if p]
        if dots:
            base = here
            for _ in range(len(dots) - 1):
                base = posixpath.dirname(base)
        else:
            base = ""
        stem = posixpath.join(base, *parts) if parts else base
        for candidate in (stem + ".py", posixpath.join(stem, "__init__.py")):
            candidate = candidate.lstrip("/")
            if candidate in code_set:
                return candidate
        return None
    if spec[:2] in ("@/", "~/"):
        bases = [spec[2:], "src/" + spec[2:]]
    else:
        joined = posixpath.normpath(posixpath.join(here, spec))
        if joined.startswith(".."):
            return None
        bases = [joined]
    for base in bases:
        stems = [base]
        root_ext = posixpath.splitext(base)
        if root_ext[1] in JS_EXTS:
            stems.append(root_ext[0])  # TS ESM imports name the compiled .js file
        for stem in stems:
            for candidate in [stem] + [stem + e for e in JS_EXTS] + [stem + "/index" + e for e in JS_EXTS]:
                if candidate in code_set:
                    return candidate
    return None


def _imports(rel, content, code_set):
    python = rel.endswith(".py")
    if python:
        specs = [(m.group(1), m.group(2)) for m in PY_IMPORT_RE.finditer(content)]
    else:
        specs = [m.group(1) for m in JS_IMPORT_RE.finditer(content)]
    found = []
    for spec in specs:
        target = _resolve_import(rel, spec, code_set, python=python)
        if target and target != rel and target not in found:
            found.append(target)
    return found


def _config_schedules(root, all_files, code_set):
    """Schedules declared in config rather than code: [(source, label, handler)]."""
    noext = {}
    for rel in sorted(code_set):
        noext.setdefault(os.path.splitext(rel)[0], rel)
    found = []
    for rel in all_files:
        base = os.path.basename(rel)
        abs_path = os.path.join(root, rel.replace("/", os.sep))
        if base == "vercel.json":
            try:
                crons = json.loads(read_code(abs_path) or "{}").get("crons") or []
            except (ValueError, AttributeError):
                crons = []
            for cron in crons:
                if not isinstance(cron, dict) or not cron.get("path"):
                    continue
                route = cron["path"].split("?")[0].strip("/")
                handler = next((f for key, f in sorted(noext.items())
                                if key == route or key.endswith("/" + route)
                                or key.endswith(route + "/route") or key.endswith(route + "/index")),
                               None)
                found.append((rel, "Vercel cron {} ({})".format(cron["path"], cron.get("schedule", "?")),
                              handler))
        elif base == "Procfile":
            for line in read_code(abs_path).splitlines():
                match = re.match(r"^([\w-]+)\s*:\s*(.+)$", line.strip())
                if not match or match.group(1) in ("web", "release"):
                    continue
                handler = None
                for token in match.group(2).split():
                    token = token.strip("'\"").lstrip("./")
                    stem = os.path.splitext(token)[0]
                    for candidate in (token, stem, re.sub(r"^(dist|build|lib)/", "src/", stem),
                                      re.sub(r"^(dist|build|lib)/", "", stem)):
                        handler = candidate if candidate in code_set else noext.get(candidate)
                        if handler:
                            break
                    if handler:
                        break
                found.append((rel, "Procfile process '{}'".format(match.group(1)), handler))
        elif base in ("wrangler.toml", "wrangler.jsonc", "wrangler.json"):
            if re.search(r"\bcrons\"?\s*[=:]", read_code(abs_path)):
                found.append((rel, "Cloudflare cron trigger", None))
        elif re.search(r"\.ya?ml$", base):
            text = read_code(abs_path)
            if (rel.startswith(".github/workflows/") and "cron" in text
                    and re.search(r"^\s*schedule\s*:", text, re.M)):
                found.append((rel, "GitHub Actions schedule", None))
            if re.search(r"^\s*kind\s*:\s*CronJob\b", text, re.M):
                found.append((rel, "Kubernetes CronJob", None))
    return found


def _outbound(content):
    return [label for label, regex in OUTBOUND_RES if regex.search(content)]


def find_background_work(root, all_files, code_files, candidates):
    """Build the list of work outside the request path.

    `candidates` maps a code file to the schedule triggers found in it during the
    main scan. Config-declared schedules are merged in, then each entry's own
    content and its direct imports are checked for paid calls and access checks.
    """
    code_set = set(code_files)
    entries = {rel: {"triggers": list(triggers), "config_only": False}
               for rel, triggers in candidates.items()}
    config = _config_schedules(root, all_files, code_set)
    for source, label, handler in config:
        if handler:
            entry = entries.setdefault(handler, {"triggers": [], "config_only": False})
            entry["triggers"].append(label + " in " + source)
        else:
            entry = entries.setdefault(source, {"triggers": [], "config_only": True})
            entry["triggers"].append(label)

    results = []
    for rel in sorted(entries):
        entry = entries[rel]
        if entry["config_only"]:
            results.append({"file": rel, "triggers": entry["triggers"], "calls": [],
                            "access_check_seen": None,
                            "note": "schedule declared here; open it to find what runs"})
            continue
        content = read_code(os.path.join(root, rel.replace("/", os.sep)))
        calls = _outbound(content)
        access = bool(ACCESS_CHECK_RE.search(content))
        for dep in _imports(rel, content, code_set):
            dep_content = read_code(os.path.join(root, dep.replace("/", os.sep)))
            calls += ["{} (via {})".format(label, dep) for label in _outbound(dep_content)
                      if label not in calls]
            access = access or bool(ACCESS_CHECK_RE.search(dep_content))
        # A file that is only in a worker-ish folder, with no schedule and no
        # paid call, is noise: types, constants, fixtures.
        if entry["triggers"] == ["in a worker/job/cron path"] and not calls:
            continue
        results.append({"file": rel, "triggers": entry["triggers"], "calls": calls,
                        "access_check_seen": access, "note": None})
    return results, config


MANIFEST_NAMES = {
    "package.json", "requirements.txt", "requirements-dev.txt", "pyproject.toml",
    "Pipfile", "go.mod", "Cargo.toml", "Gemfile", "composer.json", "pom.xml",
    "build.gradle", "build.gradle.kts", "mix.exs", "pubspec.yaml",
}


def read_manifest_text(root, files):
    """Concatenate manifest contents once, lowercased, for dependency marker checks."""
    chunks = []
    for rel in files:
        if os.path.basename(rel) in MANIFEST_NAMES:
            chunks.append(read_code(os.path.join(root, rel.replace("/", os.sep))).lower())
    return "\n".join(chunks)


def resolve_domain(raw):
    """Map free-text feature descriptions onto a domain.

    Developers describe features, not taxonomies - "e-signature for contracts" or
    "add stripe billing" should land somewhere useful rather than erroring. Exact
    match wins, then a known term appearing anywhere in the phrase, then None so
    the caller can fall back to the generic profile.
    """
    if not raw:
        return None
    text = raw.strip().lower()
    if text in DOMAINS:
        return text
    if text in DOMAIN_ALIASES:
        return DOMAIN_ALIASES[text]
    tokens = [t for t in re.split(r"[^a-z0-9-]+", text) if t]
    # Longest known term first so "feature-flags" beats a bare "flags".
    known = sorted(list(DOMAINS) + list(DOMAIN_ALIASES), key=len, reverse=True)
    for term in known:
        if term in tokens or (("-" in term or " " in term) and term in text):
            return DOMAIN_ALIASES.get(term, term)
    return None


def iter_code_files(root, max_files):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
            if any(part in SKIP_DIRS for part in rel.split("/")):
                continue
            files.append(rel)
            if len(files) >= max_files:
                return sorted(files)
    return sorted(files)


def read_code(path):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def scan(root, domain_key, max_files=8000, per_role_cap=12):
    domain = DOMAINS[domain_key]
    all_files = iter_code_files(root, max_files)
    code_files = [f for f in all_files if os.path.splitext(f)[1].lower() in CODE_EXTS]

    compiled = {}
    for role, (path_pattern, content_pattern) in domain["roles"].items():
        compiled[role] = (
            re.compile(path_pattern, re.I) if path_pattern else None,
            re.compile(content_pattern, re.I) if content_pattern else None,
        )

    hits = {role: [] for role in domain["roles"]}
    touched = set()
    schedule_candidates = {}
    for rel in code_files:
        abs_path = os.path.join(root, rel.replace("/", os.sep))
        content = None
        for role, (path_re, content_re) in compiled.items():
            path_match = bool(path_re.search(rel)) if path_re else False
            content_match = False
            if content_re is not None and (path_re is None or not path_match):
                if content is None:
                    content = read_code(abs_path)
                content_match = bool(content_re.search(content))
            elif content_re is not None and path_match:
                if content is None:
                    content = read_code(abs_path)
                content_match = bool(content_re.search(content))
            # A path-only role matches on path; a content-only role on content;
            # a role with both matches if either signal fires (path is a strong
            # hint even when the file does not yet contain the code).
            if (path_re is not None and path_match) or content_match:
                hits[role].append(rel)
                touched.add(rel)

        if TEST_PATH_RE.search(rel):
            continue
        if content is None:
            content = read_code(abs_path)
        client = (os.path.splitext(rel)[1].lower() in CLIENT_EXTS
                  or re.search(r"^\s*['\"]use client['\"]", content, re.M))
        triggers = [label for label, regex in SCHEDULE_RES
                    if regex.search(content) and not (client and label == "setInterval loop")]
        if not triggers and WORKER_PATH_RE.search(rel):
            triggers = ["in a worker/job/cron path"]
        if triggers:
            schedule_candidates[rel] = triggers

    background, config_schedules = find_background_work(
        root, all_files, code_files, schedule_candidates)
    gates_access = domain_key in ACCESS_DOMAINS
    unchecked = [e for e in background if e["calls"] and e["access_check_seen"] is False]
    if gates_access:
        touched.update(e["file"] for e in background if e["calls"])

    manifest_text = read_manifest_text(root, all_files)
    infra = {}
    for key, (pattern, description, markers) in INFRA_CHECKS.items():
        regex = re.compile(pattern, re.I)
        matches = [f for f in all_files if regex.search(f)]
        dep_hits = [
            marker for marker in markers
            if re.search(r"(^|[^a-z0-9_-])" + re.escape(marker) + r"([^a-z0-9_-]|$)", manifest_text)
        ]
        examples = matches[:3] + ["dependency: " + m for m in dep_hits[:2]]
        infra[key] = {
            "present": bool(matches) or bool(dep_hits),
            "description": description,
            "examples": examples[:3],
            "from_dependency_only": bool(dep_hits) and not matches,
        }

    # A platform scheduler is a job runner even with no queue library or folder.
    platform_crons = [source for source, label, _ in config_schedules
                      if label.startswith(("Vercel cron", "Cloudflare cron", "Kubernetes CronJob"))]
    jobs = infra["background_jobs"]
    if platform_crons and not jobs["present"]:
        jobs["present"] = True
        jobs["examples"] = sorted(set(platform_crons))[:3]

    env_keys = set()
    for rel in all_files:
        base = os.path.basename(rel)
        if re.search(r"\.env\.(example|sample|template|dist)$|^env\.example$", base):
            for line in read_code(os.path.join(root, rel.replace("/", os.sep))).splitlines():
                match = re.match(r"^(?:export\s+)?([A-Z0-9_]{2,})\s*=", line.strip())
                if match:
                    env_keys.add(match.group(1))

    # Effort band: base range for the domain, scaled by how much surface the
    # scan actually found, plus explicit penalties for missing infrastructure.
    # Shown with its inputs so a reader can disagree with the arithmetic.
    low, high = domain["base_effort_days"]
    touch_count = len(touched)
    if touch_count > 60:
        surface_factor, surface_note = 1.6, "large touch surface (>60 files)"
    elif touch_count > 25:
        surface_factor, surface_note = 1.3, "moderate touch surface (26-60 files)"
    elif touch_count > 8:
        surface_factor, surface_note = 1.0, "contained touch surface (9-25 files)"
    else:
        surface_factor, surface_note = 0.8, "small touch surface (<=8 files)"

    penalties = []
    penalty_days = 0.0
    if not infra["http_endpoint"]["present"] and domain_key in {"payments", "auth", "notifications"}:
        penalties.append("no HTTP route surface: webhook/callback endpoint must be built")
        penalty_days += 1.5
    if not infra["background_jobs"]["present"] and domain_key in {"payments", "search", "notifications", "ai"}:
        penalties.append("no job runner: async retries/reconciliation need new infrastructure")
        penalty_days += 2.0
    if not infra["migrations"]["present"] and domain_key in {"payments", "auth", "search", "database", "notifications"}:
        penalties.append("no migration tooling: schema changes have no repeatable path")
        penalty_days += 1.0
    if not infra["tests"]["present"]:
        penalties.append("no test suite: verification is manual, so allow rework time")
        penalty_days += 1.0
    if gates_access and unchecked:
        penalties.append("{} background job(s) make outbound calls with no access check seen: "
                         "each needs gating".format(len(unchecked)))
        penalty_days += min(2.0, 0.5 * len(unchecked))

    effort = {
        "low_days": round(low * surface_factor + penalty_days, 1),
        "high_days": round(high * surface_factor + penalty_days, 1),
        "inputs": {
            "domain_base_days": [low, high],
            "surface_factor": surface_factor,
            "surface_note": surface_note,
            "files_touched": touch_count,
            "penalty_days": round(penalty_days, 1),
            "penalties": penalties,
        },
        "caveat": ("Heuristic band for one experienced developer familiar with this codebase. "
                   "It counts surface area, not product complexity - treat it as a floor."),
    }

    return {
        "schema_version": 1,
        "root": os.path.abspath(root),
        "domain": domain_key,
        "domain_label": domain["label"],
        "files_scanned": len(all_files),
        "code_files_scanned": len(code_files),
        "touchpoints": {
            role: {"count": len(paths), "files": paths[:per_role_cap],
                   "truncated": len(paths) > per_role_cap}
            for role, paths in sorted(hits.items())
        },
        "total_files_touched": touch_count,
        "background_work": {
            "count": len(background),
            "entries": background[:BACKGROUND_CAP],
            "truncated": len(background) > BACKGROUND_CAP,
            "unchecked_paid_work": [e["file"] for e in unchecked] if gates_access else [],
            "note": ("Work that runs without a request. For features that gate access, "
                     "each entry making paid calls needs the same check as the routes. "
                     "Imports are followed one level; read the files to confirm."),
        },
        "infrastructure": infra,
        "required_capabilities": domain["needs"],
        "existing_env_keys": sorted(env_keys),
        "effort_estimate": effort,
    }


def render_text(result):
    lines = []
    add = lines.append
    add("IMPACT SCAN: {} ({})".format(result["domain_label"], result["domain"]))
    add("repo: {}".format(result["root"]))
    add("scanned {} files ({} code files)".format(
        result["files_scanned"], result["code_files_scanned"]))
    add("")
    add("LIKELY TOUCHPOINTS ({} distinct files)".format(result["total_files_touched"]))
    any_hits = False
    for role, data in result["touchpoints"].items():
        if not data["count"]:
            continue
        any_hits = True
        add("  {} - {} file(s)".format(role, data["count"]))
        for path in data["files"]:
            add("      {}".format(path))
        if data["truncated"]:
            add("      ... and {} more".format(data["count"] - len(data["files"])))
    if not any_hits:
        add("  No matching files. Either this is greenfield for this domain, or the code")
        add("  lives somewhere the patterns miss - confirm by reading the repo directly.")
    background = result["background_work"]
    if background["entries"]:
        add("")
        add("WORK OUTSIDE THE REQUEST PATH ({} found)".format(background["count"]))
        unchecked = set(background["unchecked_paid_work"])
        for entry in background["entries"]:
            add("  {}".format(entry["file"]))
            add("      runs: {}".format("; ".join(entry["triggers"])))
            if entry["note"]:
                add("      " + entry["note"])
                continue
            add("      calls: {}".format(", ".join(entry["calls"]) or "no outbound calls seen"))
            if entry["file"] in unchecked:
                add("      ! no access check seen - users who lose access may keep costing money")
        if background["truncated"]:
            add("  ... and {} more".format(background["count"] - len(background["entries"])))
    add("")
    add("INFRASTRUCTURE READINESS")
    for key, data in sorted(result["infrastructure"].items()):
        mark = "present" if data["present"] else "MISSING"
        add("  [{}] {} - {}".format(mark, key, data["description"]))
        if data["present"] and data["examples"]:
            add("      e.g. {}".format(", ".join(data["examples"])))
    add("")
    add("THIS DOMAIN NORMALLY REQUIRES")
    for need in result["required_capabilities"]:
        add("  - " + need)
    effort = result["effort_estimate"]
    add("")
    add("EFFORT BAND: {}-{} developer-days".format(effort["low_days"], effort["high_days"]))
    inputs = effort["inputs"]
    add("  base {}-{} days x {} ({}) + {} penalty days".format(
        inputs["domain_base_days"][0], inputs["domain_base_days"][1],
        inputs["surface_factor"], inputs["surface_note"], inputs["penalty_days"]))
    for penalty in inputs["penalties"]:
        add("    + " + penalty)
    add("  " + effort["caveat"])
    return "\n".join(lines)


def _allow_piping():
    """Exit quietly when output is piped into something like `head`.

    Without this, `analyze_stack.py . | head` prints a BrokenPipeError
    traceback, which looks like a crash in what is a completely normal usage.
    """
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def main(argv=None):
    _allow_piping()
    parser = argparse.ArgumentParser(description="Estimate integration blast radius.")
    parser.add_argument("path", nargs="?", default=".", help="repository root (default: .)")
    parser.add_argument("--domain", help="feature domain, e.g. payments, auth, search")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--max-files", type=int, default=8000)
    parser.add_argument("--list-domains", action="store_true")
    args = parser.parse_args(argv)

    if args.list_domains:
        for key in sorted(DOMAINS):
            print("{:<14} {}".format(key, DOMAINS[key]["label"]))
        print("\naliases: " + ", ".join(
            "{}->{}".format(k, v) for k, v in sorted(DOMAIN_ALIASES.items())))
        return 0

    if not args.domain:
        sys.stderr.write("error: --domain is required (see --list-domains)\n")
        return 2
    domain = resolve_domain(args.domain)
    if not domain:
        # Fall back rather than fail: the workflow applies to any integration, and
        # a feature without a named domain still deserves a touchpoint scan. The
        # note tells the caller the scan was broad so it can be said in the report.
        sys.stderr.write(
            "note: no specific playbook for '{}', scanning with the generic profile. "
            "Named domains: {}\n".format(args.domain, ", ".join(sorted(DOMAINS))))
        domain = "generic"
    if not os.path.isdir(args.path):
        sys.stderr.write("error: not a directory: {}\n".format(args.path))
        return 2

    result = scan(args.path, domain, max_files=args.max_files)
    print(json.dumps(result, indent=2, sort_keys=True) if args.format == "json"
          else render_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
