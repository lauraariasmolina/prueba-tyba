FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY correr_cortes.sh .
RUN sed -i 's/\r$//' correr_cortes.sh

CMD ["sh", "correr_cortes.sh"]
