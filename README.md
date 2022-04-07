# WebDevCon 2022 workshop
## Media Insights Engine: A Back-End Solution For Video Processing on AWS

Event page:

[http://webdevcon.amazon.com/wdc/wdc2022/spring/#schedule](http://webdevcon.amazon.com/wdc/wdc2022/spring/#schedule)

Workshop procedure:

[https://catalog.us-east-1.prod.workshops.aws/workshops/5a06b78f-4be9-4420-bd3c-fb3ecafaf4a7/en-US/](https://catalog.us-east-1.prod.workshops.aws/workshops/5a06b78f-4be9-4420-bd3c-fb3ecafaf4a7/en-US/)

### Abstract 

Have you ever thought about what it would take to build a searchable video catalog like YouTube? There is a lot that goes on behind-the-scenes to make videos searchable. In this workshop you'll automate video content analysis with AWS services for computer vision and natural language processing. You'll configure data pipelines to load video content data into AI-enhanced databases that support intelligent full-text search.

At the end of this workshop you will be familiar with AWS AI/ML technologies applicable for video search. You will also be equipped with the knowledge to build your own multimedia workflows using the AWS Media Insights Engine solution.

### Deploy

Run the following commands to deploy the workshop:
```
git clone https://github.com/ianwow/webdevcon_workshop
export MY_WORKSHOP_BUCKET=...
aws s3 mb $MY_WORKSHOP_BUCKET
aws s3 cp cloudformation/aws-content-analysis.template s3://$MY_WORKSHOP_BUCKET/webdevcon/

export TEMPLATE=https://rodeolabz-us-east-1.s3.amazonaws.com/aws-content-analysis/2.0.5-webcondev/aws-content-analysis.template
export TEMPLATE=https://$MY_WORKSHOP_BUCKET.s3.amazonaws.com/webdevcon/aws-content-analysis.template
aws cloudformation create-stack --stack-name webdevcon2 --template-url $TEMPLATE --region us-east-1 --parameters ParameterKey=AdminEmail,ParameterValue=admin@example.com ParameterKey=SetupCloud9ForEventEngine,ParameterValue=false --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND --disable-rollback --profile default
```
