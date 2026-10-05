const legacyApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// A separate public value supports demo deployment when a legacy Vercel
// secret cannot be converted into a public configuration variable.
export const API_URL = process.env.NEXT_PUBLIC_DOCUMENT_DEMO === "true"
  ? process.env.NEXT_PUBLIC_DOCUMENT_DEMO_API_URL || legacyApiUrl
  : legacyApiUrl;
