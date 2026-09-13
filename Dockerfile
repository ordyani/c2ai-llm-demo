# Minimal image for the C2AI demo. No dependencies — Python standard library only.
FROM python:3.12-slim

WORKDIR /app
COPY main.py .

# The health server listens here; match this to the "Port" you register in Athena.
EXPOSE 8080

CMD ["python", "main.py"]
