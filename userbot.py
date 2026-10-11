import asyncio
import json
import logging
import os
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
        "Defina as variáveis:\n"
        "  export API_ID=12345678\n"
        "  export API_HASH=abcdef123456...\n"
    )

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"source": None, "dest": None}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

config = load_config()
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# Flag para evitar rodar várias cópias ao mesmo tempo
copying = False


# ========== COMANDOS ==========

@client.on(events.NewMessage(pattern=r"(?i)^/start$"))
async def cmd_start(event: Message):
    if not event.is_private:
        return
    await event.reply(
        "**Referral Message - Userbot**\n\n"
        "Comandos disponíveis:\n\n"
        "/setsource `@canal` ou `ID`\n"
        "→ Define o canal de origem\n\n"
        "/setdest `@canal` ou `ID`\n"
        "→ Define o canal de destino\n\n"
        "/status\n"
        "→ Mostra a configuração atual\n\n"
        "/copyimages\n"
        "→ Copia **todas as imagens** já existentes do canal de origem\n\n"
        "/copyall\n"
        "→ Copia **todas as mensagens** (texto + mídia) do canal de origem\n\n"
        "/stop\n"
        "→ Para de copiar mensagens novas\n\n"
        "Envie os comandos em **Mensagens Salvas**."
    )


@client.on(events.NewMessage(pattern=r"(?i)^/setsource\s+(.+)$"))
async def cmd_setsource(event: Message):
    if not event.is_private:
        return
    source = event.pattern_match.group(1).strip()
    config["source"] = source
    save_config(config)
    await event.reply(f"✅ Canal de **origem** definido:\n`{source}`")
    logger.info(f"Origem definida: {source}")


@client.on(events.NewMessage(pattern=r"(?i)^/setdest\s+(.+)$"))
async def cmd_setdest(event: Message):
    if not event.is_private:
        return
    dest = event.pattern_match.group(1).strip()
    config["dest"] = dest
    save_config(config)
    await event.reply(f"✅ Canal de **destino** definido:\n`{dest}`")
    logger.info(f"Destino definido: {dest}")


@client.on(events.NewMessage(pattern=r"(?i)^/status$"))
async def cmd_status(event: Message):
    if not event.is_private:
        return
    source = config.get("source") or "_não definido_"
    dest = config.get("dest") or "_não definido_"
    await event.reply(
        f"**Configuração atual:**\n\n"
        f"Origem: `{source}`\n"
        f"Destino: `{dest}`"
    )


@client.on(events.NewMessage(pattern=r"(?i)^/stop$"))
async def cmd_stop(event: Message):
    if not event.is_private:
        return
    config["source"] = None
    config["dest"] = None
    save_config(config)
    await event.reply("🛑 Cópia de mensagens novas parada.")
    logger.info("Configuração limpa pelo usuário")


@client.on(events.NewMessage(pattern=r"(?i)^/copyimages$"))
async def cmd_copyimages(event: Message):
    if not event.is_private:
        return
    await copy_history(event, only_photos=True)


@client.on(events.NewMessage(pattern=r"(?i)^/copyall$"))
async def cmd_copyall(event: Message):
    if not event.is_private:
        return
    await copy_history(event, only_photos=False)


async def copy_history(event: Message, only_photos: bool = True):
    global copying

    source = config.get("source")
    dest = config.get("dest")

    if not source or not dest:
        await event.reply(
            "❌ Defina primeiro os canais:\n"
            "/setsource @canal\n"
            "/setdest @canal"
        )
        return

    if copying:
        await event.reply("⚠️ Já existe uma cópia em andamento. Aguarde terminar.")
        return

    copying = True
    tipo = "imagens" if only_photos else "todas as mensagens"
    status_msg = await event.reply(f"🔄 Iniciando cópia de **{tipo}**...\nIsso pode demorar.")

    count = 0
    errors = 0

    try:
        async for message in client.iter_messages(source, reverse=True):
            # Filtra só fotos se for /copyimages
            if only_photos and not message.photo:
                continue

            # Ignora mensagens de serviço
            if not message.media and not message.text:
                continue

            try:
                await message.forward_to(dest)
                count += 1

                # Atualiza status a cada 10 mensagens
                if count % 10 == 0:
                    await status_msg.edit(
                        f"🔄 Copiando...\n"
                        f"Enviadas: **{count}**"
                    )

                # Pequena pausa para evitar flood
                await asyncio.sleep(1.2)

            except FloodWaitError as e:
                logger.warning(f"FloodWait: esperando {e.seconds}s")
                await status_msg.edit(
                    f"⏳ Telegram pediu para esperar {e.seconds} segundos...\n"
                    f"Já copiei: **{count}**"
                )
                await asyncio.sleep(e.seconds + 1)

            except Exception as e:
                errors += 1
                logger.error(f"Erro ao copiar msg {message.id}: {e}")

        await status_msg.edit(
            f"✅ Cópia finalizada!\n\n"
            f"Total enviado: **{count}**\n"
            f"Erros: **{errors}**"
        )
        logger.info(f"Cópia finalizada: {count} mensagens, {errors} erros")

    except Exception as e:
        await status_msg.edit(f"❌ Erro durante a cópia:\n`{e}`")
        logger.error(f"Erro geral na cópia: {e}")

    finally:
        copying = False


# ========== COPIADOR DE MENSAGENS NOVAS ==========

@client.on(events.NewMessage)
async def copy_handler(event: Message):
    source = config.get("source")
    dest = config.get("dest")

    if not source or not dest:
        return

    chat = await event.get_chat()
    chat_username = f"@{chat.username}" if getattr(chat, "username", None) else None
    chat_id = str(event.chat_id)

    is_source = (
        chat_id == str(source)
        or (chat_username and chat_username.lower() == source.lower())
        or str(getattr(chat, "id", "")) == str(source).replace("-100", "")
    )

    if not is_source:
        return

    try:
        await event.message.forward_to(dest)
        logger.info(f"Mensagem nova {event.message.id} copiada → {dest}")
    except Exception as e:
        logger.error(f"Erro ao copiar mensagem nova: {e}")


async def main():
    print("Iniciando userbot...")
    await client.start()
    me = await client.get_me()
    print(f"Conectado como: {me.first_name} ({me.id})")
    print("Envie /start no chat privado (ou Mensagens Salvas) para ver os comandos.\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
