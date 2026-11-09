"""STEP 04. 장면별 화이트보드 이미지 생성 -> images/scene_XX.png."""
from base64 import b64decode
from pathlib import Path
from tempfile import NamedTemporaryFile

from pipeline.config import IMAGE_MODEL, OPENAI_API_KEY, PROMPTS_DIR
from pipeline.schema import Project

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def run(project: Project, job_dir: Path, source: str) -> Project:
    if not project.scenes:
        raise ValueError("STEP 04 전에 STEP 03에서 장면을 생성하세요.")
    if not OPENAI_API_KEY:
        raise ValueError("STEP 04를 실행하려면 프로젝트 .env에 OPENAI_API_KEY를 설정하세요.")

    from openai import OpenAI

    preset = (PROMPTS_DIR / "image_style.md").read_text(encoding="utf-8").strip()
    image_dir = job_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    with OpenAI(api_key=OPENAI_API_KEY, timeout=180.0) as client:
        for scene in project.scenes:
            out = image_dir / f"scene_{scene.id:02d}.png"
            if not out.is_file():
                if not scene.image_prompt.strip():
                    raise ValueError(f"장면 {scene.id}의 이미지 프롬프트가 비어 있습니다.")
                result = client.images.generate(
                    model=IMAGE_MODEL,
                    prompt=f"{preset}\n{project.style_prompt}\n\nScene: {scene.image_prompt}",
                    size="1024x1536",
                    quality="medium",
                    output_format="png",
                )
                encoded = result.data[0].b64_json if result.data else None
                if not encoded:
                    raise ValueError(f"장면 {scene.id}의 이미지가 반환되지 않았습니다.")
                png = b64decode(encoded, validate=True)
                if not png.startswith(PNG_SIGNATURE):
                    raise ValueError(f"장면 {scene.id}의 응답이 PNG 형식이 아닙니다.")
                with NamedTemporaryFile(dir=image_dir, delete=False) as temp:
                    temp_path = Path(temp.name)
                    try:
                        temp.write(png)
                        temp.close()
                        temp_path.replace(out)
                    finally:
                        temp_path.unlink(missing_ok=True)
            scene.image = out.relative_to(job_dir).as_posix()
    return project
