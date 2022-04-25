echo "Installing utilities..."
sudo yum -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
sudo yum install jq -y
sudo yum install python38 python38-devel python38-pip -y

cd ~/environment/workshop/
virtualenv venv -p $(which python3)
source ~/environment/workshop/venv/bin/activate
pip install botocore
pip install awscurl

echo "Defining environment variables for workshop procedures..."
export AWS_DEFAULT_REGION='us-east-1'
export CAS_STACK_NAME=$(aws cloudformation describe-stacks --region us-east-1  --query 'Stacks[?contains(StackName, `MieStack`)].StackName | [-1]' | tr -d '"' | awk -F '-MieStack-' '{print $1}')
export MIE_STACK_NAME=$(aws cloudformation describe-stacks --region us-east-1  --query 'Stacks[?contains(StackName, `MieStack`)].StackName | [-1]' | tr -d '"' | awk -F '-MieStack-.*-' '{print $1}')
export OPENSEARCH_STACK_NAME=$(aws cloudformation list-stacks --region us-east-1 --query 'StackSummaries[?starts_with(StackName,`'$CAS_STACK_NAME-Opensearch'`) && StackStatus==`CREATE_COMPLETE`].StackName' --output text)
export AUTH_STACK_NAME=$(aws cloudformation list-stacks --region us-east-1 --query 'StackSummaries[?starts_with(StackName,`'$CAS_STACK_NAME-Auth'`) && StackStatus==`CREATE_COMPLETE`].StackName' --output text)
export CAS_USERNAME=$(aws cloudformation describe-stacks --region us-east-1 --stack-name $AUTH_STACK_NAME --query 'Stacks[0].Parameters[?ParameterKey==`AdminEmail`].ParameterValue' --output text)
export C9_EC2_ID=`aws --region $AWS_DEFAULT_REGION ec2 describe-instances --region us-east-1 --filters Name=tag-key,Values='aws:cloud9:environment' Name=instance-state-name,Values='running' --query "Reservations[*].Instances[*].InstanceId" --output text`
aws --region $AWS_DEFAULT_REGION ec2 associate-iam-instance-profile --iam-instance-profile Name=AIM315WorkshopInstanceProfile --region us-east-1 --instance-id $C9_EC2_ID 2> /dev/null
export KIBANA_IP=$(aws --region $AWS_DEFAULT_REGION cloudformation list-exports --query "Exports[?Name==\`${OPENSEARCH_STACK_NAME}:KibanaIP\`].Value" --no-paginate --output text)
export CAS_URL=$(aws --region $AWS_DEFAULT_REGION cloudformation describe-stacks --stack-name $CAS_STACK_NAME  --no-paginate --output text --query 'Stacks[0].Outputs[?OutputKey==`ContentAnalyisSolution`].OutputValue')
# Initialize webapp password
export USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name $AUTH_STACK_NAME --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' --output text  --region us-east-1)
# Specify the OpenSearch endpoint for the vue sample app
export VUE_APP_OPENSEARCH_ENDPOINT="http://$KIBANA_IP" 
# Set dataplane variable
export DATAPLANE_API_ENDPOINT=$(aws --region $AWS_DEFAULT_REGION cloudformation list-exports --query "Exports[?Name==\`${MIE_STACK_NAME}:DataplaneApiEndpoint\`].Value" --no-paginate --output text)
export DATAPLANE_API_ARN=$(aws cloudformation list-exports --region $AWS_DEFAULT_REGION --query "Exports[?Name==\`${MIE_STACK_NAME}:DataPlaneHandlerArn\`].Value" --no-paginate --output text)
export DATAPLANE_API_NAME=$(echo $DATAPLANE_API_ARN | awk -F ":" '{print $NF}')
# Set workflow variable
export WORKFLOW_API_ENDPOINT=$(aws --region $AWS_DEFAULT_REGION cloudformation list-exports --query "Exports[?Name==\`${MIE_STACK_NAME}:WorkflowApiEndpoint\`].Value" --no-paginate --output text)
export WORKFLOW_API_NAME=$(aws --region $AWS_DEFAULT_REGION cloudformation list-exports --query "Exports[?Name==\`${MIE_STACK_NAME}:WorkflowApiHandlerName\`].Value" --no-paginate --output text)
# Set bucket variable
export DATAPLANE_BUCKET=$(aws --region $AWS_DEFAULT_REGION cloudformation list-exports --query "Exports[?Name==\`${MIE_STACK_NAME}:DataplaneBucket\`].Value" --no-paginate --output text)
# Set layer variable
export MIE_LAYER=$(aws --region $AWS_DEFAULT_REGION cloudformation list-exports --query "Exports[?Name==\`${MIE_STACK_NAME}:MediaInsightsEnginePython38Layer\`].Value" --no-paginate --output text)
# Set custom resource variable
export CUSTOM_RESOURCE=$(aws --region $AWS_DEFAULT_REGION cloudformation list-exports --query "Exports[?Name==\`${MIE_STACK_NAME}:WorkflowCustomResourceArn\`].Value" --no-paginate --output text)

# Apply patch to support AWS accounts with an AI opt-out policy. 
# See https://github.com/aws-solutions/media-insights-on-aws/pull/700
export MIE_OPERATOR_STACK_NAME=$(aws cloudformation list-stacks --region us-east-1 --query 'StackSummaries[?starts_with(StackName,`'$MIE_STACK_NAME-OperatorLibrary'`) && StackStatus==`CREATE_COMPLETE`].StackName' --output text)
FUNCTION_NAME=$(aws --region $AWS_DEFAULT_REGION cloudformation list-stack-resources --stack-name $MIE_OPERATOR_STACK_NAME  --no-paginate --output json --query 'StackResourceSummaries[?LogicalResourceId==`CheckTranscribeFunction`].PhysicalResourceId' --output text)
wget https://raw.githubusercontent.com/aws-solutions/media-insights-on-aws/9ad1711de00ae278dbf71b0e65d3dc52fa987852/source/operators/transcribe/get_transcribe.py
zip get_transcribe.zip get_transcribe.py
aws lambda update-function-code --function-name $FUNCTION_NAME --zip-file fileb://get_transcribe.zip --region us-east-1
FUNCTION_NAME=$(aws --region $AWS_DEFAULT_REGION cloudformation list-stack-resources --stack-name $MIE_OPERATOR_STACK_NAME  --no-paginate --output json --query 'StackResourceSummaries[?LogicalResourceId==`StartTranscribeFunction`].PhysicalResourceId' --output text)
wget https://raw.githubusercontent.com/aws-solutions/media-insights-on-aws/9ad1711de00ae278dbf71b0e65d3dc52fa987852/source/operators/transcribe/start_transcribe.py
zip start_transcribe.zip start_transcribe.py
aws lambda update-function-code --function-name $FUNCTION_NAME --zip-file fileb://start_transcribe.zip --region us-east-1


# Initialize the Kibana index pattern 
echo "Initializing an index pattern for Kibana..."
curl http://$KIBANA_IP/_plugin/kibana/api/saved_objects/index-pattern -X POST -H 'Content-Type: application/json' -H 'kbn-version: 7.10.2' -d '{"attributes":{"title":"*"}}'
echo ""
echo "-----------------------------------------"
sleep 2
echo ""
echo "Workshop application: "$CAS_URL
echo "Your username is: "$CAS_USERNAME
echo ""
echo "Please set a password for "$CAS_USERNAME
while true; do
  echo -n "New Password: " 
  read -s PASSWORD1
  echo
  echo -n "Verify Password: " 
  read -s PASSWORD2
  echo
  if [ "$PASSWORD1" = "$PASSWORD2" ] && [ "$PASSWORD1" != "" ]; then
    # Reset password in Cognito
    aws cognito-idp admin-set-user-password --user-pool-id $USER_POOL_ID --username ${CAS_USERNAME} --password ${PASSWORD1} --permanent --region us-east-1
     if [ $? -eq 0 ]; then break; fi
  fi
  echo "Please try again."
done

echo ""
echo "Your workshop environment is ready."
