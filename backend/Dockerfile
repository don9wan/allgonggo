FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium 설치 (캐치·그룹바이 크롤러 - Cloudflare WAF 우회)
RUN playwright install chromium --with-deps

COPY . .

CMD ["python", "start.py"]
