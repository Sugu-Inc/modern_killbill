# General Configuration
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
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

# VPC Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

# RDS Configuration
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "Initial allocated storage for RDS (GB)"
  type        = number
  default     = 100
}

variable "db_max_allocated_storage" {
  description = "Maximum allocated storage for RDS autoscaling (GB)"
  type        = number
  default     = 500
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "billing"
}

variable "db_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "billing_admin"
}

variable "db_password" {
  description = "PostgreSQL master password (use environment variable or secrets manager)"
  type        = string
  sensitive   = true
}

variable "db_multi_az" {
  description = "Enable Multi-AZ deployment for RDS"
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "Number of days to retain database backups"
  type        = number
  default     = 30
}

# ElastiCache Redis Configuration
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.medium"
}

variable "redis_num_cache_nodes" {
  description = "Number of cache nodes in the Redis cluster"
  type        = number
  default     = 2
}

variable "redis_snapshot_retention" {
  description = "Number of days to retain Redis snapshots"
  type        = number
  default     = 7
}

# ECS Configuration
variable "app_cpu" {
  description = "CPU units for ECS task (1 vCPU = 1024)"
  type        = string
  default     = "1024"
}

variable "app_memory" {
  description = "Memory for ECS task (MB)"
  type        = string
  default     = "2048"
}

variable "app_desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 2
}

variable "app_min_count" {
  description = "Minimum number of ECS tasks for autoscaling"
  type        = number
  default     = 2
}

variable "app_max_count" {
  description = "Maximum number of ECS tasks for autoscaling"
  type        = number
  default     = 10
}

variable "ecr_repository_url" {
  description = "ECR repository URL for Docker images"
  type        = string
}

variable "app_image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

# ALB Configuration
variable "acm_certificate_arn" {
  description = "ACM certificate ARN for HTTPS listener"
  type        = string
}

variable "alb_deletion_protection" {
  description = "Enable deletion protection for ALB"
  type        = bool
  default     = true
}

# CloudWatch Configuration
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}
