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
