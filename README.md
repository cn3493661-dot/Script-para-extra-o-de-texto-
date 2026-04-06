# Script-para-extra-o-de-texto-
Script em Python para extração automática de transcrições de vídeos do YouTube, utilizando múltiplas estratégias (API oficial e endpoints públicos) com fallback inteligente e opção de tradução automática
# Extração de Transcrição do YouTube com Fallback Inteligente

## 📌 Sobre o projeto
Este script em Python foi desenvolvido para extrair transcrições de vídeos do YouTube sem a necessidade de baixar o vídeo.

Ele utiliza múltiplas abordagens para garantir a obtenção do conteúdo, incluindo API oficial e endpoints públicos, com sistema de fallback automático.

## 🚀 Funcionalidades
- Extração de transcrição a partir de ID ou URL
- Suporte a múltiplos idiomas (pt, en, etc.)
- Fallback automático caso a API falhe
- Conversão de XML/VTT para texto limpo
- Tradução automática opcional
- Execução via linha de comando (CLI)

## 🛠️ Tecnologias utilizadas
- Python
- requests
- XML parsing (ElementTree)
- Regex
- youtube-transcript-api
- deep-translator

## ⚙️ Como usar

```bash
python get_transcript_fallback.py VIDEO_ID
