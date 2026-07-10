variable "environment" {
  description = "The deployment environment (e.g., dev, stag, prod)"
  type        = string
}

variable "instance_type" {
  description = "The EC2 instance type to provision"
  type        = string
}

variable "key_name" {
  description = "The name of the SSH key pair"
  type        = string
}

variable "aws_region" {
  description = "AWS region where resources will be created"
  type        = string
  default     = "us-east-1"
}

variable "allowed_ssh_cidr_blocks" {
  description = "Allowed CIDR blocks for SSH access"
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

variable "allowed_vault_cidr_blocks" {
  description = "Allowed CIDR blocks for Vault access"
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

variable "allowed_backend_cidr_blocks" {
  description = "Allowed CIDR blocks for backend access"
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

variable "allowed_frontend_cidr_blocks" {
  description = "Allowed CIDR blocks for frontend access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
