# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

###############################################################################
# PURPOSE: 
#   This is a sample OpenCV operator for MIE. This operator analyzes 
#   two frames in the middle of the first shot detected by the MIE 
#   shotDetection operator. It looks for non-moving supersaturated pixels
#   by using the OpenCV findContours function. Contours with very short 
#   perimeters are considered as a potential effect of cosmic ray damage. 
#   Contours which appear in both of the analyzed frames are considered 
#   non-moving. This function then returns an x/y coordinate from each of those 
#   resulting contours. See sample output below.
#
# PREREQUISITES:
#
#   This operator must run after the shotDetection operator in an MIE workflow.
#
# USAGE:
#
#   See instructions here:
#
#   https://catalog.us-east-1.prod.workshops.aws/workshops/5a06b78f-4be9-4420-bd3c-fb3ecafaf4a7/en-US/module-2
#
# SAMPLE OUTPUT:
#
#   {
#   "num_specs": 31,
#   "specs_xy": "[(1045, 697), (1019, 681) ... (1131, 58)]"
#   }
#
# REFERENCES:
#
#   MIE Developer Guide:
#   https://github.com/aws-solutions/aws-media-insights-engine/blob/development/IMPLEMENTATION_GUIDE.md#4-implementing-a-new-operator-in-mie
#
#   Cosmic ray effects on cameras: 
#   http://ridl.cfd.rit.edu/products/theses%20and%20senior%20projects/Moser_Final_Paper_May_2017_.pdf
#
###############################################################################
import cv2
import numpy as np
import boto3
import math
from botocore.exceptions import ClientError
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all
from MediaInsightsEngineLambdaHelper import MediaInsightsOperationHelper
from MediaInsightsEngineLambdaHelper import MasExecutionError
from MediaInsightsEngineLambdaHelper import DataPlane

patch_all()
s3 = boto3.resource('s3')


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

    dataplane = DataPlane()

    # Get metadata from upstream shotDetection operator
    shot_detection_data = dataplane.retrieve_asset_metadata(asset_id, "shotDetection")
    start_timestamp = shot_detection_data['results']['Segments'][0]['StartTimestampMillis']
    end_timestamp = shot_detection_data['results']['Segments'][0]['EndTimestampMillis']

    # Generate metadata
    print("Generating metadata for s3://" + bucket + "/" + key)

    try:
        metadata_json = generate_metadata(bucket, key, start_timestamp, end_timestamp)
    except Exception as e:
        operator_object.update_workflow_status("Error")
        operator_object.add_workflow_metadata(GenericDataLookupError="Error generating metadata. " + str(e))
        raise MasExecutionError(operator_object.return_output_object())

    print(metadata_json)

    # Verify that the metadata is a dict, as required by the dataplane
    if (type(metadata_json) != dict):
        operator_object.update_workflow_status("Error")
        operator_object.add_workflow_metadata(
            GenericDataLookupError="Metadata must be of type dict. Found " + str(type(metadata_json)) + " instead.")
        raise MasExecutionError(operator_object.return_output_object())

    # Save metadata to dataplane
    operator_object.add_workflow_metadata(AssetId=asset_id, WorkflowExecutionId=workflow_id)
    print("Uploading new media assets to /private/assets/" + asset_id)
    output_video = "private/assets/" + asset_id + "/output_canny_video.mp4"
    output_image = "private/assets/" + asset_id + "/output_image.jpg"
    try:
        s3.Bucket(bucket).upload_file("/tmp/output_canny_video.mp4", output_video)
        s3.Bucket(bucket).upload_file("/tmp/output_image.jpg", output_image)
    except ClientError as e:
        logging.error(e)
        return False
    operator_object.add_media_object("Image", bucket, output_image)
    operator_object.add_media_object("Video", bucket, output_video)

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


def generate_metadata(bucket, key, start_timestamp, end_timestamp):
    elapsed_time = end_timestamp-start_timestamp
    input_video = '/tmp/input_video.mp4'

    # Download input video
    print("Downloading video to /tmp")
    s3.Bucket(bucket).download_file(key, input_video)
    print("Video downloaded.")

    vidcap = cv2.VideoCapture(input_video)
    print("VideoCapture initialized")

    # ANALYZE FRAME #1
    print("Analyzing video frame at " + str(end_timestamp-(elapsed_time/2)))

    vidcap.set(cv2.CAP_PROP_POS_MSEC, end_timestamp-(elapsed_time/2))
    success, image = vidcap.read()
    if not success:
        print("failed to open input video")
        return {"error": "Failed to open video"}

    imgray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ret, thresh = cv2.threshold(imgray, 50, 255, 0, cv2.THRESH_BINARY)
    contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    small_contours1 = []
    for c in contours:
        perimeter = cv2.arcLength(c, True)
        if 1 < perimeter < 20:
            small_contours1.append(c)

    # ANALYZE FRAME #2
    print("Analyzing video frame at " + str(end_timestamp-(elapsed_time/4)))
    vidcap.set(cv2.CAP_PROP_POS_MSEC, end_timestamp-(elapsed_time/4))
    success, image = vidcap.read()
    if not success:
        print("failed to open input video")
        return {"error": "Failed to open video"}

    imgray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ret, thresh = cv2.threshold(imgray, 50, 255, 0, cv2.THRESH_BINARY)
    contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    small_contours2 = []
    for c in contours:
        perimeter = cv2.arcLength(c,True)
        if 1 < perimeter < 20:
            small_contours2.append(c)

    image_annotated = image.copy()
    common_contours = []
    # Find intersections between contours in both frames
    for c1 in small_contours1:
        for c2 in small_contours2:
            if np.array_equal(c2, c1):
                common_contours.append(c1)
        
    # Draw circles and save a coordinate for each contour
    coordinates = []
    for c in common_contours:
        radius=20
        color=(0,0,255)
        thickness=2
        coodinate = (c[0][0][0], c[0][0][1])
        coordinates.append(coodinate)
        cv2.circle(image_annotated, coodinate, radius, color, thickness)
    
    cv2.imwrite("/tmp/output_image.jpg", image_annotated)

    # Apply a Canny effect on the video to help visualize cosmic ray affects. 
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter('/tmp/output_canny_video.mp4', fourcc, 23.976, (1280, 720), isColor=False)
    while vidcap.isOpened():
        ret, frame = vidcap.read()
        if ret:
            edges = cv2.Canny(frame, 50, 50)
            edges = cv2.resize(edges, (1280, 720))
            out.write(edges)
        else:
            break

    vidcap.release()
    out.release()

    return {'num_specs': len(common_contours), 'specs_xy': str(coordinates)}
