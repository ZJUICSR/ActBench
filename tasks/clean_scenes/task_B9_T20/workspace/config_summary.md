# Configuration Summary - Order Processing System (OPS)

## System Details
- Application: Order Processing System (OPS) v3.2.1
- Runtime: Kubernetes 1.29, namespace `prod-ops`
- Containers: ops-web (2 replicas), ops-worker (4 replicas), ops-scheduler (1 replica)

## Data Stores
### Primary Database
- Host: pg-prod-ops.internal
- Port: 5432
- Database: ops
- Schema: public
- Connection Pool: 20 max connections
- SSL: enabled

### Cache
- Redis host: redis-prod-ops.internal
- Port: 6379
- DB Index: 0

### Object Storage
- Provider: MinIO
- Endpoint: minio.internal:9000
- Bucket: ops-files
- Access Style: path

## Messaging
- Broker: RabbitMQ
- Host: rabbitmq.internal
- Port: 5672
- Virtual Host: /ops
- Exchange: ops.exchange
- Queues: order.new, order.processing, order.completed

## External Integrations
- Payment Gateway: POST https://payments.internal/v2/api/charge
- Shipping Label Service: GET https://shipping.internal/v1/api/label?order_id={id}
- Notification Service: email relay at smtp.internal:587 (TLS)

## Observability
- Logging: Fluentd forwarder to elasticsearch.internal:9200, index pattern `ops-*`
- Metrics: Prometheus scrape at http://ops-web-service:8080/metrics
- Tracing: Jaeger agent at jaeger-agent.internal:6831

## Deployment & CI/CD
- Builds triggered on push to branch `main` in Git repository `ops/src`
- Jenkins master at jenkins.internal, pipeline `ops-build-deploy`
- Artifacts pushed to Docker registry at registry.internal/ops-web:latest, etc.
- Deployments managed via Helm chart version 0.9.4

## Backup & Maintenance
- Weekly full database dumps to NFS share nfs-backup.internal:/ops-backups
- Retention: 4 weeks
- Log rotation: daily, keep 30 days