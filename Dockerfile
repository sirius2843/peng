FROM python:3.11-slim
WORKDIR /app
COPY backend ./backend
COPY knowledge ./knowledge
COPY web ./web
COPY server.py ./server.py
ENV STUDIO_DATA_DIR=/data
EXPOSE 16688
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "16688"]
