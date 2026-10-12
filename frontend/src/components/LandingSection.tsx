"use client";

import React from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  Code2,
  Database,
  FileText,
  Files,
  Fingerprint,
  GraduationCap,
  Layers3,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import styles from "./LandingSection.module.css";

type PreviewTab = "report" | "batch" | "knowledge";

const capabilities = [
  { icon: Files, label: "Batch grading", value: "Up to 30 files", text: "Stage a class, confirm student names and follow every report from one queue." },
  { icon: BookOpen, label: "Course knowledge", value: "Cited references", text: "Ground feedback in your lecture notes, chapters and marking schemes." },
  { icon: Fingerprint, label: "Internal similarity", value: "Reviewable matches", text: "See overlapping passages and their sources before making an academic judgement." },
  { icon: Code2, label: "Code assessment", value: "Python · C++ · Java", text: "Run supported single-file submissions in an isolated execution environment." },
];

const workflow = [
  ["01", "Set the standard", "Create the assignment, define the rubric and add course references."],
  ["02", "Bring in the work", "Upload one submission or stage a ZIP containing up to 30 files."],
  ["03", "Build the evidence", "GradeWise extracts the work, retrieves references and prepares criterion-level feedback."],
  ["04", "Review and approve", "Inspect the report, similarity evidence and execution output before publishing."],
];

export const LandingSection: React.FC = () => {
  const { loginWithGoogle, error, loading } = useAuth();
  const [previewTab, setPreviewTab] = React.useState<PreviewTab>("report");
  const signIn = () => void loginWithGoogle();

  return (
    <div className={styles.site}>
      <div className={styles.heroShell} id="top">
        <header className={styles.header}>
          <a className={styles.brand} href="#top" aria-label="GradeWise home">
            <span className={styles.brandMark}><GraduationCap size={21} /></span>
            <span>GradeWise</span>
          </a>
          <nav aria-label="Main navigation">
            <a href="#capabilities">Capabilities</a>
            <a href="#workflow">How it works</a>
            <a href="#assurance">Grading process</a>
            <a href="#questions">FAQ</a>
          </nav>
          <button className={styles.headerCta} onClick={signIn} disabled={loading}>
            Open workspace <ArrowRight size={16} />
          </button>
        </header>

        <main className={styles.hero}>
          <div className={styles.heroCopy}>
            <div className={styles.eyebrow}><span /> AI-assisted assessment for educators</div>
            <h1>Grade a class without losing the <em>evidence.</em></h1>
            <p className={styles.heroIntro}>
              Evaluate documents and code against your rubric, ground feedback in course material,
              review internal similarity, and keep the final decision in the instructor&apos;s hands.
            </p>
            <div className={styles.heroActions}>
              <button className={styles.primary} onClick={signIn} disabled={loading}>
                {loading ? "Opening workspace…" : "Continue with Google"}
                <ArrowRight size={18} />
              </button>
              <a className={styles.secondary} href="#workflow">See how grading works</a>
            </div>
            <p className={styles.accessNote}>
              <ShieldCheck size={15} /> Invitation-only demo · Instructor review required before approval
            </p>
            {error && <p role="alert" className={styles.error}>{error}</p>}
          </div>

          <div className={styles.productStage} aria-label="Interactive GradeWise product preview">
            <div className={styles.glowOne} />
            <div className={styles.glowTwo} />
            <div className={styles.productWindow}>
              <div className={styles.windowTopbar}>
                <div className={styles.windowBrand}><GraduationCap size={15} /> GradeWise</div>
                <div className={styles.windowContext}>Foundations of Science <span>·</span> Assignment 03</div>
                <span className={styles.previewBadge}>Sample data</span>
              </div>
              <div className={styles.previewTabs} role="tablist" aria-label="Product preview">
                <button role="tab" aria-selected={previewTab === "report"} onClick={() => setPreviewTab("report")}>
                  <FileText size={15} /> Evidence report
                </button>
                <button role="tab" aria-selected={previewTab === "batch"} onClick={() => setPreviewTab("batch")}>
                  <Files size={15} /> Class batch
                </button>
                <button role="tab" aria-selected={previewTab === "knowledge"} onClick={() => setPreviewTab("knowledge")}>
                  <Database size={15} /> Course knowledge
                </button>
              </div>

              {previewTab === "report" && (
                <div className={styles.reportPanel} role="tabpanel">
                  <div className={styles.reportSummary}>
                    <div>
                      <span>REPORT FOR REVIEW</span>
                      <h2>Properties of water</h2>
                      <p>Student 08 · Document submission</p>
                    </div>
                    <div className={styles.scoreRing}><strong>17</strong><span>/20</span></div>
                  </div>
                  <div className={styles.reportGrid}>
                    <div className={styles.criteria}>
                      <div><span><CheckCircle2 size={15} /> Freezing point</span><strong>5/5</strong></div>
                      <div><span><CheckCircle2 size={15} /> Boiling point</span><strong>5/5</strong></div>
                      <div><span><ScanSearch size={15} /> Density explanation</span><strong>3/5</strong></div>
                      <div><span><CheckCircle2 size={15} /> Scientific language</span><strong>4/5</strong></div>
                    </div>
                    <aside className={styles.evidenceCard}>
                      <span>COURSE EVIDENCE · [2]</span>
                      <p>Ice forms an open crystal structure, making it less dense than liquid water.</p>
                      <small>Lecture 04 · States of matter</small>
                    </aside>
                  </div>
                  <div className={styles.feedbackBar}>
                    <div><Fingerprint size={16} /><span><strong>12% similarity</strong><small>1 passage to review</small></span></div>
                    <button type="button">Review report <ArrowRight size={14} /></button>
                  </div>
                </div>
              )}

              {previewTab === "batch" && (
                <div className={styles.batchPanel} role="tabpanel">
                  <div className={styles.batchHeader}>
                    <div><span>CLASS BATCH</span><h2>Assignment 03</h2></div>
                    <strong>18 of 30 reports ready</strong>
                  </div>
                  <div className={styles.progress}><span /></div>
                  <div className={styles.fileRows}>
                    <div><span className={styles.fileIcon}>AK</span><p><strong>Ayesha Khan</strong><small>submission-08.pdf</small></p><em className={styles.complete}>Complete</em></div>
                    <div><span className={styles.fileIcon}>HU</span><p><strong>Hamza Umar</strong><small>submission-09.docx</small></p><em className={styles.reviewing}>Reviewing</em></div>
                    <div><span className={styles.fileIcon}>SA</span><p><strong>Sara Ahmed</strong><small>solution.py</small></p><em className={styles.queued}>Queued</em></div>
                  </div>
                  <div className={styles.batchFooter}><Check size={15} /> Names confirmed before processing</div>
                </div>
              )}

              {previewTab === "knowledge" && (
                <div className={styles.knowledgePanel} role="tabpanel">
                  <div className={styles.knowledgeHeader}>
                    <div><span>SUBJECT KNOWLEDGE BASE</span><h2>Foundations of Science</h2></div>
                    <span className={styles.ready}><Check size={13} /> Ready</span>
                  </div>
                  <div className={styles.referenceList}>
                    <article><BookOpen size={20} /><div><strong>Lecture 04 — States of matter</strong><p>12 cited passages indexed</p></div><span>PDF</span></article>
                    <article><FileText size={20} /><div><strong>Assignment 03 marking guide</strong><p>8 cited passages indexed</p></div><span>DOCX</span></article>
                  </div>
                  <div className={styles.retrievalExample}>
                    <span>RETRIEVED FOR THIS REPORT</span>
                    <p>“Ice forms an open crystal structure…”</p>
                    <small>Lecture 04 · passage 2 of 12</small>
                  </div>
                </div>
              )}
            </div>
            <div className={styles.floatingStatus}><span><CheckCircle2 size={17} /></span><div><strong>Evidence linked</strong><small>Ready for instructor review</small></div></div>
          </div>
        </main>

        <div className={styles.proofStrip} aria-label="GradeWise availability">
          <span>Available in the hosted demo</span>
          <strong><Check size={14} /> Documents & scans</strong>
          <strong><Check size={14} /> Python, C++ & Java</strong>
          <strong><Check size={14} /> 30-file batches</strong>
          <strong><Check size={14} /> Internal similarity</strong>
        </div>
      </div>

      <section className={styles.capabilities} id="capabilities">
        <div className={styles.sectionIntro}>
          <div className={styles.kicker}>A complete review workspace</div>
          <h2>Move from submission to defensible feedback.</h2>
          <p>GradeWise keeps the rubric, student work, course evidence and instructor decision in one connected assessment process.</p>
        </div>
        <div className={styles.capabilityGrid}>
          {capabilities.map(({ icon: Icon, label, value, text }, index) => (
            <article key={label}>
              <div className={styles.capabilityNumber}>0{index + 1}</div>
              <div className={styles.capabilityIcon}><Icon size={21} /></div>
              <span>{label}</span>
              <h3>{value}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.featureStory}>
        <div className={styles.storyVisual} aria-label="Illustration of rubric-based evidence">
          <div className={styles.visualHeader}><span>Criterion 03</span><span>Evidence trace</span></div>
          <h3>Explain why ice floats on water.</h3>
          <div className={styles.sourceQuote}><span>STUDENT SUBMISSION</span><p>Ice floats because it is lighter than water.</p></div>
          <div className={styles.connectionLine} />
          <div className={styles.sourceQuoteAccent}><span>COURSE REFERENCE · [2]</span><p>Solid water is less dense because hydrogen bonds hold molecules in an open structure.</p></div>
          <div className={styles.visualOutcome}><CheckCircle2 size={17} /><span><strong>Partial evidence</strong> · Explanation needs the molecular reason</span></div>
        </div>
        <div className={styles.storyCopy}>
          <div className={styles.kicker}>Feedback with a traceable basis</div>
          <h2>See why the report reached its conclusion.</h2>
          <p>Each report brings together the rubric criterion, relevant student evidence, retrieved course passages and a specific improvement step.</p>
          <ul>
            <li><Check size={16} /> Criterion-level marks and reasoning</li>
            <li><Check size={16} /> Source citations from subject material</li>
            <li><Check size={16} /> Actionable feedback for the student</li>
          </ul>
        </div>
      </section>

      <section className={styles.workflow} id="workflow">
        <div className={styles.workflowIntro}>
          <div className={styles.kicker}>How it works</div>
          <h2>Four steps. One accountable assessment.</h2>
        </div>
        <ol>
          {workflow.map(([number, title, text]) => (
            <li key={number}>
              <span>{number}</span>
              <div><h3>{title}</h3><p>{text}</p></div>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.assurance} id="assurance">
        <div className={styles.assuranceCopy}>
          <div className={styles.kickerLight}>Designed for academic review</div>
          <h2>AI prepares the case.<br />The educator makes the call.</h2>
          <p>Three distinct grading stages examine the work before the report reaches the instructor. Similarity is shown as review evidence and never deducts marks automatically.</p>
          <button className={styles.lightCta} onClick={signIn} disabled={loading}>Open faculty workspace <ArrowRight size={17} /></button>
        </div>
        <div className={styles.pipeline} aria-label="GradeWise grading pipeline">
          <article><span>01</span><div><strong>Specialist</strong><p>Checks the submission against the rubric and available evidence.</p></div><CheckCircle2 size={18} /></article>
          <i />
          <article><span>02</span><div><strong>Judge</strong><p>Audits consistency, fairness and unsupported conclusions.</p></div><CheckCircle2 size={18} /></article>
          <i />
          <article><span>03</span><div><strong>Senior</strong><p>Synthesizes the final criterion-level report for review.</p></div><CheckCircle2 size={18} /></article>
          <div className={styles.instructorGate}><ShieldCheck size={19} /><span><strong>Instructor approval</strong><small>Required before the assessment is final</small></span></div>
        </div>
      </section>

      <section className={styles.questions} id="questions">
        <div className={styles.questionsIntro}>
          <div className={styles.kicker}>Clear answers</div>
          <h2>What instructors should know.</h2>
          <p>The hosted project is built for a controlled demonstration, with explicit limits and instructor oversight.</p>
        </div>
        <div className={styles.questionList}>
          <details><summary>Does GradeWise replace the instructor?</summary><p>No. It prepares evidence and feedback for review. The instructor approves the final assessment, and similarity flags never change rubric marks automatically.</p></details>
          <details><summary>What can an instructor upload?</summary><p>PDF, DOCX, text and supported image documents, or single Python, C++ and Java files. A batch ZIP can contain up to 30 files and total up to 100 MB. Each file is limited to 5 MB and PDFs to 20 pages. Multi-file code projects are not supported in this demo.</p></details>
          <details><summary>How does the course knowledge base work?</summary><p>Course material is extracted into cited passages. This hosted deployment uses subject-scoped full-text retrieval to select relevant passages for grading.</p></details>
          <details><summary>What does the similarity percentage mean?</summary><p>It measures text overlap within the batch or recent work for the same assignment. It is evidence for instructor review, not a plagiarism verdict.</p></details>
          <details><summary>Who can access the workspace?</summary><p>Access is invitation-only through an approved Google account. Student, instructor and administrator roles open their respective workspaces.</p></details>
        </div>
      </section>

      <section className={styles.finalCta}>
        <div className={styles.finalIcon}><Layers3 size={26} /></div>
        <div><span>Ready for the next assessment?</span><h2>Bring the work, the rubric and the evidence together.</h2></div>
        <button className={styles.primary} onClick={signIn} disabled={loading}>Continue with Google <ArrowRight size={18} /></button>
      </section>

      <footer className={styles.footer}>
        <a className={styles.footerBrand} href="#top"><GraduationCap size={19} /> GradeWise</a>
        <p>AI-assisted feedback for student assignments, with the educator in control.</p>
        <span>Created by Muhammad Ibrahim · QAU</span>
      </footer>
    </div>
  );
};
