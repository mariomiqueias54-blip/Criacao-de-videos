# Arquivo Zero Studio

Estúdio web responsivo para iPhone e notebook, com geração de roteiro (OpenAI API opcional), narração em português via edge-tts e renderização de vídeos MP4 1080×1920 ou 1920×1080 a partir de imagens ou slides.

## Publicação no Render
1. Conecte este repositório no Render em **New → Web Service**.
2. Escolha **Docker** como ambiente de execução.
3. Configure a variável **OPENAI_API_KEY** nas configurações secretas do Render (opcional para roteiros com IA). Nunca envie chaves para o GitHub.
4. Faça o deploy. O endereço HTTPS será fornecido pelo Render.
5. Abra o endereço no Safari ou Chrome.

## Avisos importantes
- Este é um protótipo que ainda precisa ser testado em hospedagem real. Não é um produto pronto para uso público.
- Não há autenticação, cotas por usuário, proteção contra abuso, armazenamento permanente ou sincronização entre dispositivos. **Não disponibilize publicamente sem essas proteções.**
- O plano gratuito de hospedagem pode não ter CPU/RAM suficientes para MP4 Full HD.
- A narração precisa de conexão com serviço externo; o roteiro com OpenAI exige chave e pode ter custo.
- O vídeo utiliza imagens estáticas ou slides; não gera filmagens realistas.
- Verifique direitos autorais, fatos e fontes antes de publicar.
