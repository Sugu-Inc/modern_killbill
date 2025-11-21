# General Configuration
variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region to deploy resources"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (e.g., production, staging, development)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "billing-platform"
}

# Network Configuration
variable "subnet_cidr" {
  description = "CIDR block for subnet"
  type        = string
  default     = "10.0.0.0/24"
}

variable "connector_cidr_range" {
  description = "CIDR range for VPC Access Connector"
  type        = string
  default     = "10.8.0.0/28"
}

# Cloud SQL Configuration
variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-custom-2-7680" # 2 vCPU, 7.68 GB RAM
}

variable "db_availability_type" {
  description = "Availability type (ZONAL or REGIONAL for HA)"
  type        = string
  default     = "REGIONAL"
}

variable "db_disk_size" {
  description = "Initial disk size for Cloud SQL (GB)"
  type        = number
  default     = 100
}

variable "db_max_disk_size" {
  description = "Maximum disk size for Cloud SQL autoscaling (GB)"
  type        = number
  default     = 500
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "billing"
}

variable "db_username" {
  description = "PostgreSQL username"
  type        = string
  default     = "billing_admin"
}

variable "db_password" {
  description = "PostgreSQL password (use environment variable)"
  type        = string
  sensitive   = true
}

variable "db_backup_retention_days" {
  description = "Number of days to retain database backups"
  type        = number
  default     = 30
}

variable "db_deletion_protection" {
  description = "Enable deletion protection for Cloud SQL"
  type        = bool
  default     = true
}

# Memorystore Redis Configuration
variable "redis_tier" {
  description = "Memorystore Redis tier (BASIC or STANDARD_HA)"
  type        = string
  default     = "STANDARD_HA"
}

variable "redis_memory_gb" {
  description = "Redis memory size in GB"
  type        = number
  default     = 4
}

# Cloud Run Configuration
variable "cloud_run_cpu" {
  description = "CPU limit for Cloud Run (e.g., '2' for 2 vCPU)"
  type        = string
  default     = "2"
}

variable "cloud_run_memory" {
  description = "Memory limit for Cloud Run (e.g., '2Gi')"
  type        = string
  default     = "2Gi"
}

variable "cloud_run_min_instances" {
  description = "Minimum number of Cloud Run instances"
  type        = string
  default     = "2"
}

variable "cloud_run_max_instances" {
  description = "Maximum number of Cloud Run instances"
  type        = string
  default     = "10"
}

variable "cloud_run_max_concurrency" {
  description = "Maximum concurrent requests per instance"
  type        = number
  default     = 80
}

# Container Registry Configuration
variable "artifact_registry_repo" {
  description = "Artifact Registry repository URL"
  type        = string
}

variable "app_image" {
  description = "Docker image name"
  type        = string
  default     = "billing-platform"
}

variable "app_image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

# Domain Configuration
variable "domain_name" {
  description = "Domain name for the application (for SSL certificate)"
  type        = string
}
