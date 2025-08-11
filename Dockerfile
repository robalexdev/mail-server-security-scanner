FROM python:3 AS app
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

FROM app AS test
RUN mkdir -p results
RUN python3 manage.py makemigrations db
RUN python3 manage.py migrate
RUN echo "robalexdev.com" > list.txt
RUN python analyze.py list.txt
RUN python3 analyze.py
RUN touch success

FROM app
COPY --from=test /app/success .
CMD [ "tail", "-f", "/dev/null" ]

