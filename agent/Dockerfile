FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 agent && mkdir -p /var/lib/pars2ray-agent && chown -R agent:agent /var/lib/pars2ray-agent
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
USER agent
EXPOSE 9100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9100"]
