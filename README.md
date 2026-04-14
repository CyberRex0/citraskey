# Citraskey
Nintendo 3DSをターゲットとしたMisskeyの軽量Webクライアント

## 環境構築

1. uv のインストール

    https://docs.astral.sh/uv/getting-started/installation/ に従ってインストールします

2. 依存パッケージのインストール

    ・`uv sync` でパッケージをインストールします

    ・ImageMagickとlibrsvg2-binをインストールします<br>
        (Ubuntu/Debianの場合: `sudo apt install imagemagick-6.q16 librsvg2-bin`)

3. 起動

    `uv run uvicorn app:asgi_app`

    ※リッスンポートは 環境変数 `PORT` で変更します


※Docker化は検討中
