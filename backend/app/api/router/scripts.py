import json
import os
import traceback

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, SessionDep
from ...database import SessionLocal
from ...models.script import Script, ScriptSegment
from app.util import logger

router = APIRouter(prefix="/scripts", tags=["scripts"])

@router.get("/{video_id}")
async def get_script(video_id: int, db: SessionDep, user: CurrentUser):
    try:
        script = db.query(Script).filter(Script.video_id == video_id).first()
        if not script:
            print('not script!!!!')
            raise HTTPException(status_code=404, detail="脚本不存在")
        print(f'find script, {script.parse_file_path}')
        print(f'find script, {script.content}')
        script_content = '未找到文件'
        if script.parse_file_path and os.path.isfile(script.parse_file_path):
            try:
                with open(script.parse_file_path, 'r', encoding='utf-8') as f:
                    script_content = f.read()
                print(f"从文件 {script.parse_file_path} 读取脚本内容成功")
                print(f'文件内容:{script_content},  type is {type(script_content)}')
            except Exception as e:
                print(f"读取脚本内容时发生错误: {e}")
                script_content = script.content

        segments = db.query(ScriptSegment).filter(ScriptSegment.script_id == script.id).order_by(ScriptSegment.start_time).all()
        return {
            "id": script.id,
            "video_id": script.video_id,
            "content": script_content,
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
    except Exception as e:
        traceback.print_exc()
        print(f'error {str(e)}')

@router.get("/{video_id}/export")
async def export_script(video_id: int, db: SessionDep):
    try:
        script = db.query(Script).filter(Script.video_id == video_id).first()
        if not script:
            raise HTTPException(status_code=404, detail="脚本不存在")
        script_content = ''
        try:
            with open(script.parse_file_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
            
        except FileNotFoundError:
            script_content = script.content
        segments = db.query(ScriptSegment).filter(ScriptSegment.script_id == script.id).order_by(ScriptSegment.start_time).all()
        export_data = {
            "video_id": script.video_id,
            "script": script_content,
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
    except Exception as e:
        logger.error(f'export_script failed. {str(e)}')
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")