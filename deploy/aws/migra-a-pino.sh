#!/bin/bash
# One-off: turns the machine created as «frankino» into «pino», keeping everything it knows
# (cards, agenda, lists, journal, the Claude login). Run it once, from your own computer, after
# the rename has been pushed to GitHub:
#
#   AWS_PROFILE=<profile> deploy/aws/migra-a-pino.sh
#
# What it does:
#   1. copies the secrets from /frankino/ to /pino/ in SSM (FRANKINO_TOKEN becomes PINO_TOKEN);
#      the old ones stay where they are, delete them by hand once Pino answers;
#   2. lets the machine's role read /pino/ (the role and the backup bucket keep their old names:
#      nobody sees them, and renaming them would mean recreating them);
#   3. on the machine: new user, folders, database name, settings and services (migra-macchina.sh);
#   4. renames the machine to «pino» (its AWS name and its Tailscale name).
# Running it again does no harm: every step checks whether it has already been done.
set -euo pipefail

: "${AWS_PROFILE:?set AWS_PROFILE}"
export AWS_REGION="${AWS_REGION:-eu-west-1}"
OLD="${OLD_NAME:-frankino}"
NEW="${PINO_NAME:-pino}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

echo "› secrets /$OLD/ → /$NEW/"
aws ssm get-parameters-by-path --path "/$OLD/" --with-decryption --query 'Parameters[].Name' --output text \
  | tr '\t' '\n' | while read -r name; do
  [ -n "$name" ] || continue
  short="${name##*/}"
  short="${short/FRANKINO_/PINO_}"
  if aws ssm get-parameter --name "/$NEW/$short" >/dev/null 2>&1; then
    echo "  /$NEW/$short already there"
    continue
  fi
  value=$(aws ssm get-parameter --name "$name" --with-decryption --query Parameter.Value --output text)
  aws ssm put-parameter --name "/$NEW/$short" --type SecureString --value "$value" >/dev/null
  echo "  /$NEW/$short"
done

echo "› the machine's role may read /$NEW/"
aws iam put-role-policy --role-name "$OLD-server" --policy-name "$NEW-segreti" --policy-document "{
  \"Version\":\"2012-10-17\",
  \"Statement\":[
    {\"Effect\":\"Allow\",\"Action\":[\"ssm:GetParametersByPath\",\"ssm:GetParameters\",\"ssm:GetParameter\"],
     \"Resource\":\"arn:aws:ssm:$AWS_REGION:$ACCOUNT:parameter/$NEW/*\"},
    {\"Effect\":\"Allow\",\"Action\":\"ssm:GetParametersByPath\",
     \"Resource\":\"arn:aws:ssm:$AWS_REGION:$ACCOUNT:parameter/$NEW\"}
  ]
}"

ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$OLD,$NEW" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
[ "$ID" != "None" ] || { echo "no running machine called $OLD or $NEW"; exit 1; }
CURRENT=$(aws ec2 describe-tags --filters "Name=resource-id,Values=$ID" "Name=key,Values=Name" \
  --query 'Tags[0].Value' --output text)

echo "› on the machine ($ID)"
if [ "$CURRENT" = "$OLD" ]; then
  PINO_NAME="$OLD" "$HERE/remoto.sh" "if [ -d /opt/$OLD ]; then
      cd /opt/$OLD && sudo -u $OLD git remote set-url origin https://github.com/alessio-ragni/$NEW.git &&
      sudo -u $OLD git pull --ff-only && bash deploy/aws/migra-macchina.sh $OLD $NEW;
    else bash /opt/$NEW/deploy/aws/migra-macchina.sh $OLD $NEW; fi"
  aws ec2 create-tags --resources "$ID" --tags "Key=Name,Value=$NEW"
else
  PINO_NAME="$NEW" "$HERE/remoto.sh" "bash /opt/$NEW/deploy/aws/migra-macchina.sh $OLD $NEW"
fi

echo
echo "Done. On the tablet: uninstall the old app, install the new one, server $NEW:4390 and the same token."
echo "When Pino answers, the old secrets can go: aws ssm delete-parameters --names /$OLD/..."
