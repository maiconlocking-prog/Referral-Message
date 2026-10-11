import asyncio
import json
import logging
import os
import sys
import subprocess
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.custom import Message
from telethon.errors import FloodWaitError

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_NAME = "referral_session"
CONFIG_FILE = Path("config.json")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

if not API_ID or not API_HASH:
    raise ValueError("Defina API_ID e API_HASH")

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("live_jobs", [])
            data.setdefault("paused", False)
            return data
    return {"source": None, "dest": None, "live_jobs": [], "paused": False}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

config = load_config()
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
history_tasks = {}
stop_flags = {}
next_task_id = 1

MENU = """**Referral Message**

**Historico (mensagens antigas)**
`/setsource @canal` — origem
`/setdest @canal` — destino
`/copyimages` — imagens sem legenda
`/copyimagescaption` — imagens com legenda
`/copyall` — tudo sem legenda
`/copyallcaption` — tudo com legenda
`/stopcopy` — parar historico

**Ao vivo (so postagens novas)**
`/liveimages @origem @destino`
`/liveimagescaption @origem @destino`
`/liveall @origem @destino`
`/stoplive` — parar todos os lives

**Controle**
`/status` — ver o que esta rodando
`/pause` — pausar tudo (bot continua ligado)
`/resume` — voltar a copiar
`/update` — atualizar codigo e reiniciar
"""

async def send_media(dest, message, with_caption=False):
    caption = (message.text or None) if with_caption else None
    entities = message.entities if with_caption else None
    if message.media:
        await client.send_file(dest, file=message.media, caption=caption, formatting_entities=entities, force_document=False)
    elif message.text and with_caption:
        await client.send_message(dest, message.text, formatting_entities=message.entities)

async def send_album(dest, messages, with_caption=False):
    files = [m.media for m in messages if m.media]
    if not files:
        return
    caption = None
    if with_caption:
        for m in messages:
            if m.text:
                caption = m.text
                break
    await client.send_file(dest, file=files, caption=caption)

def is_source_match(chat, source):
    chat_username = f"@{chat.username}" if getattr(chat, "username", None) else None
    chat_id = str(getattr(chat, "id", ""))
    return (
        chat_id == str(source)
        or (chat_username and chat_username.lower() == str(source).lower())
        or chat_id == str(source).replace("-100", "")
    )

async def status_text():
    paused = config.get("paused", False)
    text = f"**Status**\n\nBot: {'PAUSADO' if paused else 'Ativo'}\n\n"
    if history_tasks:
        text += "**Historico:**\n" + "".join(f"  #{t}\n" for t in history_tasks) + "\n"
    else:
        text += "Historico: nenhuma\n\n"
    jobs = config.get("live_jobs", [])
    if jobs:
        text += "**Lives:**\n"
        for i, job in enumerate(jobs, 1):
            text += f"  #{i} `{job['source']}` -> `{job['dest']}` ({job.get('mode')})\n"
    else:
        text += "Lives: nenhum\n"
    text += f"\nOrigem: `{config.get('source') or '-'}\nDestino: `{config.get('dest') or '-'}`"
    return text

@client.on(events.NewMessage(pattern=r"(?i)^/start$"))
async def cmd_start(event: Message):
    if event.is_private:
        await event.respond(MENU)

@client.on(events.NewMessage(pattern=r"(?i)^/status$"))
async def cmd_status(event: Message):
    if event.is_private:
        await event.respond(await status_text())

@client.on(events.NewMessage(pattern=r"(?i)^/pause$"))
async def cmd_pause(event: Message):
    if not event.is_private:
        return
    config["paused"] = True
    save_config(config)
    for tid in list(stop_flags.keys()):
        stop_flags[tid] = True
    await event.respond("Bot PAUSADO. Use /resume para voltar.")

@client.on(events.NewMessage(pattern=r"(?i)^/resume$"))
async def cmd_resume(event: Message):
    if not event.is_private:
        return
    config["paused"] = False
    save_config(config)
    await event.respond(f"Bot ATIVO. Lives: {len(config.get('live_jobs', []))}")

@client.on(events.NewMessage(pattern=r"(?i)^/update$"))
async def cmd_update(event: Message):
    if not event.is_private:
        return
    await event.respond("Atualizando...")
    try:
        result = subprocess.run(["git", "pull"], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=60)
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            await event.respond(f"Erro:\n{output[-1000:]}")
            return
        await event.respond(f"Atualizado! Reiniciando...\n{output[-400:] or 'ok'}")
        await asyncio.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        await event.respond(f"Erro: {e}")

@client.on(events.NewMessage(pattern=r"(?i)^/setsource\s+(.+)$"))
async def cmd_setsource(event: Message):
    if event.is_private:
        config["source"] = event.pattern_match.group(1).strip()
        save_config(config)
        await event.respond(f"Origem: `{config['source']}`")

@client.on(events.NewMessage(pattern=r"(?i)^/setdest\s+(.+)$"))
async def cmd_setdest(event: Message):
    if event.is_private:
        config["dest"] = event.pattern_match.group(1).strip()
        save_config(config)
        await event.respond(f"Destino: `{config['dest']}`")

@client.on(events.NewMessage(pattern=r"(?i)^/copyimages$"))
async def _(e):
    if e.is_private:
        await start_history_copy(e, True, False)

@client.on(events.NewMessage(pattern=r"(?i)^/copyimagescaption$"))
async def _(e):
    if e.is_private:
        await start_history_copy(e, True, True)

@client.on(events.NewMessage(pattern=r"(?i)^/copyall$"))
async def _(e):
    if e.is_private:
        await start_history_copy(e, False, False)

@client.on(events.NewMessage(pattern=r"(?i)^/copyallcaption$"))
async def _(e):
    if e.is_private:
        await start_history_copy(e, False, True)

@client.on(events.NewMessage(pattern=r"(?i)^/liveimages\s+(\S+)\s+(\S+)$"))
async def _(e):
    if e.is_private:
        config.setdefault("live_jobs", []).append({"source": e.pattern_match.group(1), "dest": e.pattern_match.group(2), "mode": "images_no_caption"})
        save_config(config)
        await e.respond(f"Live ativado: `{e.pattern_match.group(1)}` -> `{e.pattern_match.group(2)}` (img sem legenda)")

@client.on(events.NewMessage(pattern=r"(?i)^/liveimagescaption\s+(\S+)\s+(\S+)$"))
async def _(e):
    if e.is_private:
        config.setdefault("live_jobs", []).append({"source": e.pattern_match.group(1), "dest": e.pattern_match.group(2), "mode": "images_with_caption"})
        save_config(config)
        await e.respond(f"Live ativado: `{e.pattern_match.group(1)}` -> `{e.pattern_match.group(2)}` (img com legenda)")

@client.on(events.NewMessage(pattern=r"(?i)^/liveall\s+(\S+)\s+(\S+)$"))
async def _(e):
    if e.is_private:
        config.setdefault("live_jobs", []).append({"source": e.pattern_match.group(1), "dest": e.pattern_match.group(2), "mode": "all_no_caption"})
        save_config(config)
        await e.respond(f"Live ativado: `{e.pattern_match.group(1)}` -> `{e.pattern_match.group(2)}` (tudo)")

@client.on(events.NewMessage(pattern=r"(?i)^/stopcopy"))
async def cmd_stopcopy(event: Message):
    if event.is_private:
        for tid in list(stop_flags.keys()):
            stop_flags[tid] = True
        await event.respond("Historico parado.")

@client.on(events.NewMessage(pattern=r"(?i)^/stoplive"))
async def cmd_stoplive(event: Message):
    if event.is_private:
        config["live_jobs"] = []
        save_config(config)
        await event.respond("Lives parados.")

async def start_history_copy(event, only_photos, with_caption):
    global next_task_id
    if config.get("paused"):
        await event.respond("Bot pausado. Use /resume.")
        return
    source, dest = config.get("source"), config.get("dest")
    if not source or not dest:
        await event.respond("Use antes:\n/setsource @canal\n/setdest @canal")
        return
    task_id = next_task_id
    next_task_id += 1
    stop_flags[task_id] = False
    modo = "imagens" if only_photos else "tudo"
    legenda = "com legenda" if with_caption else "sem legenda"
    status = await event.respond(f"#{task_id}: {modo} | {legenda}\n`{source}` -> `{dest}`")

    async def runner():
        count = errors = 0
        processed = set()
        try:
            messages = []
            async for msg in client.iter_messages(source, reverse=True):
                if only_photos and not msg.photo:
                    continue
                if not msg.media and not msg.text:
                    continue
                messages.append(msg)
            i = 0
            while i < len(messages):
                if stop_flags.get(task_id) or config.get("paused"):
                    await status.edit(f"#{task_id} parada. Enviadas: {count}")
                    break
                msg = messages[i]
                if msg.grouped_id:
                    if msg.grouped_id in processed:
                        i += 1
                        continue
                    album = [m for m in messages if m.grouped_id == msg.grouped_id]
                    processed.add(msg.grouped_id)
                    try:
                        await send_album(dest, album, with_caption)
                        count += len(album)
                        await asyncio.sleep(2)
                    except FloodWaitError as e:
                        await asyncio.sleep(e.seconds + 2)
                        try:
                            await send_album(dest, album, with_caption)
                            count += len(album)
                        except Exception:
                            errors += 1
                    except Exception:
                        errors += 1
                else:
                    try:
                        await send_media(dest, msg, with_caption)
                        count += 1
                        await asyncio.sleep(1.5)
                    except FloodWaitError as e:
                        await asyncio.sleep(e.seconds + 2)
                        try:
                            await send_media(dest, msg, with_caption)
                            count += 1
                        except Exception:
                            errors += 1
                    except Exception:
                        errors += 1
                if count % 15 == 0 and count > 0:
                    await status.edit(f"#{task_id}... {count}")
                i += 1
            if not stop_flags.get(task_id) and not config.get("paused"):
                await status.edit(f"#{task_id} ok! Total: {count} | Erros: {errors}")
        except Exception as e:
            await status.edit(f"Erro #{task_id}: {e}")
        finally:
            history_tasks.pop(task_id, None)
            stop_flags.pop(task_id, None)

    history_tasks[task_id] = asyncio.create_task(runner())

@client.on(events.NewMessage)
async def live_handler(event: Message):
    if config.get("paused") or not config.get("live_jobs"):
        return
    if event.is_private:
        return
    chat = await event.get_chat()
    for job in config["live_jobs"]:
        if not is_source_match(chat, job["source"]):
            continue
        mode = job["mode"]
        if mode.startswith("images") and not event.message.photo:
            continue
        try:
            await send_media(job["dest"], event.message, "with_caption" in mode)
        except Exception as e:
            logger.error(f"Erro live: {e}")

async def main():
    print("Iniciando userbot...")
    await client.start()
    me = await client.get_me()
    print(f"Conectado: {me.first_name} ({me.id})")
    print("Envie /start em Mensagens Salvas.\n")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
