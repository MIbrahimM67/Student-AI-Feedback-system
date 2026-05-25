import os
import sys
import unittest
from fastapi.testclient import TestClient

# Add workspace backend directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Set environment variable to force mocks
os.environ["USE_MOCKS"] = "True"

from backend.app.main import app

class TestAssignmentFeedbackSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Mock bearer headers for active role profiles
        cls.admin_headers = {"Authorization": "Bearer mock_admin_token"}
        cls.instructor_headers = {"Authorization": "Bearer mock_instructor_token"}
        cls.student_headers = {"Authorization": "Bearer mock_student_token"}

    def test_01_health_check(self):
        """Test the basic root API endpoint returns online status."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["database"], "mock_in_memory")

    def test_02_auth_me(self):
        """Test auth /me retrieves student and admin user settings correctly."""
        # Test student auth
        response = self.client.get("/api/auth/me", headers=self.student_headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["uid"], "mock_student_uid")
        self.assertEqual(data["role"], "student")
        
        # Test admin auth
        response = self.client.get("/api/auth/me", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["uid"], "mock_admin_uid")
        self.assertEqual(data["role"], "admin")

    def test_03_role_selection(self):
        """Test student and instructor onboarding role selector."""
        response = self.client.post(
            "/api/auth/select-role", 
            json={"role": "student"},
            headers=self.student_headers
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "role_updated")
        self.assertEqual(data["user"]["role"], "student")

    def test_04_student_submit_text(self):
        """Test single assignment essay submission, warning policies, and AI pipeline results."""
        # Test a standard essay (pass)
        response = self.client.post(
            "/api/student/submissions",
            data={
                "type": "text",
                "prompt": "Write a short summary of modern tech history.",
                "rubric": "Structure, Content, Flow",
                "inputText": "This is a brief student essay highlighting the history of industrialization and steam machines."
            },
            headers=self.student_headers
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("submissionId", data)
        self.assertIn("pdfUrl", data)
        self.assertGreaterEqual(data["evaluation"]["overallScore"], 70)
        self.assertEqual(data["evaluation"]["status"], "pass")

    def test_05_student_submit_warning_violation(self):
        """Test compliance scanning warning flag and blocking logic."""
        response = self.client.post(
            "/api/student/submissions",
            data={
                "type": "text",
                "prompt": "Submit final test draft",
                "rubric": "Clarity",
                "inputText": "Here is the leaked exam cheat sheet that has confidential key answers for tomorrow."
            },
            headers=self.student_headers
        )
        self.assertEqual(response.status_code, 200) # Returns 200 with flagged status JSON
        data = response.json()
        self.assertEqual(data["status"], "flagged")
        self.assertIn("warning", data["detail"].lower())

    def test_06_instructor_apply_verification(self):
        """Test faculty verification submission with proof files."""
        # Simple bytes buffer for file upload testing
        proof_file = ("proof.pdf", b"Official University Faculty Proof PDF Data", "application/pdf")
        
        response = self.client.post(
            "/api/instructor/faculty-application",
            data={
                "fullName": "Sarah Jenkins",
                "university": "Quaid-e-Azam University",
                "department": "Computer Science",
                "designation": "Assistant Professor",
                "officialEmail": "jenkins@qau.edu.pk"
            },
            files={"proofFile": proof_file},
            headers=self.instructor_headers
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "submitted")

    def test_07_instructor_batch_grading(self):
        """Test instructor bulk uploads (up to 30 files) staging and name edits."""
        files = [
            ("files", ("student1.txt", b"Mathematical eigenvalues solve charakteristic lambda A - lambda I = 0.", "text/plain")),
            ("files", ("student2.txt", b"World history has experienced industrial shifts in textile looms.", "text/plain"))
        ]
        
        response = self.client.post(
            "/api/instructor/batch",
            data={
                "prompt": "Evaluate history or math matrices assignment.",
                "rubric": "Detail, Logic",
                "plagiarismEnabled": "True",
                "type": "text"
            },
            files=files,
            headers=self.instructor_headers # Pro instructor
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("batchId", data)
        self.assertEqual(data["totalFiles"], 2)
        # Check name review lists are generated
        self.assertEqual(len(data["nameReviewList"]), 2)

    def test_08_admin_approvals_and_warnings(self):
        """Test administrative listings, verification approvals, and warnings list."""
        # List warnings
        response = self.client.get("/api/admin/warnings", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        warnings_list = response.json()
        self.assertTrue(len(warnings_list) > 0) # The student leak submission generated one

        # List applications
        response = self.client.get("/api/admin/faculty-applications", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        apps_list = response.json()
        self.assertTrue(len(apps_list) > 0)

if __name__ == "__main__":
    unittest.main()
