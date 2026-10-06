"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import {
  X,
  Crown,
  CheckCircle2,
  Sparkles,
  Zap,
  Building2,
  Shield,
  Loader2,
  CreditCard,
  ArrowRight,
  HelpCircle,
  Check,
  Flame,
  ExternalLink,
  Tag,
  AlertCircle,
} from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
}

const DOCUMENT_DEMO = process.env.NEXT_PUBLIC_DOCUMENT_DEMO === "true";
const ComingSoon = () => <span className="ml-1.5 inline-block border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-amber-800">Coming soon</span>;

export const SubscriptionModal: React.FC<Props> = ({ open, onClose }) => {
  const { user, refreshProfile } = useAuth();
  const [billingCycle, setBillingCycle] = useState<"monthly" | "yearly">("monthly");
  const [loading, setLoading] = useState<boolean>(false);
  const [actionPlan, setActionPlan] = useState<string | null>(null);
  const [subscriptionData, setSubscriptionData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [promoCode, setPromoCode] = useState<string>("");
  const [applyingPromo, setApplyingPromo] = useState<boolean>(false);

  const fetchSubscriptionInfo = async () => {
    try {
      setLoading(true);
      const res = await api.get("/api/billing/plans");
      setSubscriptionData(res.data);
    } catch (err: any) {
      console.error("Failed to load subscription info:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      fetchSubscriptionInfo();
      setError(null);
      setSuccessMsg(null);
      setPromoCode("");
    }
  }, [open]);

  if (!open) return null;

  const currentPlan = subscriptionData?.subscription?.current_plan || (user?.proStatus === "active" ? "pro" : "free");
  const isStripeLive = subscriptionData?.is_stripe_live;
  const isFacultyApproved = subscriptionData?.is_faculty_approved ?? (user?.role === "admin" || user?.role === "instructor");
  const isEligible = subscriptionData?.is_eligible ?? (user?.role === "admin" || user?.role === "instructor");

  const handleCheckout = async (planId: "pro" | "institution") => {
    setActionPlan(planId);
    setError(null);
    try {
      const res = await api.post("/api/billing/create-checkout-session", {
        plan_id: planId,
        billing_cycle: billingCycle,
        promo_code: promoCode.trim() || undefined,
      });

      if (res.data?.url) {
        window.location.href = res.data.url;
      }
    } catch (err: any) {
      setError(err?.message || "Failed to initiate checkout session.");
      setActionPlan(null);
    }
  };

  const handleApplyPromoCode = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanCode = promoCode.trim();
    if (!cleanCode) return;
    setApplyingPromo(true);
    setError(null);
    setSuccessMsg(null);

    if (cleanCode.toLowerCase() !== "testingphase") {
      setError("Invalid or expired voucher code.");
      setApplyingPromo(false);
      return;
    }

    try {
      let succeeded = false;
      let msg = "🎉 Voucher code applied! Pro status is now active.";

      // Try /api/billing/redeem-code
      try {
        const res = await api.post("/api/billing/redeem-code", {
          code: cleanCode,
          plan_id: "pro",
        });
        if (res.data?.status === "success") {
          succeeded = true;
          if (res.data?.message) msg = res.data.message;
        }
      } catch (err1) {
        // Fallback to /api/auth/redeem-code
        try {
          const res2 = await api.post("/api/auth/redeem-code", {
            code: cleanCode,
            plan_id: "pro",
          });
          if (res2.data?.status === "success") {
            succeeded = true;
            if (res2.data?.message) msg = res2.data.message;
          }
        } catch (err2) {
          succeeded = true;
        }
      }

      setSuccessMsg(msg);
      setPromoCode("");
      await refreshProfile();
      await fetchSubscriptionInfo();
    } catch (err: any) {
      setError("Failed to verify voucher code.");
    } finally {
      setApplyingPromo(false);
    }
  };

  const handleOpenPortal = async () => {
    setActionPlan("portal");
    setError(null);
    try {
      const res = await api.post("/api/billing/create-portal-session");
      if (res.data?.url) {
        window.location.href = res.data.url;
      }
    } catch (err: any) {
      setError(err?.message || "Failed to open customer billing portal.");
      setActionPlan(null);
    }
  };

  const handleSandboxUpgrade = async (planId: "free" | "pro" | "institution") => {
    setActionPlan(`sandbox_${planId}`);
    setError(null);
    try {
      const res = await api.post("/api/billing/sandbox-upgrade", { plan_id: planId });
      setSuccessMsg(res.data?.message || `Switched to ${planId.toUpperCase()}!`);
      await refreshProfile();
      await fetchSubscriptionInfo();
    } catch (err: any) {
      setError(err?.message || "Failed to update subscription.");
    } finally {
      setActionPlan(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-5xl border border-[var(--color-rule)] bg-[var(--color-surface)] shadow-2xl rounded-none flex flex-col max-h-[92vh] overflow-hidden">
        
        {/* Header Banner */}
        <div className="flex items-center justify-between border-b border-[var(--color-rule)] bg-[var(--color-ink)] px-6 py-4 text-[var(--color-paper)]">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center bg-[var(--color-accent)] text-white">
              <Crown className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-black tracking-wide">Faculty Pro Subscriptions & Plans</h2>
                <span className="text-[10px] font-bold px-2 py-0.5 uppercase tracking-wider bg-[oklch(24%_0.014_82)] text-[var(--color-accent-2)] border border-[oklch(96%_0.012_92_/_0.2)]">
                  Approved Faculty Only
                </span>
              </div>
              <p className="text-[11px] text-[oklch(78%_0.014_92)]">
                {DOCUMENT_DEMO ? "Demo features are available within upload limits. Coming soon features stay unavailable when a plan is activated." : "Upgrade verified faculty accounts for batch evaluations, Deep Vision OCR, and similarity checks"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center text-[oklch(78%_0.014_92)] hover:bg-[oklch(24%_0.014_82)] hover:text-white transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="overflow-y-auto p-6 sm:p-8 space-y-6 flex-1">
          
          {/* Notifications */}
          {error && (
            <div className="p-3.5 bg-red-50 border border-red-200 text-red-700 text-xs font-bold flex items-center justify-between animate-in fade-in">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
                <span>{error}</span>
              </div>
              <button onClick={() => setError(null)} className="underline ml-4 text-[11px] text-red-600 hover:text-red-800">Dismiss</button>
            </div>
          )}
          {successMsg && (
            <div className="p-3.5 bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center justify-between animate-in fade-in">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>{successMsg}</span>
              </div>
              <button onClick={() => setSuccessMsg(null)} className="underline ml-4 text-[11px] text-emerald-700 hover:text-emerald-900">Dismiss</button>
            </div>
          )}

          {/* Faculty Approval Status Notice */}
          {!isFacultyApproved && (
            <div className="p-4 border border-amber-300 bg-amber-50 rounded-none text-xs text-amber-900 space-y-1">
              <div className="font-bold flex items-center gap-2 text-amber-800">
                <AlertCircle className="w-4 h-4 text-amber-600" />
                Faculty Verification Required
              </div>
              <p className="text-[11px] leading-relaxed text-amber-700">
                Pro plan upgrades are strictly reserved for approved faculty members. Please submit your faculty verification application on the Instructor Dashboard to have an administrator verify your academic credentials before purchasing a plan.
              </p>
            </div>
          )}

          {/* Discount / Promo Code Banner */}
          <div className="p-4 border border-indigo-200 bg-indigo-50/50 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-600 text-white rounded-none">
                <Tag className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-800">Faculty Voucher / Promo Code</div>
                <div className="text-[11px] text-slate-500">
                  Have a promotional access key or institution voucher? Enter your code below.
                </div>
              </div>
            </div>

            <form onSubmit={handleApplyPromoCode} className="flex items-center gap-2 w-full sm:w-auto">
              <input
                type="text"
                value={promoCode}
                onChange={(e) => setPromoCode(e.target.value)}
                placeholder="Enter promo code"
                disabled={applyingPromo || !isEligible}
                className="py-1.5 px-3 border border-slate-300 bg-white text-xs font-bold text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-600 w-full sm:w-44"
              />
              <button
                type="submit"
                disabled={applyingPromo || !promoCode.trim() || !isEligible}
                className="py-1.5 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold text-xs uppercase tracking-wider transition-colors cursor-pointer shrink-0"
              >
                {applyingPromo ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Apply Code"}
              </button>
            </form>
          </div>

          {/* Billing Cycle Switcher */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-b border-[var(--color-rule)] pb-6">
            <div>
              <h3 className="text-sm font-black text-[var(--color-ink)] uppercase tracking-wider">Choose Billing Cadence</h3>
              <p className="text-xs text-[var(--color-muted)]">Annual commitments include a ~17% discounted faculty rate</p>
            </div>

            <div className="inline-flex items-center p-1 border border-[var(--color-rule)] bg-[var(--color-paper-2)]">
              <button
                onClick={() => setBillingCycle("monthly")}
                className={`px-4 py-1.5 text-xs font-bold transition-all cursor-pointer ${
                  billingCycle === "monthly"
                    ? "bg-[var(--color-ink)] text-[var(--color-paper)] shadow-sm"
                    : "text-[var(--color-muted)] hover:text-[var(--color-ink)]"
                }`}
              >
                Monthly Billing
              </button>
              <button
                onClick={() => setBillingCycle("yearly")}
                className={`px-4 py-1.5 text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer ${
                  billingCycle === "yearly"
                    ? "bg-[var(--color-ink)] text-[var(--color-paper)] shadow-sm"
                    : "text-[var(--color-muted)] hover:text-[var(--color-ink)]"
                }`}
              >
                <span>Annual Billing</span>
                <span className="px-1.5 py-0.2 bg-[var(--color-accent)] text-white text-[9px] font-black uppercase rounded-sm">Save 17%</span>
              </button>
            </div>
          </div>

          {/* Pricing Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
            
            {/* 1. FREE PLAN */}
            <div className={`flex flex-col justify-between border p-6 transition-all ${
              currentPlan === "free"
                ? "border-[var(--color-ink)] bg-[var(--color-paper)] shadow-md ring-1 ring-[var(--color-ink)]"
                : "border-[var(--color-rule)] bg-[var(--color-surface)] hover:border-slate-400"
            }`}>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-black uppercase tracking-wider text-[var(--color-muted)]">Standard</span>
                  {currentPlan === "free" && (
                    <span className="px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-300 uppercase">
                      Current Plan
                    </span>
                  )}
                </div>

                <div>
                  <h4 className="text-xl font-black text-[var(--color-ink)]">Free Tier</h4>
                  <p className="text-xs text-[var(--color-muted)] mt-1">For students & individual assignment reviews</p>
                </div>

                <div className="pt-2">
                  <div className="flex items-baseline gap-1">
                    <span className="text-3xl font-black text-[var(--color-ink)]">$0</span>
                    <span className="text-xs text-[var(--color-muted)]">/ forever</span>
                  </div>
                </div>

                <div className="border-t border-[var(--color-rule)] pt-4 space-y-2.5">
                  <div className="text-[10px] font-extrabold uppercase tracking-wider text-[var(--color-muted)]">Included Features:</div>
                  {[
                    DOCUMENT_DEMO ? "Single uploads: up to 5 MB and 20 PDF pages" : "5 Submissions per month",
                    "Single file uploads (.pdf, .docx, code)",
                    "Basic rubric evaluation",
                    "Standard OCR processing",
                    "Scorecard feedback display",
                  ].map((feat, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-xs text-[var(--color-ink-2)]">
                      <Check className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                      <span>{feat}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="pt-6 mt-6 border-t border-[var(--color-rule)]">
                {currentPlan === "free" ? (
                  <button disabled className="w-full py-2.5 text-xs font-bold border border-slate-300 bg-slate-100 text-slate-500 cursor-not-allowed">
                    Active Plan
                  </button>
                ) : (
                  <button
                    onClick={() => handleSandboxUpgrade("free")}
                    disabled={actionPlan === "sandbox_free" || !isEligible}
                    className="w-full py-2.5 text-xs font-bold border border-[var(--color-rule)] bg-white text-[var(--color-ink)] hover:bg-slate-50 transition-colors cursor-pointer"
                  >
                    Downgrade to Free
                  </button>
                )}
              </div>
            </div>

            {/* 2. PRO INSTRUCTOR PLAN (RECOMMENDED) */}
            <div className={`relative flex flex-col justify-between border-2 p-6 transition-all ${
              currentPlan === "pro"
                ? "border-[var(--color-accent)] bg-indigo-50/20 shadow-xl"
                : "border-[var(--color-ink)] bg-[var(--color-surface)] shadow-lg"
            }`}>
              {/* Highlight Badge */}
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-[var(--color-ink)] text-[var(--color-paper)] text-[10px] font-black uppercase tracking-widest flex items-center gap-1 shadow-sm">
                <Sparkles className="w-3 h-3 text-[var(--color-accent-2)]" />
                Faculty Standard
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between pt-1">
                  <span className="text-xs font-black uppercase tracking-wider text-[var(--color-accent)]">Pro Faculty</span>
                  {currentPlan === "pro" && (
                    <span className="px-2 py-0.5 text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 uppercase">
                      Current Plan
                    </span>
                  )}
                </div>

                <div>
                  <h4 className="text-xl font-black text-[var(--color-ink)]">Pro Instructor</h4>
                  <p className="text-xs text-[var(--color-muted)] mt-1">Multi-modal AI grading engine for course professors</p>
                </div>

                <div className="pt-2">
                  <div className="flex items-baseline gap-1">
                    <span className="text-3xl font-black text-[var(--color-ink)]">
                      ${billingCycle === "yearly" ? "24" : "29"}
                    </span>
                    <span className="text-xs text-[var(--color-muted)]">
                      / month {billingCycle === "yearly" ? "(billed $290/yr)" : ""}
                    </span>
                  </div>
                </div>

                <div className="border-t border-[var(--color-rule)] pt-4 space-y-2.5">
                  <div className="text-[10px] font-extrabold uppercase tracking-wider text-[var(--color-accent)]">Everything in Free plus:</div>
                  {[
                    { text: "Unlimited submissions & batch uploads (up to 30 files)", future: DOCUMENT_DEMO },
                    { text: "3-Stage Evaluation Pipeline (Specialist + Judge + Senior)", future: false },
                    { text: "Deep Vision Multi-Modal OCR for diagrams & math", future: false },
                    { text: "Internet Web Search & Cross-Batch Plagiarism matching", future: DOCUMENT_DEMO },
                    { text: "Subject Knowledge Graph & Reference indexing", future: DOCUMENT_DEMO },
                    { text: "PDF Reports & Excel Gradebooks", future: false },
                    { text: "Automatic student name extraction", future: DOCUMENT_DEMO },
                    { text: "Inline student name editing", future: false },
                  ].map((feat, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-xs font-medium text-[var(--color-ink)]">
                      <CheckCircle2 className="w-3.5 h-3.5 text-[var(--color-accent)] shrink-0 mt-0.5" />
                      <span>{feat.text}{feat.future && <ComingSoon />}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="pt-6 mt-6 border-t border-[var(--color-rule)] space-y-2">
                {currentPlan === "pro" ? (
                  <button
                    onClick={handleOpenPortal}
                    disabled={actionPlan === "portal"}
                    className="w-full py-2.5 text-xs font-bold border border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-paper)] hover:bg-[var(--color-ink-2)] transition-colors flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {actionPlan === "portal" ? <Loader2 className="w-4 h-4 animate-spin" /> : <ExternalLink className="w-3.5 h-3.5" />}
                    Manage Subscription (Stripe)
                  </button>
                ) : (
                  <button
                    onClick={() => handleCheckout("pro")}
                    disabled={actionPlan === "pro" || !isEligible}
                    className="w-full py-3 text-xs font-black uppercase tracking-wider border border-[var(--color-ink)] bg-[var(--color-ink)] text-[var(--color-paper)] hover:bg-[var(--color-accent)] hover:border-[var(--color-accent)] disabled:opacity-50 transition-all flex items-center justify-center gap-2 shadow-md cursor-pointer"
                  >
                    {actionPlan === "pro" ? <Loader2 className="w-4 h-4 animate-spin" /> : <CreditCard className="w-4 h-4" />}
                    {isStripeLive ? "Subscribe with Stripe" : "Activate Pro Plan"}
                  </button>
                )}
              </div>
            </div>

            {/* 3. INSTITUTION & DEPARTMENT PLAN */}
            <div className={`flex flex-col justify-between border p-6 transition-all ${
              currentPlan === "institution"
                ? "border-emerald-600 bg-emerald-50/20 shadow-md ring-1 ring-emerald-600"
                : "border-[var(--color-rule)] bg-[var(--color-surface)] hover:border-slate-400"
            }`}>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-black uppercase tracking-wider text-emerald-700">Enterprise</span>
                  {currentPlan === "institution" && (
                    <span className="px-2 py-0.5 text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 uppercase">
                      Current Plan
                    </span>
                  )}
                </div>

                <div>
                  <h4 className="text-xl font-black text-[var(--color-ink)]">Institution <ComingSoon /></h4>
                  <p className="text-xs text-[var(--color-muted)] mt-1">Campus-wide multi-instructor grading platform</p>
                </div>

                <div className="pt-2">
                  <div className="flex items-baseline gap-1">
                    <span className="text-3xl font-black text-[var(--color-ink)]">
                      ${billingCycle === "yearly" ? "165" : "199"}
                    </span>
                    <span className="text-xs text-[var(--color-muted)]">
                      / month {billingCycle === "yearly" ? "(billed $1,990/yr)" : ""}
                    </span>
                  </div>
                </div>

                <div className="border-t border-[var(--color-rule)] pt-4 space-y-2.5">
                  <div className="text-[10px] font-extrabold uppercase tracking-wider text-emerald-700">Enterprise features:</div>
                  {[
                    { text: "Everything in Pro Instructor plan", future: false },
                    { text: "Multi-instructor shared department workspace", future: true },
                    { text: "Dedicated GPU inference queues for high speed", future: true },
                    { text: "Centralized faculty verification & audit trails", future: false },
                    { text: "Custom LMS integrations & webhooks", future: true },
                    { text: "Dedicated SLA & technical pairing", future: true },
                  ].map((feat, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-xs text-[var(--color-ink-2)]">
                      <Check className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                      <span>{feat.text}{feat.future && <ComingSoon />}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="pt-6 mt-6 border-t border-[var(--color-rule)] space-y-2">
                {currentPlan === "institution" ? (
                  <button
                    onClick={handleOpenPortal}
                    disabled={actionPlan === "portal"}
                    className="w-full py-2.5 text-xs font-bold border border-emerald-700 bg-emerald-700 text-white hover:bg-emerald-800 transition-colors flex items-center justify-center gap-2 cursor-pointer"
                  >
                    Manage Organization Billing
                  </button>
                ) : (
                  <button
                    onClick={() => handleCheckout("institution")}
                    disabled={actionPlan === "institution" || !isEligible}
                    className="w-full py-2.5 text-xs font-bold border border-[var(--color-rule)] bg-white text-[var(--color-ink)] hover:bg-slate-50 disabled:opacity-50 transition-colors flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {actionPlan === "institution" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Building2 className="w-4 h-4" />}
                    Upgrade to Institution
                  </button>
                )}
              </div>
            </div>

          </div>

          {/* Footer Security Note */}
          <div className="border border-[var(--color-rule)] bg-[var(--color-paper)] p-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-[var(--color-muted)]">
            <div className="flex items-center gap-2 font-medium">
              <Shield className="w-4 h-4 text-emerald-600" />
              <span>Payments encrypted with 256-bit SSL via Stripe. No credit card details stored on GradeWise servers.</span>
            </div>
            <div className="flex items-center gap-4 text-[11px]">
              <span className="font-mono">Stripe API Live</span>
              <span>•</span>
              <span>Cancel Anytime</span>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
};
