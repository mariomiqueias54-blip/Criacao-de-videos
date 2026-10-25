import os, json, uuid, tempfile, subprocess, shutil
from pathlib import Path
from fastapi import FastAPI, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from PIL import Image, ImageDraw, ImageFont, ImageOps
import edge_tts

app = FastAPI(title="Arquivo Zero Studio")
BASE = Path(__file__).parent
OUT = BASE / "outputs"
OUT.mkdir(exist_ok=True)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "index.html").read_text(encoding="utf-8")

@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(BASE / "manifest.webmanifest", media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    return FileResponse(BASE / "sw.js", media_type="application/javascript")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/roteiro")
async def roteiro(topic: str = Form(...), seconds: int = Form(60), style: str = Form("Sombrio e investigativo")):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, "Configure OPENAI_API_KEY no servidor para gerar roteiros com IA.")
    from openai import AsyncOpenAI
    try:
        client = AsyncOpenAI(api_key=key)
        response = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role":"user","content":f"Crie roteiro documental em português brasileiro com cerca de {seconds} segundos. Tema: {topic}. Estilo: {style}. Responda em JSON com title, script, caption e hook. Não invente fatos, fontes ou citações; sinalize incertezas."}],
            response_format={"type":"json_object"})
        return json.loads(response.choices[0].message.content)
    except Exception:
        raise HTTPException(502, "Falha na API de IA. Verifique a chave, saldo e modelo.")

def run(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if p.returncode:
        raise RuntimeError(p.stderr[-500:])
    return p.stdout

def make_slide(path, title, text, image_path, width, height):
    bg = Image.new("RGB", (width,height), "#081017")
    if image_path:
        img = ImageOps.fit(Image.open(image_path).convert("RGB"), (width,height))
        bg = Image.blend(img, bg, .48)
    d = ImageDraw.Draw(bg)
    d.rectangle((0,0,width,12), fill="#37d9a0")
    large = ImageFont.truetype(FONT, int(width*.045))
    small = ImageFont.truetype(FONT, int(width*.029))
    d.text((int(width*.06),int(height*.10)), "ARQUIVO ZERO  /  STUDIO", fill="#37d9a0",font=small)
    def lines(s, f, max_width):
        out=[]; current=""
        for word in s.split():
            test=(current+" "+word).strip()
            if current and d.textbbox((0,0,test),font=f)[2]>max_width:
                out.append(current);current=word
            else:current=test
        return out+[current]
    y=int(height*.36)
    for line in lines(title.upper(),large,int(width*.88))[:5]:
        d.text((int(width*.06),y),line,font=large,fill="white");y+=int(width*.06)
    y=int(height*.77)
    for line in lines(text,small,int(width*.88))[:5]:
        d.text((int(width*.06),y),line,font=small,fill="white");y+=int(width*.042)
    bg.save(path)

@app.post("/api/render")
async def render(title: str=Form(...), script: str=Form(...), format: str=Form("vertical"), voice: str=Form("pt-BR-AntonioNeural"), images: list[UploadFile]=File(default=[])):
    if not title.strip() or not script.strip() or len(script)>5000:
        raise HTTPException(400, "Informe título e narração de até 5000 caracteres.")
    if voice not in ("pt-BR-AntonioNeural","pt-BR-FranciscaNeural"):
        raise HTTPException(400,"Voz inválida")
    if format not in ("vertical","horizontal") or len(images)>15:
        raise HTTPException(400,"Formato ou quantidade de imagens inválidos")
    width,height=(1080,1920) if format=="vertical" else (1920,1080)
    job=uuid.uuid4().hex
    temp=Path(tempfile.mkdtemp(prefix="az_"))
    try:
        pics=[]
        for i,upload in enumerate(images):
            if not upload.filename: continue
            data=await upload.read(12000001)
            if len(data)>12000000:raise HTTPException(400,"Imagem acima de 12 MB")
            from io import BytesIO
            try:
                im=Image.open(BytesIO(data)); im.verify()
                im=Image.open(BytesIO(data)).convert("RGB")
                im.thumbnail((2500,2500))
                path=temp/f"photo{i}.jpg"; im.save(path);pics.append(path)
            except Exception:raise HTTPException(400,"Imagem inválida")
        audio=OUT/f"{job}.mp3"
        await edge_tts.Communicate(script,voice).save(str(audio))
        seconds=float(run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(audio)]).strip())
        words=script.split()
        chunks=[" ".join(words[i:i+28]) for i in range(0,len(words),28)] or [script]
        parts=[]
        for i,chunk in enumerate(chunks):
            slide=temp/f"slide{i}.jpg"
            make_slide(slide,title,chunk,pics[i%len(pics)] if pics else None,width,height)
            clip=temp/f"clip{i}.mp4"
            run(["ffmpeg","-y","-loop","1","-framerate","25","-i",str(slide),"-t",str(max(.5,seconds/len(chunks))),"-vf",f"scale={width}:{height},format=yuv420p","-c:v","libx264","-preset","ultrafast","-r","25",str(clip)])
            parts.append(clip)
        concat=temp/"list.txt"
        concat.write_text("".join("file '"+str(p)+"'\\n" for p in parts))
        video=OUT/f"{job}.mp4"
        run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-i",str(audio),"-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p","-c:a","aac","-shortest","-movflags","+faststart",str(video)])
        return {"video":f"/download/{job}.mp4","audio":f"/download/{job}.mp3","duration":round(seconds,1),"resolution":f"{width} x {height}"}
    except HTTPException:raise
    except Exception:raise HTTPException(500,"Falha ao renderizar. Verifique recursos do servidor e serviço de voz.")
    finally:shutil.rmtree(temp,ignore_errors=True)

@app.get("/download/{filename}")
def download(filename: str):
    if not filename.endswith((".mp4",".mp3")) or len(filename)>40 or "/" in filename:
        raise HTTPException(404)
    path=OUT/filename
    if not path.is_file():raise HTTPException(404)
    return FileResponse(path,filename=filename)
