#! /bin/sh

update_cert() {
    nginx -s reload
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S')][DataJoint]: Certs updated."
}

if [ ! -z "$SUBDOMAINS" ]; then 
    export SUBDOMAINS=${SUBDOMAINS}.
fi

cp /base.conf /etc/nginx/conf.d/base.conf
cp /ssl.conf /etc/nginx/conf.d/ssl.conf
cp /nginx.conf /etc/nginx/nginx.conf

env | grep ADD | sort | while IFS= read -r line; do
    TEMP_VAR=$(echo $line | cut -d'=' -f1)
    TEMP_VALUE=$(echo $line | cut -d'=' -f2)
    if echo $TEMP_VAR | grep ENDPOINT; then 
        TEMP_ENDPOINT=$TEMP_VALUE
    elif echo $TEMP_VAR | grep PREFIX; then 
        TEMP_PREFIX=$TEMP_VALUE
    elif echo $TEMP_VAR | grep TYPE; then 
        TEMP_TYPE=$TEMP_VALUE
        if [ "$TEMP_PREFIX" = "/" ]; then
            TEMP_PREFIX=""
        fi
        service=$(echo $TEMP_ENDPOINT | cut -d':' -f1)
        port=$(echo $TEMP_ENDPOINT | cut -d':' -f2)
        if [ "$TEMP_TYPE" = "MINIO" ]; then
            sed -i '1 i\
server {\
  listen '${port}';\
  server_name {{SUBDOMAINS}}{{URL}};\
  client_max_body_size 0;\
  proxy_buffering off;\
  ignore_invalid_headers off;\
  \
  location '${TEMP_PREFIX}'/ {\
    access_log off;\
    proxy_http_version 1.1;\
    proxy_set_header Host $http_host;\
    proxy_pass http://'${TEMP_ENDPOINT}'/;\
  }\
}\
' /etc/nginx/conf.d/base.conf

            sed -i '$ i\
  location '${TEMP_PREFIX}'/ {\
    access_log off;\
    proxy_http_version 1.1;\
    proxy_set_header Host $http_host;\
    proxy_pass http://'${TEMP_ENDPOINT}'/;\
  }\
' /etc/nginx/conf.d/ssl.conf
        elif [ "$TEMP_TYPE" = "DATABASE" ]; then
            tee -a /etc/nginx/nginx.conf > /dev/null <<EOT
stream {
    upstream target_${service} {
    server ${TEMP_ENDPOINT};
  }

  server {
    listen 3306;
    proxy_pass target_${service};
  }
}
EOT
        else
            sed -i '1 i\
server {\
  listen '${port}';\
  server_name {{SUBDOMAINS}}{{URL}};\
  \
  location '${TEMP_PREFIX}'/ {\
    proxy_pass http://'${TEMP_ENDPOINT}'/;\
  }\
}\
' /etc/nginx/conf.d/base.conf

            sed -i '$ i\
  location '${TEMP_PREFIX}'/ {\
    proxy_pass http://'${TEMP_ENDPOINT}'/;\
  }\
' /etc/nginx/conf.d/ssl.conf
        fi;
        TEMP_ENDPOINT=""
        TEMP_PREFIX=""
        TEMP_TYPE=""
    fi
done

sed -i "s|{{SUBDOMAINS}}|${SUBDOMAINS}|g" /etc/nginx/conf.d/base.conf
sed -i "s|{{URL}}|${URL}|g" /etc/nginx/conf.d/base.conf
sed -i "s|{{SUBDOMAINS}}|${SUBDOMAINS}|g" /etc/nginx/conf.d/ssl.conf
sed -i "s|{{URL}}|${URL}|g" /etc/nginx/conf.d/ssl.conf
# echo "--------DEBUG: CURRENT NGINX CONF--------"
# cat /etc/nginx/nginx.conf
# echo "--------DEBUG: CURRENT HTTP CONF--------"
# cat /etc/nginx/conf.d/base.conf
# echo "--------DEBUG: CURRENT SSL CONF--------"
# cat /etc/nginx/conf.d/ssl.conf

mv /etc/nginx/conf.d/ssl.conf /tmp/ssl.conf

# nginx -g "daemon off;"
nginx

echo "[$(date -u '+%Y-%m-%d %H:%M:%S')][DataJoint]: Waiting for initial certs"
while [ ! -d /etc/letsencrypt/live/${SUBDOMAINS}.${URL} ]; do
    sleep 5
done
echo "[$(date -u '+%Y-%m-%d %H:%M:%S')][DataJoint]: Enabling SSL feature"
mv /tmp/ssl.conf /etc/nginx/conf.d/ssl.conf
update_cert

INIT_TIME=$(date +%s)
LAST_MOD_TIME=$(date -r $(echo /etc/letsencrypt/live/${SUBDOMAINS}.${URL}/$(ls -t /etc/letsencrypt/live/${SUBDOMAINS}.${URL}/ | head -n 1)) +%s)
DELTA=$(expr $LAST_MOD_TIME - $INIT_TIME)
while true; do
    CURR_FILEPATH=$(ls -t /etc/letsencrypt/live/${SUBDOMAINS}.${URL}/ | head -n 1)
    CURR_LAST_MOD_TIME=$(date -r $(echo /etc/letsencrypt/live/${SUBDOMAINS}.${URL}/${CURR_FILEPATH}) +%s)
    CURR_DELTA=$(expr $CURR_LAST_MOD_TIME - $INIT_TIME)
    if [ "$DELTA" -lt "$CURR_DELTA" ]; then
        echo "[$(date -u '+%Y-%m-%d %H:%M:%S')][DataJoint]: Renewal: Reloading NGINX since \`$CURR_FILEPATH\` changed."
        update_cert
        DELTA=$CURR_DELTA
    else
        sleep 5
    fi
done