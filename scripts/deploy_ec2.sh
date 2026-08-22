#!/usr/bin/env bash
# ─── Deploy Cloud Cost App to EC2 ──────────────────────────────────────────────
set -euo pipefail

ENV="${1:-dev}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "============================================================"
echo "🚀 Provisioning EC2 Infrastructure via Terraform (${ENV})..."
echo "============================================================"

cd "terraform/environment/${ENV}"
terraform init
terraform apply -auto-approve

PUBLIC_IP=$(terraform output -raw public_ip)
echo "✅ EC2 Instance Provisioned: Public IP = ${PUBLIC_IP}"

cd "../../../"

echo "============================================================"
echo "📦 Deploying Application via Ansible to EC2 (${PUBLIC_IP})..."
echo "============================================================"

ansible-playbook ansible/playbooks/deploy.yml \
  -i "${PUBLIC_IP}," \
  -u ubuntu \
  --private-key terraform/terrakey \
  -e "docker_repo=rakesh-patra/cloud_cost_detector image_tag=latest"

echo "============================================================"
echo "🎉 Deployment Complete!"
echo "Backend:  http://${PUBLIC_IP}:8000/docs"
echo "Frontend: http://${PUBLIC_IP}:5173"
echo "============================================================"
