"use client";

import { useState } from "react";

interface Issue {
  severity: string;
  category: string;
  message: string;
  detail: string | null;
  fix: string | null;
}

interface AuditResult {
  url: string;
  seo_score: number;
  scores: Record<string, number>;
  issues: Issue[];
  page_data: Record<string, unknown>;
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AuditResult | null>(null);
  const [error, setError] = useState("");
  const [waitlistEmail, setWaitlistEmail] = useState("");
  const [waitlistSubmitted, setWaitlistSubmitted] = useState(false);
  const [waitlistError, setWaitlistError] = useState("");

  const runAudit = async (e: React.FormEvent) => {
    e.preventDefault();
    let auditUrl = url.trim();
    if (!auditUrl) return;
    // Auto-add https:// if missing
    if (!auditUrl.startsWith('http://') && !auditUrl.startsWith('https://')) {
      auditUrl = 'https://' + auditUrl;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      // Use the Vercel proxy route first, fall back to direct API
      const apiBase = window.location.origin;
      const res = await fetch(`${apiBase}/api/audit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: auditUrl }),
      });

      if (!res.ok) {
        // If proxy fails, try direct Railway API
        const fallbackRes = await fetch("https://sublime-illumination-production-5373.up.railway.app/api/audit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: auditUrl }),
        });
        if (!fallbackRes.ok) {
          const data = await fallbackRes.json();
          throw new Error(data.detail || "Audit failed");
        }
        const data: AuditResult = await fallbackRes.json();
        setResult(data);
      } else {
        const data: AuditResult = await res.json();
        setResult(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const handleWaitlist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!waitlistEmail.trim()) return;
    setWaitlistError("");
    try {
      const res = await fetch(`${window.location.origin}/api/waitlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: waitlistEmail.trim() }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to join waitlist");
      }
      setWaitlistSubmitted(true);
    } catch (err) {
      setWaitlistError(err instanceof Error ? err.message : "Failed to join waitlist. Please try again.");
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return "#22c55e";
    if (score >= 60) return "#eab308";
    return "#ef4444";
  };

  const getScoreGrade = (score: number) => {
    if (score >= 90) return "A+";
    if (score >= 80) return "A";
    if (score >= 70) return "B";
    if (score >= 60) return "C";
    if (score >= 50) return "D";
    return "F";
  };

  const severityEmoji: Record<string, string> = {
    critical: "🔴",
    warning: "🟡",
    info: "🟢",
  };

  const criticalCount = result?.issues.filter((i) => i.severity === "critical").length || 0;
  const warningCount = result?.issues.filter((i) => i.severity === "warning").length || 0;
  const infoCount = result?.issues.filter((i) => i.severity === "info").length || 0;

  return (
    <div className="min-h-screen">
      {/* Nav */}
      <nav className="fixed top-0 w-full z-50 border-b border-white/10 bg-[#0f172a]/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-2xl pulse-logo">⚡</span>
            <span className="text-xl font-bold">Boost<span className="gradient-text">Rank</span></span>
          </div>
          <div className="hidden md:flex items-center gap-6 text-sm text-slate-400">
            <a href="#features" className="hover:text-white transition">Features</a>
            <a href="#pricing" className="hover:text-white transition">Pricing</a>
            <a href="#faq" className="hover:text-white transition">FAQ</a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section id="audit" className="pt-32 pb-16 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-5xl md:text-6xl font-bold mb-4 fade-up">
            Your store&apos;s SEO{" "}
            <span className="gradient-text">boost</span>
          </h1>
          <p className="text-xl text-slate-400 mb-10 max-w-2xl mx-auto fade-up fade-up-delay-1">
            Instant SEO audits for any e-commerce store. Catch what Google sees
            before your customers see what&apos;s broken. Powered by BrandBoost Studio.
          </p>

          {/* Audit Form */}
          <form onSubmit={runAudit} className="max-w-2xl mx-auto fade-up fade-up-delay-2">
            <div className="flex gap-2">
              <input
                type="text"
                inputMode="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="Enter your store URL (e.g. epictrendsstore.com)"
                className="flex-1 px-5 py-4 rounded-xl bg-[#1e293b] border border-white/10 text-white placeholder:text-slate-500 focus:outline-none focus:border-[#22c55e] focus:ring-1 focus:ring-[#22c55e] transition text-lg"
              />
              <button
                type="submit"
                disabled={loading}
                className="px-8 py-4 rounded-xl bg-[#22c55e] text-black font-semibold hover:bg-[#16a34a] disabled:opacity-50 disabled:cursor-not-allowed transition text-lg whitespace-nowrap cursor-pointer"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Scanning...
                  </span>
                ) : (
                  "Audit Now"
                )}
              </button>
            </div>
            <p className="text-sm text-slate-500 mt-3">
              No signup required. Results in 30 seconds.
            </p>
            <p className="text-xs text-green-400 mt-1">
              🏷️ A BrandBoost Studio product
            </p>
          </form>

          {error && (
            <div className="max-w-2xl mx-auto mt-4 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400">
              {error}
            </div>
          )}
        </div>
      </section>

      {/* Results */}
      {result && (
        <section className="px-4 pb-16">
          <div className="max-w-4xl mx-auto">
            {/* Score Hero */}
            <div className="bg-[#1e293b] rounded-2xl border border-white/10 p-8 mb-6 fade-up">
              <div className="flex flex-col md:flex-row items-center gap-8">
                {/* Score Ring */}
                <div className="relative">
                  <svg width="140" height="140" className="-rotate-90">
                    <circle cx="70" cy="70" r="60" stroke="#1e293b" strokeWidth="10" fill="none" />
                    <circle
                      cx="70" cy="70" r="60"
                      stroke={getScoreColor(result.seo_score)}
                      strokeWidth="10"
                      fill="none"
                      strokeLinecap="round"
                      strokeDasharray={`${(result.seo_score / 100) * 377} 377`}
                      className="score-ring"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-4xl font-bold" style={{ color: getScoreColor(result.seo_score) }}>
                      {result.seo_score}
                    </span>
                    <span className="text-sm text-slate-400">/100</span>
                  </div>
                </div>

                <div className="flex-1 text-center md:text-left">
                  <h2 className="text-2xl font-bold mb-1">
                    SEO Grade: {getScoreGrade(result.seo_score)}
                  </h2>
                  <p className="text-slate-400 text-sm mb-4 break-all">{result.url}</p>
                  <div className="flex flex-wrap gap-4 justify-center md:justify-start">
                    <span className="text-sm">
                      <span className="text-red-400 font-semibold">{criticalCount}</span> Critical
                    </span>
                    <span className="text-sm">
                      <span className="text-yellow-400 font-semibold">{warningCount}</span> Warnings
                    </span>
                    <span className="text-sm">
                      <span className="text-green-400 font-semibold">{infoCount}</span> Passed
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Category Scores */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
              {(["meta", "headings", "images", "technical", "schema"] as const).map((cat) => {
                const score = result.scores[cat] ?? 0;
                return (
                  <div key={cat} className="bg-[#1e293b] rounded-xl border border-white/10 p-4 text-center card-hover">
                    <div className="text-2xl font-bold mb-1" style={{ color: getScoreColor(score) }}>
                      {score}
                    </div>
                    <div className="text-xs text-slate-400 uppercase tracking-wider">{cat}</div>
                  </div>
                );
              })}
            </div>

            {/* Issues List */}
            <div className="bg-[#1e293b] rounded-2xl border border-white/10 p-6">
              <h3 className="text-lg font-semibold mb-4">
                Issues Found ({result.issues.length})
              </h3>
              <div className="space-y-3">
                {result.issues
                  .sort((a, b) => {
                    const order: Record<string, number> = { critical: 0, warning: 1, info: 2 };
                    return (order[a.severity] ?? 3) - (order[b.severity] ?? 3);
                  })
                  .map((issue, i) => (
                    <div
                      key={i}
                      className="p-4 rounded-xl bg-[#0f172a] border border-white/5"
                    >
                      <div className="flex items-start gap-3">
                        <span className="text-lg mt-0.5">
                          {severityEmoji[issue.severity] || "⚪"}
                        </span>
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-medium text-sm">
                              {issue.message}
                            </span>
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-slate-400 uppercase">
                              {issue.category}
                            </span>
                          </div>
                          {issue.detail && (
                            <p className="text-xs text-slate-500 mb-2">
                              {issue.detail}
                            </p>
                          )}
                          {issue.fix && (
                            <p className="text-xs text-green-400/80">
                              💡 {issue.fix}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            {/* Page Data Summary */}
            <div className="bg-[#1e293b] rounded-2xl border border-white/10 p-6 mt-6">
              <h3 className="text-lg font-semibold mb-4">Page Data</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div className="flex justify-between p-3 rounded-lg bg-[#0f172a]">
                  <span className="text-slate-400">Title</span>
                  <span className="text-white truncate ml-4 max-w-[200px]">
                    {String(result.page_data.title || "—")}
                  </span>
                </div>
                <div className="flex justify-between p-3 rounded-lg bg-[#0f172a]">
                  <span className="text-slate-400">Description</span>
                  <span className="text-white truncate ml-4 max-w-[200px]">
                    {String(result.page_data.description || "—").slice(0, 60)}...
                  </span>
                </div>
                <div className="flex justify-between p-3 rounded-lg bg-[#0f172a]">
                  <span className="text-slate-400">H1 Tags</span>
                  <span className="text-white">{String(result.page_data.h1_count)}</span>
                </div>
                <div className="flex justify-between p-3 rounded-lg bg-[#0f172a]">
                  <span className="text-slate-400">Images</span>
                  <span className="text-white">
                    {String(result.page_data.image_count)} (
                    {String(result.page_data.images_missing_alt)} missing alt)
                  </span>
                </div>
                <div className="flex justify-between p-3 rounded-lg bg-[#0f172a]">
                  <span className="text-slate-400">HTTPS</span>
                  <span className={result.page_data.is_https ? "text-green-400" : "text-red-400"}>
                    {result.page_data.is_https ? "✅ Yes" : "❌ No"}
                  </span>
                </div>
                <div className="flex justify-between p-3 rounded-lg bg-[#0f172a]">
                  <span className="text-slate-400">Schema Types</span>
                  <span className="text-white text-xs">
                    {Array.isArray(result.page_data.schema_types)
                      ? (result.page_data.schema_types as string[]).join(", ") || "None"
                      : "None"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Features */}
      <section id="features" className="px-4 py-20 bg-[#1e293b]/50">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">
            Everything your store needs to <span className="gradient-text">rank higher</span>
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                icon: "🩺",
                title: "Page Speed Check",
                desc: "Core Web Vitals analysis powered by Lighthouse. See exactly what's slowing you down.",
              },
              {
                icon: "🏷️",
                title: "Meta Tag Audit",
                desc: "Title too long? Description missing? OG tags broken? We catch it all.",
              },
              {
                icon: "📐",
                title: "Content Structure",
                desc: "Heading hierarchy, keyword density, internal links — organized the way Google likes.",
              },
              {
                icon: "🔍",
                title: "Schema Validator",
                desc: "Is your JSON-LD valid? Will you get rich results? Find out instantly.",
              },
              {
                icon: "📱",
                title: "Mobile Check",
                desc: "Mobile-first indexing is real. See your site through a phone-sized viewport.",
              },
              {
                icon: "🏆",
                title: "Competitor Compare",
                desc: "Stack your SEO against up to 3 competitors. Find the gaps they're exploiting.",
              },
            ].map((f) => (
              <div
                key={f.title}
                className="bg-[#1e293b] rounded-xl border border-white/10 p-6 card-hover"
              >
                <div className="text-3xl mb-3">{f.icon}</div>
                <h3 className="font-semibold mb-2">{f.title}</h3>
                <p className="text-sm text-slate-400">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="px-4 py-20">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">
            Three steps to a <span className="gradient-text">healthier store</span>
          </h2>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { step: "1", title: "Enter Your URL", desc: "Paste any page URL. We analyze it in 30 seconds." },
              { step: "2", title: "Get Your Score", desc: "See your SEO vitals: speed, tags, structure, schema — color-coded and prioritized." },
              { step: "3", title: "Fix & Rank", desc: "Follow step-by-step fixes. Watch your score climb. Get more organic traffic." },
            ].map((s) => (
              <div key={s.step} className="text-center">
                <div className="w-14 h-14 rounded-full bg-[#22c55e]/10 border border-[#22c55e]/30 flex items-center justify-center text-[#22c55e] text-xl font-bold mx-auto mb-4">
                  {s.step}
                </div>
                <h3 className="font-semibold mb-2">{s.title}</h3>
                <p className="text-sm text-slate-400">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="px-4 py-20 bg-[#1e293b]/50">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">
            Simple <span className="gradient-text">pricing</span>
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                name: "Free",
                price: "$0",
                period: "/mo",
                features: [
                  "5 site audits per month",
                  "Page speed + meta tags + headings",
                  "Basic SEO score",
                  "Chrome extension",
                ],
                cta: "Start Free",
                href: "#audit",
                highlight: false,
              },
              {
                name: "Pro",
                price: "$19",
                period: "/mo",
                features: [
                  "50 audits per month",
                  "2 competitor comparisons/week",
                  "1 PDF report per week",
                  "Email support",
                ],
                cta: "Get Pro",
                href: "https://buy.stripe.com/14A8wP5dndOJ2FcaHA2Ji0h",
                highlight: false,
              },
              {
                name: "Business",
                price: "$49",
                period: "/mo",
                features: [
                  "Unlimited audits",
                  "10 competitor comparisons/week",
                  "Unlimited PDF reports",
                  "API access (1,000 calls/mo)",
                  "Priority support",
                ],
                cta: "Get Business",
                href: "https://buy.stripe.com/eVq6oH35f3a56Vs3f82Ji0i",
                highlight: true,
              },
              {
                name: "Agency",
                price: "$99",
                period: "/mo",
                features: [
                  "Unlimited audits",
                  "Unlimited comparisons",
                  "White-label reports",
                  "API access (10,000 calls/mo)",
                  "Priority support",
                ],
                cta: "Get Agency",
                href: "https://buy.stripe.com/7sYbJ1eNX2616VsdTM2Ji0j",
                highlight: false,
              },
            ].map((plan) => (
              <div
                key={plan.name}
                className={`rounded-2xl border p-8 card-hover ${
                  plan.highlight
                    ? "bg-[#22c55e]/5 border-[#22c55e]/30"
                    : "bg-[#1e293b] border-white/10"
                }`}
              >
                <h3 className="text-lg font-semibold mb-1">{plan.name}</h3>
                <div className="mb-6">
                  <span className="text-4xl font-bold">{plan.price}</span>
                  <span className="text-slate-400">{plan.period}</span>
                </div>
                <ul className="space-y-3 mb-8">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-slate-300">
                      <span className="text-[#22c55e]">✓</span>
                      {f}
                    </li>
                  ))}
                </ul>
                <a
                  href={plan.href}
                  target={plan.href.startsWith('http') ? '_blank' : undefined}
                  rel={plan.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                  className={`block w-full py-3 rounded-xl font-semibold transition cursor-pointer text-center ${
                    plan.highlight
                      ? "bg-[#22c55e] text-black hover:bg-[#16a34a]"
                      : "bg-white/5 text-white hover:bg-white/10 border border-white/10"
                  }`}
                >
                  {plan.cta}
                </a>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="px-4 py-20">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">
            Frequently asked <span className="gradient-text">questions</span>
          </h2>
          <div className="space-y-4">
            {[
              {
                q: "How is this different from Lighthouse?",
                a: "Lighthouse only checks speed and basic tags. BoostRank adds e-commerce-specific checks: product schema, OG tags for social sharing, competitor benchmarking, and weekly tracking over time.",
              },
              {
                q: "Does it work with Shopify / WooCommerce / BigCommerce?",
                a: "Yes! BoostRank works with ANY website. No platform integration needed for the core audit.",
              },
              {
                q: "Is the Chrome extension really free?",
                a: "Yes — the extension gives instant page-level audits free forever. Dashboard features like competitor tracking and weekly reports unlock with Pro.",
              },
              {
                q: "How fast is the analysis?",
                a: "Most pages complete in under 30 seconds. Large sites (100+ pages) take 2-3 minutes for a full crawl.",
              },
            ].map((faq) => (
              <div key={faq.q} className="bg-[#1e293b] rounded-xl border border-white/10 p-5">
                <h3 className="font-semibold mb-2">{faq.q}</h3>
                <p className="text-sm text-slate-400">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Waitlist */}
      <section id="waitlist" className="px-4 py-20 bg-gradient-to-b from-[#0f172a] to-[#1e293b]/50">
        <div className="max-w-lg mx-auto text-center">
          <h2 className="text-3xl font-bold mb-4">
            Get early <span className="gradient-text">access</span>
          </h2>
          <p className="text-slate-400 mb-8">Pro & Agency plans launching soon. Join the waitlist and be first in line — plus get 50% off your first month.</p>
          <form onSubmit={handleWaitlist} className="flex gap-2">
            <input
              type="email"
              value={waitlistEmail}
              onChange={(e) => setWaitlistEmail(e.target.value)}
              placeholder="you@yourstore.com"
              className="flex-1 px-5 py-4 rounded-xl bg-[#1e293b] border border-white/10 text-white placeholder:text-slate-500 focus:outline-none focus:border-[#22c55e] focus:ring-1 focus:ring-[#22c55e] transition"
              required
            />
            <button
              type="submit"
              disabled={waitlistSubmitted}
              className="px-8 py-4 rounded-xl bg-[#22c55e] text-black font-semibold hover:bg-[#16a34a] disabled:opacity-50 transition cursor-pointer whitespace-nowrap"
            >
              {waitlistSubmitted ? "✓ You're in!" : "Join Waitlist"}
            </button>
          </form>
          {waitlistError && <p className="text-red-400 text-sm mt-3">{waitlistError}</p>}
          {waitlistSubmitted && (
            <div className="mt-6 p-4 rounded-xl bg-green-500/10 border border-green-500/30">
              <p className="text-green-400 font-medium">🎉 You&apos;re on the list!</p>
              <p className="text-green-400/70 text-sm mt-1">We&apos;ll email you when Pro &amp; Agency plans launch. Early members get 50% off.</p>
            </div>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer className="px-4 py-10 border-t border-white/10">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-slate-500">
          <div className="flex items-center gap-2">
            <span className="text-lg">⚡</span>
            <span className="font-semibold text-slate-300">BoostRank</span>
            <span>— SEO analytics for e-commerce, made simple.</span>
          </div>
          <div>Built with ❤️ by BrandBoost Studio</div>
        </div>
      </footer>
    </div>
  );
}