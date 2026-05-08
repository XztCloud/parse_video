# 视频脚本解析平台 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个视频脚本解析Web平台，支持上传视频/抖音链接，通过国内云端AI服务生成结构化脚本（台词、镜头、时间戳）。

**Architecture:** 前端Vue3+Element Plus，后端FastAPI+Celery异步任务队列，AI服务使用阿里云ASR+通义千问VL+通义千问，视频处理使用FFmpeg，数据存储PostgreSQL+本地文件系统。

**Tech Stack:** Vue3, TypeScript, Element Plus, Vite, video.js, FastAPI, Celery, Redis, PostgreSQL, FFmpeg, 阿里云ASR, 通义千问VL, 通义千问, yt-dlp

---

## 文件结构

```
parse_video/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── video.py
│   │   │   └── script.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── video.py
│   │   │   └── script.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── videos.py
│   │   │   └── scripts.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── video_processor.py
│   │   │   ├── douyin_parser.py
│   │   │   ├── asr_service.py
│   │   │   ├── visual_service.py
│   │   │   └── script_generator.py
│   │   └── tasks/
│   │       ├── __init__.py
│   │       └── parse_video.py
│   ├── celery_app.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.vue
│   │   ├── main.ts
│   │   ├── router/index.ts
│   │   ├── views/
│   │   │   ├── HomeView.vue
│   │   │   ├── ParseProgress.vue
│   │   │   └── ScriptDetail.vue
│   │   ├── components/
│   │   │   ├── VideoUploader.vue
│   │   │   ├── DouyinInput.vue
│   │   │   ├── ScriptTimeline.vue
│   │   │   └── VideoPlayer.vue
│   │   ├── api/index.ts
│   │   └── types/index.ts
│   ├── package.json
│   └── vite.config.ts
├── docs/superpowers/
│   ├── specs/
│   └── plans/
└── docker-compose.yml
```

---

### Task 1: 后端项目初始化与基础设施

**Files:**
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`
- Create: `backend/requirements.txt`
- Create: `docker-compose.yml`

- [ ] **Step 1: 创建后端项目目录和requirements.txt**

```txt
fastapi==0.104.1
uvicorn==0.24.0
sqlalchemy==2.0.23
alembic==1.13.0
psycopg2-binary==2.9.9
celery==5.3.6
redis==5.0.1
python-multipart==0.0.6
httpx==0.25.2
pydantic==2.5.2
pydantic-settings==2.1.0
python-dotenv==1.0.0
dashscope==1.14.1
yt-dlp==2023.12.30
```

- [ ] **Step 2: 创建配置管理模块 config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/parse_video"
    REDIS_URL: str = "redis://localhost:6379/0"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 500 * 1024 * 1024
    ALIYUN_ASR_APP_KEY: str = ""
    ALIYUN_ASR_ACCESS_KEY: str = ""
    ALIYUN_ASR_ACCESS_SECRET: str = ""
    DASHSCOPE_API_KEY: str = ""
    MAX_CONCURRENT_TASKS: int = 3

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 3: 创建数据库连接模块 database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: 创建FastAPI入口 main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
import os

app = FastAPI(title="视频脚本解析平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

@app.get("/health")
def health_check():
    return {"status": "ok"}
```

- [ ] **Step 5: 创建docker-compose.yml**

```yaml
version: "3.8"
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: parse_video
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
volumes:
  pgdata:
```

- [ ] **Step 6: 启动基础设施并验证**

Run: `cd parse_video && docker-compose up -d`
Expected: PostgreSQL和Redis容器正常运行

---

### Task 2: 数据模型定义

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/video.py`
- Create: `backend/app/models/script.py`
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/video.py`
- Create: `backend/app/schemas/script.py`

- [ ] **Step 1: 创建Video数据模型**

```python
from sqlalchemy import Column, String, Integer, Float, DateTime, Enum
from sqlalchemy.orm import relationship
from ..database import Base
import enum
from datetime import datetime

class VideoSource(enum.Enum):
    LOCAL = "local"
    DOUYIN = "douyin"

class VideoStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"

class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    source_type = Column(Enum(VideoSource), default=VideoSource.LOCAL)
    source_url = Column(String(1024), nullable=True)
    file_path = Column(String(512), nullable=False)
    duration = Column(Float, nullable=True)
    status = Column(Enum(VideoStatus), default=VideoStatus.PENDING)
    progress = Column(Integer, default=0)
    error_message = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    script = relationship("Script", back_populates="video", uselist=False)
```

- [ ] **Step 2: 创建Script和ScriptSegment数据模型**

```python
from sqlalchemy import Column, String, Integer, Float, DateTime, Enum, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from ..database import Base
from datetime import datetime
import enum

class SegmentType(enum.Enum):
    SHOT = "shot"
    DIALOGUE = "dialogue"
    MIXED = "mixed"

class Script(Base):
    __tablename__ = "scripts"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), unique=True)
    content = Column(JSON, nullable=True)
    raw_asr_text = Column(Text, nullable=True)
    raw_visual_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    video = relationship("Video", back_populates="script")
    segments = relationship("ScriptSegment", back_populates="script", cascade="all, delete-orphan")

class ScriptSegment(Base):
    __tablename__ = "script_segments"
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("scripts.id"))
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    shot_description = Column(Text, nullable=True)
    dialogue = Column(Text, nullable=True)
    segment_type = Column(Enum(SegmentType), default=SegmentType.MIXED)
    script = relationship("Script", back_populates="segments")
```

- [ ] **Step 3: 创建Pydantic Schemas**

schemas/video.py:
```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class VideoUploadResponse(BaseModel):
    id: int
    title: str
    source_type: str
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

class VideoDetail(VideoUploadResponse):
    duration: Optional[float] = None
    progress: int = 0
    error_message: Optional[str] = None

class DouyinParseRequest(BaseModel):
    url: str
```

schemas/script.py:
```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class ScriptSegmentOut(BaseModel):
    id: int
    start_time: float
    end_time: float
    shot_description: Optional[str] = None
    dialogue: Optional[str] = None
    segment_type: str
    class Config:
        from_attributes = True

class ScriptSegmentUpdate(BaseModel):
    shot_description: Optional[str] = None
    dialogue: Optional[str] = None

class ScriptDetail(BaseModel):
    id: int
    video_id: int
    content: Optional[dict] = None
    raw_asr_text: Optional[str] = None
    raw_visual_text: Optional[str] = None
    segments: List[ScriptSegmentOut] = []
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True
```

- [ ] **Step 4: 在main.py中注册模型并创建数据库表**

在 main.py 末尾添加：
```python
from .database import Base, engine
from .models import video, script

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 5: 验证数据库表创建成功**

Run: `cd parse_video/backend && python -c "from app.models import video, script; print('Models loaded OK')"`
Expected: 输出 "Models loaded OK"

---

### Task 3: 视频处理服务（FFmpeg + 抖音解析）

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/video_processor.py`
- Create: `backend/app/services/douyin_parser.py`

- [ ] **Step 1: 创建FFmpeg视频处理服务**

```python
import subprocess
import os

class VideoProcessor:
    @staticmethod
    def extract_audio(video_path: str, output_path: str = None) -> str:
        if output_path is None:
            base = os.path.splitext(video_path)[0]
            output_path = f"{base}.wav"
        cmd = ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-y", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    @staticmethod
    def extract_frames(video_path: str, output_dir: str, fps: float = 1.0) -> list[str]:
        os.makedirs(output_dir, exist_ok=True)
        pattern = os.path.join(output_dir, "frame_%04d.jpg")
        cmd = ["ffmpeg", "-i", video_path, "-vf", f"fps={fps}", "-q:v", "2", "-y", pattern]
        subprocess.run(cmd, check=True, capture_output=True)
        frames = sorted([os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".jpg")])
        return frames

    @staticmethod
    def get_duration(video_path: str) -> float:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
```

- [ ] **Step 2: 创建抖音链接解析服务**

```python
import yt_dlp
import os
from ..config import settings

class DouyinParser:
    @staticmethod
    def download_video(url: str, output_dir: str = None) -> tuple[str, str]:
        if output_dir is None:
            output_dir = settings.UPLOAD_DIR
        os.makedirs(output_dir, exist_ok=True)
        ydl_opts = {"outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"), "format": "best", "quiet": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "unknown")
            filename = ydl.prepare_filename(info)
            return filename, title
```

- [ ] **Step 3: 验证服务导入**

Run: `cd parse_video/backend && python -c "from app.services.video_processor import VideoProcessor; from app.services.douyin_parser import DouyinParser; print('Services OK')"`
Expected: 输出 "Services OK"

---

### Task 4: AI服务集成（ASR + 视觉理解 + 脚本生成）

**Files:**
- Create: `backend/app/services/asr_service.py`
- Create: `backend/app/services/visual_service.py`
- Create: `backend/app/services/script_generator.py`

- [ ] **Step 1: 创建阿里云ASR语音识别服务**

```python
from ..config import settings

class ASRService:
    @staticmethod
    async def transcribe(audio_path: str) -> list[dict]:
        import dashscope
        dashscope.api_key = settings.DASHSCOPE_API_KEY
        from dashscope.audio.asr import Recognition
        recognition = Recognition(model="paraformer-v2", file_urls=[audio_path])
        result = recognition.call()
        segments = []
        if result.status_code == 200:
            for sentence in result.output.get("results", []):
                for item in sentence.get("text", []):
                    segments.append({
                        "text": item.get("text", ""),
                        "start_time": item.get("begin_time", 0) / 1000.0,
                        "end_time": item.get("end_time", 0) / 1000.0,
                    })
        return segments
```

- [ ] **Step 2: 创建通义千问VL视觉理解服务**

```python
import base64
from ..config import settings

class VisualService:
    @staticmethod
    async def analyze_frames(frame_paths: list[str], fps: float = 1.0) -> list[dict]:
        import dashscope
        dashscope.api_key = settings.DASHSCOPE_API_KEY
        from dashscope import MultiModalConversation
        segments = []
        batch_size = 4
        for i in range(0, len(frame_paths), batch_size):
            batch = frame_paths[i:i + batch_size]
            messages = [{"role": "user", "content": [{"text": "请分析以下视频帧，描述镜头画面内容，包括景别、画面主体、动作、场景环境。用简洁一句话描述。"}]}]
            for frame_path in batch:
                with open(frame_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                messages[0]["content"].append({"image": f"data:image/jpeg;base64,{img_b64}"})
            response = MultiModalConversation.call(model="qwen-vl-plus", messages=messages)
            description = ""
            if response.status_code == 200:
                description = response.output.choices[0].message.content[0]["text"]
            segments.append({"start_time": i / fps, "end_time": min(i + batch_size, len(frame_paths)) / fps, "shot_description": description})
        return segments
```

- [ ] **Step 3: 创建脚本整合生成服务**

```python
import json
from ..config import settings

class ScriptGenerator:
    @staticmethod
    async def generate_script(asr_segments: list[dict], visual_segments: list[dict]) -> dict:
        import dashscope
        dashscope.api_key = settings.DASHSCOPE_API_KEY
        from dashscope import Generation
        prompt = f"""你是专业视频脚本分析师。将以下语音识别和镜头分析结果整合为结构化视频脚本。

语音识别结果（带时间戳）：{asr_segments}
镜头分析结果（带时间戳）：{visual_segments}

输出JSON格式脚本，每个片段包含：start_time, end_time, shot_description, dialogue, segment_type(shot/dialogue/mixed)。按时间顺序合并，时间连续不重叠。"""
        response = Generation.call(model="qwen-plus", prompt=prompt, result_format="message")
        if response.status_code == 200:
            content = response.output.choices[0].message.content
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"raw_script": content, "segments": []}
        return {"segments": []}
```

- [ ] **Step 4: 验证AI服务模块导入**

Run: `cd parse_video/backend && python -c "from app.services.asr_service import ASRService; from app.services.visual_service import VisualService; from app.services.script_generator import ScriptGenerator; print('AI services OK')"`
Expected: 输出 "AI services OK"

---

### Task 5: Celery异步任务定义

**Files:**
- Create: `backend/celery_app.py`
- Create: `backend/app/tasks/__init__.py`
- Create: `backend/app/tasks/parse_video.py`

- [ ] **Step 1: 创建Celery配置入口**

```python
from celery import Celery
from app.config import settings

celery_app = Celery("parse_video", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="Asia/Shanghai", enable_utc=True)
celery_app.autodiscover_tasks(["app.tasks"])
```

- [ ] **Step 2: 创建视频解析Celery任务**

```python
import os, json, asyncio
from celery_app import celery_app
from app.database import SessionLocal
from app.models.video import Video, VideoStatus
from app.models.script import Script, ScriptSegment, SegmentType
from app.services.video_processor import VideoProcessor
from app.services.asr_service import ASRService
from app.services.visual_service import VisualService
from app.services.script_generator import ScriptGenerator

@celery_app.task(bind=True)
def parse_video_task(self, video_id: int):
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return
        video.status = VideoStatus.PROCESSING
        video.progress = 0
        db.commit()
        audio_path = VideoProcessor.extract_audio(video.file_path)
        video.progress = 20
        db.commit()
        frame_dir = os.path.join(os.path.dirname(video.file_path), f"frames_{video.id}")
        frames = VideoProcessor.extract_frames(video.file_path, frame_dir, fps=1.0)
        video.progress = 30
        db.commit()
        asr_segments = asyncio.run(ASRService.transcribe(audio_path))
        video.progress = 60
        db.commit()
        visual_segments = asyncio.run(VisualService.analyze_frames(frames, fps=1.0))
        video.progress = 80
        db.commit()
        script_result = asyncio.run(ScriptGenerator.generate_script(asr_segments, visual_segments))
        video.progress = 95
        db.commit()
        script = Script(video_id=video.id, content=script_result, raw_asr_text=json.dumps(asr_segments, ensure_ascii=False), raw_visual_text=json.dumps(visual_segments, ensure_ascii=False))
        db.add(script)
        db.flush()
        for seg in script_result.get("segments", []):
            segment = ScriptSegment(script_id=script.id, start_time=seg.get("start_time", 0), end_time=seg.get("end_time", 0), shot_description=seg.get("shot_description", ""), dialogue=seg.get("dialogue", ""), segment_type=SegmentType(seg.get("segment_type", "mixed")))
            db.add(segment)
        video.status = VideoStatus.DONE
        video.progress = 100
        db.commit()
    except Exception as e:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = VideoStatus.FAILED
            video.error_message = str(e)
            db.commit()
        raise
    finally:
        db.close()
```

- [ ] **Step 3: 验证Celery任务注册**

Run: `cd parse_video/backend && python -c "from celery_app import celery_app; print(list(celery_app.tasks.keys()))"`
Expected: 输出包含 parse_video_task

---

### Task 6: 后端API接口开发

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/videos.py`
- Create: `backend/app/api/scripts.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建视频上传和抖音解析API**

```python
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.video import Video, VideoSource, VideoStatus
from ..schemas.video import VideoUploadResponse, VideoDetail, DouyinParseRequest
from ..services.douyin_parser import DouyinParser
from ..services.video_processor import VideoProcessor
from ..tasks.parse_video import parse_video_task
from ..config import settings
import os, uuid

router = APIRouter(prefix="/api/videos", tags=["videos"])

@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if file.size and file.size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过500MB限制")
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    duration = VideoProcessor.get_duration(file_path)
    video = Video(title=os.path.splitext(file.filename)[0], source_type=VideoSource.LOCAL, file_path=file_path, duration=duration)
    db.add(video)
    db.commit()
    db.refresh(video)
    parse_video_task.delay(video.id)
    return VideoUploadResponse.model_validate(video)

@router.post("/douyin", response_model=VideoUploadResponse)
async def parse_douyin(request: DouyinParseRequest, db: Session = Depends(get_db)):
    try:
        file_path, title = DouyinParser.download_video(request.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"抖音视频下载失败: {str(e)}")
    duration = VideoProcessor.get_duration(file_path)
    video = Video(title=title, source_type=VideoSource.DOUYIN, source_url=request.url, file_path=file_path, duration=duration)
    db.add(video)
    db.commit()
    db.refresh(video)
    parse_video_task.delay(video.id)
    return VideoUploadResponse.model_validate(video)

@router.get("/{video_id}", response_model=VideoDetail)
async def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    return VideoDetail.model_validate(video)

@router.get("/", response_model=list[VideoDetail])
async def list_videos(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    videos = db.query(Video).order_by(Video.created_at.desc()).offset(skip).limit(limit).all()
    return [VideoDetail.model_validate(v) for v in videos]
```

- [ ] **Step 2: 创建脚本查询、编辑、导出API**

```python
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.script import Script, ScriptSegment
from ..schemas.script import ScriptDetail, ScriptSegmentUpdate, ScriptSegmentOut

router = APIRouter(prefix="/api/scripts", tags=["scripts"])

@router.get("/{video_id}", response_model=ScriptDetail)
async def get_script(video_id: int, db: Session = Depends(get_db)):
    script = db.query(Script).filter(Script.video_id == video_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")
    return ScriptDetail.model_validate(script)

@router.patch("/segments/{segment_id}", response_model=ScriptSegmentOut)
async def update_segment(segment_id: int, update: ScriptSegmentUpdate, db: Session = Depends(get_db)):
    segment = db.query(ScriptSegment).filter(ScriptSegment.id == segment_id).first()
    if not segment:
        raise HTTPException(status_code=404, detail="片段不存在")
    if update.shot_description is not None:
        segment.shot_description = update.shot_description
    if update.dialogue is not None:
        segment.dialogue = update.dialogue
    db.commit()
    db.refresh(segment)
    return ScriptSegmentOut.model_validate(segment)

@router.get("/{video_id}/export/txt")
async def export_txt(video_id: int, db: Session = Depends(get_db)):
    script = db.query(Script).filter(Script.video_id == video_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")
    lines = []
    for seg in script.segments:
        t = f"[{seg.start_time:.1f}s - {seg.end_time:.1f}s]"
        lines.append(f"{t} 镜头: {seg.shot_description or '无'}")
        if seg.dialogue:
            lines.append(f"{t} 台词: {seg.dialogue}")
        lines.append("")
    return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")

@router.get("/{video_id}/export/srt")
async def export_srt(video_id: int, db: Session = Depends(get_db)):
    script = db.query(Script).filter(Script.video_id == video_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")
    lines = []
    for idx, seg in enumerate(script.segments, 1):
        start = _format_srt_time(seg.start_time)
        end = _format_srt_time(seg.end_time)
        text = seg.dialogue or seg.shot_description or ""
        lines.extend([str(idx), f"{start} --> {end}", text, ""])
    return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")

@router.get("/{video_id}/export/json")
async def export_json(video_id: int, db: Session = Depends(get_db)):
    script = db.query(Script).filter(Script.video_id == video_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")
    data = {"video_id": video_id, "segments": [{"start_time": s.start_time, "end_time": s.end_time, "shot_description": s.shot_description, "dialogue": s.dialogue, "segment_type": s.segment_type.value} for s in script.segments]}
    return JSONResponse(content=data)

def _format_srt_time(seconds: float) -> str:
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
```

- [ ] **Step 3: 在main.py中注册路由**

```python
from .api import videos, scripts
app.include_router(videos.router)
app.include_router(scripts.router)
```

- [ ] **Step 4: 验证API启动**

Run: `cd parse_video/backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
Expected: 服务启动成功，/health 返回 {"status": "ok"}

---

### Task 7: 前端项目初始化

**Files:**
- Create: `frontend/` (via Vite scaffolding)
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/api/index.ts`
- Create: `frontend/src/router/index.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: 使用Vite创建Vue3项目**

Run: `cd parse_video && npm create vite@latest frontend -- --template vue-ts`
Expected: frontend目录创建成功

- [ ] **Step 2: 安装前端依赖**

Run: `cd parse_video/frontend && npm install element-plus axios video.js @videojs-player/vue`
Expected: 依赖安装成功

- [ ] **Step 3: 配置Vite代理**

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
```

- [ ] **Step 4: 创建TypeScript类型定义**

```typescript
export interface Video {
  id: number
  title: string
  source_type: 'local' | 'douyin'
  source_url?: string
  duration?: number
  status: 'pending' | 'processing' | 'done' | 'failed'
  progress: number
  error_message?: string
  created_at: string
}

export interface ScriptSegment {
  id: number
  start_time: number
  end_time: number
  shot_description?: string
  dialogue?: string
  segment_type: 'shot' | 'dialogue' | 'mixed'
}

export interface Script {
  id: number
  video_id: number
  content?: Record<string, any>
  raw_asr_text?: string
  raw_visual_text?: string
  segments: ScriptSegment[]
  created_at: string
  updated_at: string
}
```

- [ ] **Step 5: 创建API请求封装**

```typescript
import axios from 'axios'
import type { Video, Script } from '../types'

const api = axios.create({ baseURL: '/api' })

export const videoApi = {
  upload: (file: File) => { const fd = new FormData(); fd.append('file', file); return api.post<Video>('/videos/upload', fd) },
  parseDouyin: (url: string) => api.post<Video>('/videos/douyin', { url }),
  get: (id: number) => api.get<Video>(`/videos/${id}`),
  list: (skip = 0, limit = 20) => api.get<Video[]>('/videos/', { params: { skip, limit } }),
}

export const scriptApi = {
  get: (videoId: number) => api.get<Script>(`/scripts/${videoId}`),
  updateSegment: (segmentId: number, data: { shot_description?: string; dialogue?: string }) => api.patch(`/scripts/segments/${segmentId}`, data),
  exportTxt: (videoId: number) => api.get(`/scripts/${videoId}/export/txt`, { responseType: 'blob' }),
  exportSrt: (videoId: number) => api.get(`/scripts/${videoId}/export/srt`, { responseType: 'blob' }),
  exportJson: (videoId: number) => api.get(`/scripts/${videoId}/export/json`, { responseType: 'blob' }),
}
```

- [ ] **Step 6: 创建路由配置**

```typescript
import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/progress/:id', name: 'progress', component: () => import('../views/ParseProgress.vue') },
    { path: '/script/:videoId', name: 'script', component: () => import('../views/ScriptDetail.vue') },
  ],
})

export default router
```

- [ ] **Step 7: 配置main.ts和App.vue**

main.ts:
```typescript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(ElementPlus)
app.use(router)
app.mount('#app')
```

App.vue:
```vue
<template>
  <el-container>
    <el-header><h1>视频脚本解析平台</h1></el-header>
    <el-main><router-view /></el-main>
  </el-container>
</template>
```

- [ ] **Step 8: 验证前端启动**

Run: `cd parse_video/frontend && npm run dev`
Expected: 前端开发服务器启动成功

---

### Task 8: 前端核心组件开发

**Files:**
- Create: `frontend/src/components/VideoUploader.vue`
- Create: `frontend/src/components/DouyinInput.vue`
- Create: `frontend/src/views/HomeView.vue`
- Create: `frontend/src/views/ParseProgress.vue`
- Create: `frontend/src/components/ScriptTimeline.vue`
- Create: `frontend/src/components/VideoPlayer.vue`
- Create: `frontend/src/views/ScriptDetail.vue`

- [ ] **Step 1: 创建VideoUploader视频上传组件**

```vue
<template>
  <el-upload
    drag
    :auto-upload="false"
    :on-change="handleFileChange"
    accept="video/*"
    :limit="1"
  >
    <el-icon class="el-icon--upload"><upload-filled /></el-icon>
    <div class="el-upload__text">拖拽视频到此处，或<em>点击上传</em></div>
    <template #tip>
      <div class="el-upload__tip">支持 MP4/MOV/AVI 格式，最大 500MB</div>
    </template>
  </el-upload>
  <el-button type="primary" :loading="uploading" @click="handleUpload" :disabled="!selectedFile" style="margin-top: 16px">
    开始解析
  </el-button>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { videoApi } from '../api'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const router = useRouter()
const selectedFile = ref<File | null>(null)
const uploading = ref(false)

const handleFileChange = (file: any) => {
  selectedFile.value = file.raw
}

const handleUpload = async () => {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    const { data } = await videoApi.upload(selectedFile.value)
    ElMessage.success('视频上传成功，开始解析')
    router.push(`/progress/${data.id}`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}
</script>
```

- [ ] **Step 2: 创建DouyinInput抖音链接输入组件**

```vue
<template>
  <el-input v-model="douyinUrl" placeholder="请输入抖音分享链接" clearable>
    <template #append>
      <el-button :loading="parsing" @click="handleParse">解析</el-button>
    </template>
  </el-input>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { videoApi } from '../api'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const router = useRouter()
const douyinUrl = ref('')
const parsing = ref(false)

const handleParse = async () => {
  if (!douyinUrl.value.trim()) { ElMessage.warning('请输入链接'); return }
  parsing.value = true
  try {
    const { data } = await videoApi.parseDouyin(douyinUrl.value.trim())
    ElMessage.success('抖音视频解析任务已创建')
    router.push(`/progress/${data.id}`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '解析失败')
  } finally {
    parsing.value = false
  }
}
</script>
```

- [ ] **Step 3: 创建HomeView首页**

```vue
<template>
  <div class="home">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="本地上传" name="upload">
        <VideoUploader />
      </el-tab-pane>
      <el-tab-pane label="抖音链接" name="douyin">
        <DouyinInput />
      </el-tab-pane>
    </el-tabs>
    <el-divider />
    <h3>历史记录</h3>
    <el-table :data="videos" stripe v-loading="loading">
      <el-table-column prop="title" label="视频名称" />
      <el-table-column prop="source_type" label="来源" width="100" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="时间" width="180" />
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="row.status === 'done' ? $router.push(`/script/${row.id}`) : $router.push(`/progress/${row.id}`)">
            {{ row.status === 'done' ? '查看脚本' : '查看进度' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { videoApi } from '../api'
import VideoUploader from '../components/VideoUploader.vue'
import DouyinInput from '../components/DouyinInput.vue'
import type { Video } from '../types'

const activeTab = ref('upload')
const videos = ref<Video[]>([])
const loading = ref(false)

const statusType = (s: string) => ({ pending: 'info', processing: 'warning', done: 'success', failed: 'danger' }[s] || 'info')
const statusLabel = (s: string) => ({ pending: '等待中', processing: '解析中', done: '已完成', failed: '失败' }[s] || s)

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await videoApi.list()
    videos.value = data
  } finally {
    loading.value = false
  }
})
</script>
```

- [ ] **Step 4: 创建ParseProgress解析进度页**

```vue
<template>
  <div class="progress-page" v-loading="!video">
    <template v-if="video">
      <h2>{{ video.title }}</h2>
      <el-steps :active="stepActive" align-center>
        <el-step title="上传完成" :status="video.progress > 0 ? 'success' : 'process'" />
        <el-step title="提取音频" :status="video.progress > 20 ? 'success' : video.progress > 0 ? 'process' : 'wait'" />
        <el-step title="语音识别" :status="video.progress > 60 ? 'success' : video.progress > 30 ? 'process' : 'wait'" />
        <el-step title="镜头分析" :status="video.progress > 80 ? 'success' : video.progress > 60 ? 'process' : 'wait'" />
        <el-step title="生成脚本" :status="video.progress >= 100 ? 'success' : video.progress > 80 ? 'process' : 'wait'" />
      </el-steps>
      <el-progress :percentage="video.progress" :status="video.status === 'failed' ? 'exception' : video.progress >= 100 ? 'success' : ''" style="margin-top: 24px" />
      <p v-if="video.status === 'failed'" style="color: red">解析失败：{{ video.error_message }}</p>
      <el-button v-if="video.status === 'done'" type="primary" @click="$router.push(`/script/${video.id}`)" style="margin-top: 16px">查看脚本</el-button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { videoApi } from '../api'
import type { Video } from '../types'

const route = useRoute()
const video = ref<Video | null>(null)
let timer: number | null = null

const stepActive = computed(() => {
  if (!video.value) return 0
  const p = video.value.progress
  if (p >= 100) return 5
  if (p > 80) return 4
  if (p > 60) return 3
  if (p > 20) return 2
  if (p > 0) return 1
  return 0
})

const fetchVideo = async () => {
  const id = Number(route.params.id)
  const { data } = await videoApi.get(id)
  video.value = data
  if (data.status === 'done' || data.status === 'failed') {
    if (timer) { clearInterval(timer); timer = null }
  }
}

onMounted(() => {
  fetchVideo()
  timer = window.setInterval(fetchVideo, 2000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>
```

- [ ] **Step 5: 创建ScriptTimeline脚本时间轴组件**

```vue
<template>
  <div class="script-timeline">
    <el-timeline>
      <el-timeline-item v-for="seg in segments" :key="seg.id" :timestamp="formatTime(seg.start_time) + ' - ' + formatTime(seg.end_time)" placement="top">
        <el-card shadow="hover">
          <p v-if="seg.shot_description"><strong>镜头：</strong>{{ seg.shot_description }}</p>
          <p v-if="seg.dialogue"><strong>台词：</strong>{{ seg.dialogue }}</p>
          <el-tag size="small" style="margin-top: 4px">{{ seg.segment_type === 'shot' ? '镜头' : seg.segment_type === 'dialogue' ? '台词' : '混合' }}</el-tag>
        </el-card>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import type { ScriptSegment } from '../types'
defineProps<{ segments: ScriptSegment[] }>()
const formatTime = (s: number) => {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
}
</script>
```

- [ ] **Step 6: 创建VideoPlayer视频播放器组件**

```vue
<template>
  <div class="video-player">
    <video ref="videoRef" controls style="width: 100%; max-height: 400px" :src="videoSrc" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
defineProps<{ videoSrc: string }>()
const videoRef = ref<HTMLVideoElement | null>(null)
</script>
```

- [ ] **Step 7: 创建ScriptDetail脚本详情页**

```vue
<template>
  <div class="script-detail" v-loading="loading">
    <template v-if="script">
      <el-page-header @back="$router.push('/')" :title="'返回首页'">
        <template #content><span>脚本详情</span></template>
      </el-page-header>
      <el-row :gutter="20" style="margin-top: 16px">
        <el-col :span="16">
          <ScriptTimeline :segments="script.segments" />
        </el-col>
        <el-col :span="8">
          <el-card>
            <h3>导出脚本</h3>
            <el-button @click="handleExport('txt')" style="margin: 4px">导出 TXT</el-button>
            <el-button @click="handleExport('srt')" style="margin: 4px">导出 SRT</el-button>
            <el-button @click="handleExport('json')" style="margin: 4px">导出 JSON</el-button>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { scriptApi } from '../api'
import ScriptTimeline from '../components/ScriptTimeline.vue'
import type { Script } from '../types'

const route = useRoute()
const script = ref<Script | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await scriptApi.get(Number(route.params.videoId))
    script.value = data
  } finally {
    loading.value = false
  }
})

const handleExport = async (format: string) => {
  const videoId = Number(route.params.videoId)
  const { data } = await (scriptApi as any)[`export${format.charAt(0).toUpperCase() + format.slice(1)}`](videoId)
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = `script.${format}`
  a.click()
  URL.revokeObjectURL(url)
}
</script>
```

- [ ] **Step 8: 验证前端完整功能**

Run: `cd parse_video/frontend && npm run dev`
Expected: 前端页面正常显示，路由切换正常

---

### Task 9: 集成测试与部署配置

**Files:**
- Create: `backend/.env.example`
- Create: `backend/app/tasks/__init__.py`
- Modify: `backend/app/main.py` (添加静态文件服务)

- [ ] **Step 1: 创建环境变量示例文件**

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/parse_video
REDIS_URL=redis://localhost:6379/0
UPLOAD_DIR=./uploads
DASHSCOPE_API_KEY=your_dashscope_api_key_here
ALIYUN_ASR_APP_KEY=your_aliyun_asr_app_key_here
ALIYUN_ASR_ACCESS_KEY=your_aliyun_access_key_here
ALIYUN_ASR_ACCESS_SECRET=your_aliyun_access_secret_here
```

- [ ] **Step 2: 在main.py中添加静态文件服务（开发环境）**

```python
from fastapi.staticfiles import StaticFiles
import os

# 在app创建后添加
upload_dir = settings.UPLOAD_DIR
os.makedirs(upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")
```

- [ ] **Step 3: 启动完整服务验证**

Run: `cd parse_video && docker-compose up -d`
Run: `cd parse_video/backend && celery -A celery_app worker --loglevel=info &`
Run: `cd parse_video/backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
Run: `cd parse_video/frontend && npm run dev`
Expected: 所有服务正常启动，前端可访问，上传视频触发解析流程