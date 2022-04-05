# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

###############################################################################
# PURPOSE: 
#   This is a sample OpenCV operator for MIE. This operator analyzes 
#   the first and last frame of the first shot detected by the MIE 
#   shotDetection operator, looking for non-moving supersaturated pixels. 
#   This operator must run after shotDetection in an MIE workflow.
#
###############################################################################
import cv2
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

    h = image.shape[0]
    w = image.shape[1]

    center_points = []
    T = 5
    # loop over the image, pixel by pixel, to find specs
    for x in range(T, w - T - 1):
        for y in range(T, h - T - 1):
            # Find the color differences
            delta_left = d(image[y][x], image[y][x - T]);
            delta_right = d(image[y][x], image[y][x + T]);
            delta_above = d(image[y][x], image[y - T][x]);
            delta_below = d(image[y][x], image[y + T][x]);
            if (delta_left > 200 and delta_right > 200 and delta_above > 200 and delta_below > 200):
                new = True;
                for center_point in center_points:
                    if abs(center_point[0] - x) < 10 and abs(center_point[1] - y) < 10:
                        new = False;
                if new:
                    center_points.append([x, y])

    # ANALYZE FRAME #2
    print("Analyzing video frame at " + str(end_timestamp-(elapsed_time/4)))
    vidcap.set(cv2.CAP_PROP_POS_MSEC, end_timestamp-(elapsed_time/4))
    success, image = vidcap.read()
    if not success:
        print("failed to open input video")
        return {"error": "Failed to open video"}

    center_points2 = []
    # loop over the image, pixel by pixel, to find specs
    for x in range(T, w - T - 1):
        for y in range(T, h - T - 1):
            # Find the color differences
            delta_left = d(image[y][x], image[y][x - T]);
            delta_right = d(image[y][x], image[y][x + T]);
            delta_above = d(image[y][x], image[y - T][x]);
            delta_below = d(image[y][x], image[y + T][x]);
            if (delta_left > 150 and delta_right > 150 and delta_above > 150 and delta_below > 150):
                already_recorded = False
                for center_point in center_points:
                    if abs(center_point[0] - x) < 5 and abs(center_point[1] - y) < 5:
                        already_recorded = True
                        break
                new = True;
                for center_point in center_points2:
                    if abs(center_point[0] - x) < 5 and abs(center_point[1] - y) < 5:
                        new = False;
                if new and already_recorded:
                    center_points2.append([x, y])

    image_annotated = image
    for center_point in center_points2:
        # Center coordinates
        center_coordinates = (center_point[0], center_point[1])

        # Radius of circle
        radius = 20

        # Blue color in BGR
        color = (0, 0, 255)

        # Line thickness of 2 px
        thickness = 2
        image_annotated = cv2.circle(image, center_coordinates, radius, color, thickness)

    cv2.imwrite("/tmp/output_image.jpg", image_annotated)  # save frame as JPEG file

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

    return {'num_specs': len(center_points2), 'specs_xy': center_points2}


def d(point1, point2):
    x1 = int(point1[0])
    y1 = int(point1[1])
    z1 = int(point1[2])
    x2 = int(point2[0])
    y2 = int(point2[1])
    z2 = int(point2[2])
    return math.sqrt(((x1 - x2) ** 2) + ((y1 - y2) ** 2) + ((z1 - z2) ** 2))
