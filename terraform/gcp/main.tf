# Modern Subscription Billing Platform - GCP Production Infrastructure
#
# Deploys:
# - Cloud SQL PostgreSQL 15 with encryption
# - Memorystore Redis 7 for caching/sessions
# - Cloud Run for containerized API
# - Cloud Load Balancer
# - Cloud Logging and Monitoring
# - Secret Manager for sensitive data
# - Cloud KMS for encryption keys
#
# Prerequisites:
# - gcloud CLI configured
# - Terraform 1.5+
# - Cloud DNS managed zone (for domain)

terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # Configure GCS backend for state storage
  backend "gcs" {
    bucket = "billing-platform-terraform-state"
    prefix = "production/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudkms.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudbuild.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}

# VPC Network
resource "google_compute_network" "vpc" {
  name                    = "${var.project_name}-vpc-${var.environment}"
  auto_create_subnetworks = false

  depends_on = [google_project_service.required_apis]
}

# Subnet
resource "google_compute_subnetwork" "subnet" {
  name          = "${var.project_name}-subnet-${var.environment}"
  ip_cidr_range = var.subnet_cidr
  region        = var.region
  network       = google_compute_network.vpc.id

  private_ip_google_access = true
}

# Cloud NAT for private instances
resource "google_compute_router" "router" {
  name    = "${var.project_name}-router-${var.environment}"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name   = "${var.project_name}-nat-${var.environment}"
  router = google_compute_router.router.name
  region = var.region

  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# Firewall Rules
resource "google_compute_firewall" "allow_internal" {
  name    = "${var.project_name}-allow-internal-${var.environment}"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = [var.subnet_cidr]
}

resource "google_compute_firewall" "allow_lb_health_check" {
  name    = "${var.project_name}-allow-lb-health-check-${var.environment}"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  # Google Cloud Load Balancer health check ranges
  source_ranges = ["35.191.0.0/16", "130.211.0.0/22"]
  target_tags   = ["cloud-run"]
}

# KMS Key Ring
resource "google_kms_key_ring" "main" {
  name     = "${var.project_name}-keyring-${var.environment}"
  location = var.region

  depends_on = [google_project_service.required_apis]
}

# KMS Crypto Key for encryption
resource "google_kms_crypto_key" "main" {
  name     = "${var.project_name}-key-${var.environment}"
  key_ring = google_kms_key_ring.main.id

  rotation_period = "7776000s" # 90 days

  lifecycle {
    prevent_destroy = true
  }
}

# Cloud SQL PostgreSQL 15
resource "google_sql_database_instance" "postgres" {
  name             = "${var.project_name}-db-${var.environment}"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier              = var.db_tier
    availability_type = var.db_availability_type
    disk_type         = "PD_SSD"
    disk_size         = var.db_disk_size
    disk_autoresize       = true
    disk_autoresize_limit = var.db_max_disk_size

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = var.db_backup_retention_days
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      require_ssl     = true
    }

    database_flags {
      name  = "log_checkpoints"
      value = "on"
    }

    database_flags {
      name  = "log_connections"
      value = "on"
    }

    database_flags {
      name  = "log_disconnections"
      value = "on"
    }

    database_flags {
      name  = "log_lock_waits"
      value = "on"
    }

    insights_config {
      query_insights_enabled  = true
      query_plans_per_minute  = 5
      query_string_length     = 1024
      record_application_tags = true
    }

    maintenance_window {
      day  = 1 # Monday
      hour = 4
    }
  }

  deletion_protection = var.db_deletion_protection

  # Encryption at rest (default in GCP)
  encryption_key_name = google_kms_crypto_key.main.id

  depends_on = [
    google_project_service.required_apis,
    google_compute_network.vpc
  ]
}

resource "google_sql_database" "database" {
  name     = var.db_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "user" {
  name     = var.db_username
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}

# Memorystore Redis 7
resource "google_redis_instance" "redis" {
  name           = "${var.project_name}-redis-${var.environment}"
  tier           = var.redis_tier
  memory_size_gb = var.redis_memory_gb
  region         = var.region

  redis_version = "REDIS_7_0"

  # Network
  authorized_network = google_compute_network.vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  # Security
  auth_enabled       = true
  transit_encryption_mode = "SERVER_AUTHENTICATION"

  # Persistence
  persistence_config {
    persistence_mode    = "RDB"
    rdb_snapshot_period = "ONE_HOUR"
  }

  # Maintenance
  maintenance_policy {
    weekly_maintenance_window {
      day = "MONDAY"
      start_time {
        hours   = 5
        minutes = 0
      }
    }
  }

  depends_on = [google_project_service.required_apis]
}

# Secret Manager Secrets
resource "google_secret_manager_secret" "db_password" {
  secret_id = "${var.project_name}-db-password-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

resource "google_secret_manager_secret" "stripe_api_key" {
  secret_id = "${var.project_name}-stripe-api-key-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret" "jwt_secret" {
  secret_id = "${var.project_name}-jwt-secret-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

# Service Account for Cloud Run
resource "google_service_account" "cloud_run" {
  account_id   = "${var.project_name}-run-${var.environment}"
  display_name = "Cloud Run Service Account for ${var.project_name}"
}

# IAM permissions for Cloud Run service account
resource "google_project_iam_member" "cloud_run_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret_iam_member" "cloud_run_db_password" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret_iam_member" "cloud_run_stripe_key" {
  secret_id = google_secret_manager_secret.stripe_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret_iam_member" "cloud_run_jwt_secret" {
  secret_id = google_secret_manager_secret.jwt_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Cloud Run Service
resource "google_cloud_run_service" "app" {
  name     = "${var.project_name}-app-${var.environment}"
  location = var.region

  template {
    spec {
      service_account_name = google_service_account.cloud_run.email

      containers {
        image = "${var.artifact_registry_repo}/${var.app_image}:${var.app_image_tag}"

        ports {
          container_port = 8000
        }

        env {
          name  = "APP_ENV"
          value = var.environment
        }

        env {
          name  = "DATABASE_HOST"
          value = google_sql_database_instance.postgres.private_ip_address
        }

        env {
          name  = "DATABASE_PORT"
          value = "5432"
        }

        env {
          name  = "DATABASE_NAME"
          value = var.db_name
        }

        env {
          name  = "DATABASE_USER"
          value = var.db_username
        }

        env {
          name = "DATABASE_PASSWORD"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.db_password.secret_id
              key  = "latest"
            }
          }
        }

        env {
          name  = "REDIS_HOST"
          value = google_redis_instance.redis.host
        }

        env {
          name  = "REDIS_PORT"
          value = google_redis_instance.redis.port
        }

        env {
          name = "STRIPE_API_KEY"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.stripe_api_key.secret_id
              key  = "latest"
            }
          }
        }

        env {
          name = "JWT_SECRET_KEY"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.jwt_secret.secret_id
              key  = "latest"
            }
          }
        }

        resources {
          limits = {
            cpu    = var.cloud_run_cpu
            memory = var.cloud_run_memory
          }
        }

        startup_probe {
          http_get {
            path = "/health"
            port = 8000
          }
          initial_delay_seconds = 10
          timeout_seconds       = 5
          period_seconds        = 10
          failure_threshold     = 3
        }

        liveness_probe {
          http_get {
            path = "/health"
            port = 8000
          }
          initial_delay_seconds = 30
          timeout_seconds       = 5
          period_seconds        = 30
          failure_threshold     = 3
        }
      }

      container_concurrency = var.cloud_run_max_concurrency

      # Auto-scaling
      timeout_seconds = 300
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale" = var.cloud_run_min_instances
        "autoscaling.knative.dev/maxScale" = var.cloud_run_max_instances
        "run.googleapis.com/vpc-access-connector" = google_vpc_access_connector.connector.id
        "run.googleapis.com/vpc-access-egress"    = "all-traffic"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  autogenerate_revision_name = true

  depends_on = [
    google_project_service.required_apis,
    google_sql_database_instance.postgres,
    google_redis_instance.redis
  ]
}

# VPC Access Connector for Cloud Run
resource "google_vpc_access_connector" "connector" {
  name          = "${var.project_name}-connector-${var.environment}"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = var.connector_cidr_range
  min_instances = 2
  max_instances = 10

  depends_on = [google_project_service.required_apis]
}

# Allow unauthenticated access to Cloud Run (behind Load Balancer)
resource "google_cloud_run_service_iam_member" "public_access" {
  service  = google_cloud_run_service.app.name
  location = google_cloud_run_service.app.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Cloud Load Balancer
resource "google_compute_global_address" "lb_ip" {
  name = "${var.project_name}-lb-ip-${var.environment}"
}

resource "google_compute_managed_ssl_certificate" "lb_cert" {
  name = "${var.project_name}-lb-cert-${var.environment}"

  managed {
    domains = [var.domain_name]
  }
}

resource "google_compute_backend_service" "backend" {
  name                  = "${var.project_name}-backend-${var.environment}"
  protocol              = "HTTP"
  port_name             = "http"
  timeout_sec           = 30
  enable_cdn            = false
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.cloud_run_neg.id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

resource "google_compute_region_network_endpoint_group" "cloud_run_neg" {
  name                  = "${var.project_name}-neg-${var.environment}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = google_cloud_run_service.app.name
  }
}

resource "google_compute_url_map" "lb" {
  name            = "${var.project_name}-lb-${var.environment}"
  default_service = google_compute_backend_service.backend.id
}

resource "google_compute_target_https_proxy" "lb_proxy" {
  name             = "${var.project_name}-lb-proxy-${var.environment}"
  url_map          = google_compute_url_map.lb.id
  ssl_certificates = [google_compute_managed_ssl_certificate.lb_cert.id]
}

resource "google_compute_global_forwarding_rule" "lb_forwarding_rule" {
  name                  = "${var.project_name}-lb-rule-${var.environment}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "443"
  target                = google_compute_target_https_proxy.lb_proxy.id
  ip_address            = google_compute_global_address.lb_ip.id
}

# HTTP to HTTPS redirect
resource "google_compute_url_map" "https_redirect" {
  name = "${var.project_name}-https-redirect-${var.environment}"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "https_redirect" {
  name    = "${var.project_name}-http-proxy-${var.environment}"
  url_map = google_compute_url_map.https_redirect.id
}

resource "google_compute_global_forwarding_rule" "https_redirect" {
  name                  = "${var.project_name}-http-rule-${var.environment}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "80"
  target                = google_compute_target_http_proxy.https_redirect.id
  ip_address            = google_compute_global_address.lb_ip.id
}

# Cloud Monitoring Alerts
resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "${var.project_name} High Error Rate - ${var.environment}"
  combiner     = "OR"

  conditions {
    display_name = "High 5xx error rate"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${google_cloud_run_service.app.name}\" AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 10

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = []
}

resource "google_monitoring_alert_policy" "high_latency" {
  display_name = "${var.project_name} High Latency - ${var.environment}"
  combiner     = "OR"

  conditions {
    display_name = "High request latency"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${google_cloud_run_service.app.name}\" AND metric.type = \"run.googleapis.com/request_latencies\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 1000 # 1 second

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_PERCENTILE_95"
      }
    }
  }

  notification_channels = []
}

resource "google_monitoring_alert_policy" "db_cpu_high" {
  display_name = "${var.project_name} Database CPU High - ${var.environment}"
  combiner     = "OR"

  conditions {
    display_name = "High database CPU utilization"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND resource.labels.database_id = \"${var.project_id}:${google_sql_database_instance.postgres.name}\" AND metric.type = \"cloudsql.googleapis.com/database/cpu/utilization\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8 # 80%

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = []
}

# Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = google_compute_network.vpc.id
}

output "db_connection_name" {
  description = "Cloud SQL connection name"
  value       = google_sql_database_instance.postgres.connection_name
}

output "db_private_ip" {
  description = "Cloud SQL private IP address"
  value       = google_sql_database_instance.postgres.private_ip_address
}

output "redis_host" {
  description = "Memorystore Redis host"
  value       = google_redis_instance.redis.host
}

output "redis_port" {
  description = "Memorystore Redis port"
  value       = google_redis_instance.redis.port
}

output "lb_ip_address" {
  description = "Load Balancer IP address"
  value       = google_compute_global_address.lb_ip.address
}

output "cloud_run_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_service.app.status[0].url
}

output "kms_key_id" {
  description = "KMS crypto key ID"
  value       = google_kms_crypto_key.main.id
}
