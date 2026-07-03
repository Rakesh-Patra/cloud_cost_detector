data "aws_ami" "ubuntu" {
  owners      = ["099720109477"]
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/*amd64*"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

module "ec2" {
  source = "../../modules/ec2"

  environment   = var.environment
  instance_type = var.instance_type
  ami           = data.aws_ami.ubuntu.id
  key_name      = var.key_name
}
