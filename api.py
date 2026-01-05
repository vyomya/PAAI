from fastapi import FastAPI
from pydantic import BaseModel
from agentic_framework import run_agent
import uvicorn

app = FastAPI()


class Request(BaseModel):
    query: str


class Response(BaseModel):
    response: str


@app.post("/agent")
async def call_agent(request: Request) -> Response:
    """Call the agentic framework and return its response"""
    # Import your agentic framework
    
    result = run_agent(request.query)
    
    return Response(response=result)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)