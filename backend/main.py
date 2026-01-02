from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import sys
import os

# Add parent directory to path to import graph modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.workflow import create_game_graph
from langgraph.types import Command

from contextlib import asynccontextmanager
from backend.database import engine, Base, AsyncSessionLocal
from backend.crud import get_all_characters, create_character
from characters import student, office_worker, artist, chef, teacher

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Seed initial data if empty
    async with AsyncSessionLocal() as db:
        characters = await get_all_characters(db)
        if not characters:
            print("Creating initial character data...")
            character_modules = [student, office_worker, artist, chef, teacher]
            for module in character_modules:
                char_info = module.get_character_info()
                # Remove keys not in model (like 'age') to prevent TypeError
                char_info_clean = {k: v for k, v in char_info.items() if k != 'age'}
                await create_character(db, char_info_clean)
            print("Seeding complete.")
            
    yield
    # Shutdown
    await engine.dispose()

app = FastAPI(title="Phantom Log API", lifespan=lifespan)

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Graph
graph_app = create_game_graph()

# Models
class GameStartRequest(BaseModel):
    thread_id: str = "phantom_game_session_1"

class UserActionRequest(BaseModel):
    thread_id: str
    action_type: str  # "chat", "vote", "suspect", "next"
    content: Optional[str] = None
    target: Optional[str] = None

class GameStateResponse(BaseModel):
    messages: List[Dict[str, Any]]
    characters: List[Dict[str, Any]]
    round_number: int  # Added round_number
    phase: str
    day_night: str
    alive_status: Dict[str, bool]
    suspicion_counts: Dict[str, int]
    night_logs: List[str]
    clues: List[str]
    round_summaries: Dict[int, str]
    game_over: bool
    phantom_name: Optional[str] = None

# Helper to format messages
def format_messages(messages):
    formatted = []
    for msg in messages:
        sender = getattr(msg, "name", "System")
        content = msg.content
        formatted.append({"sender": sender, "content": content})
    return formatted

@app.post("/api/game/start")
async def start_game(request: GameStartRequest):
    config = {"configurable": {"thread_id": request.thread_id}}
    
    try:
        # Check if state exists
        current_state = await graph_app.aget_state(config)
        if not current_state.next:
             # Initial start
            await graph_app.ainvoke({}, config)
        
        return {"message": "Game session started", "thread_id": request.thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/game/state/{thread_id}")
async def get_game_state(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    current_state = await graph_app.aget_state(config)
    
    if not current_state.values:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    state = current_state.values
    
    return {
        "messages": format_messages(state.get("messages", [])),
        "characters": state.get("characters", []),
        "round_number": state.get("round_number", 1),  # Return round_number
        "phase": state.get("phase", "unknown"),
        "day_night": state.get("day_night", "day"),
        "alive_status": state.get("alive_status", {}),
        "suspicion_counts": state.get("suspicion_counts", {}),
        "night_logs": state.get("night_logs", []),
        "clues": state.get("clues", []),
        "round_summaries": state.get("round_summaries", {}),
        "game_over": state.get("phase") == "end",
        "phantom_name": state.get("phantom_name") if state.get("phase") == "end" else None
    }

@app.post("/api/game/action")
async def perform_action(request: UserActionRequest):
    config = {"configurable": {"thread_id": request.thread_id}}
    
    resume_data = {}
    
    if request.action_type == "chat":
        # User chatting or interrupting
        resume_data = {"user_input": request.content}
        # If in discussion, might need to specify phase to ensure correct routing
        # But usually user_input is enough for wait_user to route to user_input node
        
    elif request.action_type == "vote":
        resume_data = {"user_target": request.target}
        
    elif request.action_type == "suspect":
        resume_data = {"user_input": "suspect", "user_target": request.target}
        
    elif request.action_type == "next":
        # Just proceed (e.g. Enter key in CLI)
        resume_data = {"action": "next"}
        
    elif request.action_type == "night_start":
         resume_data = {"phase": "night"}

    elif request.action_type == "discuss":
        resume_data = {
            "user_input": "[AI들끼리 자유롭게 대화를 시작합니다]",
            "phase": "free_discussion",
            "action": "next"
        }

    elif request.action_type == "end_discuss":
        resume_data = {
            "user_input": "exit",
            "phase": "discussion"
        }

    elif request.action_type == "start_one_on_one":
        # Start 1:1 chat with a specific target
        resume_data = {
            "phase": "one_on_one",
            "user_input": f"[{request.target}에게] (대화 시작)"
        }

    try:
        # Resume graph execution
        await graph_app.ainvoke(Command(resume=resume_data), config)
        
        # Fetch updated state
        return await get_game_state(request.thread_id)
        
    except Exception as e:
        # If graph is not in a state to accept the command (e.g. not interrupted), 
        # it might raise an error.
        raise HTTPException(status_code=400, detail=f"Action failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
