name: Auto Login Vortexa

on:
  schedule:
    # 每天 UTC 时间 06:30 运行（对应北京时间下午 02:30）
    - cron: '30 6 * * *'
  
  workflow_dispatch: # 允许手动触发

jobs:
  web-automation:
    runs-on: ubuntu-latest
    
    # 核心新增：赋予 GitHub Actions 修改仓库文件的写权限
    permissions:
      contents: write

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install playwright requests
          playwright install chromium --with-deps

      - name: Execute Login Script
        env:
          VORTEXA_USER: ${{ secrets.VORTEXA_USER }}
          VORTEXA_PASS: ${{ secrets.VORTEXA_PASS }}
          TG_BOT_TOKEN: ${{ secrets.TG_BOT_TOKEN }}
          TG_CHAT_ID: ${{ secrets.TG_CHAT_ID }}
        run: |
          python login.py

      # 核心新增：如果 README.md 被修改了，自动提交并推送到仓库
      - name: Commit and Push README Updates
        run: |
          git config --local user.email "actions@github.com"
          git config --local user.name "github-actions[bot]"
          git add README.md
          # 检查是否有变动，有变动才提交，防止无变动时报错导致工作流显示失败
          git diff --quiet && git diff --staged --quiet || (git commit -m "chore: update README running time [skip ci]" && git push)
