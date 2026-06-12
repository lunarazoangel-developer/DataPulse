from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from api.routes import files, analyze, payload, databases, ai

app = FastAPI(title="DataPulse API", description="Backend API for DataPulse data cleaning application")

@app.middleware("http")
async def add_cors_headers(request, call_next):
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            }
        )
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(databases.router, prefix="/api/databases", tags=["databases"])
app.include_router(analyze.router, prefix="/api/analyze", tags=["analyze"])
app.include_router(payload.router, prefix="/api/payload", tags=["payload"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])

@app.get("/")
def root():
    return {"message": "DataPulse API is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
