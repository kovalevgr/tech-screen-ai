variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Default GCP region for regional resources"
  type        = string
  default     = "europe-west1"
}
