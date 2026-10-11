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
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_NAME = "referral_session"
CONFIG_FILE = Path("config.json")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
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

# cache: texto do canal -> entity id resolvido
entity_cache = {}

MENU = """**Referral Message**

**Historico**
`/setsource @canal`
`/setdest @canal`
`/copyimages` — imagens sem legenda
`/copyimagescaption` — imagens com legenda
`/copyall` — tudo sem legenda
`/copyallcaption` — tudo com legenda
`/stopcopy`

**Ao vivo**
`/liveimages @origem @destino`
`/liveimagescaption @origem @destino`
`/liveall @origem @destino`
`/stoplive`

**Controle**
`/status`
`/pause`
`/resume`
`/test` — testa se o bot responde
`/update`
"""


async def resolve_entity(ref):
    """Resolve @username ou ID para a entidade do Telegram."""
    ref = str(ref).strip()
    if ref in entity_cache:
        return entity_cache[ref]
    try:
        # tenta como esta
        ent = await client.get_entity(ref)
    except Exception:
        try:
            # tenta sem @
            ent = await client.get_entity(ref.lstrip("@"))
        except Exception as e:
            logger.error(f"Nao resolveu entidade {ref}: {e}")
            return None
    entity_cache[ref] = ent
    entity_cache[str(ent.id)] = ent
    if getattr(ent, "username", None):
        entity_cache[f"@{ent.username}"] = ent
        entity_cache[ent.username] = ent
    return ent


def chat_matches_source(chat, source_ref, source_id=None):
    """Verifica se o chat da mensagem e o canal de origem."""
    if source_id is not None:
        # IDs de canal no Telethon podem vir como id simples ou -100...
        cid = getattr(chat, "id", None)
        if cid is not None and int(cid) == int(source_id):
            return True
        # formato -100...
        try:
            if int(f"-100{cid}") == int(source_id) or int(cid) == int(str(source_id).replace("-100", "")):
                return True
        except Exception:
            pass

    source_ref = str(source_ref).strip()
    uname = getattr(chat, "username", None)
    if uname:
        if source_ref.lower() in (f"@{uname}".lower(), uname.lower()):
            return True
    try:
        if str(getattr(chat, "id", "")) == str(source_ref).replace("-100", ""):
            return True
        if str(getattr(chat, "id", "")) == str(source_ref):
            return True
    except Exception:
        pass
    return False


def is_photo_message(message):
    if message.photo:
        return True
    if isinstance(message.media, MessageMediaPhoto):
        return True
    # imagem enviada como documento
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc and getattr(doc, "mime_type", "").startswith("image/"):
            return True
    return False


async def send_media(dest, message, with_caption=False):
    caption = (message.text or None) if with_caption else None
    entities = message.entities if with_caption else None
    if message.media:
        await client.send_file(
            dest,
            file=message.media,
            caption=caption,
            formatting_entities=entities,
            force_document=False,
        )
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
            text += (
                f"  #{i} `{job.get('source')}` -> `{job.get('dest')}` "
                f"({job.get('mode')}) id={job.get('source_id')}\n"
            )
    else:
        text += "Lives: nenhum\n"
    text += f"\nOrigem: `{config.get('source') or '-'}\nDestino: `{config.get('dest') or '-'}`"
    return text


@client.on(events.NewMessage(pattern=r"(?i)^/start$"))
async def cmd_start(event: Message):
    if event.is_private:
        await event.respond(MENU)


@client.on(events.NewMessage(pattern=r"(?i)^/test$"))
async def cmd_test(event: Message):
    if event.is_private:
        me = await client.get_me()
        jobs = config.get("live_jobs", [])
        await event.respond(
            f"OK! Bot funcionando.\n"
            f"Conta: {me.first_name} (`{me.id}`)\n"
            f"Lives ativos: {len(jobs)}\n"
            f"Pausado: {config.get('paused')}"
        )


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
    await event.respond("Bot PAUSADO. Use /resume")


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
        result = subprocess.run(
            ["git", "pull"], cwd=Path(__file__).parent,
            capture_output=True, text=True, timeout=60
        )
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
    if not event.is_private:
        return
    ref = event.pattern_match.group(1).strip()
    ent = await resolve_entity(ref)
    if not ent:
        await event.respond(f"Nao encontrei o canal: `{ref}`\nEntre no canal com esta conta e tente de novo.")
        return
    config["source"] = ref
    config["source_id"] = ent.id
    save_config(config)
    uname = f"@{ent.username}" if getattr(ent, "username", None) else ent.id
    await event.respond(f"Origem OK: `{uname}` (id `{ent.id}`)")


@client.on(events.NewMessage(pattern=r"(?i)^/setdest\s+(.+)$"))
async def cmd_setdest(event: Message):
    if not event.is_private:
        return
    ref = event.pattern_match.group(1).strip()
    ent = await resolve_entity(ref)
    if not ent:
        await event.respond(f"Nao encontrei o canal: `{ref}`")
        return
    config["dest"] = ref
    config["dest_id"] = ent.id
    save_config(config)
    uname = f"@{ent.username}" if getattr(ent, "username", None) else ent.id
    await event.respond(f"Destino OK: `{uname}` (id `{ent.id}`)")


async def add_live_job(event, source_ref, dest_ref, mode):
    source_ref = source_ref.strip()
    dest_ref = dest_ref.strip()

    src = await resolve_entity(source_ref)
    dst = await resolve_entity(dest_ref)

    if not src:
        await event.respond(
            f"Nao encontrei a **origem** `{source_ref}`.\n"
            f"Entre nesse canal com esta conta e tente de novo."
        )
        return
    if not dst:
        await event.respond(
            f"Nao encontrei o **destino** `{dest_ref}`.\n"
            f"Verifique se a conta tem acesso e pode postar la."
        )
        return

    job = {
        "source": source_ref,
        "dest": dest_ref,
        "source_id": src.id,
        "dest_id": dst.id,
        "mode": mode,
    }
    config.setdefault("live_jobs", []).append(job)
    save_config(config)

    modo = {
        "images_no_caption": "imagens sem legenda",
        "images_with_caption": "imagens com legenda",
        "all_no_caption": "tudo sem legenda",
    }.get(mode, mode)

    extra = "\nAVISO: bot esta PAUSADO. Use /resume" if config.get("paused") else ""
    await event.respond(
        f"Live #{len(config['live_jobs'])} ativado\n"
        f"`{source_ref}` -> `{dest_ref}`\n"
        f"Modo: {modo}\n"
        f"source_id: `{src.id}`\n"
        f"So copia o que for postado a partir de agora.{extra}"
    )
    logger.info(f"Live job: {source_ref}({src.id}) -> {dest_ref}({dst.id}) mode={mode}")


@client.on(events.NewMessage(pattern=r"(?i)^/liveimages\s+(\S+)\s+(\S+)$"))
async def cmd_liveimages(event: Message):
    if event.is_private:
        await add_live_job(event, event.pattern_match.group(1), event.pattern_match.group(2), "images_no_caption")


@client.on(events.NewMessage(pattern=r"(?i)^/liveimagescaption\s+(\S+)\s+(\S+)$"))
async def cmd_liveimagescaption(event: Message):
    if event.is_private:
        await add_live_job(event, event.pattern_match.group(1), event.pattern_match.group(2), "images_with_caption")


@client.on(events.NewMessage(pattern=r"(?i)^/liveall\s+(\S+)\s+(\S+)$"))
async def cmd_liveall(event: Message):
    if event.is_private:
        await add_live_job(event, event.pattern_match.group(1), event.pattern_match.group(2), "all_no_caption")


@client.on(events.NewMessage(pattern=r"(?i)^/stoplive"))
async def cmd_stoplive(event: Message):
    if event.is_private:
        config["live_jobs"] = []
        save_config(config)
        await event.respond("Todos os lives parados.")


@client.on(events.NewMessage(pattern=r"(?i)^/stopcopy"))
async def cmd_stopcopy(event: Message):
    if event.is_private:
        for tid in list(stop_flags.keys()):
            stop_flags[tid] = True
        await event.respond("Historico parado.")


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


async def start_history_copy(event, only_photos, with_caption):
    global next_task_id
    if config.get("paused"):
        await event.respond("Bot pausado. Use /resume")
        return

    source_ref = config.get("source")
    dest_ref = config.get("dest")
    if not source_ref or not dest_ref:
        await event.respond("Use antes:\n/setsource @canal\n/setdest @canal")
        return

    src = await resolve_entity(source_ref)
    dst = await resolve_entity(dest_ref)
    if not src or not dst:
        await event.respond("Nao consegui acessar origem ou destino. Entre nos canais com esta conta.")
        return

    task_id = next_task_id
    next_task_id += 1
    stop_flags[task_id] = False
    modo = "imagens" if only_photos else "tudo"
    legenda = "com legenda" if with_caption else "sem legenda"
    status = await event.respond(f"#{task_id}: {modo} | {legenda}\n`{source_ref}` -> `{dest_ref}`")

    async def runner():
        count = errors = 0
        processed = set()
        try:
            messages = []
            async for msg in client.iter_messages(src, reverse=True):
                if only_photos and not is_photo_message(msg):
                    continue
                if not msg.media and not msg.text:
                    continue
                messages.append(msg)

            await status.edit(f"#{task_id}: encontradas {len(messages)} msgs. Copiando...")

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
                        await send_album(dst, album, with_caption)
                        count += len(album)
                        await asyncio.sleep(2)
                    except FloodWaitError as e:
                        await asyncio.sleep(e.seconds + 2)
                        try:
                            await send_album(dst, album, with_caption)
                            count += len(album)
                        except Exception as e2:
                            errors += 1
                            logger.error(f"album erro: {e2}")
                    except Exception as e:
                        errors += 1
                        logger.error(f"album erro: {e}")
                else:
                    try:
                        await send_media(dst, msg, with_caption)
                        count += 1
                        await asyncio.sleep(1.5)
                    except FloodWaitError as e:
                        await asyncio.sleep(e.seconds + 2)
                        try:
                            await send_media(dst, msg, with_caption)
                            count += 1
                        except Exception as e2:
                            errors += 1
                            logger.error(f"msg erro: {e2}")
                    except Exception as e:
                        errors += 1
                        logger.error(f"msg erro: {e}")
                if count % 10 == 0 and count > 0:
                    await status.edit(f"#{task_id}... {count} enviadas")
                i += 1

            if not stop_flags.get(task_id) and not config.get("paused"):
                await status.edit(f"#{task_id} ok! Total: {count} | Erros: {errors}")
        except Exception as e:
            await status.edit(f"Erro #{task_id}: {e}")
            logger.exception("history copy")
        finally:
            history_tasks.pop(task_id, None)
            stop_flags.pop(task_id, None)

    history_tasks[task_id] = asyncio.create_task(runner())


# ---------- LIVE: escuta canais ----------
@client.on(events.NewMessage)
async def live_handler(event: Message):
    if config.get("paused"):
        return
    jobs = config.get("live_jobs") or []
    if not jobs:
        return
    # ignora mensagens privadas (comandos)
    if event.is_private:
        return

    chat = await event.get_chat()
    msg = event.message

    for job in jobs:
        if not chat_matches_source(chat, job.get("source"), job.get("source_id")):
            continue

        mode = job.get("mode", "")
        dest_ref = job.get("dest_id") or job.get("dest")

        if mode.startswith("images") and not is_photo_message(msg):
            continue

        with_caption = "with_caption" in mode

        try:
            await send_media(dest_ref, msg, with_caption)
            logger.info(
                f"LIVE ok msg={msg.id} chat={getattr(chat,'id',None)} -> {dest_ref} mode={mode}"
            )
        except Exception as e:
            logger.error(f"LIVE erro msg={msg.id}: {e}")
            # tenta avisar no Saved Messages uma vez a cada erro grave
            try:
                me = await client.get_me()
                await client.send_message(me.id, f"Erro ao copiar live: `{e}`")
            except Exception:
                pass


async def main():
    print("Iniciando userbot...")
    await client.start()
    me = await client.get_me()
    print(f"Conectado: {me.first_name} ({me.id})")
    print(f"Lives carregados: {len(config.get('live_jobs', []))}")
    print(f"Pausado: {config.get('paused')}")
    print("Envie /start ou /test em Mensagens Salvas.\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
