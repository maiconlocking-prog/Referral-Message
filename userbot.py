import asyncio
import json
import logging
import os
import sys
import subprocess
from pathlib import Path

from telethon import TelegramClient, events, Button
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
    raise ValueError("Defina API_ID e API_HASH nas variáveis de ambiente.")

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

# Estado de espera de texto por usuário: user_id -> {"action": "..."}
pending = {}


def main_menu():
    return [
        [Button.inline("📁 Histórico", b"menu_hist"), Button.inline("🔴 Ao vivo", b"menu_live")],
        [Button.inline("⚙️ Controle", b"menu_ctrl"), Button.inline("📊 Status", b"menu_status")],
        [Button.inline("🔄 Atualizar bot", b"do_update")],
    ]

def hist_menu():
    return [
        [Button.inline("📋 Definir origem", b"ask_source"), Button.inline("📋 Definir destino", b"ask_dest")],
        [Button.inline("🖼️ Imagens sem legenda", b"copy_img")],
        [Button.inline("🖼️ Imagens com legenda", b"copy_img_cap")],
        [Button.inline("📦 Tudo sem legenda", b"copy_all")],
        [Button.inline("📦 Tudo com legenda", b"copy_all_cap")],
        [Button.inline("⏹️ Parar histórico", b"stop_copy")],
        [Button.inline("⬅️ Voltar", b"menu_main")],
    ]

def live_menu():
    return [
        [Button.inline("🖼️ Live imagens sem legenda", b"ask_live_img")],
        [Button.inline("🖼️ Live imagens com legenda", b"ask_live_img_cap")],
        [Button.inline("📦 Live tudo sem legenda", b"ask_live_all")],
        [Button.inline("⏹️ Parar todos os lives", b"stop_live")],
        [Button.inline("⬅️ Voltar", b"menu_main")],
    ]

def ctrl_menu():
    return [
        [Button.inline("⏸️ Pausar tudo", b"do_pause"), Button.inline("▶️ Retomar", b"do_resume")],
        [Button.inline("⬅️ Voltar", b"menu_main")],
    ]


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
    text = f"**Status**\n\nBot: {'⏸️ PAUSADO' if paused else '▶️ Ativo'}\n\n"
    if history_tasks:
        text += "**Histórico em andamento:**\n" + "".join(f"  #{t}\n" for t in history_tasks) + "\n"
    else:
        text += "Histórico: nenhuma\n\n"
    jobs = config.get("live_jobs", [])
    if jobs:
        text += "**Lives ativos:**\n"
        for i, job in enumerate(jobs, 1):
            text += f"  #{i} `{job['source']}` → `{job['dest']}` ({job.get('mode')})\n"
    else:
        text += "Lives: nenhum\n"
    text += f"\nOrigem temp: `{config.get('source') or '—'}`\nDestino temp: `{config.get('dest') or '—'}`"
    return text


# ===================== /start + botões =====================

@client.on(events.NewMessage(pattern=r"(?i)^/start$"))
async def cmd_start(event: Message):
    if not event.is_private:
        return
    await event.reply(
        "**Referral Message**\n\nEscolha uma opção:",
        buttons=main_menu()
    )


@client.on(events.CallbackQuery)
async def on_button(event):
    data = event.data.decode()
    uid = event.sender_id

    if data == "menu_main":
        await event.edit("**Referral Message**\n\nEscolha uma opção:", buttons=main_menu())

    elif data == "menu_hist":
        await event.edit(
            "**Cópia de histórico**\n\n1. Defina origem e destino\n2. Escolha o tipo de cópia",
            buttons=hist_menu()
        )

    elif data == "menu_live":
        await event.edit(
            "**Cópia ao vivo**\n\nSó copia o que for postado a partir de agora.\nToque e depois envie: `@origem @destino`",
            buttons=live_menu()
        )

    elif data == "menu_ctrl":
        await event.edit("**Controle**", buttons=ctrl_menu())

    elif data == "menu_status":
        await event.answer()
        await event.respond(await status_text(), buttons=[[Button.inline("⬅️ Menu", b"menu_main")]])

    elif data == "ask_source":
        pending[uid] = {"action": "set_source"}
        await event.edit("Envie o canal de **origem** (`@canal` ou ID):")

    elif data == "ask_dest":
        pending[uid] = {"action": "set_dest"}
        await event.edit("Envie o canal de **destino** (`@canal` ou ID):")

    elif data == "ask_live_img":
        pending[uid] = {"action": "live", "mode": "images_no_caption"}
        await event.edit("Envie: `@origem @destino`\n(ex: `@canalA @canalB`)")

    elif data == "ask_live_img_cap":
        pending[uid] = {"action": "live", "mode": "images_with_caption"}
        await event.edit("Envie: `@origem @destino`\n(com legenda)")

    elif data == "ask_live_all":
        pending[uid] = {"action": "live", "mode": "all_no_caption"}
        await event.edit("Envie: `@origem @destino`\n(tudo sem legenda)")

    elif data == "copy_img":
        await event.answer()
        await start_history_copy(event, only_photos=True, with_caption=False)

    elif data == "copy_img_cap":
        await event.answer()
        await start_history_copy(event, only_photos=True, with_caption=True)

    elif data == "copy_all":
        await event.answer()
        await start_history_copy(event, only_photos=False, with_caption=False)

    elif data == "copy_all_cap":
        await event.answer()
        await start_history_copy(event, only_photos=False, with_caption=True)

    elif data == "stop_copy":
        for tid in list(stop_flags.keys()):
            stop_flags[tid] = True
        await event.answer("Parando histórico...")
        await event.respond("⏹️ Cópias de histórico interrompidas.")

    elif data == "stop_live":
        config["live_jobs"] = []
        save_config(config)
        await event.answer("Lives parados")
        await event.respond("⏹️ Todas as cópias ao vivo foram paradas.")

    elif data == "do_pause":
        config["paused"] = True
        save_config(config)
        for tid in list(stop_flags.keys()):
            stop_flags[tid] = True
        await event.answer("Pausado")
        await event.edit("⏸️ **Bot pausado**\nUse Retomar para voltar.", buttons=ctrl_menu())

    elif data == "do_resume":
        config["paused"] = False
        save_config(config)
        await event.answer("Retomado")
        await event.edit(
            f"▶️ **Bot ativo**\nLives: {len(config.get('live_jobs', []))}",
            buttons=ctrl_menu()
        )

    elif data == "do_update":
        await event.answer("Atualizando...")
        await event.respond("🔄 Atualizando código do GitHub...")
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
                await event.respond(f"❌ Erro:\n```\n{output[-1000:]}\n```")
                return
            await event.respond(f"✅ Atualizado!\n```\n{output[-600:] or 'Já estava atualizado.'}\n```\nReiniciando...")
            await asyncio.sleep(2)
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            await event.respond(f"❌ Erro: `{e}`")


# Texto pendente (origem/destino/live)
@client.on(events.NewMessage(func=lambda e: e.is_private and e.sender_id in pending and e.text and not e.text.startswith("/")))
async def on_pending_text(event: Message):
    uid = event.sender_id
    state = pending.pop(uid, None)
    if not state:
        return

    text = event.text.strip()
    action = state["action"]

    if action == "set_source":
        config["source"] = text
        save_config(config)
        await event.reply(f"✅ Origem: `{text}`", buttons=hist_menu())

    elif action == "set_dest":
        config["dest"] = text
        save_config(config)
        await event.reply(f"✅ Destino: `{text}`", buttons=hist_menu())

    elif action == "live":
        parts = text.split()
        if len(parts) < 2:
            await event.reply("Formato: `@origem @destino`")
            pending[uid] = state
            return
        source, dest = parts[0], parts[1]
        mode = state["mode"]
        config.setdefault("live_jobs", []).append({"source": source, "dest": dest, "mode": mode})
        save_config(config)
        modo = {
            "images_no_caption": "imagens sem legenda",
            "images_with_caption": "imagens com legenda",
            "all_no_caption": "tudo sem legenda",
        }.get(mode, mode)
        extra = "\n⚠️ Bot pausado — use Retomar." if config.get("paused") else ""
        await event.reply(
            f"✅ Live ativado\n`{source}` → `{dest}`\nModo: {modo}{extra}",
            buttons=live_menu()
        )


# Comandos de texto ainda funcionam
@client.on(events.NewMessage(pattern=r"(?i)^/status$"))
async def cmd_status(event: Message):
    if event.is_private:
        await event.reply(await status_text())

@client.on(events.NewMessage(pattern=r"(?i)^/pause$"))
async def cmd_pause(event: Message):
    if not event.is_private:
        return
    config["paused"] = True
    save_config(config)
    for tid in list(stop_flags.keys()):
        stop_flags[tid] = True
    await event.reply("⏸️ Bot pausado. Use /resume ou o botão Retomar.")

@client.on(events.NewMessage(pattern=r"(?i)^/resume$"))
async def cmd_resume(event: Message):
    if not event.is_private:
        return
    config["paused"] = False
    save_config(config)
    await event.reply(f"▶️ Bot ativo. Lives: {len(config.get('live_jobs', []))}")

@client.on(events.NewMessage(pattern=r"(?i)^/update$"))
async def cmd_update(event: Message):
    if not event.is_private:
        return
    await event.reply("🔄 Atualizando...")
    try:
        result = subprocess.run(["git", "pull"], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=60)
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            await event.reply(f"❌ Erro:\n```\n{output[-1000:]}\n```")
            return
        await event.reply(f"✅ Atualizado! Reiniciando...\n```\n{output[-500:]}\n```")
        await asyncio.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        await event.reply(f"❌ `{e}`")

@client.on(events.NewMessage(pattern=r"(?i)^/setsource\s+(.+)$"))
async def cmd_setsource(event: Message):
    if event.is_private:
        config["source"] = event.pattern_match.group(1).strip()
        save_config(config)
        await event.reply(f"✅ Origem: `{config['source']}`")

@client.on(events.NewMessage(pattern=r"(?i)^/setdest\s+(.+)$"))
async def cmd_setdest(event: Message):
    if event.is_private:
        config["dest"] = event.pattern_match.group(1).strip()
        save_config(config)
        await event.reply(f"✅ Destino: `{config['dest']}`")

@client.on(events.NewMessage(pattern=r"(?i)^/copyimages$"))
async def _(e):
    if e.is_private: await start_history_copy(e, True, False)

@client.on(events.NewMessage(pattern=r"(?i)^/copyimagescaption$"))
async def _(e):
    if e.is_private: await start_history_copy(e, True, True)

@client.on(events.NewMessage(pattern=r"(?i)^/copyall$"))
async def _(e):
    if e.is_private: await start_history_copy(e, False, False)

@client.on(events.NewMessage(pattern=r"(?i)^/copyallcaption$"))
async def _(e):
    if e.is_private: await start_history_copy(e, False, True)

@client.on(events.NewMessage(pattern=r"(?i)^/liveimages\s+(\S+)\s+(\S+)$"))
async def _(e):
    if e.is_private:
        await add_live(e, e.pattern_match.group(1), e.pattern_match.group(2), "images_no_caption")

@client.on(events.NewMessage(pattern=r"(?i)^/liveimagescaption\s+(\S+)\s+(\S+)$"))
async def _(e):
    if e.is_private:
        await add_live(e, e.pattern_match.group(1), e.pattern_match.group(2), "images_with_caption")

@client.on(events.NewMessage(pattern=r"(?i)^/liveall\s+(\S+)\s+(\S+)$"))
async def _(e):
    if e.is_private:
        await add_live(e, e.pattern_match.group(1), e.pattern_match.group(2), "all_no_caption")

@client.on(events.NewMessage(pattern=r"(?i)^/stopcopy(?:\s+(\d+))?$"))
async def cmd_stopcopy(event: Message):
    if not event.is_private:
        return
    arg = event.pattern_match.group(1)
    if arg:
        tid = int(arg)
        if tid in stop_flags:
            stop_flags[tid] = True
            await event.reply(f"⏹️ Parando #{tid}...")
        else:
            await event.reply("Não encontrada.")
    else:
        for tid in list(stop_flags.keys()):
            stop_flags[tid] = True
        await event.reply("⏹️ Histórico parado.")

@client.on(events.NewMessage(pattern=r"(?i)^/stoplive(?:\s+(\d+))?$"))
async def cmd_stoplive(event: Message):
    if not event.is_private:
        return
    arg = event.pattern_match.group(1)
    jobs = config.get("live_jobs", [])
    if not jobs:
        await event.reply("Nenhum live.")
        return
    if arg:
        idx = int(arg) - 1
        if 0 <= idx < len(jobs):
            removed = jobs.pop(idx)
            save_config(config)
            await event.reply(f"⏹️ Removido: `{removed['source']}` → `{removed['dest']}`")
        else:
            await event.reply("Número inválido.")
    else:
        config["live_jobs"] = []
        save_config(config)
        await event.reply("⏹️ Todos os lives parados.")


async def add_live(event, source, dest, mode):
    config.setdefault("live_jobs", []).append({"source": source.strip(), "dest": dest.strip(), "mode": mode})
    save_config(config)
    await event.reply(f"✅ Live: `{source}` → `{dest}`")


async def start_history_copy(event, only_photos, with_caption):
    global next_task_id

    # event pode ser CallbackQuery ou Message
    reply = event.respond if hasattr(event, "respond") else event.reply

    if config.get("paused"):
        await reply("⏸️ Bot pausado. Use Retomar.")
        return

    source = config.get("source")
    dest = config.get("dest")
    if not source or not dest:
        await reply("❌ Defina origem e destino primeiro (menu Histórico).")
        return

    task_id = next_task_id
    next_task_id += 1
    stop_flags[task_id] = False

    modo = "imagens" if only_photos else "tudo"
    legenda = "com legenda" if with_caption else "sem legenda"
    status = await reply(f"🔄 Cópia #{task_id}: {modo} | {legenda}\n`{source}` → `{dest}`")

    async def runner():
        count = errors = 0
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
                    await status.edit(f"⏹️ #{task_id} parada. Enviadas: **{count}**")
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
                    await status.edit(f"🔄 #{task_id}... Enviadas: **{count}**")
                i += 1

            if not stop_flags.get(task_id) and not config.get("paused"):
                await status.edit(f"✅ #{task_id} ok! Total: **{count}** | Erros: **{errors}**")
        except Exception as e:
            await status.edit(f"❌ Erro #{task_id}: `{e}`")
        finally:
            history_tasks.pop(task_id, None)
            stop_flags.pop(task_id, None)

    history_tasks[task_id] = asyncio.create_task(runner())


@client.on(events.NewMessage)
async def live_handler(event: Message):
    if config.get("paused") or not config.get("live_jobs"):
        return
    if event.is_private and (event.sender_id in pending or (event.text and event.text.startswith("/"))):
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
