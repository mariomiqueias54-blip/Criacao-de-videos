import os, json, uuid, tempfile, subprocess, shutil, logging
from pathlib import Path
from fastapi import FastAPI, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from PIL import Image, ImageDraw, ImageFont, ImageOps
import edge_tts
from openai import AsyncOpenAI

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

@app.get("/api/capabilities")
def capabilities():
    return {"ai_enabled": bool(os.getenv("OPENAI_API_KEY", "").strip())}

@app.get("/health")
def health():
    return {"ok": True}

def roteiro_basico(topic: str, seconds: int, style: str):
    """Modelo editorial offline, sem alegações factuais não verificadas."""
    topic = " ".join(topic.split())[:180]
    if not topic:
        raise HTTPException(400, "Informe o tema do vídeo.")
    if seconds not in (30, 60, 90):
        raise HTTPException(400, "Escolha 30, 60 ou 90 segundos.")
    styles = {
        "Sombrio e investigativo": ("Um mistério merece investigação, não suposições.", "com atmosfera de suspense"),
        "Jornalístico e objetivo": ("O que sabemos, e o que ainda precisa ser confirmado?", "com linguagem objetiva"),
        "Documentário cinematográfico": ("Toda história tem perguntas que merecem respostas.", "com ritmo documental"),
    }
    hook, tone = styles.get(style, styles["Sombrio e investigativo"])
    sections = [
        f"{hook} Hoje, o Arquivo Zero examina o tema: {topic}.",
        "Para compreender este assunto, precisamos separar os acontecimentos documentados das interpretações e das hipóteses.",
        "O primeiro passo é estabelecer a cronologia, identificar as fontes originais e verificar o contexto em que cada informação surgiu.",
        "Também é importante comparar relatos independentes e observar o que permanece incerto ou controverso.",
        "Imagens, depoimentos e manchetes podem ser impactantes, mas não substituem evidências verificáveis.",
        "Antes de tirar conclusões, confira datas, documentos e informações em fontes confiáveis.",
        f"Este foi o Arquivo Zero. O tema de hoje foi {topic}. Quais perguntas você investigaria primeiro?"
    ]
    count = {30: 3, 60: 5, 90: 7}[seconds]
    selected = sections if count == 7 else [sections[0], *sections[1:-1][:count-2], sections[-1]]
    script = " ".join(selected)
    return {
        "title": topic[:100],
        "script": script,
        "hook": hook,
        "caption": f"Arquivo Zero | {topic}. Conteúdo editorial {tone}. Verifique os fatos antes de publicar. #ArquivoZero #Documentario",
        "mode": "modelo_gratuito",
        "notice": "Roteiro estrutural gerado sem IA e sem pesquisa. Acrescente fatos e fontes verificadas. A duração é aproximada."
    }

@app.post("/api/roteiro")
async def roteiro(topic: str = Form(...), seconds: int = Form(60),
                  style: str = Form("Sombrio e investigativo"),
                  mode: str = Form("auto")):
    topic = " ".join(topic.split()).strip()
    if not topic or len(topic) > 180:
        raise HTTPException(400, "Informe um tema de até 180 caracteres.")
    if seconds not in (30, 60, 90):
        raise HTTPException(400, "Escolha 30, 60 ou 90 segundos.")
    if mode not in ("auto", "modelo", "ia"):
        raise HTTPException(400, "Modo inválido.")
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if mode == "ia" and not key:
        raise HTTPException(400, "IA avançada não configurada. Use o modo gratuito ou configure OPENAI_API_KEY no Render.")
    if key and mode != "modelo":
        try:
            client = AsyncOpenAI(api_key=key, timeout=35.0)
            result = await client.chat.completions.create(
                model=os.getenv("OPENAI_SCRIPT_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role":"system","content":(
                        "Você escreve roteiros originais de documentários curtos em português do Brasil. "
                        "Responda apenas em JSON com as chaves title, script, hook, caption. "
                        "Crie narração completa com abertura impactante, contexto, desenvolvimento e fechamento. "
                        "Não invente datas, citações, notícias ou fatos; quando houver incerteza, sinalize. "
                        "Não alegue ter consultado fontes ou notícias em tempo real. "
                        "Não inclua instruções de câmera no texto da narração."
                    )},
                    {"role":"user","content":f"Tema: {topic}. Estilo: {style}. Duração aproximada: {seconds} segundos. Escreva cerca de {int(seconds*2.2)} palavras."}
                ], response_format={"type":"json_object"}, temperature=0.7, max_tokens=900)
            data = json.loads(result.choices[0].message.content)
            if not isinstance(data.get("script"), str) or not data["script"].strip():
                raise ValueError("Resposta sem roteiro.")
            return {"title":str(data.get("title") or topic)[:130],
                    "script":data["script"][:5000],
                    "hook":str(data.get("hook") or ""),
                    "caption":str(data.get("caption") or ""),
                    "mode":"ia",
                    "notice":"Roteiro criado com IA. Confira todas as informações antes de publicar."}
        except Exception as exc:
            logging.exception("Falha na geracao de roteiro com IA")
            if mode == "ia":
                raise HTTPException(502, "Falha na geração com IA. Verifique a configuração e os créditos da API.") from exc
    fallback = roteiro_basico(topic, seconds, style)
    fallback["notice"] += " Para roteiros realmente personalizados, habilite a opção IA avançada."
    return fallback

def run(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if p.returncode:
        raise RuntimeError(p.stderr[-500:])
    return p.stdout

def make_slide(path, title, text, image_path, width, height, visual_style="documentary"):
    palettes = {"documentary":("#081017","#37d9a0"),"minimal":("#14100f","#d3ae75"),"breaking":("#0c101b","#ff4c48"),"cinematic":("#090b12","#e2bc74"),"social":("#12111b","#c9a4ff")}
    bg_color, accent = palettes.get(visual_style, palettes["documentary"])
    bg = Image.new("RGB", (width,height), bg_color)
    if image_path:
        img = ImageOps.fit(Image.open(image_path).convert("RGB"), (width,height))
        bg = Image.blend(img, bg, .68 if visual_style == "cinematic" else .48)
    d = ImageDraw.Draw(bg)
    d.rectangle((0,0,width,12), fill=accent)
    large = ImageFont.truetype(FONT, int(width*.045))
    small = ImageFont.truetype(FONT, int(width*.029))
    d.text((int(width*.06),int(height*.10)), "ARQUIVO ZERO  /  STUDIO", fill=accent,font=small)
    def lines(s, f, max_width):
        out=[]; current=""
        for word in s.split():
            test=(current+" "+word).strip()
            if current and d.textbbox((0,0),test,font=f)[2]>max_width:
                out.append(current);current=word
            else:current=test
        return out+[current]
    y=int(height*.36)
    for line in lines(title.upper(),large,int(width*.88))[:5]:
        d.text((int(width*.06),y),line,font=large,fill="white");y+=int(width*.06)
    y=int(height*.77)
    for line in lines(text,small,int(width*.88))[:5]:
        d.text((int(width*.06),y),line,font=small,fill=accent if visual_style=="minimal" else "white");y+=int(width*.042)
    bg.save(path)

@app.post("/api/voice-preview")
async def voice_preview(voice: str = Form("pt-BR-AntonioNeural"), voice_rate: str = Form("+0%"), voice_pitch: str = Form("+0Hz")):
    allowed = ("pt-BR-AntonioNeural","pt-BR-FranciscaNeural","pt-BR-BrendaNeural","pt-BR-DonatoNeural","pt-BR-GiovannaNeural","pt-BR-HumbertoNeural","pt-BR-JulioNeural","pt-BR-LeilaNeural","pt-BR-ManuelaNeural","pt-BR-NicolauNeural","pt-BR-ThalitaNeural","pt-BR-YaraNeural")
    if voice not in allowed or voice_rate not in ("-15%","-8%","+0%","+8%","+15%") or voice_pitch not in ("-10Hz","-5Hz","+0Hz","+5Hz"):
        raise HTTPException(400, "Configuração de voz inválida.")
    filename = uuid.uuid4().hex + ".mp3"
    try:
        await edge_tts.Communicate("Bem-vindo ao Arquivo Zero Studio. Esta é uma demonstração da minha voz para seus próximos vídeos.",voice,rate=voice_rate,pitch=voice_pitch).save(str(OUT / filename))
        return {"audio":"/download/"+filename}
    except Exception as exc:
        logging.exception("Falha na prévia da voz")
        raise HTTPException(502, "Não foi possível gerar a prévia da voz.") from exc

@app.post("/api/render")
async def render(title: str=Form(...), script: str=Form(...), format: str=Form("vertical"), voice: str=Form("pt-BR-AntonioNeural"), images: list[UploadFile]=File(default=[]), visual_style: str=Form("documentary"), voice_rate: str=Form("+0%"), voice_pitch: str=Form("+0Hz"), captions: str=Form("on")):
    if not title.strip() or not script.strip() or len(script)>5000:
        raise HTTPException(400, "Informe título e narração de até 5000 caracteres.")
    if voice not in ("pt-BR-AntonioNeural","pt-BR-FranciscaNeural","pt-BR-BrendaNeural","pt-BR-DonatoNeural","pt-BR-GiovannaNeural","pt-BR-HumbertoNeural","pt-BR-JulioNeural","pt-BR-LeilaNeural","pt-BR-ManuelaNeural","pt-BR-NicolauNeural","pt-BR-ThalitaNeural","pt-BR-YaraNeural"):
        raise HTTPException(400,"Voz inválida")
    if format not in ("vertical","horizontal","square","portrait") or len(images)>15:
        raise HTTPException(400,"Formato ou quantidade de imagens inválidos")
    if visual_style not in ("documentary","minimal","breaking","cinematic","social"):
        raise HTTPException(400,"Estilo visual inválido")
    if voice_rate not in ("-15%","-8%","+0%","+8%","+15%") or voice_pitch not in ("-10Hz","-5Hz","+0Hz","+5Hz"):
        raise HTTPException(400,"Ajuste de voz inválido")
    if captions not in ("on","off"):
        raise HTTPException(400,"Configuração de legendas inválida")
    width,height={"vertical":(1080,1920),"horizontal":(1920,1080),"square":(1080,1080),"portrait":(1080,1350)}[format]
    # Desenha as telas em meia resolucao para poupar RAM; exporta em Full HD.
    slide_width,slide_height=width//2,height//2
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
        await edge_tts.Communicate(script,voice,rate=voice_rate,pitch=voice_pitch).save(str(audio))
        seconds=float(run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(audio)]).strip())
        words=script.split()
        chunks=[" ".join(words[i:i+28]) for i in range(0,len(words),28)] or [script]
        # Renderiza uma única vez, sem clips intermediários nem recodificação dupla.
        # Limita threads para reduzir picos de memória em hospedagens pequenas.
        slides=[]
        for i,chunk in enumerate(chunks):
            slide=temp/f"slide{i}.jpg"
            make_slide(slide,title,chunk if captions=="on" else "",pics[i%len(pics)] if pics else None,slide_width,slide_height,visual_style)
            slides.append(slide)
        concat=temp/"slides.txt"
        duration=max(0.5,seconds/len(slides))
        entries=[]
        for slide in slides:
            entries.extend([f"file '{slide}'", f"duration {duration:.6f}"])
        entries.append(f"file '{slides[-1]}'")
        concat.write_text("\n".join(entries)+"\n",encoding="utf-8")
        video=OUT/f"{job}.mp4"
        # Limita buffers e paralelismo do FFmpeg em servidores de 512 MB.
        run(["ffmpeg","-y","-nostdin","-threads","1","-filter_threads","1","-filter_complex_threads","1","-f","concat","-safe","0","-i",str(concat),
             "-i",str(audio),"-map","0:v:0","-map","1:a:0",
             "-vf",f"fps=6,scale={width}:{height}:flags=fast_bilinear,format=yuv420p",
             "-c:v","mpeg4","-threads","1","-q:v","7","-bf","0",
             "-c:a","aac","-b:a","96k","-shortest","-movflags","+faststart",str(video)])
        return {"video":f"/download/{job}.mp4","audio":f"/download/{job}.mp3","duration":round(seconds,1),"resolution":f"{width} x {height}"}
    except HTTPException:raise
    except Exception as exc:
        logging.exception("Falha na renderizacao do video")
        raise HTTPException(500, "Falha ao renderizar. Consulte os logs do Render para identificar a etapa.") from exc
    finally:shutil.rmtree(temp,ignore_errors=True)

@app.get("/download/{filename}")
def download(filename: str):
    if not filename.endswith((".mp4",".mp3")) or len(filename)>40 or "/" in filename:
        raise HTTPException(404)
    path=OUT/filename
    if not path.is_file():raise HTTPException(404)
    return FileResponse(path,filename=filename)
