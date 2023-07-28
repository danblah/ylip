FROM python:3.8-slim
RUN mkdir /app
WORKDIR /app
ADD requirements.txt /app
RUN pip3 install -r requirements.txt
ADD . /app
EXPOSE 8088
RUN chmod +x ./gunicorn_start.sh
ENTRYPOINT ["./gunicorn_start.sh"]