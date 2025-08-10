
FROM python:3.11-slim
WORKDIR /app
COPY memory-service.py .
RUN pip install fastapi uvicorn pydantic
EXPOSE 8000
CMD ["uvicorn", "memory-service:app", "--host", "0.0.0.0", "--port", "8000"]

# This Dockerfile sets up a FastAPI application for the memory service.

# It uses Python 3.11 on a slim base image, installs necessary dependencies,
