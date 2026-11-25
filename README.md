# Backup local do site Kaori

Este repositório contém um espelho estático e editável do storefront público de
<https://try-kaori.com>. O conteúdo recuperado fica em `site/`.

## Abrir localmente

No PowerShell, dentro desta pasta:

```powershell
python .\serve_local.py
```

Depois abra <http://127.0.0.1:8000>.

## Conectar o checkout

Edite apenas `overrides/storefront-config.js` e preencha `checkoutUrl`. Todos os
botões de compra, carrinho e checkout usam essa configuração centralizada. Sem
uma URL definida, eles exibem um aviso em inglês e permanecem na prévia local.

## Atualizar o backup

```powershell
python .\tools\mirror_site.py
```

O inventário completo de páginas, arquivos e eventuais falhas fica em
`backup-manifest.json`.

## Limitações importantes

Este é um backup do **front-end público renderizado**. Ele inclui HTML, CSS,
JavaScript, imagens, fontes e vídeos encontrados, mas não recupera o tema Liquid
original nem dados privados do Shopify (pedidos, clientes, configurações, apps,
checkout e banco de dados). Formulários, carrinho e checkout ficam desativados no
modo local até serem ligados a um novo backend.
