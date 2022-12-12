FROM python:alpine

COPY ./nginx/entrypoint.py /entrypoint.py
RUN \
    apk update && \
    pip install \
        --platform=musllinux_1_1_x86_64 \
        --only-binary=:all: \
        --target=/usr/local/lib/python3.10/site-packages \
        --no-cache-dir \
        cffi && \
    apk add openssl nginx nginx-mod-stream && \
    pip install otumat && \
    chmod +x /entrypoint.py && \
    rm /etc/nginx/http.d/default.conf
ENTRYPOINT ["/entrypoint.py"]
HEALTHCHECK       \
    --timeout=30s \
    --retries=5  \
    --interval=15s \
    CMD           \
    ps -a | grep -e "root.*nginx" | grep -v grep

CMD ["main"]

# DATAJOINT DEFAULTS
COPY ./nginx/privkey.pem /etc/letsencrypt/live/fakeservices.datajoint.io/privkey.pem
COPY ./nginx/fullchain.pem /etc/letsencrypt/live/fakeservices.datajoint.io/fullchain.pem
ENV SUBDOMAINS fakeservices
ENV URL datajoint.io
