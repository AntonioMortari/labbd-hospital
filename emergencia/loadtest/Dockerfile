FROM python:3.12-slim
WORKDIR /t
RUN pip install --no-cache-dir httpx
COPY test.py .
CMD ["python", "test.py"]
