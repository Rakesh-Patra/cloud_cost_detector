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
