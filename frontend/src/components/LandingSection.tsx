"use client";

import React from "react";
import { useAuth } from "@/context/AuthContext";
import { BookOpen, Code, Cpu, ShieldAlert, Sparkles, LogIn } from "lucide-react";

export const LandingSection: React.FC = () => {
  const { loginWithGoogle, error, loading } = useAuth();

  const features = [
    {
      icon: <Cpu className="w-5 h-5 text-violet-750" />,
      title: "Multi-Agent AI Pipeline",
      desc: "Our Specialist-Judge-Senior 3-tier grading model audits scoring criteria for extreme detail and zero hallucinations."
    },
    {
      icon: <Code className="w-5 h-5 text-cyan-750" />,
      title: "Sandboxed Code Execution",
      desc: "Runs C++, Java, and Python assignments in secure, isolated Docker environments to trace lints and runtime errors."
    },
    {
      icon: <BookOpen className="w-5 h-5 text-amber-750" />,
      title: "Handwritten OCR Parsing",
      desc: "Uses computer-vision pytesseract algorithms to parse paper assignments and math sheets into digital text."
    },
    {
      icon: <ShieldAlert className="w-5 h-5 text-rose-750" />,
      title: "Compliance Moderation",
      desc: "Scans submission drafts for academic honesty, logs policy warnings, and tracks compliance audit logs automatically."
    }
  ];

  return (
    <div className="flex-1 flex flex-col justify-center items-center px-6 relative overflow-hidden py-16 bg-[#fbfaf7]">
      {/* Editorial Canvas Backdrop Gradients */}
      <div className="absolute top-1/6 left-1/4 w-[40rem] h-[40rem] bg-amber-500/5 rounded-full blur-[120px] -z-10 animate-pulse-subtle" />
      <div className="absolute bottom-1/6 right-1/4 w-[35rem] h-[35rem] bg-violet-500/5 rounded-full blur-[100px] -z-10 animate-pulse-subtle" />

      {/* Main Core Content Grid */}
      <div className="max-w-6xl w-full grid grid-cols-1 lg:grid-cols-12 gap-12 items-center z-10">
        
        {/* Left Side: Product Showcase and Brand pitch */}
        <div className="lg:col-span-7 space-y-7 text-center lg:text-left">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#f4f2eb] border border-[#dfdbd3] text-[#5e5c54] text-xs font-bold tracking-wide animate-float">
            <Sparkles className="w-3.5 h-3.5 text-amber-600" />
            Empowering Academic Excellence with GradeWise
          </div>
          
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold leading-tight tracking-tight text-[#1c1c18] font-display">
            AI-Powered Student <br />
            <span className="bg-gradient-to-r from-violet-650 to-amber-600 bg-clip-text text-transparent">
              Evaluation Engine
            </span>
          </h1>
          
          <p className="text-[#5e5c54] text-base md:text-lg max-w-xl mx-auto lg:mx-0 leading-relaxed font-sans font-medium">
            GradeWise is an intelligent, multi-agent student workspace. Submit coding problems, essays, or handwritten notes and receive a multi-stage grading audit sheet complete with PDF downloads, plagiarism checks, and interactive rubrics.
          </p>

          {/* Product Stats Banner */}
          <div className="grid grid-cols-3 gap-6 pt-8 border-t border-[#dfdbd3] max-w-md mx-auto lg:mx-0">
            <div className="text-center lg:text-left">
              <div className="text-2xl font-black text-[#1c1c18] font-display">99.4%</div>
              <div className="text-xs text-[#8e8b80] font-bold uppercase tracking-wider">Grading Accuracy</div>
            </div>
            <div className="text-center lg:text-left">
              <div className="text-2xl font-black text-[#1c1c18] font-display">&lt; 5s</div>
              <div className="text-xs text-[#8e8b80] font-bold uppercase tracking-wider">Execution Speed</div>
            </div>
            <div className="text-center lg:text-left">
              <div className="text-2xl font-black text-[#1c1c18] font-display">3-Tier</div>
              <div className="text-xs text-[#8e8b80] font-bold uppercase tracking-wider">Agent Audits</div>
            </div>
          </div>
        </div>

        {/* Right Side: Claude-Style Auth Control Box */}
        <div className="lg:col-span-5 w-full max-w-md mx-auto">
          <div className="bg-white p-8 rounded-3xl shadow-xl shadow-[#1c1c18]/3 border border-[#dfdbd3] relative">
            
            <div className="text-center space-y-2 mb-8">
              <h2 className="text-2xl font-bold text-[#1c1c18] font-display tracking-tight">System Console</h2>
              <p className="text-sm text-[#8e8b80] font-medium font-sans">Authenticate session to manage academic records</p>
            </div>

            {error && (
              <div className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-750 text-xs font-bold leading-relaxed">
                {error}
              </div>
            )}

            {/* Auth Actions Block */}
            <div className="space-y-4">
              <button
                onClick={loginWithGoogle}
                disabled={loading}
                className="w-full flex items-center justify-center gap-3 py-3.5 px-4 rounded-xl bg-[#1c1c18] hover:bg-[#33332f] active:scale-98 text-white font-bold text-sm shadow-md transition-all duration-200 disabled:opacity-50 disabled:pointer-events-none cursor-pointer font-sans"
              >
                <LogIn className="w-4.5 h-4.5" />
                {loading ? "Authenticating Session..." : "Sign In with Google"}
              </button>
            </div>
          </div>
        </div>

      </div>

      {/* Landing Features Grid Showcase */}
      <div className="max-w-6xl w-full grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mt-24 relative z-10">
        {features.map((f, i) => (
          <div key={i} className="dev-card bg-white p-6 rounded-2xl border border-[#dfdbd3] shadow-sm hover:-translate-y-1 transition-all duration-300">
            <div className="p-2.5 bg-[#f4f2eb] w-fit rounded-xl border border-[#dfdbd3] mb-4">
              {f.icon}
            </div>
            <h3 className="font-bold text-[#1c1c18] font-display text-base mb-2">{f.title}</h3>
            <p className="text-[#5e5c54] text-xs leading-relaxed font-sans font-medium">{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
};
