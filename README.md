# Referral Message

Userbot do Telegram que copia automaticamente mensagens e mídias de um canal para outro.

## Diferença do bot normal

- **Não precisa ser administrador** no canal de **origem**
- Funciona como uma conta de usuário normal
- Ainda precisa ter permissão de postar no canal de **destino** (ser admin ou dono)

## Como usar no Termux

### 1. Instalar dependências
```bash
pkg update && pkg upgrade -y
pkg install python git -y
pip install telethon
```

### 2. Clonar o repositório
```bash
git clone https://github.com/maiconlocking-prog/Referral-Message.git
cd Referral-Message
```

### 3. Pegar API_ID e API_HASH
1. Acesse: https://my.telegram.org
2. Faça login com o **mesmo número** que você usa no Telegram
3. Clique em **API development tools**
4. Crie um aplicativo (pode colocar qualquer nome)
5. Copie o `api_id` e o `api_hash`

### 4. Definir as variáveis
```bash
export API_ID=12345678
export API_HASH="abcdef1234567890abcdef1234567890"
export SOURCE_CHANNEL="@canal_origem"
export DEST_CHANNEL="@canal_destino"
```

> Você pode usar `@username` ou o ID numérico (`-100...`)

### 5. Rodar o userbot
```bash
python userbot.py
```

Na primeira vez ele vai pedir:
- Seu número de telefone (com código do país, ex: +5511999999999)
- O código que chegar no Telegram
- (Se tiver) senha de verificação em duas etapas

Depois disso ele fica rodando e copiando as mensagens automaticamente.

## Observações importantes

- A conta usada **precisa estar no canal de origem** (pode ser só membro)
- A conta usada **precisa conseguir postar** no canal de destino (geralmente ser admin)
- Não compartilhe o arquivo `referral_session.session` (ele contém a sessão da sua conta)
- Use com moderção para evitar risco de limitação da conta

## Arquivos

- `userbot.py` → versão userbot (Telethon) → **recomendada**
- `bot.py` → versão bot normal (precisa ser admin nos dois canais)

## Licença

Livre para uso pessoal.
