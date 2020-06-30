FROM nginx:alpine

COPY ./nginx/http.conf /http.conf
COPY ./nginx/https.conf /https.conf
COPY ./nginx/nginx.conf /nginx.conf
COPY ./nginx/entrypoint.sh /entrypoint.sh
RUN \
    apk add openssl && \
    chmod +x /entrypoint.sh && \
    rm /etc/nginx/conf.d/default.conf
ENTRYPOINT ["/entrypoint.sh"]
HEALTHCHECK       \
    --timeout=5s \
    --retries=300  \
    --interval=1s \
    CMD           \
        ps -a | grep master | grep -v grep

# DATAJOINT DEFAULTS
COPY ./nginx/privkey.pem /etc/letsencrypt/live/fakeservices.datajoint.io/privkey.pem
COPY ./nginx/fullchain.pem /etc/letsencrypt/live/fakeservices.datajoint.io/fullchain.pem
ENV SUBDOMAINS fakeservices
ENV URL datajoint.io
