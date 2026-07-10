variable "environment" {
  description = "The deployment environment (e.g., dev, stag, prod)"
  type        = string
}

variable "instance_type" {
  description = "The EC2 instance type to provision"
  type        = string
  default     = "t3.micro"
}

variable "ami" {
  description = "The AMI ID to use for the EC2 instance"
  type        = string
}

variable "key_name" {
  description = "The name of the SSH key pair to attach to the EC2 instance"
  type        = string
}

variable "project_name" {
  description = "The name of the project"
  type        = string
  default     = "cloud-cost-detector"
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
