#!/usr/bin/env python3
"""
analyze_stack.py - Deterministic repository analysis for StackFit.

Reads a repository and reports the facts a recommendation has to be built on:
languages, frameworks, databases/ORMs, existing third-party vendors, deployment
target, background-job capability, and webhook readiness.

Design notes:
  * Standard library only, Python 3.8+. Runs offline. No writes to the repo.
  * Deterministic: identical input trees produce byte-identical JSON output.
  * Never reads secret material. Real `.env` files are skipped entirely; only
    `.env.example`-style templates are parsed, and only for key NAMES.

Usage:
    python3 analyze_stack.py [PATH] [--format json|text] [--max-files N]
    python3 analyze_stack.py . --format json > stack.json

Exit codes: 0 analysis succeeded (even if the repo looks empty), 2 bad path.
"""

import argparse
import json
import os
import re
import signal
import sys
from collections import Counter

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor",
    "__pycache__", ".venv", "venv", "env", ".env.d", "dist", "build", "out",
    ".next", ".nuxt", ".svelte-kit", ".output", "target", ".gradle", ".idea",
    ".vscode", "coverage", ".coverage", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".terraform", ".serverless", "Pods", "DerivedData",
    ".dart_tool", ".parcel-cache", ".turbo", ".cache", "tmp", ".tox",
    "site-packages", "migrations_backup", ".angular", "obj", "bin",
}

LANG_BY_EXT = {
    ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript",
    ".cts": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".py": "Python",
    ".rb": "Ruby", ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".kt": "Kotlin", ".kts": "Kotlin", ".swift": "Swift", ".m": "Objective-C",
    ".cs": "C#", ".php": "PHP", ".ex": "Elixir", ".exs": "Elixir",
    ".scala": "Scala", ".dart": "Dart", ".vue": "Vue", ".svelte": "Svelte",
    ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++", ".cc": "C++",
    ".sql": "SQL", ".sh": "Shell", ".clj": "Clojure", ".erl": "Erlang",
}

# dependency name -> (category, human label)
# Prefix entries end with "/" and match scoped package families.
SIGNATURES = {
    # --- web frameworks ---
    "next": ("framework", "Next.js"),
    "nuxt": ("framework", "Nuxt"),
    "@remix-run/": ("framework", "Remix"),
    "@sveltejs/kit": ("framework", "SvelteKit"),
    "astro": ("framework", "Astro"),
    "gatsby": ("framework", "Gatsby"),
    "express": ("framework", "Express"),
    "fastify": ("framework", "Fastify"),
    "koa": ("framework", "Koa"),
    "hono": ("framework", "Hono"),
    "@nestjs/": ("framework", "NestJS"),
    "django": ("framework", "Django"),
    "flask": ("framework", "Flask"),
    "fastapi": ("framework", "FastAPI"),
    "litestar": ("framework", "Litestar"),
    "starlette": ("framework", "Starlette"),
    "rails": ("framework", "Ruby on Rails"),
    "sinatra": ("framework", "Sinatra"),
    "laravel/framework": ("framework", "Laravel"),
    "symfony/framework-bundle": ("framework", "Symfony"),
    "spring-boot-starter-web": ("framework", "Spring Boot"),
    "github.com/gin-gonic/gin": ("framework", "Gin"),
    "github.com/labstack/echo": ("framework", "Echo"),
    "github.com/gofiber/fiber": ("framework", "Fiber"),
    "actix-web": ("framework", "Actix Web"),
    "axum": ("framework", "Axum"),
    "phoenix": ("framework", "Phoenix"),
    # --- frontend ---
    "react": ("frontend", "React"),
    "react-native": ("frontend", "React Native"),
    "vue": ("frontend", "Vue"),
    "svelte": ("frontend", "Svelte"),
    "@angular/core": ("frontend", "Angular"),
    "solid-js": ("frontend", "SolidJS"),
    "flutter": ("frontend", "Flutter"),
    "tailwindcss": ("frontend", "Tailwind CSS"),
    # --- ORM / data access ---
    "prisma": ("orm", "Prisma"),
    "@prisma/client": ("orm", "Prisma"),
    "drizzle-orm": ("orm", "Drizzle"),
    "typeorm": ("orm", "TypeORM"),
    "sequelize": ("orm", "Sequelize"),
    "mongoose": ("orm", "Mongoose"),
    "knex": ("orm", "Knex"),
    "kysely": ("orm", "Kysely"),
    "sqlalchemy": ("orm", "SQLAlchemy"),
    "alembic": ("orm", "Alembic (migrations)"),
    "django-orm": ("orm", "Django ORM"),
    "tortoise-orm": ("orm", "Tortoise ORM"),
    "peewee": ("orm", "Peewee"),
    "activerecord": ("orm", "ActiveRecord"),
    "gorm.io/gorm": ("orm", "GORM"),
    "diesel": ("orm", "Diesel"),
    "sqlx": ("orm", "SQLx"),
    "hibernate-core": ("orm", "Hibernate"),
    # --- databases / drivers ---
    "pg": ("database", "PostgreSQL"),
    "postgres": ("database", "PostgreSQL"),
    "psycopg2": ("database", "PostgreSQL"),
    "psycopg2-binary": ("database", "PostgreSQL"),
    "psycopg": ("database", "PostgreSQL"),
    "asyncpg": ("database", "PostgreSQL"),
    "mysql2": ("database", "MySQL"),
    "mysqlclient": ("database", "MySQL"),
    "pymysql": ("database", "MySQL"),
    "sqlite3": ("database", "SQLite"),
    "better-sqlite3": ("database", "SQLite"),
    "mongodb": ("database", "MongoDB"),
    "pymongo": ("database", "MongoDB"),
    "redis": ("cache", "Redis"),
    "ioredis": ("cache", "Redis"),
    "@upstash/redis": ("cache", "Upstash Redis"),
    "memcached": ("cache", "Memcached"),
    "cassandra-driver": ("database", "Cassandra"),
    "neo4j-driver": ("database", "Neo4j"),
    "@planetscale/database": ("database", "PlanetScale"),
    "@neondatabase/serverless": ("database", "Neon"),
    "libsql": ("database", "libSQL/Turso"),
    "@libsql/client": ("database", "libSQL/Turso"),
    # --- background jobs / queues ---
    "bullmq": ("queue", "BullMQ"),
    "bull": ("queue", "Bull"),
    "agenda": ("queue", "Agenda"),
    "celery": ("queue", "Celery"),
    "rq": ("queue", "RQ"),
    "dramatiq": ("queue", "Dramatiq"),
    "sidekiq": ("queue", "Sidekiq"),
    "resque": ("queue", "Resque"),
    "inngest": ("queue", "Inngest"),
    "@trigger.dev/sdk": ("queue", "Trigger.dev"),
    "graphile-worker": ("queue", "Graphile Worker"),
    "temporalio": ("queue", "Temporal"),
    "@temporalio/client": ("queue", "Temporal"),
    "amqplib": ("queue", "RabbitMQ"),
    "kafkajs": ("queue", "Kafka"),
    "pika": ("queue", "RabbitMQ"),
    "kombu": ("queue", "Kombu"),
    "@aws-sdk/client-sqs": ("queue", "AWS SQS"),
    # --- auth ---
    "next-auth": ("auth", "NextAuth / Auth.js"),
    "@auth/core": ("auth", "Auth.js"),
    "@clerk/": ("auth", "Clerk"),
    "@auth0/": ("auth", "Auth0"),
    "auth0": ("auth", "Auth0"),
    "passport": ("auth", "Passport"),
    "lucia": ("auth", "Lucia"),
    "better-auth": ("auth", "Better Auth"),
    "@workos-inc/node": ("auth", "WorkOS"),
    "firebase-admin": ("auth", "Firebase"),
    "@supabase/supabase-js": ("auth", "Supabase"),
    "supabase": ("auth", "Supabase"),
    "jsonwebtoken": ("auth", "JWT (hand-rolled)"),
    "jose": ("auth", "JOSE/JWT"),
    "pyjwt": ("auth", "JWT (hand-rolled)"),
    "bcrypt": ("auth", "bcrypt password hashing"),
    "bcryptjs": ("auth", "bcrypt password hashing"),
    "argon2": ("auth", "argon2 password hashing"),
    "devise": ("auth", "Devise"),
    "django-allauth": ("auth", "django-allauth"),
    "djangorestframework-simplejwt": ("auth", "DRF SimpleJWT"),
    "spring-boot-starter-security": ("auth", "Spring Security"),
    # --- payments / billing ---
    "stripe": ("payments", "Stripe"),
    "@stripe/stripe-js": ("payments", "Stripe.js"),
    "@paddle/paddle-js": ("payments", "Paddle"),
    "paddle-sdk": ("payments", "Paddle"),
    "@lemonsqueezy/lemonsqueezy.js": ("payments", "Lemon Squeezy"),
    "braintree": ("payments", "Braintree"),
    "@paypal/checkout-server-sdk": ("payments", "PayPal"),
    "razorpay": ("payments", "Razorpay"),
    "square": ("payments", "Square"),
    "@chargebee/chargebee-js": ("payments", "Chargebee"),
    "chargebee": ("payments", "Chargebee"),
    "recurly": ("payments", "Recurly"),
    # --- storage / media ---
    "@aws-sdk/client-s3": ("storage", "AWS S3"),
    "aws-sdk": ("storage", "AWS SDK v2"),
    "boto3": ("storage", "AWS SDK (boto3)"),
    "@google-cloud/storage": ("storage", "Google Cloud Storage"),
    "@azure/storage-blob": ("storage", "Azure Blob Storage"),
    "cloudinary": ("storage", "Cloudinary"),
    "uploadthing": ("storage", "UploadThing"),
    "@vercel/blob": ("storage", "Vercel Blob"),
    "multer": ("storage", "Multer (uploads)"),
    "django-storages": ("storage", "django-storages"),
    "activestorage": ("storage", "ActiveStorage"),
    "minio": ("storage", "MinIO"),
    # --- email / messaging ---
    "resend": ("email", "Resend"),
    "@sendgrid/mail": ("email", "SendGrid"),
    "sendgrid": ("email", "SendGrid"),
    "postmark": ("email", "Postmark"),
    "mailgun.js": ("email", "Mailgun"),
    "nodemailer": ("email", "Nodemailer (SMTP)"),
    "@react-email/components": ("email", "React Email"),
    "django-anymail": ("email", "Anymail"),
    "twilio": ("sms", "Twilio"),
    "@slack/web-api": ("notifications", "Slack API"),
    "firebase": ("notifications", "Firebase (FCM)"),
    "onesignal-node": ("notifications", "OneSignal"),
    "@knocklabs/node": ("notifications", "Knock"),
    "novu": ("notifications", "Novu"),
    "expo-notifications": ("notifications", "Expo Notifications"),
    # --- search ---
    "algoliasearch": ("search", "Algolia"),
    "meilisearch": ("search", "Meilisearch"),
    "typesense": ("search", "Typesense"),
    "@elastic/elasticsearch": ("search", "Elasticsearch"),
    "elasticsearch": ("search", "Elasticsearch"),
    "opensearch-py": ("search", "OpenSearch"),
    "django-haystack": ("search", "Haystack"),
    "pg_search": ("search", "pg_search"),
    # --- analytics / product ---
    "posthog-js": ("analytics", "PostHog"),
    "posthog-node": ("analytics", "PostHog"),
    "posthog": ("analytics", "PostHog"),
    "mixpanel": ("analytics", "Mixpanel"),
    "mixpanel-browser": ("analytics", "Mixpanel"),
    "amplitude-js": ("analytics", "Amplitude"),
    "@amplitude/analytics-browser": ("analytics", "Amplitude"),
    "@segment/analytics-node": ("analytics", "Segment"),
    "analytics-node": ("analytics", "Segment"),
    "@vercel/analytics": ("analytics", "Vercel Analytics"),
    "plausible-tracker": ("analytics", "Plausible"),
    # --- observability ---
    "@sentry/": ("monitoring", "Sentry"),
    "sentry-sdk": ("monitoring", "Sentry"),
    "datadog": ("monitoring", "Datadog"),
    "dd-trace": ("monitoring", "Datadog"),
    "newrelic": ("monitoring", "New Relic"),
    "@opentelemetry/": ("monitoring", "OpenTelemetry"),
    "opentelemetry-api": ("monitoring", "OpenTelemetry"),
    "prom-client": ("monitoring", "Prometheus"),
    "pino": ("monitoring", "Pino logging"),
    "winston": ("monitoring", "Winston logging"),
    "structlog": ("monitoring", "structlog"),
    # --- realtime ---
    "socket.io": ("realtime", "Socket.IO"),
    "pusher": ("realtime", "Pusher"),
    "pusher-js": ("realtime", "Pusher"),
    "ably": ("realtime", "Ably"),
    "@liveblocks/client": ("realtime", "Liveblocks"),
    "partysocket": ("realtime", "PartyKit"),
    "channels": ("realtime", "Django Channels"),
    "actioncable": ("realtime", "ActionCable"),
    # --- AI ---
    "openai": ("ai", "OpenAI"),
    "@anthropic-ai/sdk": ("ai", "Anthropic"),
    "anthropic": ("ai", "Anthropic"),
    "langchain": ("ai", "LangChain"),
    "llamaindex": ("ai", "LlamaIndex"),
    "@pinecone-database/pinecone": ("ai", "Pinecone"),
    "pinecone-client": ("ai", "Pinecone"),
    "chromadb": ("ai", "Chroma"),
    "weaviate-client": ("ai", "Weaviate"),
    "qdrant-client": ("ai", "Qdrant"),
    "pgvector": ("ai", "pgvector"),
    "ai": ("ai", "Vercel AI SDK"),
    # --- cloud / infra SDKs ---
    "@aws-sdk/": ("cloud", "AWS SDK v3"),
    "@google-cloud/": ("cloud", "Google Cloud SDK"),
    "@azure/": ("cloud", "Azure SDK"),
    "google-cloud-storage": ("cloud", "Google Cloud SDK"),
    "azure-identity": ("cloud", "Azure SDK"),
    # --- testing ---
    "jest": ("testing", "Jest"),
    "vitest": ("testing", "Vitest"),
    "mocha": ("testing", "Mocha"),
    "@playwright/test": ("testing", "Playwright"),
    "cypress": ("testing", "Cypress"),
    "pytest": ("testing", "pytest"),
    "unittest2": ("testing", "unittest"),
    "rspec": ("testing", "RSpec"),
    "rspec-rails": ("testing", "RSpec"),
    "junit": ("testing", "JUnit"),
    "testing-library": ("testing", "Testing Library"),
    "@testing-library/react": ("testing", "Testing Library"),
}

DEPLOY_FILES = {
    "vercel.json": ("Vercel", "serverless"),
    "netlify.toml": ("Netlify", "serverless"),
    "fly.toml": ("Fly.io", "container"),
    "render.yaml": ("Render", "container"),
    "railway.json": ("Railway", "container"),
    "railway.toml": ("Railway", "container"),
    "app.yaml": ("Google App Engine", "managed"),
    "Procfile": ("Heroku-style buildpack host", "long-running"),
    "serverless.yml": ("Serverless Framework", "serverless"),
    "serverless.yaml": ("Serverless Framework", "serverless"),
    "template.yaml": ("AWS SAM", "serverless"),
    "samconfig.toml": ("AWS SAM", "serverless"),
    "Dockerfile": ("Docker", "container"),
    "docker-compose.yml": ("Docker Compose", "container"),
    "docker-compose.yaml": ("Docker Compose", "container"),
    "wrangler.toml": ("Cloudflare Workers", "edge"),
    "wrangler.jsonc": ("Cloudflare Workers", "edge"),
    "amplify.yml": ("AWS Amplify", "serverless"),
    "Pulumi.yaml": ("Pulumi (IaC)", "iac"),
    "main.tf": ("Terraform (IaC)", "iac"),
    "cdk.json": ("AWS CDK (IaC)", "iac"),
    "skaffold.yaml": ("Kubernetes", "container"),
    "Chart.yaml": ("Helm/Kubernetes", "container"),
}

MONOREPO_FILES = {
    "turbo.json": "Turborepo",
    "nx.json": "Nx",
    "lerna.json": "Lerna",
    "pnpm-workspace.yaml": "pnpm workspaces",
    "rush.json": "Rush",
}

# Directories that indicate the app can host an inbound HTTP endpoint
# (needed by anything webhook-driven, e.g. billing or async provider callbacks).
WEBHOOK_DIR_HINTS = (
    "pages/api", "app/api", "src/app/api", "src/pages/api", "api/",
    "routes/", "src/routes/", "controllers/", "app/controllers/",
    "functions/", "netlify/functions", "supabase/functions", "handlers/",
    "views.py", "urls.py",
)

MIGRATION_DIR_HINTS = (
    "migrations", "migrate", "db/migrate", "alembic", "prisma/migrations",
    "drizzle", "supabase/migrations", "liquibase", "flyway",
)


def is_skipped(rel_parts):
    return any(part in SKIP_DIRS for part in rel_parts)


def walk_repo(root, max_files):
    """Yield (relative_path, absolute_path), deterministically ordered."""
    collected = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".git"))
        filenames.sort()
        for fn in filenames:
            abs_path = os.path.join(dirpath, fn)
            rel = os.path.relpath(abs_path, root)
            if is_skipped(rel.split(os.sep)):
                continue
            collected.append((rel.replace(os.sep, "/"), abs_path))
            if len(collected) >= max_files:
                truncated = True
                break
        if truncated:
            break
    collected.sort()
    return collected, truncated


def read_text(path, limit=400_000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except (OSError, UnicodeError):
        return ""


def norm_dep(name):
    return name.strip().strip('"\'').lower()


def match_signature(dep):
    """Return (category, label) for a dependency name, or None."""
    dep = norm_dep(dep)
    if not dep:
        return None
    if dep in SIGNATURES:
        return SIGNATURES[dep]
    for key, value in SIGNATURES.items():
        if key.endswith("/") and dep.startswith(key):
            return value
        # go modules and maven coords carry paths; match on the tail too
        if "/" in dep and not key.endswith("/") and dep.endswith("/" + key):
            return value
    return None


def parse_package_json(text):
    deps, meta = [], {}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return deps, meta
    if not isinstance(data, dict):
        return deps, meta
    for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        block = data.get(field)
        if isinstance(block, dict):
            deps.extend(block.keys())
    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        meta["scripts"] = sorted(scripts.keys())
    if isinstance(data.get("workspaces"), (list, dict)):
        meta["workspaces"] = True
    engines = data.get("engines")
    if isinstance(engines, dict):
        meta["engines"] = engines
    if isinstance(data.get("type"), str):
        meta["module_type"] = data["type"]
    return deps, meta


def parse_requirements(text):
    deps = []
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[\[<>=!~;\s]", line, 1)[0]
        if name:
            deps.append(name)
    return deps


def parse_pyproject(text):
    """Extract dependency names without requiring tomllib (Python < 3.11)."""
    deps = []
    for match in re.finditer(r'^\s*"([A-Za-z0-9._-]+)\s*[\[<>=!~;].*?"\s*,?\s*$', text, re.M):
        deps.append(match.group(1))
    for match in re.finditer(r'^\s*"([A-Za-z0-9._-]+)"\s*,\s*$', text, re.M):
        deps.append(match.group(1))
    # poetry style: name = "^1.2.3"
    for match in re.finditer(r'^\s*([A-Za-z0-9._-]+)\s*=\s*[\{"]', text, re.M):
        name = match.group(1)
        if name.lower() not in {"python", "name", "version", "description", "authors",
                                "readme", "requires-python", "license", "homepage"}:
            deps.append(name)
    return deps


def parse_go_mod(text):
    deps = []
    for match in re.finditer(r"^\s*(?:require\s+)?([\w.\-]+\.[\w.\-]+/[^\s]+)\s+v", text, re.M):
        deps.append(match.group(1))
    return deps


def parse_cargo(text):
    deps, in_deps = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_deps = "dependencies" in stripped
            continue
        if in_deps:
            match = re.match(r'^([A-Za-z0-9._-]+)\s*=', stripped)
            if match:
                deps.append(match.group(1))
    return deps


def parse_gemfile(text):
    return re.findall(r'^\s*gem\s+["\']([^"\']+)["\']', text, re.M)


def parse_composer(text):
    deps = []
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return deps
    for field in ("require", "require-dev"):
        block = data.get(field) if isinstance(data, dict) else None
        if isinstance(block, dict):
            deps.extend(block.keys())
    return deps


def parse_maven_gradle(text):
    deps = re.findall(r"<artifactId>([^<]+)</artifactId>", text)
    deps += re.findall(r'["\']([a-zA-Z0-9.\-]+:[a-zA-Z0-9.\-]+):', text)
    flat = []
    for dep in deps:
        flat.append(dep.split(":")[-1] if ":" in dep else dep)
    return flat


def parse_pubspec(text):
    return re.findall(r"^\s{2}([a-z0-9_]+):", text, re.M)


MANIFEST_PARSERS = [
    ("package.json", parse_package_json),
    ("requirements.txt", lambda t: (parse_requirements(t), {})),
    ("requirements-dev.txt", lambda t: (parse_requirements(t), {})),
    ("pyproject.toml", lambda t: (parse_pyproject(t), {})),
    ("Pipfile", lambda t: (parse_pyproject(t), {})),
    ("go.mod", lambda t: (parse_go_mod(t), {})),
    ("Cargo.toml", lambda t: (parse_cargo(t), {})),
    ("Gemfile", lambda t: (parse_gemfile(t), {})),
    ("composer.json", lambda t: (parse_composer(t), {})),
    ("pom.xml", lambda t: (parse_maven_gradle(t), {})),
    ("build.gradle", lambda t: (parse_maven_gradle(t), {})),
    ("build.gradle.kts", lambda t: (parse_maven_gradle(t), {})),
    ("pubspec.yaml", lambda t: (parse_pubspec(t), {})),
    ("mix.exs", lambda t: (re.findall(r"\{:([a-z_]+),", t), {})),
]


def collect_env_keys(files, root):
    """Collect env var NAMES from template files only. Real .env is never read."""
    keys = set()
    sources = []
    for rel, abs_path in files:
        base = os.path.basename(rel)
        is_template = (
            base.startswith(".env.") and any(
                base.endswith(suffix) for suffix in (".example", ".sample", ".template", ".dist")
            )
        ) or base in {"env.example", ".env.example", ".env.sample", ".env.template"}
        if not is_template:
            continue
        sources.append(rel)
        for line in read_text(abs_path, 40_000).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^(?:export\s+)?([A-Z0-9_]{2,})\s*=", line)
            if match:
                keys.add(match.group(1))
    return sorted(keys), sorted(sources)


def analyze(root, max_files=20000):
    files, truncated = walk_repo(root, max_files)
    rel_paths = [rel for rel, _ in files]
    path_set = set(rel_paths)

    # languages
    ext_counter = Counter()
    for rel in rel_paths:
        ext = os.path.splitext(rel)[1].lower()
        if ext in LANG_BY_EXT:
            ext_counter[LANG_BY_EXT[ext]] += 1
    languages = [
        {"language": lang, "files": count}
        for lang, count in sorted(ext_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    # manifests + dependencies
    manifests, all_deps, package_meta = [], set(), {}
    for rel, abs_path in files:
        base = os.path.basename(rel)
        for manifest_name, parser in MANIFEST_PARSERS:
            if base != manifest_name:
                continue
            text = read_text(abs_path)
            result = parser(text)
            deps, meta = result if isinstance(result, tuple) else (result, {})
            manifests.append({"path": rel, "type": manifest_name, "dependency_count": len(deps)})
            all_deps.update(norm_dep(d) for d in deps if d)
            if meta and not package_meta:
                package_meta = meta
            break

    # classify dependencies
    detected = {}
    for dep in sorted(all_deps):
        hit = match_signature(dep)
        if not hit:
            continue
        category, label = hit
        detected.setdefault(category, {})
        detected[category].setdefault(label, [])
        if dep not in detected[category][label]:
            detected[category][label].append(dep)
    stack = {
        category: [
            {"name": label, "packages": sorted(pkgs)}
            for label, pkgs in sorted(labels.items())
        ]
        for category, labels in sorted(detected.items())
    }

    # deployment
    deploy_targets, runtime_kinds = [], set()
    for rel in rel_paths:
        base = os.path.basename(rel)
        if base in DEPLOY_FILES and rel.count("/") <= 2:
            target, kind = DEPLOY_FILES[base]
            if target not in [d["target"] for d in deploy_targets]:
                deploy_targets.append({"target": target, "evidence": rel, "runtime": kind})
            runtime_kinds.add(kind)
    ci = sorted({rel for rel in rel_paths if rel.startswith(".github/workflows/")
                 or os.path.basename(rel) in {".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml"}})

    # runtime model inference: matters because serverless hosts cannot run
    # long-lived workers, which changes which integrations are viable.
    if {"container", "long-running"} & runtime_kinds:
        runtime_model = "long-running"
    elif {"serverless", "edge"} & runtime_kinds:
        runtime_model = "serverless"
    elif runtime_kinds:
        runtime_model = "managed"
    else:
        runtime_model = "unknown"

    # structural signals
    webhook_paths = sorted({
        rel for rel in rel_paths
        if any(hint in rel for hint in WEBHOOK_DIR_HINTS)
    })[:40]
    migration_paths = sorted({
        rel.split("/")[0] + "/" + rel.split("/")[1] if rel.count("/") >= 1 else rel
        for rel in rel_paths
        if any(hint in rel.lower() for hint in MIGRATION_DIR_HINTS)
    })[:20]
    monorepo = sorted({
        MONOREPO_FILES[os.path.basename(rel)]
        for rel in rel_paths if os.path.basename(rel) in MONOREPO_FILES
    })
    if package_meta.get("workspaces"):
        monorepo = sorted(set(monorepo) | {"npm/yarn workspaces"})

    env_keys, env_sources = collect_env_keys(files, root)

    has_tests = bool(stack.get("testing")) or any(
        re.search(r"(^|/)(tests?|__tests__|spec)/", rel) or
        re.search(r"\.(test|spec)\.[a-z]+$", rel) or
        re.match(r"^test_.*\.py$", os.path.basename(rel))
        for rel in rel_paths
    )
    has_typescript = any(
        rel.endswith((".ts", ".tsx")) for rel in rel_paths
    ) or "tsconfig.json" in {os.path.basename(p) for p in rel_paths}

    capabilities = {
        "can_receive_webhooks": bool(webhook_paths),
        "has_background_jobs": bool(stack.get("queue")),
        "has_database": bool(stack.get("database") or stack.get("orm")),
        "has_migrations": bool(migration_paths),
        "has_tests": has_tests,
        "has_ci": bool(ci),
        "typed_codebase": has_typescript or bool(stack.get("orm")),
        "is_monorepo": bool(monorepo),
    }

    # gaps worth flagging in any recommendation
    constraints = []
    if runtime_model == "serverless" and not stack.get("queue"):
        constraints.append(
            "Serverless/edge deployment with no job runner: anything needing retries, "
            "long-running work, or scheduled reconciliation needs a hosted queue "
            "(or provider-managed jobs) rather than an in-process worker."
        )
    if not capabilities["can_receive_webhooks"]:
        constraints.append(
            "No inbound HTTP route directory detected: webhook-driven providers would "
            "require new endpoint infrastructure plus signature verification."
        )
    if not capabilities["has_migrations"] and capabilities["has_database"]:
        constraints.append(
            "Database present but no migrations directory found: schema changes may be "
            "applied manually, so any integration adding tables needs a migration story."
        )
    if not capabilities["has_tests"]:
        constraints.append(
            "No test suite detected: integrations with complex state machines "
            "(billing, auth) carry higher regression risk here."
        )
    if truncated:
        constraints.append(
            "File walk hit the --max-files cap, so this inventory is partial. "
            "Re-run against subdirectories for full coverage."
        )

    return {
        "schema_version": 1,
        "root": os.path.abspath(root),
        "file_count": len(files),
        "truncated": truncated,
        "languages": languages,
        "manifests": sorted(manifests, key=lambda m: m["path"]),
        "stack": stack,
        "existing_vendors": sorted({
            item["name"]
            for category in ("auth", "payments", "storage", "email", "sms", "analytics",
                             "monitoring", "search", "notifications", "realtime", "ai",
                             "cloud", "queue")
            for item in stack.get(category, [])
        }),
        "deployment": {
            "targets": deploy_targets,
            "runtime_model": runtime_model,
            "ci": ci[:10],
        },
        "structure": {
            "monorepo": monorepo,
            "http_route_paths": webhook_paths[:15],
            "migration_paths": migration_paths,
            "package_scripts": package_meta.get("scripts", [])[:25],
        },
        "env": {"keys": env_keys, "sources": env_sources},
        "capabilities": capabilities,
        "constraints": constraints,
    }


def render_text(result):
    lines = []
    add = lines.append
    add("STACK ANALYSIS: " + result["root"])
    add("files scanned: {}{}".format(
        result["file_count"], " (TRUNCATED)" if result["truncated"] else ""))
    if not result["manifests"] and not result["languages"]:
        add("")
        add("No manifests or source files found. Treat this as a greenfield repo: "
            "recommendations must be framed against a stack the user confirms.")
        return "\n".join(lines)

    langs = ", ".join("{} ({})".format(l["language"], l["files"]) for l in result["languages"][:6])
    add("languages: " + (langs or "none detected"))
    add("manifests: " + (", ".join(m["path"] for m in result["manifests"][:8]) or "none"))
    add("")
    add("DETECTED STACK")
    if not result["stack"]:
        add("  (no recognised libraries - inspect manifests manually)")
    for category, items in result["stack"].items():
        add("  {:<14} {}".format(category + ":", ", ".join(i["name"] for i in items)))
    add("")
    deploy = result["deployment"]
    targets = ", ".join(d["target"] for d in deploy["targets"]) or "none detected"
    add("DEPLOYMENT")
    add("  targets: " + targets)
    add("  runtime model: " + deploy["runtime_model"])
    add("  ci: " + (", ".join(deploy["ci"][:3]) or "none detected"))
    add("")
    add("CAPABILITIES")
    for key, value in sorted(result["capabilities"].items()):
        add("  {:<24} {}".format(key, "yes" if value else "no"))
    if result["existing_vendors"]:
        add("")
        add("EXISTING VENDORS (prefer extending these before adding new ones)")
        add("  " + ", ".join(result["existing_vendors"]))
    if result["env"]["keys"]:
        add("")
        add("ENV KEYS FROM TEMPLATES ({} keys)".format(len(result["env"]["keys"])))
        add("  " + ", ".join(result["env"]["keys"][:20]))
    if result["constraints"]:
        add("")
        add("CONSTRAINTS TO CARRY INTO THE RECOMMENDATION")
        for constraint in result["constraints"]:
            add("  - " + constraint)
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
    parser = argparse.ArgumentParser(description="Analyze a repository's stack.")
    parser.add_argument("path", nargs="?", default=".", help="repository root (default: .)")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    parser.add_argument("--max-files", type=int, default=20000)
    parser.add_argument("--output", help="write result to this file instead of stdout")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.path):
        sys.stderr.write("error: not a directory: {}\n".format(args.path))
        return 2

    result = analyze(args.path, max_files=args.max_files)
    text = json.dumps(result, indent=2, sort_keys=True) if args.format == "json" else render_text(result)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("wrote {}".format(args.output))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
