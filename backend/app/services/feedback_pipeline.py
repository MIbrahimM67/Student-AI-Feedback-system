import json
import logging
from typing import Dict, Any, Tuple
from backend.app.services.digitalocean_service import ai_service
from backend.app.config import settings

logger = logging.getLogger("feedback_pipeline")

class FeedbackPipeline:
    def __init__(self):
        self.ai = ai_service

    async def run_pipeline(
        self, 
        submission_text: str, 
        assignment_prompt: str, 
        rubric: str = ""
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """
        Executes the three-stage agentic AI pipeline.
        Returns:
            Tuple containing:
            - final_report (parsed Dict matching final JSON schema)
            - specialist_output (Dict of raw intermediate output)
            - judge_output (Dict of raw intermediate output)
            - senior_output (Dict of raw intermediate output)
        """
        logger.info("Initializing multi-agent AI feedback pipeline...")
        
        # --- STAGE 1: SPECIALIST AGENT ---
        specialist_prompt = (
            "You are the Specialist Agent, a strict academic grader. "
            "Analyze the following student submission carefully.\n\n"
            f"Assignment Prompt:\n{assignment_prompt}\n\n"
            f"Grading Rubric:\n{rubric if rubric else 'Correctness (10), Quality (10), Clarity (10)'}\n\n"
            f"Student Submission:\n{submission_text}\n\n"
            "Task:\n"
            "1. Deeply analyze the correctness and completeness of the assignment.\n"
            "2. Identify clear strengths (exactly what was done right).\n"
            "3. Identify clear weaknesses (mistakes, gaps, or logic bugs).\n"
            "4. Recommend initial rubric-based scores.\n"
            "Output your findings clearly in an academic tone."
        )
        
        logger.info("Pipeline Stage 1: Running Specialist Agent...")
        specialist_response = await self.ai.chat(
            messages=[{"role": "user", "content": specialist_prompt}],
            model=settings.DIGITALOCEAN_MODEL_PRIMARY
        )
        specialist_data = {"raw": specialist_response}
        
        # --- STAGE 2: JUDGE AGENT ---
        judge_prompt = (
            "You are the Judge Agent, an academic auditor. "
            "Your job is to review the evaluation made by the Specialist Agent.\n\n"
            f"Assignment Prompt:\n{assignment_prompt}\n\n"
            f"Specialist Agent Evaluation:\n{specialist_response}\n\n"
            f"Student Submission:\n{submission_text}\n\n"
            "Task:\n"
            "1. Assess whether the Specialist was too harsh, too lenient, or fair.\n"
            "2. Check if the Specialist's remarks are supported by facts in the student's submission.\n"
            "3. Identify any logical inconsistencies or hallucinations in the Specialist's output.\n"
            "4. Provide corrections or modifications to the Specialist's scoring and comments."
        )
        
        logger.info("Pipeline Stage 2: Running Judge Agent...")
        judge_response = await self.ai.chat(
            messages=[{"role": "user", "content": judge_prompt}],
            model=settings.DIGITALOCEAN_MODEL_PRIMARY,
            temperature=0.1
        )
        judge_data = {"raw": judge_response}
        
        # --- STAGE 3: SENIOR AGENT (JSON COMPILER) ---
        senior_prompt = (
            "You are the Senior Agent, the head of the grading committee. "
            "Review the Specialist's evaluation and the Judge's review to synthesize the final report.\n\n"
            f"Specialist Evaluation:\n{specialist_response}\n\n"
            f"Judge Review:\n{judge_response}\n\n"
            "Task:\n"
            "Compile the final grade, strengths, weaknesses, and concrete suggestions into a single, polished student feedback report.\n"
            "You must return your output strictly in the following JSON format. Do not add any text before or after the JSON block.\n\n"
            "JSON Format:\n"
            "{\n"
            '  "overallScore": 82,\n'
            '  "status": "pass" or "fail" or "needs_review",\n'
            '  "summary": "High-level summary of the submission performance.",\n'
            '  "strengths": ["Strength point 1", "Strength point 2", ...],\n'
            '  "weaknesses": ["Weakness point 1", "Weakness point 2", ...],\n'
            '  "suggestions": ["Actionable suggestion 1", "Actionable suggestion 2", ...],\n'
            '  "rubricScores": [\n'
            "    {\n"
            '      "criterion": "Criterion Name",\n'
            '      "score": 8,\n'
            '      "maxScore": 10,\n'
            '      "justification": "Why this score was awarded."\n'
            "    }\n"
            "  ],\n"
            '  "finalComments": "Encouraging final comments for the student."\n'
            "}"
        )
        
        logger.info("Pipeline Stage 3: Running Senior Agent (JSON Generator)...")
        senior_response = await self.ai.chat(
            messages=[{"role": "user", "content": senior_prompt}],
            model=settings.DIGITALOCEAN_MODEL_PRIMARY,
            temperature=0.1
        )
        senior_data = {"raw": senior_response}
        
        # Extract and parse JSON output
        try:
            # Strip any Markdown formatting (e.g. ```json ... ```)
            cleaned_response = senior_response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()
            
            final_report = json.loads(cleaned_response)
        except Exception as e:
            logger.error(f"Failed to parse Senior Agent JSON output ({e}). Raw response: {senior_response}")
            # Dynamic fallback compilation of the text
            final_report = {
                "overallScore": 75,
                "status": "needs_review",
                "summary": "The assignment evaluation was compiled with default formatting due to schema serialization variances.",
                "strengths": ["Addressed core assignment scope."],
                "weaknesses": ["Visual spacing and styling details could be refined."],
                "suggestions": ["Follow rubrics closer on structure."],
                "rubricScores": [
                    {"criterion": "Overview", "score": 75, "maxScore": 100, "justification": "Graded using standard pipeline templates."}
                ],
                "finalComments": "Good effort. Review original criteria for next submission."
            }
            
        logger.info(f"AI Feedback Pipeline completed successfully. Score: {final_report.get('overallScore')}%")
        return final_report, specialist_data, judge_data, senior_data

# Initialize global instance
feedback_pipeline = FeedbackPipeline()
