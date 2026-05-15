import boto3
import os
import io
import urllib.parse
from PIL import Image

s3_client = boto3.client('s3')

# We can optionally set the DESTINATION_BUCKET via environment variables.
# If not set, we'll append '-resized' to the source bucket name.
DESTINATION_BUCKET = os.environ.get('DESTINATION_BUCKET')

def lambda_handler(event, context):
    print("Received event: ", event)
    
    # Extract bucket and key from the S3 event
    for record in event['Records']:
        source_bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'], encoding='utf-8')
        
        # Define destination bucket (if not provided, default to a derived name)
        target_bucket = DESTINATION_BUCKET if DESTINATION_BUCKET else f"{source_bucket}-resized"
        
        try:
            print(f"Downloading s3://{source_bucket}/{key}")
            # Download the image from S3
            response = s3_client.get_object(Bucket=source_bucket, Key=key)
            image_content = response['Body'].read()
            
            # Open the image using Pillow
            with Image.open(io.BytesIO(image_content)) as image:
                print(f"Original size: {image.size}")
                
                # Resize image (e.g., to max 800x800, preserving aspect ratio)
                image.thumbnail((800, 800))
                print(f"Resized to: {image.size}")
                
                # Save resized image to a bytes buffer
                buffer = io.BytesIO()
                # Determine format based on original image or default to JPEG
                img_format = image.format if image.format else 'JPEG'
                if img_format == 'JPEG' and image.mode in ('RGBA', 'P'):
                    image = image.convert('RGB')
                
                image.save(buffer, format=img_format)
                buffer.seek(0)
                
                # Upload the resized image to the destination bucket
                print(f"Uploading resized image to s3://{target_bucket}/{key}")
                s3_client.put_object(
                    Bucket=target_bucket,
                    Key=key,
                    Body=buffer,
                    ContentType=f"image/{img_format.lower()}"
                )
                print(f"Successfully resized and uploaded {key} to {target_bucket}")
                
        except Exception as e:
            print(f"Error processing object {key} from bucket {source_bucket}: {e}")
            raise e
            
    return {
        'statusCode': 200,
        'body': 'Images processed successfully'
    }
