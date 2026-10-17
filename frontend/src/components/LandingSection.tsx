"use client";

import React from "react";
import {
  ArrowRight,
  BookOpen,
  Braces,
  Check,
  CheckCircle2,
  ChevronRight,
  Code2,
  FileCheck2,
  Files,
  GraduationCap,
  Home,
  Layers3,
  LockKeyhole,
  ScanSearch,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import styles from "./LandingSection.module.css";

type LandingSectionProps = {
  onOpenWorkspace?: () => void;
};

const outputs = [
  {
    icon: FileCheck2,
    number: "01",
    title: "Rubric-level grading",
    text: "Every mark is tied to a named criterion.",
  },
  {
    icon: BookOpen,
    number: "02",
    title: "Cited course evidence",
    text: "Feedback points back to the material you supplied.",
  },
  {
    icon: Code2,
    number: "03",
    title: "Document and code review",
    text: "PDF, DOCX, scans, Python, C++ and Java.",
  },
  {
    icon: ShieldCheck,
    number: "04",
    title: "Instructor approval",
    text: "Nothing becomes final before educator review.",
  },
];

const process = [
  ["01", "Define", "Add the assignment, rubric and course material."],
  ["02", "Upload", "Submit one file or stage a class of up to 30."],
  ["03", "Evaluate", "Build criterion marks, citations and feedback."],
  ["04", "Decide", "Review the evidence and approve the final report."],
];

export const LandingSection: React.FC<LandingSectionProps> = ({ onOpenWorkspace }) => {
  const { loginWithGoogle, redeemBetaAccess, betaAccessRequired, error, loading, user } = useAuth();
  const [accessCode, setAccessCode] = React.useState("");

  const openWorkspace = () => {
    if (user && onOpenWorkspace) {
      onOpenWorkspace();
      return;
    }
    void loginWithGoogle();
  };

  React.useEffect(() => {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
    if (!("IntersectionObserver" in window)) {
      nodes.forEach((node) => { node.dataset.visible = "true"; });
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            (entry.target as HTMLElement).dataset.visible = "true";
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.16, rootMargin: "0px 0px -8% 0px" },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, []);

  return (
    <div className={styles.site}>
      <div className={styles.heroShell} id="top">
        <header className={styles.header}>
          <a className={styles.brand} href="#top" aria-label="GradeWise homepage">
            <span className={styles.brandMark}><GraduationCap size={20} /></span>
            <span>GradeWise</span>
          </a>

          <nav aria-label="Landing page navigation">
            <a href="#product">Product</a>
            <a href="#evidence">Evidence</a>
            <a href="#process">Process</a>
            <a href="#future">Future</a>
          </nav>

          <button className={styles.headerCta} onClick={openWorkspace} disabled={loading}>
            {user ? <Home size={15} /> : null}
            {user ? "Return to workspace" : "Open workspace"}
            <ArrowRight size={15} />
          </button>
        </header>

        <section className={styles.hero} aria-labelledby="landing-title">
          <div className={styles.heroCopy}>
            <div className={styles.eyebrow}>
              <span>AI-assisted assessment</span>
              <i />
              <span>Instructor controlled</span>
            </div>

            <h1 id="landing-title" aria-label="Grade student work. Keep every decision explainable.">
              <span className={styles.heroLine}><span>Grade student work.</span></span>
              <span className={styles.heroLine}><span>Keep every decision</span></span>
              <span className={styles.heroLine}><span><em>explainable.</em></span></span>
            </h1>

            <p className={styles.heroIntro}>
              Upload a rubric, course material and up to 30 submissions. GradeWise prepares
              criterion-level feedback, cited evidence and review-ready reports—while the instructor
              stays in control.
            </p>

            <div className={styles.heroActions}>
              <button className={styles.primary} onClick={openWorkspace} disabled={loading}>
                {loading ? "Opening…" : user ? "Return to workspace" : "Continue with Google"}
                <ArrowRight size={17} />
              </button>
              <a className={styles.textLink} href="#evidence">
                See a graded example <ChevronRight size={16} />
              </a>
            </div>

            <div className={styles.trustLine}>
              <LockKeyhole size={14} />
              Private beta
              <span />
              Instructor approval required
            </div>
            {betaAccessRequired && (
              <form className={styles.betaForm} onSubmit={(event) => {
                event.preventDefault();
                if (accessCode.trim()) void redeemBetaAccess(accessCode.trim());
              }}>
                <label htmlFor="beta-access-code">Beta tester access code</label>
                <div className={styles.betaFormRow}>
                  <input
                    id="beta-access-code"
                    type="password"
                    autoComplete="off"
                    value={accessCode}
                    onChange={(event) => setAccessCode(event.target.value)}
                    placeholder="Enter your access code"
                    required
                    disabled={loading}
                  />
                  <button type="submit" disabled={loading || !accessCode.trim()}>
                    {loading ? "Checking…" : "Unlock access"}
                  </button>
                </div>
                <p>Access is limited to invited testers. Ask the project team for a code.</p>
              </form>
            )}
            {error && <p role="alert" className={styles.error}>{error}</p>}

          </div>

          <div className={styles.demoStage} aria-label="Concrete GradeWise report example">
            <div className={styles.demoWindow}>
              <div className={styles.demoTopbar}>
                <div className={styles.demoBrand}><GraduationCap size={14} /> GradeWise</div>
                <div className={styles.demoCourse}>Data Structures · Assignment 04</div>
                <span>Sample report</span>
              </div>

              <div className={styles.demoHeading}>
                <div>
                  <small>REPORT READY FOR REVIEW</small>
                  <h2>Dijkstra&apos;s shortest path</h2>
                  <p>Student 12 · Python submission</p>
                </div>
                <div className={styles.score}><strong>19</strong><span>/25</span></div>
              </div>

              <div className={styles.demoBody}>
                <div className={styles.criteriaList}>
                  <div><span><CheckCircle2 size={14} /> Relaxation logic</span><strong>8/10</strong></div>
                  <div><span><CheckCircle2 size={14} /> Complexity analysis</span><strong>4/5</strong></div>
                  <div><span><ScanSearch size={14} /> Edge cases</span><strong>3/5</strong></div>
                  <div><span><CheckCircle2 size={14} /> Code clarity</span><strong>4/5</strong></div>
                </div>

                <aside className={styles.evidencePanel}>
                  <span>COURSE EVIDENCE · LECTURE 07</span>
                  <code>if d[u] + w(u,v) &lt; d[v]: d[v] = d[u] + w(u,v)</code>
                  <p>Correct relaxation step. The explanation must state why negative edge weights are unsupported.</p>
                </aside>
              </div>

              <div className={styles.execution}>
                <div><Braces size={16} /><span><strong>6 of 7 tests passed</strong><small>Disconnected graph case failed</small></span></div>
                <span className={styles.reviewState}><ShieldCheck size={15} /> Instructor review</span>
              </div>
            </div>

            <div className={styles.floatingCard}>
              <span><Check size={15} /></span>
              <div><strong>Evidence linked</strong><small>Rubric + lecture + execution</small></div>
            </div>
            <div className={styles.orbitOne} />
            <div className={styles.orbitTwo} />
          </div>
        </section>

        <div className={styles.proofBar}>
          <span>Built for real coursework</span>
          <strong><Files size={14} /> 30-file batches</strong>
          <strong><BookOpen size={14} /> Subject knowledge base</strong>
          <strong><Code2 size={14} /> Code execution</strong>
          <strong><ShieldCheck size={14} /> Human approval</strong>
        </div>
      </div>

      <main>
        <section className={styles.product} id="product" data-reveal>
          <div className={styles.sectionHeading}>
            <span>One review workspace</span>
            <h2>The grading trail stays visible.</h2>
            <p>Rubric, evidence, execution output and the instructor&apos;s decision live in the same report.</p>
          </div>

          <div className={styles.outputGrid}>
            {outputs.map(({ icon: Icon, number, title, text }, index) => (
              <article key={title} style={{ "--delay": `${index * 70}ms` } as React.CSSProperties}>
                <div className={styles.outputTop}><span>{number}</span><Icon size={19} /></div>
                <h3>{title}</h3>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.evidenceStory} id="evidence" data-reveal>
          <div className={styles.codePane}>
            <div className={styles.paneTop}>
              <span><Braces size={16} /> student_12.py</span>
              <span>Python</span>
            </div>
            <pre><code>{`def relax(u, v, weight):
    if distance[u] + weight < distance[v]:
        distance[v] = distance[u] + weight
        parent[v] = u`}</code></pre>
            <div className={styles.testRows}>
              <div><CheckCircle2 size={14} /><span>Standard weighted graph</span><strong>Passed</strong></div>
              <div><CheckCircle2 size={14} /><span>Single source node</span><strong>Passed</strong></div>
              <div className={styles.failed}><ScanSearch size={14} /><span>Disconnected graph</span><strong>Review</strong></div>
            </div>
          </div>

          <div className={styles.evidenceCopy}>
            <span className={styles.kicker}>A specific result, not a vague score</span>
            <h2>“Correct algorithm. Incomplete reasoning.”</h2>
            <p>
              The report identifies the working relaxation step, cites the matching lecture rule,
              and isolates the failed edge case. The instructor sees exactly why the draft received
              19/25 before approving or changing it.
            </p>
            <div className={styles.evidenceFacts}>
              <span><strong>19/25</strong> rubric score</span>
              <span><strong>1</strong> cited lecture passage</span>
              <span><strong>6/7</strong> tests passed</span>
            </div>
          </div>
        </section>

        <section className={styles.process} id="process" data-reveal>
          <div className={styles.sectionHeadingCompact}>
            <span>Four deliberate steps</span>
            <h2>From coursework to an approved report.</h2>
          </div>
          <ol>
            {process.map(([number, title, text], index) => (
              <li key={number} style={{ "--delay": `${index * 70}ms` } as React.CSSProperties}>
                <span>{number}</span>
                <div><h3>{title}</h3><p>{text}</p></div>
                {index < process.length - 1 && <i />}
              </li>
            ))}
          </ol>
        </section>

        <section className={styles.future} id="future" data-reveal>
          <div className={styles.futureIcon}><Layers3 size={25} /></div>
          <div>
            <span className={styles.futureBadge}>Future enhancement</span>
            <h2>Batch cross-checking</h2>
            <p>
              A planned cohort view will compare a complete submission set and surface repeated
              solution patterns for instructor investigation. It will remain a review signal—not an
              automatic plagiarism verdict.
            </p>
          </div>
          <Sparkles size={28} className={styles.futureSpark} />
        </section>

        <section className={styles.finalCta} data-reveal>
          <div>
            <span>Evidence before automation.</span>
            <h2>Make grading faster without making it opaque.</h2>
          </div>
          <button className={styles.primaryLight} onClick={openWorkspace} disabled={loading}>
            {user ? "Return to workspace" : "Open GradeWise"}
            <ArrowRight size={17} />
          </button>
        </section>
      </main>

      <footer className={styles.footer}>
        <a href="#top"><GraduationCap size={18} /> GradeWise</a>
        <p>AI-assisted grading with the educator in control.</p>
        <span>QAU · Final Year Project</span>
      </footer>
    </div>
  );
};
