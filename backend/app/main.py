import uvicorn
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.config import settings
from backend.app.api import auth_routes, student_routes, instructor_routes, admin_routes

# Initialize Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Initialize FastAPI App
app = FastAPI(
    title=settings.APP_NAME,
    description="Full-stack AI-Powered Student Assignment Feedback System Backend APIs.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Policy configuration
origins = [
    "http://localhost:3000",
    "https://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For flexible FYP local demonstrations
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Endpoints Routers
app.include_router(auth_routes.router)
app.include_router(student_routes.router)
app.include_router(instructor_routes.router)
app.include_router(admin_routes.router)

# --- GLOBAL MIDDLEWARE & DIAGNOSTIC ROOT ---

@app.middleware("http")
async def db_request_logger_middleware(request: Request, call_next):
    """
    HTTP traffic and operational processing latency logger.
    """
    import time
    start = time.time()
    response = await call_next(request)
    latency = time.time() - start
    logger.info(f"API Traffic: {request.method} {request.url.path} | Status {response.status_code} | Duration {int(latency*1000)}ms")
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches all unhandled syntax/runtime bugs and packages them safely inside a JSON response.
    """
    logger.critical(f"Unhandled runtime exception caught at {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"System error has occurred: {str(exc)}"}
    )

@app.get("/")
async def root():
    """
    Base server diagnostics health status route.
    """
    import sys
    from backend.app.firebase import is_mock_firebase
    return {
        "status": "online",
        "service": settings.APP_NAME,
        "python": sys.version,
        "database": "mock_in_memory" if is_mock_firebase else "firebase_firestore_cloud",
        "documentation": "/docs"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
