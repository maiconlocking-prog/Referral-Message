import logging
import os
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ================== CONFIGURAÇÃO ==================
# O token é lido da variável de ambiente BOT_TOKEN
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError(
        "Token não encontrado!\n"
        "Defina a variável de ambiente BOT_TOKEN antes de rodar o bot.\n"
        "Exemplo (Linux/Mac): export BOT_TOKEN='seu_token_aqui'\n"
        "Exemplo (Windows PowerShell): $env:BOT_TOKEN='seu_token_aqui'"
    )
# ==================================================

# Estados da conversa
WAITING_SOURCE, WAITING_DEST = range(2)

# Dicionário em memória: user_id -> (source_id, dest_id)
user_configs = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá! Eu vou copiar mensagens e mídias de um canal para outro.\n\n"
        "① Me envie o **canal de origem** (pode ser @username ou o ID numérico).\n"
        "Exemplo: @meucanal ou -1001234567890"
    )
    return WAITING_SOURCE


async def receive_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    source = update.message.text.strip()
    context.user_data["source"] = source
    await update.message.reply_text(
        "Canal de origem salvo!\n\n"
        "② Agora me envie o **canal de destino** (onde as mensagens serão publicadas)."
    )
    return WAITING_DEST


async def receive_dest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dest = update.message.text.strip()
    source = context.user_data["source"]
    user_id = update.effective_user.id

    user_configs[user_id] = (source, dest)

    await update.message.reply_text(
        f"✅ Configuração concluída!\n\n"
        f"Origem: `{source}`\n"
        f"Destino: `{dest}`\n\n"
        "Agora adicione o bot como **administrador** nos dois canais.\n"
        "No canal de destino, dê permissão de **Publicar mensagens**.\n\n"
        "Assim que uma nova mensagem for postada no canal de origem, "
        "ela será copiada automaticamente para o destino.\n\n"
        "Para reconfigurar, envie /start novamente."
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe postagens de canais e copia para o destino configurado."""
    if not update.channel_post:
        return

    message = update.channel_post
    source_chat_id = message.chat.id
    source_username = f"@{message.chat.username}" if message.chat.username else None

    # Procura qual usuário configurou este canal como origem
    for user_id, (src, dest) in user_configs.items():
        # Aceita tanto ID numérico quanto @username
        if str(source_chat_id) == str(src) or (source_username and source_username == src):
            try:
                await context.bot.copy_message(
                    chat_id=dest,
                    from_chat_id=source_chat_id,
                    message_id=message.message_id
                )
                logger.info(f"Mensagem {message.message_id} copiada de {source_chat_id} para {dest}")
            except Exception as e:
                logger.error(f"Erro ao copiar mensagem: {e}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_source)],
            WAITING_DEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_dest)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    # Handler que captura postagens de canais
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))

    print("Bot rodando...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
