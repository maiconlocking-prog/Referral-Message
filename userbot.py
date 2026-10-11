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

# ================== CONFIGURAÇÃO ==================
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_NAME = "referral_session"
CONFIG_FILE = Path("config.json")
# ==================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if not API_ID or not API_HASH:
    raise ValueError(
        "\nAPI_ID e API_HASH não encontrados!\n"
        "Defina: export API_ID=... e export API_HASH=..."
    )

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "live_jobs" not in data:
                data["live_jobs"] = []
            if "paused" not in data:
                data["paused"] = False
            return data
    return {"source": None, "dest": None, "live_jobs": [], "paused": False}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

config = load_config()
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# Controle de cópias históricas
history_tasks = {}
stop_flags = {}
next_task_id = 1


async def send_media(dest, message, with_caption=False):
    caption = (message.text or None) if with_caption else None
    entities = message.entities if with_caption else None

    if message.media:
        await client.send_file(
            dest,
            file=message.media,
            caption=caption,
            formatting_entities=entities,
            force_document=False
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


def is_source_match(chat, source):
    chat_username = f"@{chat.username}" if getattr(chat, "username", None) else None
    chat_id = str(getattr(chat, "id", ""))
    return (
        chat_id == str(source)
        or (chat_username and chat_username.lower() == str(source).lower())
        or chat_id == str(source).replace("-100", "")
    )


# ===================== COMANDOS =====================

@client.on(events.NewMessage(pattern=r"(?i)^/start$"))
async def cmd_start(event: Message):
    if not event.is_private:
        return
    await event.reply(
        "**Referral Message – Userbot**\n\n"
        "**1. Configurar canais (cópia histórica)**\n"
        "/setsource `@canal`\n"
        "/setdest `@canal`\n\n"
        "**2. Cópia do histórico**\n"
        "/copyimages → imagens **sem** legenda\n"
        "/copyimagescaption → imagens **com** legenda\n"
        "/copyall → tudo sem legenda\n"
        "/copyallcaption → tudo com legenda\n\n"
        "**3. Cópia ao vivo**\n"
        "/liveimages `@origem` `@destino`\n"
        "/liveimagescaption `@origem` `@destino`\n"
        "/liveall `@origem` `@destino`\n\n"
        "**4. Controle**\n"
        "/status\n"
        "/pause → pausa toda cópia (bot continua ligado)\n"
        "/resume → volta a copiar\n"
        "/stoplive \| /stoplive `n`\n"
        "/stopcopy \| /stopcopy `n`\n"
        "/update → atualiza o código e reinicia sozinho\n\n"
        "Você pode rodar **várias cópias ao mesmo tempo**."
    )


@client.on(events.NewMessage(pattern=r"(?i)^/setsource\s+(.+)$"))
async def cmd_setsource(event: Message):
    if not event.is_private:
        return
    config["source"] = event.pattern_match.group(1).strip()
    save_config(config)
    await event.reply(f"✅ Origem temporária: `{config['source']}`")


@client.on(events.NewMessage(pattern=r"(?i)^/setdest\s+(.+)$"))
async def cmd_setdest(event: Message):
    if not event.is_private:
        return
    config["dest"] = event.pattern_match.group(1).strip()
    save_config(config)
    await event.reply(f"✅ Destino temporário: `{config['dest']}`")


@client.on(events.NewMessage(pattern=r"(?i)^/status$"))
async def cmd_status(event: Message):
    if not event.is_private:
        return

    paused = config.get("paused", False)
    text = "**Status atual**\n\n"
    text += f"Bot: {'⏸️ PAUSADO' if paused else '▶️ Ativo'}\n\n"

    if history_tasks:
        text += "**Cópias de histórico em andamento:**\n"
        for tid in history_tasks:
            text += f"  #{tid} – rodando\n"
    else:
        text += "Cópias de histórico: nenhuma\n"

    jobs = config.get("live_jobs", [])
    if jobs:
        text += "\n**Cópias ao vivo:**\n"
        for i, job in enumerate(jobs, 1):
            text += f"  #{i} `{job['source']}` → `{job['dest']}` ({job.get('mode', '?')})\n"
    else:
        text += "\nCópias ao vivo: nenhuma\n"

    text += f"\nOrigem temp: `{config.get('source') or 'não definida'}`\n"
    text += f"Destino temp: `{config.get('dest') or 'não definido'}`"
    await event.reply(text)


@client.on(events.NewMessage(pattern=r"(?i)^/pause$"))
async def cmd_pause(event: Message):
    if not event.is_private:
        return
    config["paused"] = True
    save_config(config)
    # Também para cópias de histórico em andamento
    for tid in list(stop_flags.keys()):
        stop_flags[tid] = True
    await event.reply(
        "⏸️ **Bot pausado**\n\n"
        "• Cópias ao vivo: desativadas\n"
        "• Cópias de histórico: interrompidas\n"
        "• O bot continua ligado (você ainda pode usar comandos)\n\n"
        "Use /resume para voltar."
    )


@client.on(events.NewMessage(pattern=r"(?i)^/resume$"))
async def cmd_resume(event: Message):
    if not event.is_private:
        return
    config["paused"] = False
    save_config(config)
    jobs = len(config.get("live_jobs", []))
    await event.reply(
        f"▶️ **Bot reativado**\n\n"
        f"Cópias ao vivo ativas: **{jobs}**\n"
        "Novas postagens voltarão a ser copiadas."
    )


@client.on(events.NewMessage(pattern=r"(?i)^/update$"))
async def cmd_update(event: Message):
    if not event.is_private:
        return

    await event.reply("🔄 Atualizando código do GitHub...")

    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=60
        )
        output = (result.stdout or "") + (result.stderr or "")

        if result.returncode != 0:
            await event.reply(f"❌ Erro no git pull:\n```\n{output[-1500:]}\n```")
            return

        await event.reply(
            f"✅ Código atualizado!\n\n```\n{output[-800:] or 'Já estava atualizado.'}\n```\n\n"
            "Reiniciando o bot em 2 segundos..."
        )
        await asyncio.sleep(2)

        # Reinicia o processo mantendo as variáveis de ambiente
        python = sys.executable
        os.execv(python, [python] + sys.argv)

    except Exception as e:
        await event.reply(f"❌ Erro ao atualizar:\n`{e}`")


# ---------- Cópia de histórico ----------

@client.on(events.NewMessage(pattern=r"(?i)^/copyimages$"))
async def cmd_copyimages(event: Message):
    if event.is_private:
        await start_history_copy(event, only_photos=True, with_caption=False)

@client.on(events.NewMessage(pattern=r"(?i)^/copyimagescaption$"))
async def cmd_copyimagescaption(event: Message):
    if event.is_private:
        await start_history_copy(event, only_photos=True, with_caption=True)

@client.on(events.NewMessage(pattern=r"(?i)^/copyall$"))
async def cmd_copyall(event: Message):
    if event.is_private:
        await start_history_copy(event, only_photos=False, with_caption=False)

@client.on(events.NewMessage(pattern=r"(?i)^/copyallcaption$"))
async def cmd_copyallcaption(event: Message):
    if event.is_private:
        await start_history_copy(event, only_photos=False, with_caption=True)


async def start_history_copy(event, only_photos, with_caption):
    global next_task_id

    if config.get("paused"):
        await event.reply("⏸️ Bot está pausado. Use /resume antes.")
        return

    source = config.get("source")
    dest = config.get("dest")
    if not source or not dest:
        await event.reply("❌ Use antes:\n/setsource @canal\n/setdest @canal")
        return

    task_id = next_task_id
    next_task_id += 1
    stop_flags[task_id] = False

    modo = "imagens" if only_photos else "tudo"
    legenda = "com legenda" if with_caption else "sem legenda"

    status = await event.reply(
        f"🔄 Cópia #{task_id} iniciada\n"
        f"{modo} | {legenda}\n"
        f"`{source}` → `{dest}`\n\n"
        f"Use /stopcopy {task_id} para parar esta."
    )

    async def runner():
        count = 0
        errors = 0
        processed_groups = set()
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
                    await status.edit(
                        f"⏹️ Cópia #{task_id} interrompida.\nEnviadas: **{count}**"
                    )
                    break

                msg = messages[i]

                if msg.grouped_id:
                    if msg.grouped_id in processed_groups:
                        i += 1
                        continue
                    album = [m for m in messages if m.grouped_id == msg.grouped_id]
                    processed_groups.add(msg.grouped_id)
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
                    await status.edit(
                        f"🔄 Cópia #{task_id}...\nEnviadas: **{count}**\n"
                        f"/stopcopy {task_id} para parar"
                    )
                i += 1

            if not stop_flags.get(task_id) and not config.get("paused"):
                await status.edit(
                    f"✅ Cópia #{task_id} finalizada!\nTotal: **{count}** | Erros: **{errors}**"
                )
        except Exception as e:
            await status.edit(f"❌ Erro na cópia #{task_id}:\n`{e}`")
        finally:
            history_tasks.pop(task_id, None)
            stop_flags.pop(task_id, None)

    task = asyncio.create_task(runner())
    history_tasks[task_id] = task


@client.on(events.NewMessage(pattern=r"(?i)^/stopcopy(?:\s+(\d+))?$"))
async def cmd_stopcopy(event: Message):
    if not event.is_private:
        return
    arg = event.pattern_match.group(1)

    if arg:
        tid = int(arg)
        if tid in stop_flags:
            stop_flags[tid] = True
            await event.reply(f"⏹️ Parando cópia de histórico #{tid}...")
        else:
            await event.reply(f"Cópia #{tid} não encontrada.")
    else:
        if not stop_flags:
            await event.reply("Nenhuma cópia de histórico em andamento.")
            return
        for tid in list(stop_flags.keys()):
            stop_flags[tid] = True
        await event.reply("⏹️ Parando todas as cópias de histórico...")


# ---------- Cópia ao vivo ----------

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


async def add_live_job(event, source, dest, mode):
    source = source.strip()
    dest = dest.strip()
    job = {"source": source, "dest": dest, "mode": mode}
    config.setdefault("live_jobs", []).append(job)
    save_config(config)

    modo_txt = {
        "images_no_caption": "imagens sem legenda",
        "images_with_caption": "imagens com legenda",
        "all_no_caption": "tudo sem legenda",
    }.get(mode, mode)

    num = len(config["live_jobs"])
    extra = "\n⚠️ Bot está **pausado**. Use /resume para ativar." if config.get("paused") else ""
    await event.reply(
        f"✅ Cópia ao vivo #{num} ativada\n"
        f"`{source}` → `{dest}`\n"
        f"Modo: {modo_txt}\n\n"
        f"Só copiará o que for postado **a partir de agora**.{extra}"
    )


@client.on(events.NewMessage(pattern=r"(?i)^/stoplive(?:\s+(\d+))?$"))
async def cmd_stoplive(event: Message):
    if not event.is_private:
        return
    arg = event.pattern_match.group(1)
    jobs = config.get("live_jobs", [])

    if not jobs:
        await event.reply("Nenhuma cópia ao vivo ativa.")
        return

    if arg:
        idx = int(arg) - 1
        if 0 <= idx < len(jobs):
            removed = jobs.pop(idx)
            save_config(config)
            await event.reply(f"⏹️ Cópia ao vivo #{idx+1} removida:\n`{removed['source']}` → `{removed['dest']}`")
        else:
            await event.reply("Número inválido. Use /status.")
    else:
        config["live_jobs"] = []
        save_config(config)
        await event.reply("⏹️ Todas as cópias ao vivo foram paradas.")


# ---------- Handler de mensagens novas ----------

@client.on(events.NewMessage)
async def live_handler(event: Message):
    if config.get("paused"):
        return

    jobs = config.get("live_jobs", [])
    if not jobs:
        return

    chat = await event.get_chat()

    for job in jobs:
        if not is_source_match(chat, job["source"]):
            continue

        mode = job["mode"]
        dest = job["dest"]

        if mode.startswith("images") and not event.message.photo:
            continue

        with_caption = "with_caption" in mode

        try:
            await send_media(dest, event.message, with_caption)
            logger.info(f"Live: {event.message.id} → {dest} ({mode})")
        except Exception as e:
            logger.error(f"Erro live: {e}")


async def main():
    print("Iniciando userbot...")
    await client.start()
    me = await client.get_me()
    print(f"Conectado como: {me.first_name} ({me.id})")
    if config.get("paused"):
        print("Estado: PAUSADO (use /resume)")
    print("Envie /start em Mensagens Salvas para ver os comandos.\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
