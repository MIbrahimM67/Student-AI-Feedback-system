# Implementation Guide for Antigravity

## Project: AI-Powered Feedback System for Student Assignments

### 1. Build Goal

Build a full-stack web application that allows students to upload assignments and receive AI-generated feedback. Instructors can apply for faculty verification, unlock Pro features, upload batches of assignments, check plagiarism, generate grades using rubrics, and export reports. Admins approve faculty applications, grant Pro access, and manage warning/block policies.

The system has three roles: Student, Instructor, and Admin. It supports single submissions, batch uploads up to 30 files, OCR, plagiarism checking, rubric-based grading, PDF/Excel exports, warnings, and an agentic AI pipeline: **Specialist → Judge → Senior**.

---

## 2. Recommended Tech Stack

### Frontend

Use:

```txt
Next.js 15
React
TypeScript
Tailwind CSS
shadcn/ui
Framer Motion
React Hook Form
Zod
Firebase Client SDK
```

Reason: the app needs dashboards, upload flows, tables, reports, role-based screens, and polished UX. Next.js + shadcn/ui is better than plain HTML/CSS for this scale.

### Backend

Use:

```txt
Python 3.11+
FastAPI
Firebase Admin SDK
Firestore
Firebase Storage
Celery or RQ for background jobs
Redis for job queue
ReportLab for PDF generation
openpyxl for Excel export
Tesseract OCR or Google Cloud Vision OCR
Docker sandbox for code execution
```

The original documentation mentions Flask, but FastAPI is recommended because it gives better API typing, automatic docs, async support, and cleaner integration for long-running AI/OCR jobs.

### Database and Storage

Keep:

```txt
Firebase Auth
Cloud Firestore
Firebase Storage
```

### AI Provider

Replace local LM Studio models with **DigitalOcean Inference / Gradient AI Platform**.

Recommended DigitalOcean setup:

```txt
Primary feedback model: Llama 3.3 70B Instruct or a strong available chat model
Fast/cheap model: smaller hosted model for preprocessing and classification
Embedding model: BGE M3 or E5 Large for similarity/plagiarism support
Router: use DigitalOcean Inference Router if available in your account
```

---

## 3. Main User Roles

### Student

Student can:

```txt
Sign in with Google
Select Student role
Upload one assignment
Paste text up to 5000 characters
Upload file up to 1MB
Select assignment type: Text, Coding, Handwritten, Custom
Receive AI feedback
Download PDF report
```

### Instructor

Instructor can:

```txt
Sign in with Google
Select Instructor role
Apply for faculty verification
Upload proof document
Wait for admin approval
Activate Pro subscription
Upload batch assignments, max 30 files
Edit extracted student names
Provide assignment prompt
Provide grading rubric
Enable plagiarism check
Generate grades
Export Excel or Excel + individual PDFs
```

### Admin

Admin can:

```txt
View faculty applications
Approve or reject instructors
Grant or revoke Pro access
View warnings
Dismiss warnings
Block users after repeated violations
```

---

## 4. Firestore Collections

Create these collections:

```txt
users
facultyApplications
subscriptions
submissions
batchJobs
feedbackReports
plagiarismReports
warnings
auditLogs
```

### users

```json
{
  "uid": "firebase_uid",
  "email": "user@example.com",
  "displayName": "Muhammad Ibrahim",
  "photoURL": "...",
  "role": "student | instructor | admin",
  "facultyStatus": "none | pending | approved | rejected",
  "proStatus": "inactive | active | revoked",
  "warningCount": 0,
  "blockedUntil": null,
  "createdAt": "timestamp",
  "updatedAt": "timestamp"
}
```

### facultyApplications

```json
{
  "id": "application_id",
  "userId": "uid",
  "fullName": "string",
  "university": "string",
  "department": "string",
  "designation": "string",
  "officialEmail": "string",
  "proofFileUrl": "firebase_storage_url",
  "status": "pending | approved | rejected",
  "rejectionReason": "",
  "reviewedBy": "admin_uid",
  "createdAt": "timestamp",
  "reviewedAt": "timestamp"
}
```

### submissions

```json
{
  "id": "submission_id",
  "userId": "uid",
  "type": "text | handwritten | coding | custom",
  "mode": "single",
  "inputText": "string",
  "fileUrl": "storage_url",
  "fileName": "assignment.pdf",
  "prompt": "assignment question",
  "rubric": "optional rubric",
  "status": "uploaded | processing | completed | failed",
  "feedbackReportId": "report_id",
  "createdAt": "timestamp"
}
```

### batchJobs

```json
{
  "id": "batch_id",
  "instructorId": "uid",
  "assignmentPrompt": "string",
  "rubric": "string",
  "plagiarismEnabled": true,
  "status": "uploaded | processing | completed | failed",
  "totalFiles": 30,
  "processedFiles": 0,
  "exportExcelUrl": "",
  "exportZipUrl": "",
  "createdAt": "timestamp"
}
```

### feedbackReports

```json
{
  "id": "report_id",
  "submissionId": "submission_id",
  "batchJobId": "optional_batch_id",
  "studentName": "string",
  "overallScore": 82,
  "status": "pass | fail | needs_review",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "suggestions": ["..."],
  "rubricScores": [
    {
      "criterion": "Correctness",
      "score": 8,
      "maxScore": 10,
      "justification": "..."
    }
  ],
  "specialistOutput": {},
  "judgeOutput": {},
  "seniorOutput": {},
  "pdfUrl": "storage_url",
  "createdAt": "timestamp"
}
```

### plagiarismReports

```json
{
  "id": "plagiarism_id",
  "submissionId": "submission_id",
  "batchJobId": "batch_id",
  "similarityScore": 28,
  "matches": [
    {
      "sourceUrl": "https://...",
      "matchedText": "...",
      "similarity": 0.74
    }
  ],
  "createdAt": "timestamp"
}
```

### warnings

```json
{
  "id": "warning_id",
  "userId": "uid",
  "submissionId": "submission_id",
  "reason": "Sensitive data detected",
  "severity": "low | medium | high",
  "status": "active | dismissed",
  "createdAt": "timestamp",
  "dismissedBy": null
}
```

---

## 5. Backend Folder Structure

Use this structure:

```txt
backend/
  app/
    main.py
    config.py
    firebase.py

    api/
      auth_routes.py
      student_routes.py
      instructor_routes.py
      admin_routes.py
      report_routes.py

    services/
      ai_service.py
      digitalocean_service.py
      ocr_service.py
      file_service.py
      feedback_pipeline.py
      plagiarism_service.py
      grading_service.py
      report_service.py
      warning_service.py
      code_sandbox_service.py

    models/
      user_models.py
      submission_models.py
      report_models.py
      batch_models.py

    workers/
      celery_app.py
      tasks.py

    utils/
      validators.py
      security.py
      prompt_templates.py
      pdf_templates.py
```

---

## 6. Frontend Folder Structure

```txt
frontend/
  app/
    page.tsx
    login/page.tsx
    role-selection/page.tsx

    student/
      dashboard/page.tsx
      submit/page.tsx
      feedback/[id]/page.tsx

    instructor/
      dashboard/page.tsx
      faculty-application/page.tsx
      subscription/page.tsx
      batch-upload/page.tsx
      batch/[id]/page.tsx

    admin/
      dashboard/page.tsx
      applications/page.tsx
      users/page.tsx
      warnings/page.tsx

  components/
    auth/
    dashboard/
    upload/
    feedback/
    reports/
    admin/
    ui/

  lib/
    firebase.ts
    api.ts
    auth.ts
    validators.ts
```

---

## 7. API Endpoints

### Auth

```txt
POST /api/auth/sync-user
GET  /api/auth/me
POST /api/auth/select-role
```

### Student

```txt
POST /api/student/submissions
GET  /api/student/submissions/{id}
GET  /api/student/submissions/{id}/feedback
GET  /api/student/submissions/{id}/download-pdf
```

### Instructor

```txt
POST /api/instructor/faculty-application
GET  /api/instructor/faculty-application/status
POST /api/instructor/batch
GET  /api/instructor/batch/{id}
POST /api/instructor/batch/{id}/confirm-names
POST /api/instructor/batch/{id}/process
GET  /api/instructor/batch/{id}/export
```

### Admin

```txt
GET  /api/admin/faculty-applications
POST /api/admin/faculty-applications/{id}/approve
POST /api/admin/faculty-applications/{id}/reject
POST /api/admin/users/{id}/grant-pro
POST /api/admin/users/{id}/revoke-pro
GET  /api/admin/warnings
POST /api/admin/warnings/{id}/dismiss
```

---

## 8. AI Pipeline Design

Implement a three-stage AI feedback pipeline:

```txt
Specialist → Judge → Senior
```

### Stage 1: Specialist Agent

Purpose:

```txt
Analyze the assignment deeply.
Extract key points.
Evaluate according to prompt and rubric.
Identify strengths, weaknesses, and mistakes.
Generate initial score.
```

### Stage 2: Judge Agent

Purpose:

```txt
Review Specialist output.
Check whether feedback is fair.
Check whether rubric scoring is consistent.
Detect hallucinations or unsupported claims.
Suggest corrections.
```

### Stage 3: Senior Agent

Purpose:

```txt
Create final polished feedback.
Produce student-friendly explanation.
Produce final grade.
Generate structured JSON for report generation.
```

### Required JSON Output

Force the final AI response to return JSON:

```json
{
  "overallScore": 0,
  "status": "pass | fail | needs_review",
  "summary": "string",
  "strengths": ["string"],
  "weaknesses": ["string"],
  "suggestions": ["string"],
  "rubricScores": [
    {
      "criterion": "string",
      "score": 0,
      "maxScore": 10,
      "justification": "string"
    }
  ],
  "finalComments": "string"
}
```

---

## 9. DigitalOcean AI API Integration

Create a service called:

```txt
digitalocean_service.py
```

Use environment variables:

```env
DIGITALOCEAN_API_KEY=
DIGITALOCEAN_MODEL_PRIMARY=
DIGITALOCEAN_MODEL_FAST=
DIGITALOCEAN_EMBEDDING_MODEL=
DIGITALOCEAN_INFERENCE_BASE_URL=
```

Recommended abstraction:

```python
class DigitalOceanAIService:
    async def chat(self, messages, model=None, temperature=0.2):
        pass

    async def embed(self, texts):
        pass
```

Do not hardcode model names everywhere. Keep them in `.env` so you can switch models later.

Use this model strategy:

```txt
Specialist Agent: stronger model
Judge Agent: stronger model, low temperature
Senior Agent: stronger model, low temperature
Sensitive-data classifier: fast/cheap model
Student name extraction: fast/cheap model
Plagiarism embeddings: embedding model
```

---

## 10. OCR Flow

For handwritten or scanned submissions:

```txt
1. Upload file to Firebase Storage.
2. Backend downloads temporary file.
3. Convert PDF/image pages to images if needed.
4. Run OCR.
5. Clean extracted text.
6. Send cleaned text to AI pipeline.
7. Save OCR text in Firestore.
```

Recommended OCR options:

```txt
Basic: Tesseract OCR
Better: Google Cloud Vision OCR
Best for handwriting: Google Cloud Vision or another paid OCR API
```

For FYP/demo, Tesseract is acceptable. For better handwriting accuracy, use an external OCR API.

---

## 11. Code Assignment Flow

Restrict code execution to:

```txt
Python
Java
C++
```

Implementation:

```txt
1. Student uploads code file or pastes code.
2. Backend detects language.
3. Store file in Firebase Storage.
4. Run static checks first.
5. If execution is needed, run inside Docker sandbox.
6. Apply timeout, memory limit, and no-network rule.
7. Send code, output, errors, and prompt to AI pipeline.
8. Generate feedback.
```

Security rules:

```txt
No network access
Timeout: 5 seconds
Memory limit: 256MB
Max output size
Delete container after execution
Never run code directly on host machine
```

---

## 12. Plagiarism Checking

Implementation approach:

```txt
1. Use assignment prompt to generate search queries.
2. Fetch 5–10 reference sources.
3. Extract text from sources.
4. Split into chunks.
5. Generate embeddings for source chunks and student submission chunks.
6. Compare cosine similarity.
7. Store top matches.
8. Include similarity score in report.
```

Important: for an FYP, keep plagiarism checking as a “similarity assistant,” not a full Turnitin replacement.

---

## 13. Report Generation

### Student PDF

Include:

```txt
Student name
Assignment type
Overall score
Pass/fail/needs review status
Summary
Strengths
Weaknesses
Suggestions
Rubric breakdown, if available
Final comments
Generated timestamp
```

### Instructor Excel

Columns:

```txt
Student Name
File Name
Overall Score
Status
Strengths Summary
Weaknesses Summary
Suggestions Summary
Plagiarism %
PDF Report Link
```

### Instructor ZIP Export

For “Excel + PDF”:

```txt
batch_report.xlsx
student_1_report.pdf
student_2_report.pdf
...
```

---

## 14. Role-Based Access Rules

Implement backend middleware:

```txt
require_auth
require_student
require_instructor
require_admin
require_verified_faculty
require_pro
check_not_blocked
```

Examples:

```txt
Student submission endpoint:
require_auth + require_student + check_not_blocked

Batch upload endpoint:
require_auth + require_instructor + require_verified_faculty + require_pro

Admin approval endpoint:
require_auth + require_admin
```

---

## 15. UI Pages to Build

### Public

```txt
Landing page
Login page
Role selection page
```

### Student

```txt
Student dashboard
Submit assignment page
Processing status page
Feedback result page
PDF download page
```

### Instructor

```txt
Instructor dashboard
Faculty verification form
Subscription/Pro page
Batch upload page
Student name editing table
Batch processing status page
Batch results page
Export reports page
```

### Admin

```txt
Admin dashboard
Faculty applications page
Application review page
User management page
Warning management page
Pro access management page
```

---

## 16. Best AI Tool for Web App Designs

### Best overall: Figma Make

Use **Figma Make** to create the UI/UX because it is built directly into Figma and can turn prompts or existing Figma designs into functional prototypes, web apps, and interactive UI.

Use it for:

```txt
Landing page
Student dashboard
Instructor dashboard
Admin panel
Upload flows
Feedback report page
Batch result table
Responsive layouts
```

### Best for React code components: v0 by Vercel

Use **v0** after Figma Make if you want production-style React components quickly. v0 is focused on generating React UI with Tailwind CSS and shadcn/ui components from text prompts or image uploads.

Use it for:

```txt
Dashboard cards
Upload components
Admin tables
Feedback report components
Pricing/subscription cards
```

### Practical workflow

Use this order:

```txt
1. Figma Make: generate the visual product design.
2. Figma: clean up layout, typography, spacing, and colors.
3. v0: generate React + Tailwind + shadcn components.
4. Antigravity: integrate generated UI with Firebase and backend APIs.
```

---

## 17. Suggested Visual Theme

Use a clean academic SaaS design:

```txt
Primary color: Deep blue or indigo
Accent color: Emerald or cyan
Background: Light gray / white
Cards: Rounded, soft shadow
Typography: Inter or Geist
Style: Modern, trustworthy, academic, minimal
```

Pages should feel like:

```txt
Google Classroom
Turnitin
Grammarly
Notion
Vercel dashboard
```

---

## 18. Antigravity Master Prompt

Copy this into Antigravity:

```txt
You are building a full-stack web application called “AI-Powered Feedback System for Student Assignments”.

Build the project using:

Frontend:
- Next.js 15
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- Framer Motion
- Firebase Client SDK
- React Hook Form
- Zod

Backend:
- Python FastAPI
- Firebase Admin SDK
- Firestore
- Firebase Storage
- Redis + Celery or RQ for background jobs
- ReportLab for PDF reports
- openpyxl for Excel exports
- Tesseract OCR service
- Docker-based sandbox for code execution
- DigitalOcean Inference API for AI model calls

The system has three roles:

1. Student
- Sign in with Google
- Select Student role
- Submit one assignment
- Upload PDF/DOCX/TXT/Image up to 1MB or paste up to 5000 characters
- Select assignment type: text, handwritten, coding, or custom
- Receive AI-generated feedback
- Download PDF feedback report

2. Instructor
- Sign in with Google
- Select Instructor role
- Apply for faculty verification
- Upload proof document
- Wait for admin approval
- Activate Pro access
- Upload batch assignments up to 30 files and 100MB total
- Enter assignment prompt
- Enter grading rubric
- Edit auto-extracted student names before processing
- Enable plagiarism checking
- Generate rubric-based grades
- Export Excel only or Excel + individual PDF reports

3. Admin
- View pending faculty applications
- Approve or reject faculty applications
- Grant or revoke Pro access
- View warnings
- Dismiss warnings
- Block users after repeated violations

Architecture:
Use MVC-inspired separation.
Frontend is the View.
FastAPI routes are Controllers.
Firestore models and services are Model/business logic.

Create these Firestore collections:
- users
- facultyApplications
- subscriptions
- submissions
- batchJobs
- feedbackReports
- plagiarismReports
- warnings
- auditLogs

AI Pipeline:
Replace local LM Studio models with DigitalOcean Inference API.
Implement a three-stage AI pipeline:

1. Specialist Agent:
Analyzes submission, assignment prompt, and rubric.
Finds strengths, weaknesses, mistakes, and initial score.

2. Judge Agent:
Reviews Specialist output.
Checks fairness, consistency, hallucinations, and rubric alignment.

3. Senior Agent:
Produces final polished feedback in JSON format.

Final AI output must be valid JSON:
{
  "overallScore": number,
  "status": "pass | fail | needs_review",
  "summary": string,
  "strengths": string[],
  "weaknesses": string[],
  "suggestions": string[],
  "rubricScores": [
    {
      "criterion": string,
      "score": number,
      "maxScore": number,
      "justification": string
    }
  ],
  "finalComments": string
}

Important backend services to create:
- digitalocean_service.py
- feedback_pipeline.py
- ocr_service.py
- plagiarism_service.py
- grading_service.py
- report_service.py
- warning_service.py
- file_service.py
- code_sandbox_service.py

API routes:

Auth:
POST /api/auth/sync-user
GET /api/auth/me
POST /api/auth/select-role

Student:
POST /api/student/submissions
GET /api/student/submissions/{id}
GET /api/student/submissions/{id}/feedback
GET /api/student/submissions/{id}/download-pdf

Instructor:
POST /api/instructor/faculty-application
GET /api/instructor/faculty-application/status
POST /api/instructor/batch
GET /api/instructor/batch/{id}
POST /api/instructor/batch/{id}/confirm-names
POST /api/instructor/batch/{id}/process
GET /api/instructor/batch/{id}/export

Admin:
GET /api/admin/faculty-applications
POST /api/admin/faculty-applications/{id}/approve
POST /api/admin/faculty-applications/{id}/reject
POST /api/admin/users/{id}/grant-pro
POST /api/admin/users/{id}/revoke-pro
GET /api/admin/warnings
POST /api/admin/warnings/{id}/dismiss

Security:
- All backend routes must verify Firebase ID token.
- Enforce role-based access control.
- Enforce student single-file limit.
- Enforce instructor batch limit of 30 files and 100MB total.
- Block users if blockedUntil is in the future.
- Never expose DigitalOcean API key to frontend.
- Code execution must run only in isolated Docker containers with timeout, memory limit, and no network access.

Frontend pages:
- Landing page
- Login page
- Role selection page
- Student dashboard
- Student submit assignment page
- Student feedback page
- Instructor dashboard
- Faculty verification page
- Pro subscription page
- Batch upload page
- Student name editing page
- Batch results/export page
- Admin dashboard
- Faculty applications page
- User management page
- Warning management page

UI style:
Modern academic SaaS.
Use shadcn/ui components.
Use responsive layouts.
Use dashboard cards, upload zones, status badges, progress bars, tables, and clean report views.
Use blue/indigo as primary color and emerald/cyan as accent.
Use Inter or Geist font.
```

---

## 19. Development Order

Build in this order:

```txt
1. Firebase project setup
2. Next.js frontend setup
3. FastAPI backend setup
4. Firebase Auth login
5. Role selection
6. Firestore user profile creation
7. Student single assignment upload
8. Firebase Storage integration
9. OCR service
10. DigitalOcean AI service
11. Specialist → Judge → Senior feedback pipeline
12. PDF report generation
13. Instructor faculty application
14. Admin approval panel
15. Pro access logic
16. Batch upload
17. Student name editing table
18. Batch AI processing with background jobs
19. Excel export
20. Individual PDF export
21. Plagiarism similarity module
22. Warning/block system
23. Testing and polish
24. Deployment
```

---

## 20. Final Recommendation

For the actual build, use:

```txt
Antigravity: full-stack coding
Figma Make: main UI/UX design generation
v0 by Vercel: React component generation
DigitalOcean Inference: AI model API instead of local LM Studio
Firebase: auth, database, and storage
FastAPI: backend API
Next.js: frontend
```

This setup keeps the FYP aligned with the documentation while making it more practical, scalable, and easier to demo than running local AI models.

