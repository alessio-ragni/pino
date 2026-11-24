#!/bin/bash
# Creates on AWS everything Pino needs: a small machine with no open ports, the role that
# reads the secrets, the backup bucket. Run it once, from your own computer:
#
#   AWS_PROFILE=<profile> deploy/aws/crea.sh
#
# Put the secrets in SSM first (see docs/deployment.md). Running it again duplicates nothing:
# if the machine already exists it stops.
set -euo pipefail

: "${AWS_PROFILE:?set AWS_PROFILE}"
export AWS_REGION="${AWS_REGION:-eu-west-1}"
NAME="${PINO_NAME:-pino}"
TYPE="${PINO_INSTANCE_TYPE:-t4g.small}"
REPO="${PINO_REPO:-https://github.com/alessio-ragni/pino.git}"
PARAMS="/$NAME/"
HERE="$(cd "$(dirname "$0")" && pwd)"

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="$NAME-backup-$ACCOUNT-$AWS_REGION"

existing=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' --output text)
if [ -n "$existing" ]; then
  echo "The machine $NAME already exists: $existing"
  exit 0
fi

echo "› backup bucket: $BUCKET"
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  aws s3api create-bucket --bucket "$BUCKET" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

echo "› machine role"
ROLE="$NAME-server"
if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]
  }' >/dev/null
  aws iam attach-role-policy --role-name "$ROLE" \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws iam create-instance-profile --instance-profile-name "$ROLE" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
fi
aws iam put-role-policy --role-name "$ROLE" --policy-name "$NAME-segreti-e-backup" --policy-document "{
  \"Version\":\"2012-10-17\",
  \"Statement\":[
    {\"Effect\":\"Allow\",\"Action\":[\"ssm:GetParametersByPath\",\"ssm:GetParameters\",\"ssm:GetParameter\"],
     \"Resource\":\"arn:aws:ssm:$AWS_REGION:$ACCOUNT:parameter/$NAME/*\"},
    {\"Effect\":\"Allow\",\"Action\":\"ssm:GetParametersByPath\",
     \"Resource\":\"arn:aws:ssm:$AWS_REGION:$ACCOUNT:parameter/$NAME\"},
    {\"Effect\":\"Allow\",\"Action\":\"s3:PutObject\",\"Resource\":\"arn:aws:s3:::$BUCKET/*\"}
  ]
}"

echo "› security group with no open ports"
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" "Name=vpc-id,Values=$VPC" \
  --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG" = "None" ]; then
  SG=$(aws ec2 create-security-group --group-name "$NAME" --vpc-id "$VPC" \
    --description "Pino: no inbound, reachable only through Tailscale" --query GroupId --output text)
fi

AMI=$(aws ssm get-parameter \
  --name /aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id \
  --query Parameter.Value --output text)

USERDATA=$(mktemp)
sed -e "s|__REPO__|$REPO|" -e "s|__BUCKET__|$BUCKET|" -e "s|__PARAMS__|$PARAMS|" \
  "$HERE/user-data.sh" >"$USERDATA"

echo "› machine $TYPE ($AMI)"
# A freshly created instance profile takes a few seconds to become visible to EC2.
for i in 1 2 3 4 5 6; do
  if ID=$(aws ec2 run-instances --image-id "$AMI" --instance-type "$TYPE" \
    --iam-instance-profile Name="$ROLE" --security-group-ids "$SG" \
    --metadata-options HttpTokens=required,HttpEndpoint=enabled \
    --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3","Encrypted":true}}]' \
    --user-data "file://$USERDATA" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
    --query 'Instances[0].InstanceId' --output text 2>/dev/null); then
    break
  fi
  sleep 10
done
rm -f "$USERDATA"
[ -n "${ID:-}" ] || { echo "could not create the machine"; exit 1; }
echo "Created: $ID. Ready in about 5 minutes: then join it to Tailscale (docs/deployment.md)"
