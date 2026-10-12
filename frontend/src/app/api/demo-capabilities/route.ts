import { API_URL } from "@/lib/api-config";
export const dynamic = "force-dynamic";
export const maxDuration = 90;

export async function GET() {
  try {
    const response = await fetch(`${API_URL}/api/capabilities`, { cache: "no-store", signal: AbortSignal.timeout(75000) });
    if (!response.ok) throw new Error("Backend unavailable");
    const value = await response.json();
    return Response.json({ document_demo: value.document_demo === true, code_execution: value.code_execution === true,
      batch_grading: value.batch_grading === true, max_batch_files: value.max_batch_files,
      internal_similarity: value.internal_similarity === true, knowledge_base: value.knowledge_base === true,
      knowledge_base_method: value.knowledge_base_method, max_file_mb: value.max_file_mb }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ code_execution: false, error: "Backend unavailable" }, { status: 503 });
  }
}

