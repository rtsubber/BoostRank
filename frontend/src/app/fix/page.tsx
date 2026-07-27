"use client";

import { useState } from "react";

interface FixPlan {
  name: string;
  price: string;
  period: string;
  description: string;
  features: string[];
  cta: string;
  highlight: boolean;
  product_type: string;
}

const plans: FixPlan[] = [
  {
    name: "One-Time SEO Fix",
    price: "$149",
    period: "one-time",
    description: "We fix all the SEO issues found in your audit. You get the corrected code + implementation guide.",
    features: [
      "Fix all critical SEO issues",
      "Corrected meta tags, schema & OG tags",
      "Step-by-step implementation guide",
      "Before/after score comparison",
      "Delivered within 48 hours",
      "Works with any platform",
    ],
    cta: "Fix My Site",
    highlight: true,
    product_type: "one_time_fix",
  },
  {
    name: "SEO Pro",
    price: "$99",
    period: "/mo",
    description: "Ongoing SEO monitoring, automatic fixes, and monthly re-audits. Cancel anytime.",
    features: [
      "Everything in One-Time Fix",
      "Monthly re-audits & fixes",
      "New page SEO optimization",
      "Schema & meta tag updates",
      "Priority email support",
      "Cancel anytime",
    ],
    cta: "Subscribe",
    highlight: false,
    product_type: "seo_subscription",
  },
];

export default function FixPage() {
  const [email, setEmail] = useState("");
  const [url, setUrl] = useState("");
  const [sitePlatform, setSitePlatform] = useState("");
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [checkoutUrl, setCheckoutUrl] = useState("");

  const handleCheckout = async (productType: string) => {
    let auditUrl = url.trim();
    if (!auditUrl) {
      setError("Please enter your website URL");
      return;
    }
    if (!email.trim()) {
      setError("Please enter your email");
      return;
    }
    if (!auditUrl.startsWith("http://") && !auditUrl.startsWith("https://")) {
      auditUrl = "https://" + auditUrl;
    }

    setLoading(true);
    setError("");
    setSelectedPlan(productType);

    try {
      // Get audit data from URL params if coming from results page
      const params = new URLSearchParams(window.location.search);
      const auditId = params.get("audit_id");
      const score = params.get("score");

      const res = await fetch(`${window.location.origin}/api/fix-orders/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          url: auditUrl,
          product_type: productType,
          audit_id: auditId ? parseInt(auditId) : null,
          seo_score: score ? parseInt(score) : null,
          site_platform: sitePlatform || null,
          success_url: `${window.location.origin}/fix/thank-you`,
          cancel_url: `${window.location.origin}/fix`,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Checkout failed");
      }

      const data = await res.json();
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
      setSelectedPlan(null);
    }
  };

  return (
    <div className="min-h-screen">
      {/* Nav */}
      <nav className="fixed top-0 w-full z-50 border-b border-white/10 bg-[#0f172a]/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <a href="https://boostrank.co" className="flex items-center gap-2">
            <span className="text-2xl">⚡</span>
            <span className="text-xl font-bold">
              Boost<span className="gradient-text">Rank</span>
            </span>
          </a>
          <div className="hidden md:flex items-center gap-6 text-sm text-slate-400">
            <a href="https://boostrank.co" className="hover:text-white transition">
              Free Audit
            </a>
            <a href="#plans" className="hover:text-white transition">
              Pricing
            </a>
            <a href="#faq" className="hover:text-white transition">
              FAQ
            </a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-16 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-block px-4 py-2 rounded-full bg-[#22c55e]/10 border border-[#22c55e]/30 text-[#22c55e] text-sm font-medium mb-6">
            From the makers of BoostRank
          </div>
          <h1 className="text-5xl md:text-6xl font-bold mb-6">
            We fix your SEO. <span className="gradient-text">You rank higher.</span>
          </h1>
          <p className="text-xl text-slate-400 max-w-2xl mx-auto mb-8">
            Your free audit found the problems. Now let our AI fix them — meta tags,
            schema markup, OG tags, sitemaps, and more. Just like we fix our own sites.
          </p>

          {/* Stats */}
          <div className="flex justify-center gap-8 md:gap-16 text-center">
            <div>
              <div className="text-3xl font-bold text-[#22c55e]">6+</div>
              <div className="text-sm text-slate-400">Sites we maintain</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-[#22c55e]">90+</div>
              <div className="text-sm text-slate-400">Avg SEO score</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-[#22c55e]">48h</div>
              <div className="text-sm text-slate-400">Delivery time</div>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="px-4 py-16 bg-[#1e293b]/50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">
            How it <span className="gradient-text">works</span>
          </h2>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                step: "1",
                title: "Run your free audit",
                desc: "Already done? We use your audit results. No re-scanning needed.",
              },
              {
                step: "2",
                title: "Choose your plan",
                desc: "One-time fix or ongoing SEO management. Pick what fits.",
              },
              {
                step: "3",
                title: "We fix it & deliver",
                desc: "You get corrected code, implementation guide, and a better score.",
              },
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

      {/* What We Fix */}
      <section className="px-4 py-16">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">
            What we <span className="gradient-text">fix</span>
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              {
                icon: "🏷️",
                title: "Meta Tags",
                desc: "Title tags, meta descriptions, canonical URLs — all optimized for your keywords.",
              },
              {
                icon: "📋",
                title: "Schema Markup",
                desc: "Organization, WebSite, Product, Article — structured data that gets rich results.",
              },
              {
                icon: "📱",
                title: "OG & Social Tags",
                desc: "Open Graph and Twitter Cards so your links look great when shared.",
              },
              {
                icon: "🗺️",
                title: "Sitemap & Robots",
                desc: "XML sitemaps and robots.txt configured for maximum crawl efficiency.",
              },
              {
                icon: "📐",
                title: "Heading Structure",
                desc: "H1-H6 hierarchy fixed so search engines understand your content.",
              },
              {
                icon: "🖼️",
                title: "Image Alt Tags",
                desc: "Descriptive alt text on all images for accessibility and image search.",
              },
              {
                icon: "🔗",
                title: "Internal Linking",
                desc: "Smart internal links that distribute authority to your key pages.",
              },
              {
                icon: "⚡",
                title: "Page Speed",
                desc: "Performance fixes: lazy loading, image optimization, render-blocking resources.",
              },
              {
                icon: "🔒",
                title: "Technical SEO",
                desc: "HTTPS redirects, clean URLs, duplicate content, and crawl budget optimization.",
              },
            ].map((item) => (
              <div
                key={item.title}
                className="bg-[#1e293b] rounded-xl border border-white/10 p-5 card-hover"
              >
                <div className="text-2xl mb-2">{item.icon}</div>
                <h3 className="font-semibold mb-1">{item.title}</h3>
                <p className="text-sm text-slate-400">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Site Info Form + Pricing */}
      <section id="plans" className="px-4 py-16 bg-[#1e293b]/50">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-4">
            Get your site <span className="gradient-text">fixed</span>
          </h2>
          <p className="text-slate-400 text-center mb-12">
            Enter your site details, choose a plan, and we&apos;ll handle the rest.
          </p>

          {/* Site Info */}
          <div className="max-w-xl mx-auto mb-12 space-y-4">
            <div>
              <label className="block text-sm text-slate-400 mb-2">Your Website URL</label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="yoursite.com"
                className="w-full px-4 py-3 rounded-xl bg-[#0f172a] border border-white/10 text-white placeholder:text-slate-500 focus:outline-none focus:border-[#22c55e] focus:ring-1 focus:ring-[#22c55e] transition"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-2">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@yourstore.com"
                className="w-full px-4 py-3 rounded-xl bg-[#0f172a] border border-white/10 text-white placeholder:text-slate-500 focus:outline-none focus:border-[#22c55e] focus:ring-1 focus:ring-[#22c55e] transition"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-2">Platform (optional)</label>
              <select
                value={sitePlatform}
                onChange={(e) => setSitePlatform(e.target.value)}
                className="w-full px-4 py-3 rounded-xl bg-[#0f172a] border border-white/10 text-white focus:outline-none focus:border-[#22c55e] focus:ring-1 focus:ring-[#22c55e] transition"
              >
                <option value="">Select your platform</option>
                <option value="shopify">Shopify</option>
                <option value="wordpress">WordPress</option>
                <option value="nextjs">Next.js / Custom</option>
                <option value="wix">Wix</option>
                <option value="squarespace">Squarespace</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="max-w-xl mx-auto mb-8 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-center">
              {error}
            </div>
          )}

          {/* Pricing Cards */}
          <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
            {plans.map((plan) => (
              <div
                key={plan.product_type}
                className={`rounded-2xl border p-8 ${
                  plan.highlight
                    ? "bg-[#22c55e]/5 border-[#22c55e]/30"
                    : "bg-[#0f172a] border-white/10"
                }`}
              >
                {plan.highlight && (
                  <div className="inline-block px-3 py-1 rounded-full bg-[#22c55e]/20 text-[#22c55e] text-xs font-semibold mb-4">
                    Most Popular
                  </div>
                )}
                <h3 className="text-xl font-semibold mb-1">{plan.name}</h3>
                <div className="mb-4">
                  <span className="text-4xl font-bold">{plan.price}</span>
                  <span className="text-slate-400">{plan.period}</span>
                </div>
                <p className="text-sm text-slate-400 mb-6">{plan.description}</p>
                <ul className="space-y-3 mb-8">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-slate-300">
                      <span className="text-[#22c55e]">✓</span>
                      {f}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => handleCheckout(plan.product_type)}
                  disabled={loading}
                  className={`w-full py-3 rounded-xl font-semibold transition cursor-pointer ${
                    plan.highlight
                      ? "bg-[#22c55e] text-black hover:bg-[#16a34a] disabled:opacity-50"
                      : "bg-white/5 text-white hover:bg-white/10 border border-white/10 disabled:opacity-50"
                  }`}
                >
                  {loading && selectedPlan === plan.product_type ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                          fill="none"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                        />
                      </svg>
                      Processing...
                    </span>
                  ) : (
                    plan.cta
                  )}
                </button>
              </div>
            ))}
          </div>

          <p className="text-center text-slate-500 text-sm mt-6">
            Secure payment via Stripe. No contracts. Cancel anytime.
          </p>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="px-4 py-16">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">
            Frequently asked <span className="gradient-text">questions</span>
          </h2>
          <div className="space-y-4">
            {[
              {
                q: "How does the one-time fix work?",
                a: "After your free audit identifies the issues, you purchase the fix. We analyze the problems, generate corrected code (meta tags, schema, OG tags, etc.), and deliver it with step-by-step implementation instructions within 48 hours.",
              },
              {
                q: "Do you push changes directly to my site?",
                a: "Not automatically. We deliver the corrected code and a clear implementation guide. For Shopify and WordPress sites, we can include liquid/PHP template patches. If you want hands-on help, upgrade to SEO Pro and we'll handle implementation.",
              },
              {
                q: "What platforms do you support?",
                a: "Any website. We generate platform-specific fixes for Shopify, WordPress, Next.js, Wix, Squarespace, and custom sites. The SEO principles are the same — we just format the fixes for your platform.",
              },
              {
                q: "What's the difference between one-time and subscription?",
                a: "One-time fix addresses the issues found in your current audit. SEO Pro gives you monthly re-audits and fixes, so as you add pages or Google changes its algorithm, your site stays optimized.",
              },
              {
                q: "Can I see the results before paying?",
                a: "Yes — the free audit is always free. You see your score and every issue before deciding to fix anything.",
              },
              {
                q: "Who fixes my site?",
                a: "The same team that maintains SEO scores of 90+ across 6 production sites including Sublett Labs, AgentSeek, and Local-Eye. We eat our own dog food.",
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

      {/* CTA */}
      <section className="px-4 py-16">
        <div className="max-w-2xl mx-auto text-center bg-[#1e293b] rounded-2xl border border-white/10 p-12">
          <h2 className="text-3xl font-bold mb-4">
            Stop leaving SEO points <span className="gradient-text">on the table</span>
          </h2>
          <p className="text-slate-400 mb-8">
            Your audit found the problems. We fix them. It&apos;s that simple.
          </p>
          <a
            href="#plans"
            className="inline-block px-8 py-4 rounded-xl bg-[#22c55e] text-black font-semibold hover:bg-[#16a34a] transition"
          >
            Get Started →
          </a>
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
          <div>
            Built with ❤️ by <a href="https://sublettlabs.com" className="text-slate-400 hover:text-white transition">Sublett Labs</a>
          </div>
        </div>
      </footer>
    </div>
  );
}