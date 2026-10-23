FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m voyager
COPY --chown=voyager:voyager backend ./backend
COPY --chown=voyager:voyager dist ./dist
COPY --chown=voyager:voyager seed ./seed
RUN mkdir /data && chown voyager:voyager /data
USER voyager
ENV VOYAGER_DATA_DIR=/data
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "--timeout", "240", "backend.app:application"]
