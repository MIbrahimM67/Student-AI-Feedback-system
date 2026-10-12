"use client";
import React from "react";
import { Archive, ArrowRight, BookOpen, Check, Files, Fingerprint, ShieldCheck, GraduationCap } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import styles from "./LandingSection.module.css";
const features = [
  {icon:Files,title:"An entire class. One workflow.",text:"Stage a ZIP with up to 30 documents or single source files. Confirm names, follow grading progress and review every report."},
  {icon:BookOpen,title:"Your course material comes first.",text:"Index notes, chapters and marking schemes in a subject knowledge base. Retrieve relevant, cited passages alongside the assignment rubric."},
  {icon:Fingerprint,title:"See the overlap. Make the judgement.",text:"Inspect internal text similarity and its source matches. A similarity flag is evidence for review, not proof of plagiarism or an automatic deduction."},
  {icon:ShieldCheck,title:"The final decision stays with you.",text:"Review criterion-level feedback, approve the assessment, and export PDF reports or an Excel grade sheet."},
];
export const LandingSection: React.FC = () => {
 const {loginWithGoogle,error,loading}=useAuth();
 const signIn=()=>{void loginWithGoogle();};
 return <div className={styles.site}>
  <header className={styles.header}>
   <a className={styles.brand} href="#top" aria-label="GradeWise home"><Archive size={24}/>GradeWise<span>for educators</span></a>
   <nav aria-label="Main navigation"><a href="#product">Product</a><a href="#workflow">How it works</a><a href="#questions">Questions</a></nav>
   <button className={styles.navButton} onClick={signIn} disabled={loading}>Open workspace<ArrowRight size={16}/></button>
  </header>
  <section id="top" className={styles.hero}>
   <div><p className={styles.eyebrow}>ASSESSMENT, WITH THE EDUCATOR IN CONTROL</p><h1>Thoughtful grading.<br/><em>Clearer feedback.</em></h1>
    <p className={styles.intro}>Bring assignments, course references and rubric-based feedback into one focused workspace. Give every submission the attention it deserves.</p>
    <div className={styles.actions}><button className={styles.primary} onClick={signIn} disabled={loading}>{loading?"Opening workspace…":"Continue with Google"}<ArrowRight size={19}/></button><a href="#workflow">Explore the workflow ↗</a></div>
    <p className={styles.access}>An invited Google account opens your student, instructor or administrator workspace.</p>
    {error&&<p role="alert" className={styles.error}>{error}</p>}
    <div className={styles.heroFooter}><GraduationCap size={19}/>Built around teaching. Designed for review.</div>
   </div>
   <div><div className={styles.preview} aria-label="Illustrative report preview">
    <div className={styles.previewTop}><span><Archive size={16}/>GradeWise / Faculty</span><span>Report for review</span></div>
    <div className={styles.previewBody}><div className={styles.reportHeading}><div><p>FOUNDATIONS OF SCIENCE</p><h2>Every mark has a reason.</h2><span>Example assignment · Properties of water</span></div><BookOpen size={28}/></div>
     <div className={styles.answer}><span>SUBMISSION EXCERPT</span><p>“Water freezes at 0°C and boils at 100°C at standard atmospheric pressure.”</p></div>
     <div className={styles.reportTable} role="table" aria-label="Example criterion breakdown">
      <div role="row"><span role="columnheader">Rubric criterion</span><span role="columnheader">Evidence</span></div>
      <div role="row"><span role="cell">Freezing temperature</span><span role="cell"><Check size={14}/>Supported</span></div>
      <div role="row"><span role="cell">Boiling temperature</span><span role="cell"><Check size={14}/>Supported</span></div>
      <div role="row"><span role="cell">Density explanation</span><span role="cell" className={styles.needsEvidence}>Needs evidence</span></div>
     </div>
     <div className={styles.feedback}><span>NEXT STEP FOR THE STUDENT</span><p>Explain why ice floats by relating its density to the density of liquid water.</p></div>
     <div className={styles.previewBottom}><ShieldCheck size={16}/>Instructor review before approval</div>
    </div>
   </div><p className={styles.exampleLabel}>Illustrative report preview · Your rubric shapes the feedback.</p></div>
  </section>
  <div className={styles.formats}><span>One workspace for</span><strong>Documents & scans</strong><strong>Python · C++ · Java</strong><strong>Classes of up to 30 files</strong></div>
  <section className={styles.product} id="product"><div className={styles.sectionHeading}><p className={styles.eyebrow}>THE WHOLE ASSESSMENT WORKFLOW</p><h2>Less fragmentation.<br/>More useful feedback.</h2><p>From the course reference to the final report, keep the evidence and the decisions together.</p></div><div className={styles.featureList}>{features.map(({icon:Icon,title,text})=><article key={title}><Icon size={24} strokeWidth={1.5}/><div><h3>{title}</h3><p>{text}</p></div></article>)}</div></section>
  <section className={styles.workflow} id="workflow"><div className={styles.sectionHeading}><p className={styles.eyebrow}>FROM SUBMISSION TO FEEDBACK</p><h2>A clear path.<br/>A considered assessment.</h2></div><ol>
   <li><span>01</span><h3>Set the standard</h3><p>Create a subject. Add references, an assignment and the rubric that defines a good answer.</p></li>
   <li><span>02</span><h3>Bring in the work</h3><p>Upload one submission or stage a batch. Documents are parsed; supported code runs in an isolated sandbox.</p></li>
   <li><span>03</span><h3>Inspect the evidence</h3><p>Specialist, Judge and Senior stages prepare feedback. Review criteria, course evidence and internal similarity.</p></li>
   <li><span>04</span><h3>Review and share</h3><p>Approve the assessment and export reports. Students receive feedback that explains what to improve.</p></li>
  </ol></section>
  <section className={styles.questions} id="questions"><div className={styles.sectionHeading}><p className={styles.eyebrow}>A FEW THINGS TO KNOW</p><h2>Made for educators.<br/>Clear about its limits.</h2></div><div>
   <details><summary>Does GradeWise replace the instructor?</summary><p>No. AI reports support assessment. Instructors review and approve the final report, and similarity flags do not automatically change rubric marks.</p></details>
   <details><summary>What can an instructor upload?</summary><p>PDF, DOCX, text and supported image documents, or single Python, C++ and Java files. A batch ZIP can contain up to 30 files and total up to 100 MB. Each file is limited to 5 MB and PDFs to 20 pages. Multi-file code projects remain unavailable.</p></details>
   <details><summary>How does the knowledge base work?</summary><p>Course material is extracted and indexed into cited passages. The hosted deployment uses subject-scoped text retrieval. Semantic retrieval is available when its embedding provider is configured.</p></details>
   <details><summary>What does a similarity percentage mean?</summary><p>It measures text overlap within the batch or recent work for the same assignment. It is not a verdict of plagiarism. Inspect source matches and the assignment context before making a decision.</p></details>
   <details><summary>Can I use the workspace right now?</summary><p>Access is currently invitation-only. Use an invited Google account. Live grading needs internet and available AI and execution quotas. Jobs are queued sequentially on this deployment.</p></details>
  </div></section>
  <section className={styles.closing}><div><p className={styles.eyebrow}>MAKE FEEDBACK THE START OF THE NEXT STEP</p><h2>Bring clarity to your next assignment.</h2></div><button className={styles.primary} onClick={signIn} disabled={loading}>Open your workspace<ArrowRight size={19}/></button></section>
  <footer className={styles.footer}><a href="#top" className={styles.brand}><Archive size={21}/>GradeWise</a><p>AI powered feedback for student assignments.</p><span>Created by Muhammad Ibrahim · QAU</span></footer>
 </div>;
};
