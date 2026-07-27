"use client";

import { useState, useEffect } from "react";

export default function ThankYouPage() {
  const [orderStatus, setOrderStatus] = useState<string>("checking");
  const [orderData, setOrderData] = useState<{
    url: string;
    product_type: string;
    seo_score_before: number | null;
    status: string;
  } | null>(null);
  const [token, setToken] = useState<string>("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get("token");
    if (t) {
      setToken(t);
      checkOrderStatus(t);
    }
  }, []);

  const checkOrderStatus = async (orderToken: string) => {
    try {
      const res = await fetch(`${window.location.origin}/api/fix-orders/status/${orderToken}`);
      if (res.ok) {
        const data = await res.json();
        setOrderData(data);
        setOrderStatus(data.status);
      } else {
        setOrderStatus("not_found");
      }
    } catch {
      setOrderStatus("error");
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="border-b border-white/10 bg-[#0f172a]/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <a href="https://boostrank.co" className="flex items-center gap-2">
            <span className="text-2xl">⚡</span>
            <span className="text-xl font-bold">
              Boost<span className="gradient-text">Rank</span>
            </span>
          </a>
        </div>
      </nav>

      {/* Content */}
      <div className="flex-1 flex items-center justify-center px-4 py-20">
        <div className="max-w-lg mx-auto text-center">
          {orderStatus === "paid" || orderStatus === "processing" ? (
            <>
              <div className="text-6xl mb-6">🎉</div>
              <h1 className="text-3xl font-bold mb-4">
                Payment confirmed!
              </h1>
              <p className="text-slate-400 mb-6">
                We&apos;re working on your SEO fixes now. Here&apos;s what happens next:
              </p>
              <div className="bg-[#1e293b] rounded-xl border border-white/10 p-6 text-left space-y-4 mb-8">
                <div className="flex items-start gap-3">
                  <span className="text-[#22c55e] font-bold">1.</span>
                  <div>
                    <p className="font-medium">We analyze your audit results</p>
                    <p className="text-sm text-slate-400">Our team reviews every issue found in your audit.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-[#22c55e] font-bold">2.</span>
                  <div>
                    <p className="font-medium">We generate your fixes</p>
                    <p className="text-sm text-slate-400">Corrected meta tags, schema markup, OG tags, and more — tailored to your platform.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-[#22c55e] font-bold">3.</span>
                  <div>
                    <p className="font-medium">You receive your fix package</p>
                    <p className="text-sm text-slate-400">Code fixes + implementation guide delivered to your email within 48 hours.</p>
                  </div>
                </div>
              </div>
              {orderData && (
                <div className="bg-[#1e293b] rounded-xl border border-white/10 p-4 mb-6">
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-slate-400">Site</span>
                    <span className="text-white break-all ml-4">{orderData.url}</span>
                  </div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-slate-400">Plan</span>
                    <span className="text-white">{orderData.product_type === "one_time_fix" ? "One-Time SEO Fix" : "SEO Pro Subscription"}</span>
                  </div>
                  {orderData.seo_score_before && (
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-400">Current Score</span>
                      <span className="text-white">{orderData.seo_score_before}/100</span>
                    </div>
                  )}
                </div>
              )}
              <p className="text-sm text-slate-500">
                Questions? Email us at{" "}
                <a href="mailto:ron@sublettlabs.com" className="text-[#22c55e] hover:underline">
                  ron@sublettlabs.com
                </a>
              </p>
            </>
          ) : orderStatus === "completed" ? (
            <>
              <div className="text-6xl mb-6">✅</div>
              <h1 className="text-3xl font-bold mb-4">Your fixes are ready!</h1>
              <p className="text-slate-400 mb-6">
                Check your email for the complete fix package with implementation instructions.
              </p>
            </>
          ) : (
            <>
              <div className="text-6xl mb-6">⏳</div>
              <h1 className="text-3xl font-bold mb-4">Processing your order...</h1>
              <p className="text-slate-400 mb-6">
                We&apos;re confirming your payment. This usually takes a few minutes.
                You&apos;ll receive a confirmation email shortly.
              </p>
              <p className="text-sm text-slate-500">
                If you don&apos;t hear from us within 24 hours, contact{" "}
                <a href="mailto:ron@sublettlabs.com" className="text-[#22c55e] hover:underline">
                  ron@sublettlabs.com
                </a>
              </p>
            </>
          )}
        </div>
      </div>

      {/* Footer */}
      <footer className="px-4 py-6 border-t border-white/10">
        <div className="max-w-6xl mx-auto text-center text-sm text-slate-500">
          <span className="text-lg">⚡</span>{" "}
          <span className="font-semibold text-slate-300">BoostRank</span> — A{" "}
          <a href="https://sublettlabs.com" className="text-slate-400 hover:text-white transition">
            Sublett Labs
          </a>{" "}
          product
        </div>
      </footer>
    </div>
  );
}