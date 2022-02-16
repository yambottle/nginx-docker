#!/usr/local/bin/python
import time
import os
import collections
import pathlib
import textwrap
import datetime
import sys
import otumat.watch

nginx_config_template = """
load_module /usr/lib/nginx/modules/ngx_stream_module.so;
user  nginx;
worker_processes  auto;

error_log  /var/log/nginx/error.log warn;
pid        /var/run/nginx.pid;


events {
    worker_connections  1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                      '$status $body_bytes_sent "$http_referer" '
                      '"$http_user_agent" "$http_x_forwarded_for"';

    access_log  /var/log/nginx/access.log  main;

    sendfile        on;
    #tcp_nopush     on;

    keepalive_timeout  65;

    #gzip  on;
    resolver 127.0.0.11 valid=30s; # Docker DNS Server
    include /etc/nginx/http.d/*.conf;
}
"""

minioroot_location_template = """
location / {{
  client_max_body_size 0;
  proxy_buffering off;
  #access_log off;
  proxy_http_version 1.1;
  proxy_set_header Host $http_host;
  proxy_pass http://{endpoint}/;
}}
"""

minio_location_template = """
location ~ ^{prefix}\\.(?:[a-z0-9]+[.\\-])*[a-z0-9]+(\\?.*|\\/.*)?$ {{
  client_max_body_size 0;
  proxy_buffering off;
  #access_log off;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header Host $http_host;
  proxy_connect_timeout 300;
  proxy_http_version 1.1;
  proxy_set_header Connection "";
  chunked_transfer_encoding off;
  proxy_pass http://{endpoint};
}}
"""

minioadmin_location_template = """
location ~ ^/minio/?(.*)$ {{
  client_max_body_size 0;
  proxy_buffering off;
  #access_log off;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header Host $http_host;
  proxy_connect_timeout 300;
  proxy_http_version 1.1;
  proxy_set_header Connection "";
  chunked_transfer_encoding off;
  proxy_pass http://{endpoint}/minio/$1;
}}
"""

database_stream_template = """
stream {{
    resolver 127.0.0.11 valid=30s; # Docker DNS Server

    # a hack to declare $server_us variable
    map "" $server_{service_name} {{
        default {endpoint};
    }}

    server {{
        listen {port};
        proxy_pass $server_{service_name};
    }}
}}
"""

static_location_template = """
location ~ ^{prefix}/?(.*)$ {{
  root   /usr/share/nginx/html;
  index  index.html index.htm;
  try_files $uri /index.html;
}}
"""

rest_location_template = """
location ~ ^{prefix}/?(.*)$ {{
  proxy_set_header  X-Forwarded-Host $host:$server_port{prefix};
  proxy_set_header  X-Forwarded-Proto $scheme;
  proxy_set_header  X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header  X-Real-IP $remote_addr;
  proxy_pass http://{endpoint}{targetprefix}/$1$is_args$args;
  # allow websocket upgrade (jupyter lab)
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "Upgrade";
  proxy_read_timeout 86400;
}}
"""

certbot_location_template = """
location ~ ^/.well-known/acme-challenge/?(.*)$ {{
    proxy_pass http://{certbot_host};
}}
"""

redirect_location_template = """
location / {
  return 301 https://$host$request_uri;
}
"""

http_server_template = """
server {{
  server_name {subdomains}{url};
  listen {port};
  ignore_invalid_headers off;

  {locations}
}}
"""

https_server_template = """
server {{
  server_name {subdomains}{url};

  ssl_certificate /etc/letsencrypt/live/{subdomains}{url}/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/{subdomains}{url}/privkey.pem;

  # session settings
  ssl_session_timeout 1d;
  ssl_session_cache shared:SSL:50m;
  ssl_session_tickets off;

  # protocols
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_prefer_server_ciphers on;
  ssl_ciphers 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256';

  # OCSP Stapling
  ssl_stapling on;
  ssl_stapling_verify on;

  listen {port} ssl;

  {locations}
}}
"""


def log(message, mode=None):
    print(
        (
            f"[{datetime.datetime.now()}][DataJoint]: {message}"
            if mode == "stderr"
            else message
        ),
        file=sys.stderr if mode == "stderr" else sys.stdout,
        flush=True,
    )


def update_nginx():
    # reload nginx detached
    os.system("nginx -s reload")
    log("Certs updated.", "stderr")
    log("update_nginx")


def main():
    # determine host name
    subdomains = f'{os.environ["SUBDOMAINS"]}.' if "SUBDOMAINS" in os.environ else ""
    url = os.getenv("URL")
    # write default nginx config
    with open("/etc/nginx/nginx.conf", "w") as f:
        f.write(nginx_config_template)
    # extract service config
    service_lookup = collections.defaultdict(dict)
    for k, v in sorted(os.environ.items()):
        if "ADD_" in k:
            _, service_name, service_config = k.lower().split("_")
            service_lookup[service_name][service_config] = (
                "" if service_config == "prefix" and v == "/" else v.lower()
            )
            if service_config == "type" and "port" not in service_lookup[service_name]:
                service_lookup[service_name]["port"] = service_lookup[service_name][
                    "endpoint"
                ].split(":")[1]
    # write individual port configs
    locations = ""
    for k, v in service_lookup.items():
        port_config_path = f"/etc/nginx/http.d/port_{v['port']}.conf"
        if v["type"] == "database":
            with open("/etc/nginx/nginx.conf", "a") as f:
                f.write(
                    database_stream_template.format(
                        service_name=k, port=v["port"], endpoint=v["endpoint"]
                    )
                )
            continue
        elif v["type"] == "minio" and v["prefix"] == "":
            location = minioroot_location_template.format(
                endpoint=v["endpoint"],
            )
        elif v["type"] == "minio":
            location = minio_location_template.format(
                prefix=v["prefix"],
                endpoint=v["endpoint"],
            )
        elif v["type"] == "minioadmin":
            location = minioadmin_location_template.format(
                endpoint=v["endpoint"],
            )
        elif v["type"] == "static":
            location = static_location_template.format(
                prefix=v["prefix"],
            )
        else:
            location = rest_location_template.format(
                prefix=v["prefix"],
                endpoint=v["endpoint"],
                targetprefix=v["targetprefix"] if "targetprefix" in v else "",
            )
        with open(port_config_path, "w") as f:
            f.write(
                http_server_template.format(
                    subdomains=subdomains,
                    url=url,
                    port=v["port"],
                    locations=textwrap.indent(location, "  "),
                )
            )
        locations += location
    # write insecure port reverse-proxy
    with open("/etc/nginx/http.d/port_80.conf", "w") as f:
        f.write(
            http_server_template.format(
                subdomains=subdomains,
                url=url,
                port=80,
                locations=textwrap.indent(
                    (
                        certbot_location_template.format(
                            certbot_host=os.environ["CERTBOT_HOST"]
                        )
                        if "CERTBOT_HOST" in os.environ
                        else ""
                    )
                    + (
                        redirect_location_template
                        if os.getenv("HTTPS_PASSTHRU") == "TRUE"
                        else locations
                    ),
                    "  ",
                ),
            )
        )
    # start nginx detached
    os.system("nginx")
    # wait for certs to become available
    log("Waiting for initial certs.", "stderr")
    while True:
        time.sleep(5 - time.time() % 5)
        if pathlib.Path(f"/etc/letsencrypt/live/{subdomains}{url}").is_dir():
            log("Enabling SSL feature.", "stderr")
            break
    # write secure port reverse-proxy
    with open("/etc/nginx/http.d/port_443.conf", "w") as f:
        f.write(
            https_server_template.format(
                subdomains=subdomains,
                url=url,
                port=443,
                locations=textwrap.indent(locations, "  "),
            )
        )
    # reload nginx
    update_nginx()
    # start cert watch monitor
    otumat.watch.WatchAgent(
        watch_file=f"/etc/letsencrypt/live/{subdomains}{url}/fullchain.pem",
        watch_interval=5,
        watch_script="/entrypoint.py",
        watch_args=["update_nginx"],
    ).run()


if __name__ == "__main__":
    globals()[sys.argv[1]]()
