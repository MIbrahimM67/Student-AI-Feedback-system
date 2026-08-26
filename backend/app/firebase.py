import os
import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from backend.app.config import settings

logger = logging.getLogger("firebase")
logging.basicConfig(level=logging.INFO)

# --- MOCK FIREBASE CLIENTS FOR OFFLINE DEVELOPMENT ---

class MockDocumentReference:
    def __init__(self, collection_name: str, doc_id: str, db_store: Dict[str, Dict[str, Any]]):
        self.collection_name = collection_name
        self.id = doc_id
        self._db_store = db_store
        
    def get(self) -> 'MockDocumentSnapshot':
        doc_data = self._db_store.get(self.collection_name, {}).get(self.id)
        return MockDocumentSnapshot(self.id, doc_data)
        
    def set(self, data: Dict[str, Any], merge: bool = False) -> None:
        if self.collection_name not in self._db_store:
            self._db_store[self.collection_name] = {}
        
        current_data = self._db_store[self.collection_name].get(self.id, {})
        
        # Merge or overwrite
        if merge:
            merged = {**current_data, **data}
            self._db_store[self.collection_name][self.id] = merged
        else:
            self._db_store[self.collection_name][self.id] = data
            
        logger.info(f"[Mock Firestore] SET in '{self.collection_name}' doc '{self.id}': {data}")

    def update(self, data: Dict[str, Any]) -> None:
        if self.collection_name not in self._db_store or self.id not in self._db_store[self.collection_name]:
            raise ValueError(f"Document {self.id} does not exist in collection {self.collection_name}")
        self._db_store[self.collection_name][self.id].update(data)
        logger.info(f"[Mock Firestore] UPDATE in '{self.collection_name}' doc '{self.id}': {data}")

    def delete(self) -> None:
        if self.collection_name in self._db_store and self.id in self._db_store[self.collection_name]:
            del self._db_store[self.collection_name][self.id]
            logger.info(f"[Mock Firestore] DELETE in '{self.collection_name}' doc '{self.id}'")


class MockDocumentSnapshot:
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]]):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        
    def to_dict(self) -> Optional[Dict[str, Any]]:
        return self._data.copy() if self._data else None


class MockQuery:
    def __init__(self, collection_name: str, db_store: Dict[str, Dict[str, Any]], filters: List[tuple] = None):
        self.collection_name = collection_name
        self._db_store = db_store
        self._filters = filters or []
        
    def where(self, field: str, op: str, value: Any) -> 'MockQuery':
        new_filters = self._filters.copy()
        new_filters.append((field, op, value))
        return MockQuery(self.collection_name, self._db_store, new_filters)
        
    def stream(self) -> List[MockDocumentSnapshot]:
        docs_dict = self._db_store.get(self.collection_name, {})
        results = []
        for doc_id, doc_data in docs_dict.items():
            match = True
            for field, op, val in self._filters:
                doc_val = doc_data.get(field)
                if op == '==' and doc_val != val:
                    match = False
                elif op == '!=' and doc_val == val:
                    match = False
                elif op == '>' and not (doc_val > val):
                    match = False
                elif op == '<' and not (doc_val < val):
                    match = False
                elif op == 'in' and doc_val not in val:
                    match = False
                elif op == 'array_contains' and val not in (doc_val or []):
                    match = False
            if match:
                results.append(MockDocumentSnapshot(doc_id, doc_data))
        return results

    def get(self) -> List[MockDocumentSnapshot]:
        return self.stream()


class MockCollectionReference(MockQuery):
    def __init__(self, collection_name: str, db_store: Dict[str, Dict[str, Any]]):
        super().__init__(collection_name, db_store)
        
    def document(self, doc_id: str) -> MockDocumentReference:
        return MockDocumentReference(self.collection_name, doc_id, self._db_store)
        
    def add(self, data: Dict[str, Any]) -> tuple[MockDocumentReference, Any]:
        doc_id = str(uuid.uuid4())
        ref = self.document(doc_id)
        ref.set(data)
        return ref, None


class MockFirestoreClient:
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        # Prepopulate with a default admin user and pro subscription for initial seed
        self._store["users"] = {
            "mock_admin_uid": {
                "uid": "mock_admin_uid",
                "email": "admin@academic.edu",
                "displayName": "System Admin",
                "role": "admin",
                "facultyStatus": "approved",
                "proStatus": "active",
                "warningCount": 0,
                "createdAt": datetime.utcnow().isoformat()
            },
            "mock_instructor_uid": {
                "uid": "mock_instructor_uid",
                "email": "instructor@academic.edu",
                "displayName": "Dr. Sarah Jenkins",
                "role": "instructor",
                "facultyStatus": "approved",
                "proStatus": "active",
                "warningCount": 0,
                "createdAt": datetime.utcnow().isoformat()
            },
            "mock_student_uid": {
                "uid": "mock_student_uid",
                "email": "student@academic.edu",
                "displayName": "Ibrahim Student",
                "role": "student",
                "facultyStatus": "none",
                "proStatus": "inactive",
                "warningCount": 0,
                "createdAt": datetime.utcnow().isoformat()
            }
        }
        
    def collection(self, collection_name: str) -> MockCollectionReference:
        return MockCollectionReference(collection_name, self._store)


class MockBlob:
    def __init__(self, name: str, mock_storage_dir: str):
        self.name = name
        self.mock_storage_dir = mock_storage_dir
        self._filepath = os.path.join(mock_storage_dir, name)
        
    def upload_from_string(self, content: Any, content_type: str = "text/plain") -> None:
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        if isinstance(content, bytes):
            with open(self._filepath, 'wb') as f:
                f.write(content)
        else:
            with open(self._filepath, 'w', encoding='utf-8') as f:
                f.write(content)
        logger.info(f"[Mock Storage] Uploaded string/byte file to '{self.name}'")

    def upload_from_filename(self, filename: str) -> None:
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        import shutil
        shutil.copy(filename, self._filepath)
        logger.info(f"[Mock Storage] Uploaded file from path to '{self.name}'")

    def download_as_string(self) -> bytes:
        if not os.path.exists(self._filepath):
            return b""
        with open(self._filepath, 'rb') as f:
            return f.read()

    def generate_signed_url(self, **kwargs) -> str:
        # Returns a mock local server URL or a file link
        clean_path = self._filepath.replace("\\", "/")
        return f"file:///{clean_path}"


class MockBucket:
    def __init__(self):
        # Create a mock storage folder in the workspace's scratch/temp area
        self.storage_dir = r"i:\fyp implementation\backend\app\temp_mock_storage"
        os.makedirs(self.storage_dir, exist_ok=True)
        
    def blob(self, blob_name: str) -> MockBlob:
        return MockBlob(blob_name, self.storage_dir)


class MockStorageClient:
    def __init__(self):
        self._bucket = MockBucket()
        
    def bucket(self, name: str = None) -> MockBucket:
        return self._bucket


# --- FIREBASE SERVICE LOADER & GRACEFUL FALLBACKS ---

firebase_auth = None
db = None
bucket = None
is_mock_firebase = False

# Pro-tier production addition: handle stringified Firebase credentials securely from environment variables
service_account_path = settings.FIREBASE_SERVICE_ACCOUNT_PATH
service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")

if service_account_json:
    try:
        temp_path = "/tmp/firebase_credentials.json" if os.name != 'nt' else "temp_firebase_credentials.json"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(service_account_json)
        service_account_path = temp_path
        logger.info("Successfully wrote stringified FIREBASE_SERVICE_ACCOUNT_JSON credentials to disk.")
    except Exception as parse_err:
        logger.error(f"Failed to write stringified FIREBASE_SERVICE_ACCOUNT_JSON credentials: {parse_err}")

try:
    if settings.USE_MOCKS or not service_account_path:
        raise ImportError("Mocks enabled or credentials path omitted.")
        
    import firebase_admin
    from firebase_admin import credentials, firestore, storage, auth
    
    cred = credentials.Certificate(service_account_path)
    firebase_admin.initialize_app(cred, {
        'storageBucket': settings.FIREBASE_STORAGE_BUCKET
    })
    
    db = firestore.client()
    bucket = storage.bucket()
    firebase_auth = auth
    logger.info("Successfully initialized Firebase Admin SDK.")
    
except Exception as e:
    logger.warning(f"Firebase Client SDK could not be loaded ({e}). Initializing In-Memory Mock clients instead.")
    db = MockFirestoreClient()
    bucket = MockBucket()
    is_mock_firebase = True
    
    # Simple Mock Auth helper
    class MockAuth:
        @staticmethod
        def verify_id_token(token: str) -> Dict[str, Any]:
            # Expect mock tokens like "mock_admin_token", "mock_instructor_token", "mock_student_token"
            if "admin" in token:
                return {"uid": "mock_admin_uid", "email": "admin@academic.edu", "name": "System Admin"}
            elif "instructor" in token:
                return {"uid": "mock_instructor_uid", "email": "instructor@academic.edu", "name": "Dr. Sarah Jenkins"}
            elif "student" in token:
                return {"uid": "mock_student_uid", "email": "student@academic.edu", "name": "Ibrahim Student"}
            else:
                # Default generic student
                return {"uid": f"uid_{token}", "email": f"{token}@example.com", "name": token.capitalize()}
                
        @staticmethod
        def get_user(uid: str) -> Any:
            class MockUser:
                def __init__(self, uid):
                    self.uid = uid
                    self.email = f"{uid}@academic.edu"
                    self.display_name = uid.replace("mock_", "").replace("_", " ").title()
            return MockUser(uid)
            
    firebase_auth = MockAuth()
