# Cert Renewal

> This should be managed by a CICD pipeline

- Find the renewal instance
- DNS points fakeservices record to it
- Remove old key directory
- Run docker-compose
- Copy key over
- Remove DNS record
