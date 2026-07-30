# BoostRank — Instant SEO Audits for E-Commerce Stores

[![Live](https://img.shields.io/badge/Live-boostrank.co-6366f1)](https://boostrank.co)
[![API](https://img.shields.io/badge/API-v1-green)](https://boostrank.co/api/v1)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-yellow)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-black)](https://nextjs.org)
[![Fly.io](https://img.shields.io/badge/Fly.io-Deployed-purple)](https://fly.io)

BoostRank catches broken meta tags, slow pages, and missing schema before Google does. Get a weighted SEO score in seconds, see every issue with fix instructions, and optionally push fixes directly to your Shopify store.

> Most stores lose 30-50% of organic traffic to fixable SEO issues they don't even know about. BoostRank finds them in 8 seconds.

## 🚀 Quick Start

### Free Audit (No Auth Required)

```bash
# Fast meta + heading check — no signup needed
curl -X POST "https://boostrank.co/api/quick-check?url=https://yourstore.com"
```

```json
{
  "url": "https://yourstore.com",
  "title": "Your Store",
  "title_length": 10,
  "description": "",
  "description_length": 0,
  "h1_count": 0,
  "heading_structure": [],
  "issues": [
    {"severity": "critical", "category": "meta", "message": "Missing meta description", "fix": "Add a meta description (120-160 chars)"}
  ]
}
```

### Full Audit (Free Tier — 1/Day)

```bash
# Sign up, get a JWT, then run a full audit
curl -X POST https://boostrank.co/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"secret","name":"You"}'

# Login → get token
TOKEN=$(curl -s -X POST https://boostrank.co/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"secret"}' | jq -r .token)

# Full audit — all 6 analyzers, weighted score, every issue
curl -X POST https://boostrank.co/api/audit \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url":"https://yourstore.com"}'
```

### AI Agent API

```bash
# For AI agents — no signup needed for free tier (5/month)
curl -X POST https://boostrank.co/api/v1/audit \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BOOSTRANK_API_KEY" \
  -d '{"url":"https://yourstore.com","detail_level":"full"}'
```

## ✨ Features

**Six SEO Analyzers** — Every audit runs all six in parallel:
- **Meta Tags** — Title length, description, canonical, Open Graph, Twitter cards
- **Headings** — H1 count, hierarchy, structure validation
- **Images** — Alt text coverage, missing alt detection
- **Technical** — SSL/HTTPS, redirects, sitemap, robots.txt, mobile viewport
- **Schema.org** — JSON-LD detection, type validation, rich result eligibility
- **Content Quality** — Keyword density, internal/external link ratios

**Weighted Scoring (0-100)** — Not a vague grade. A real score with category breakdown:
- Meta Tags: 30%
- Images: 20%
- Technical: 20%
- Schema: 15%
- Headings: 15%

**Competitor Comparison** — Side-by-side SEO score comparison with up to 5 competitors (Pro+)

**PDF Reports** — Branded audit reports. Agency tier supports white-labeling with custom logo and colors.

**Fix Engine** — Don't just find issues, fix them:
- `audit_runner` — Runs the same deep analysis as the free audit, produces structured issues with fix types
- `fix_generator` — Generates corrected HTML/code for each issue found
- `audit_trail` — Full audit history with score tracking over time

**Shopify Integration** — Connect your store via OAuth and push fixes directly:
- Shopify OAuth flow (`/auth/shopify/install` → `/auth/shopify/callback`)
- Automatic platform detection (Shopify, WordPress, Squarespace, Wix, Webflow, Next.js)
- Fix applier pushes corrected meta tags, schema, and product data via Shopify Admin API
- Connection status check and disconnect endpoints

**AI Agent API** — Built for programmatic use:
- `POST /api/v1/audit` — Full audit with API key auth
- `POST /api/v1/quick` — Fast summary audit
- `GET /api/v1/credits` — Check remaining credits
- Free tier: 5 audits/month, no signup required

**Auth & Billing** — JWT auth, API key management, Stripe integration for Pro/Agency upgrades

## 💰 Pricing

| Tier | Price | Audits | Competitor Compare | Reports | API Access |
|------|-------|--------|--------------------|---------|------------|
| **Free** | $0/mo | 1/day | — | — | 5/month |
| **Pro** | $19/mo | Unlimited | 5/week | 1/week | 100/month |
| **Agency** | $49/mo | Unlimited | Unlimited | Unlimited (white-label) | 1,000/month |

**Fix Services** (one-time purchases):
- **One-Time SEO Fix** — $149: We fix all critical issues found in your audit, delivered with corrected code + implementation guide within 48 hours
- **SEO Pro Subscription** — $99/mo: Ongoing monitoring, automatic fixes, and monthly re-audits

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                    FRONTEND                           │
│  Next.js 16 + Tailwind CSS                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Landing  │  │ Audit UI │  │ Fix Flow  │           │
│  │ Page     │  │ + Score  │  │ + Shopify │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       └─────────────┼─────────────┘                  │
│                     ▼                                 │
├─────────────────────────────────────────────────────┤
│                   BACKEND                             │
│  FastAPI (Python 3.12)                                │
│  ┌──────────────────────────────────────────┐        │
│  │            API Gateway                    │        │
│  │  Auth (JWT) · Rate Limiting · CORS       │        │
│  └──────────────────┬───────────────────────┘        │
│                     │                                 │
│    ┌────────────────┼────────────────┐               │
│    ▼                ▼                ▼               │
│  ┌─────────┐  ┌───────────┐  ┌────────────┐         │
│  │ Audit   │  │ Fix Engine │  │ Shopify    │         │
│  │ Engine  │  │            │  │ OAuth +   │         │
│  │ (6 ana- │  │ audit_runner│  │ Apply     │         │
│  │ lyzers) │  │ fix_gen    │  │           │         │
│  │         │  │ audit_trail│  │           │         │
│  └────┬────┘  └─────┬─────┘  └─────┬─────┘         │
│       │             │              │                 │
│       ▼             ▼              ▼                 │
│  ┌──────────────────────────────────────────┐        │
│  │          SHARED SERVICES                 │        │
│  │  Scoring · Compare · Reports · Billing   │        │
│  │  Stripe · Auth · API Keys · Waitlist     │        │
│  └──────────────────┬───────────────────────┘        │
│                     ▼                                 │
│  ┌──────────────────────────────────────────┐        │
│  │          DATA LAYER                       │        │
│  │  SQLite (audits, users, fixes, stores)   │        │
│  └──────────────────────────────────────────┘        │
├─────────────────────────────────────────────────────┤
│                   DEPLOYMENT                          │
│  Fly.io (DFW region) · Docker · Auto-scale           │
│  Frontend: Vercel                                     │
└─────────────────────────────────────────────────────┘
```

**Tech Stack:**
- **Backend:** FastAPI 0.111, Python 3.12, SQLite, httpx, BeautifulSoup4, lxml, Stripe, ReportLab
- **Frontend:** Next.js 16, React 19, Tailwind CSS 4, TypeScript 5
- **Deployment:** Fly.io (backend, DFW region, auto-stop/start machines), Vercel (frontend)
- **AI:** OpenRouter (Claude Sonnet) for fix generation and recommendations

## 📡 API Endpoints

### Public
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API info |
| `/health` | GET | Health check |
| `/api/quick-check` | POST | Fast meta + heading check (no auth) |

### Auth Required (JWT)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/signup` | POST | Register |
| `/api/auth/login` | POST | Login → JWT |
| `/api/auth/me` | GET | Current user |
| `/api/auth/tier` | GET | Tier + limits |
| `/api/auth/keys` | POST/GET/DELETE | API key management |
| `/api/audit` | POST | Full SEO audit |
| `/api/audits` | GET | Audit history |
| `/api/audits/{id}` | GET | Specific audit |
| `/api/compare` | POST | Competitor comparison (Pro+) |
| `/api/reports/history` | GET | Report history |
| `/api/billing/*` | — | Stripe checkout/webhooks |

### AI Agent API (`/api/v1`)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/` | GET | — | API info |
| `/api/v1/audit` | POST | API Key | Full audit (5 free/month) |
| `/api/v1/quick` | POST | — | Quick audit |
| `/api/v1/credits` | GET | API Key | Check credits |

### Shopify Integration
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/shopify/install` | GET | Start OAuth flow |
| `/auth/shopify/callback` | GET | OAuth callback |
| `/auth/shopify/status` | GET | Connection status |
| `/auth/shopify/disconnect` | DELETE | Disconnect store |
| `/api/shopify/status/{shop}` | GET | Check shop status |
| `/api/shopify/apply-fixes` | POST | Push fixes to Shopify |

### Fix Orders
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/fix-orders/*` | — | Order, track, and deliver SEO fixes |

## 🔗 Part of the Agent Business Suite

BoostRank is a [BrandBoost Studio](https://brandbooststudio.co) product, built alongside a suite of AI-powered tools for e-commerce and agencies:

| Product | What It Does |
|---------|-------------|
| **[BoostRank](https://boostrank.co)** | Instant SEO audits and fix engine for e-commerce stores |
| **[AgentSeek](https://agentseek.co)** | AI agent marketplace — find and hire AI talent for your business |
| **[Local-Eye](https://localeye.co)** | Web verification API for AI agents — verify the real world |

> LinkedIn is where you find human talent. AgentSeek is where you find AI talent. Local-Eye is how they verify it. BoostRank is how they rank.

## 🛠️ Local Development

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Environment Variables
```bash
# Backend
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
SHOPIFY_CLIENT_ID=...
SHOPIFY_CLIENT_SECRET=...
ADMIN_API_KEY=...
OPENROUTER_API_KEY=sk-or-...

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8001
```

## 📄 License

MIT — see [LICENSE](LICENSE).

---

Built by [BrandBoost Studio](https://brandbooststudio.co). Live at [boostrank.co](https://boostrank.co).