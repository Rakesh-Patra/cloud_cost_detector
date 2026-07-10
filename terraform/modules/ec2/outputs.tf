output "instance_id" {
  description = "The ID of the EC2 instance"
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "The public IP of the EC2 instance"
  value       = aws_instance.app.public_ip
}

output "public_dns" {
  description = "The public DNS of the EC2 instance"
  value       = aws_instance.app.public_dns
}

output "security_group_id" {
  description = "The ID of the EC2 security group"
  value       = aws_security_group.ec2.id
}

