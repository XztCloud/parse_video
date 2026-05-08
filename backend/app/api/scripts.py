from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from ..database import SessionLocal
from ..models.script import Script, ScriptSegment

router = APIRouter(prefix="/scripts", tags=["scripts"])

@router.get("/{video_id}")
async def get_script(video_id: int):
    db = SessionLocal()
    try:
        script = db.query(Script).filter(Script.video_id == video_id).first()
        if not script:
            raise HTTPException(status_code=404, detail="脚本不存在")
        segments = db.query(ScriptSegment).filter(ScriptSegment.script_id == script.id).order_by(ScriptSegment.start_time).all()
        return {
            "id": script.id,
            "video_id": script.video_id,
            "content": script.content,
            "segments": [
                {
                    "id": seg.id,
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "shot_description": seg.shot_description,
                    "dialogue": seg.dialogue,
                    "segment_type": seg.segment_type.value,
                }
                for seg in segments
            ],
        }
    finally:
        db.close()

@router.get("/{video_id}/export")
async def export_script(video_id: int):
    db = SessionLocal()
    try:
        script = db.query(Script).filter(Script.video_id == video_id).first()
        if not script:
            raise HTTPException(status_code=404, detail="脚本不存在")
        segments = db.query(ScriptSegment).filter(ScriptSegment.script_id == script.id).order_by(ScriptSegment.start_time).all()
        export_data = {
            "video_id": script.video_id,
            "script": script.content,
            "segments": [
                {
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "shot_description": seg.shot_description,
                    "dialogue": seg.dialogue,
                    "segment_type": seg.segment_type.value,
                }
                for seg in segments
            ],
        }
        return JSONResponse(content=export_data, headers={"Content-Disposition": f"attachment; filename=script_{video_id}.json"})
    finally:
        db.close()