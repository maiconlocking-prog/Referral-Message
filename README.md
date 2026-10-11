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
4. Crie um aplicativo e copie o `api_id` e o `api_hash`

### 4. Definir API_ID e API_HASH
```bash
export API_ID=39897941
export API_HASH="3951ac4e1d548390392f4b05754cdc9c"
```

### 5. Rodar o userbot
```bash
python userbot.py
```

Na primeira vez ele vai pedir seu número e o código do Telegram.

### 6. Configurar os canais por comando

Abra o Telegram → **Mensagens Salvas** (ou qualquer chat privado) e envie:

```
/start
```

Depois:

```
/setsource @canal_de_origem
```

ou com ID:

```
/setsource -1001234567890
```

```
/setdest @canal_de_destino
```

Para ver a configuração atual:

```
/status
```

Para parar de copiar:

```
/stop
```

## Comandos disponíveis

| Comando              | Função                          |
|----------------------|---------------------------------|
| `/start`             | Mostra a ajuda                  |
| `/setsource @canal`  | Define o canal de origem        |
| `/setdest @canal`    | Define o canal de destino       |
| `/status`            | Mostra a configuração atual    |
| `/stop`              | Para de copiar e limpa config   |

## Observações importantes

- A conta usada **precisa estar no canal de origem** (pode ser só membro)
- A conta usada **precisa conseguir postar** no canal de destino (geralmente ser admin)
- Não compartilhe o arquivo `referral_session.session`
- A configuração é salva no arquivo `config.json`

## Licença

Livre para uso pessoal.
