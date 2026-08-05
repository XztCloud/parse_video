import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import AsyncSessionDep
from ...models.script import Script, ScriptSegment
from app.util import logger

router = APIRouter(prefix="/scripts", tags=["scripts"])

@router.get("/{video_id}")
async def get_script(video_id: int, db: AsyncSessionDep):
    try:
        result = await db.execute(select(Script).where(Script.video_id == video_id))
        script = result.scalar_one_or_none()
        if not script:
            logger.error('not script!!!!')
            raise HTTPException(status_code=404, detail="脚本不存在")
        logger.info(f'find script, {script.parse_file_path}')
        script_content = '未找到文件'
        if script.parse_file_path and os.path.isfile(script.parse_file_path):
            try:
                with open(script.parse_file_path, 'r', encoding='utf-8') as f:
                    script_content = f.read()
                logger.info(f"从文件 {script.parse_file_path} 读取脚本内容成功")
            except Exception as e:
                logger.error(f"读取脚本内容时发生错误: {e}")
                script_content = script.content

        result = await db.execute(
            select(ScriptSegment)
            .where(ScriptSegment.script_id == script.id)
            .order_by(ScriptSegment.start_time)
        )
        segments = result.scalars().all()
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception('get_script 失败')
        logger.error(f'error {str(e)}')
        raise

@router.get("/{video_id}/export")
async def export_script(video_id: int, db: AsyncSessionDep):
    try:
        result = await db.execute(select(Script).where(Script.video_id == video_id))
        script = result.scalar_one_or_none()
        if not script:
            raise HTTPException(status_code=404, detail="脚本不存在")
        script_content = ''
        try:
            with open(script.parse_file_path, 'r', encoding='utf-8') as f:
                script_content = f.read()

        except FileNotFoundError:
            script_content = script.content
        except Exception as e:
            # 其他文件读取错误，也回退到使用 content
            logger.warning(f"读取脚本文件失败: {e}，使用 content 字段")
            script_content = script.content
        result = await db.execute(
            select(ScriptSegment)
            .where(ScriptSegment.script_id == script.id)
            .order_by(ScriptSegment.start_time)
        )
        segments = result.scalars().all()
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception('get_script_export 失败')
        logger.error(f'export_script failed.')
        raise
