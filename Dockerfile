FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home agrosan && mkdir -p /app/instance && chown -R agrosan:agrosan /app
USER agrosan
EXPOSE 8080
CMD ["waitress-serve", "--listen=0.0.0.0:8080", "app:app"]
