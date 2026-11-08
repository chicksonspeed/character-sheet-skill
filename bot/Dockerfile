FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot
COPY bot.py .

# Bot token and admin ID come from environment
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
