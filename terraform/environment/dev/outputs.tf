output "instance_id" {
  description = "The ID of the EC2 instance"
  value       = module.ec2.instance_id
}

output "public_ip" {
  description = "The public IP of the EC2 instance"
  value       = module.ec2.public_ip
}

output "public_dns" {
  description = "The public DNS of the EC2 instance"
  value       = module.ec2.public_dns
}
