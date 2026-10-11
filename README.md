# Referral Message

Bot do Telegram que copia automaticamente mensagens e mídias de um canal para outro.

## Funcionalidades

- Ao dar `/start`, configura o canal de origem e o canal de destino
- Copia **textos, fotos, vídeos, documentos e qualquer mídia**
- Usa `copy_message` (sem a tag "Encaminhado de")
- Funciona com canais públicos e privados (bot precisa ser admin)

## Como usar

### 1. Criar o bot
1. Fale com [@BotFather](https://t.me/BotFather)
2. Envie `/newbot` e siga as instruções
3. Copie o token gerado

### 2. Instalar dependências
```bash
pip install -r requirements.txt
```

### 3. Configurar o token
Abra o arquivo `bot.py` e substitua:
```python
BOT_TOKEN = "COLE_SEU_TOKEN_AQUI"
```
pelo token real do seu bot.

### 4. Rodar o bot
```bash
python bot.py
```

### 5. Configurar os canais
1. Abra o bot no Telegram e envie `/start`
2. Envie o canal de **origem** (ex: `@meucanal` ou `-1001234567890`)
3. Envie o canal de **destino**
4. Adicione o bot como **administrador** nos dois canais
   - No canal de destino → dê permissão de **Publicar mensagens**

Pronto! Todas as novas mensagens do canal de origem serão copiadas automaticamente para o destino.

## Observações

- O bot só copia mensagens **novas** (postadas depois da configuração)
- As configurações ficam apenas em memória (reiniciar o bot apaga)
- Para reconfigurar, envie `/start` novamente

## Licença

Livre para uso pessoal e comercial.
