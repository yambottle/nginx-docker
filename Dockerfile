FROM nginx:alpine

COPY ./nginx/base.conf /base.conf
COPY ./nginx/nginx.conf /nginx.conf
COPY ./nginx/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
HEALTHCHECK       \
    --timeout=5s \
    --retries=300  \
    --interval=1s \
    CMD           \
        ps -a | grep master | grep -v grep

# DATAJOINT DEFAULTS
COPY ./nginx/privkey.pem /certs/privkey.pem
COPY ./nginx/fullchain.pem /certs/fullchain.pem
ENV SUBDOMAINS fakeservices
ENV URL datajoint.io
