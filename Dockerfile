FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
ENV OLLAMA_URL=http://host.docker.internal:11434 DETOUR_DB=/data/detour.db
VOLUME /data
EXPOSE 8000
CMD ["gunicorn","-b","0.0.0.0:8000","app:app"]
