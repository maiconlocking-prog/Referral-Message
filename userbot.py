import asyncio
import logging
import os
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel

# ================== CONFIGURAÇÃO ==================
# Pegue em https://my.telegram.org
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# Sessão (não precisa mudar)
SESSION_NAME = "referral_session"

# Canais (pode usar @username ou ID numérico)
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL", "")   # Ex: @canalorigem ou -1001234567890
DEST_CHANNEL = os.getenv("DEST_CHANNEL", "")       # Ex: @canaldestino ou -1009876543210
# ==================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if not API_ID or not API_HASH:
    raise ValueError(
        "\nAPI_ID e API_HASH não encontrados!\n"
        "1. Acesse https://my.telegram.org\n"
        "2. Faça login com seu número\n"
        "3. Vá em 'API development tools'\n"
        "4. Crie um aplicativo e copie api_id e api_hash\n"
        "5. Defina as variáveis:\n"
        "   export API_ID=12345678\n"
        "   export API_HASH=abcdef123456...\n"
    )

if not SOURCE_CHANNEL or not DEST_CHANNEL:
    raise ValueError(
        "\nDefina SOURCE_CHANNEL e DEST_CHANNEL:\n"
        "export SOURCE_CHANNEL=@canalorigem\n"
        "export DEST_CHANNEL=@canaldestino\n"
    )

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def handler(event):
    """Copia qualquer nova mensagem do canal de origem para o destino."""
    try:
        # Copia a mensagem (mantém mídia, formatação etc.)
        await event.message.forward_to(DEST_CHANNEL)
        # Se quiser copiar sem a tag "Encaminhado de", use:
        # await client.send_message(DEST_CHANNEL, event.message)
        logger.info(f"Mensagem {event.message.id} copiada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao copiar mensagem: {e}")


async def main():
    print("Iniciando userbot...")
    await client.start()
    print("Userbot conectado!")
    print(f"Monitorando: {SOURCE_CHANNEL}")
    print(f"Enviando para: {DEST_CHANNEL}")
    print("Pressione Ctrl+C para parar.\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
