# GradeWise Roadmap Notes

## Internet Plagiarism Search

Status: planned / off by default.

Internal similarity is implemented with local Postgres + embeddings and can compare submissions inside the same batch, assignment, or subject.

Internet plagiarism should remain disabled until a real web-search provider is configured. DigitalOcean serverless inference alone can grade and reason over supplied text, but it does not browse the public web by itself. To enable web plagiarism later, create a DigitalOcean Gradient Agent with a web-search tool and set:

```env
DIGITALOCEAN_WEB_SEARCH_AGENT_URL=
DIGITALOCEAN_WEB_SEARCH_AGENT_KEY=
```

Expected future behavior:

1. Extract strongest unique passages from the submission.
2. Send them to the DigitalOcean web-search agent.
3. Receive structured JSON matches with source URL, source title, matched snippet, and similarity percent.
4. Store results in `plagiarism_reports`.
5. Show evidence to the instructor for review.

Important grading rule: internet plagiarism findings should flag the report for instructor review, not automatically deduct marks.
