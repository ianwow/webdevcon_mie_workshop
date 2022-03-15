# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

###############################################################################
# PURPOSE:
#   JSON datasets can be precomputed and uploaded along with their associated
#   media files to MIE. This lambda function is an operator that puts that
#   precomputed data into DynamoDB. Don't forget to extend the Elasticsearch
#   consumer (source/consumers/elastic/lambda_handler.py) if you want said data
#   to be added to Elasticsearch so it can be searched and rendered on the MIE
#   front-end.
#
# USAGE:
#   Users must use operator configuration parameters "Bucket" and "Key" to
#   the S3 location of the data file.
#
#   To run this operator add
#   '"GenericDataLookup":{"Bucket": "myBucket", "Key":"test-media/My Video.json", "Enabled":true}'
#   to the workflow configuration, like this:
#
#   curl -k -X POST -H "Authorization: $MIE_ACCESS_TOKEN" -H "Content-Type: application/json" --data '{"Name":"MieCompleteWorkflow","Configuration":{"defaultVideoStage":{"GenericDataLookup":{"Bucket": "myBucket", "Key":"test-media/My Video.json","Enabled":true}}},"Input":{"Media":{"Video":{"S3Bucket":"'$DATAPLANE_BUCKET'","S3Key":"My Video.mp4"}}}}'  $WORKFLOW_API_ENDPOINT/workflow/execution
#
#  For instructions on getting $MIE_ACCESS_TOKEN, see:
#  https://github.com/awslabs/aws-media-insights-engine/blob/master/IMPLEMENTATION_GUIDE.md#step-6-test-your-operator

#
###############################################################################

import json
import boto3
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all
from MediaInsightsEngineLambdaHelper import MediaInsightsOperationHelper
from MediaInsightsEngineLambdaHelper import MasExecutionError
from MediaInsightsEngineLambdaHelper import DataPlane

patch_all()

# Lambda function entrypoint:
def lambda_handler(event, context):
    print("We got the following event:\n", event)
    operator_object = MediaInsightsOperationHelper(event)
    # Get operator parameters
    try:
        workflow_id = str(event["WorkflowExecutionId"])
        asset_id = event['AssetId']
        if "Video" in operator_object.input["Media"]:
            bucket = operator_object.input["Media"]["Video"]["S3Bucket"]
            key = operator_object.input["Media"]["Video"]["S3Key"]
    except Exception:
        operator_object.update_workflow_status("Error")
        operator_object.add_workflow_metadata(GenericDataLookupError="No valid inputs")
        raise MasExecutionError(operator_object.return_output_object())

    # Generate metadata
    print("Generating metadata for s3://"+bucket+"/"+key)

    try:        
        metadata_json = generate_metadata(bucket, key)
    except Exception as e:
        operator_object.update_workflow_status("Error")
        operator_object.add_workflow_metadata(GenericDataLookupError="Error generating metadata. " + str(e))
        raise MasExecutionError(operator_object.return_output_object())

    # Verify that the metadata is a dict, as required by the dataplane
    if (type(metadata_json) != dict):
        operator_object.update_workflow_status("Error")
        operator_object.add_workflow_metadata(
            GenericDataLookupError="Metadata must be of type dict. Found " + str(type(metadata_json)) + " instead.")
        raise MasExecutionError(operator_object.return_output_object())

    # Save metadata to dataplane
    operator_object.add_workflow_metadata(AssetId=asset_id,WorkflowExecutionId=workflow_id)
    dataplane = DataPlane()
    metadata_upload = dataplane.store_asset_metadata(asset_id, operator_object.name, workflow_id, metadata_json)
    print(metadata_upload)

    # Validate that the metadata was saved to the dataplane
    if "Status" not in metadata_upload:
        operator_object.add_workflow_metadata(
            GenericDataLookupError="Unable to upload metadata for asset: {asset}".format(asset=asset_id))
        operator_object.update_workflow_status("Error")
        raise MasExecutionError(operator_object.return_output_object())
    else:
        # Update the workflow status
        if metadata_upload["Status"] == "Success":
            print("Uploaded metadata for asset: {asset}".format(asset=asset_id))
            operator_object.update_workflow_status("Complete")
            return operator_object.return_output_object()
        else:
            operator_object.add_workflow_metadata(
                GenericDataLookupError="Unable to upload metadata for asset: {asset}".format(asset=asset_id))
            operator_object.update_workflow_status("Error")
            raise MasExecutionError(operator_object.return_output_object())

def generate_metadata(bucket, key):
    return {'hello':'World!'}
